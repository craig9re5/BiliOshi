"""Background release polling, idle-stream gate, and atomic Windows self-update."""

import logging
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from bilioshi.runtime import APP_VERSION, read_json, write_json
from bilioshi.safety import blocks_watch
from bilioshi.updater import (
    RELEASE_PUBLIC_KEY,
    download_release_exe,
    fetch_manifest,
    is_newer_version,
    load_updater_settings,
    load_updater_state,
    mark_skipped_version,
    normalize_version,
    prune_staged_updates,
    save_updater_settings,
    sha256_file,
    update_updater_state,
)
from desktop import supervisor
from desktop.windows import Mutex, instance_name, terminate_verified, process_identity

STARTUP_DELAY_SECONDS = 12.0
POLL_INTERVAL_SECONDS = 20 * 60.0
POLL_JITTER_SECONDS = 180.0
READY_RECHECK_SECONDS = 10.0
FOREGROUND_IDLE_GRACE_SECONDS = 60.0


def _creation_flags():
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "CREATE_NEW_PROCESS_GROUP", 0
    )


def _clean_pyinstaller_env(root):
    return {
        **os.environ,
        "BILIOSHI_APP_DATA": str(root),
        "PYTHONIOENCODING": "utf-8",
        "PYINSTALLER_RESET_ENVIRONMENT": "1",
    }


def can_self_update(executable=None, *, frozen=None):
    is_frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
    if os.name != "nt":
        return False, "当前系统暂不支持二进制原地替换"
    if not is_frozen:
        return False, "源码运行模式不自动覆盖文件，请通过 git pull 更新"
    target = Path(executable or sys.executable).resolve()
    parent = target.parent
    if not target.is_file() or not parent.is_dir():
        return False, "未找到可替换的程序路径"
    probe = parent / f".bilioshi-write-probe-{os.getpid()}"
    try:
        probe.write_bytes(b"")
        probe.unlink(missing_ok=True)
        return True, ""
    except OSError:
        return False, "安装目录无写入权限，请使用管理员权限或手动替换更新"


def evaluate_idle_blocker(
    host_or_engine,
    *,
    qr_active=False,
    io_active=False,
    foreground_active=False,
    now=None,
):
    """Return '' when safe to silently restart, or a Chinese deferral reason."""
    moment = time.time() if now is None else now
    if qr_active:
        return "正在扫码登录，暂缓自动更新"
    if io_active:
        return "正在执行操作，完成后自动更新"

    engines = []
    if host_or_engine is not None:
        if hasattr(host_or_engine, "engines") and isinstance(host_or_engine.engines, dict):
            engines = list(host_or_engine.engines.values())
        else:
            engines = [host_or_engine]

    global_paused = getattr(host_or_engine, "global_paused", False) is True
    if not global_paused:
        for engine in engines:
            if engine is None:
                continue
            if getattr(engine, "suspended", False) is True or getattr(engine, "paused", False) is True:
                continue
            if getattr(engine, "_started", True) is False:
                continue
            if getattr(engine, "probe", None) is not None:
                return "正在检测直播间状态，完成后自动更新"
            members = list(getattr(engine, "members", None) or [])
            if (
                members
                and getattr(engine, "last_check", 0) == 0
                and (Path(engine.root) / "credentials.json").exists()
                and 0 <= moment - getattr(engine, "started_at", 0) < 90
            ):
                return "正在等待首次开播巡检完成"
            workers = getattr(engine, "workers", None) or {}
            if any(proc is not None and proc.poll() is None for proc in workers.values()):
                return "直播挂机进行中，将在全部下播后静默安装"
            safety = getattr(engine, "safety", None) or {}
            if not blocks_watch(safety):
                statuses = getattr(engine, "statuses", None) or {}
                for member in members:
                    room = str(member.get("room", ""))
                    if (statuses.get(room) or {}).get("live_status") == 1:
                        return "关注主播正在直播，将在下播后静默安装"

    if foreground_active:
        return "主窗口正在使用中，关闭到托盘或点击“立即重启更新”即可安装"
    return ""


def verify_staged_executable(staged_exe, expected_version, *, runner=subprocess.run, timeout=45):
    """Run `--diagnostic` in an isolated data root before ever stopping live watch."""
    staged_exe = Path(staged_exe).resolve()
    td_kwargs = {"ignore_cleanup_errors": True} if sys.version_info >= (3, 10) else {}
    with tempfile.TemporaryDirectory(prefix="bilioshi-upd-diag-", **td_kwargs) as tmp:
        tmp_root = Path(tmp)
        proc = runner(
            [str(staged_exe), "--diagnostic"],
            cwd=str(staged_exe.parent),
            env=_clean_pyinstaller_env(tmp_root),
            capture_output=True,
            creationflags=_creation_flags(),
            timeout=timeout,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"新版本预检进程退出码异常（{proc.returncode}）")
        report = read_json(tmp_root / "diagnostic.json", {})
        if not isinstance(report, dict) or not report.get("ok") or not report.get("frozen"):
            raise RuntimeError("新版本预检报告未通过")
        if normalize_version(str(report.get("version", ""))) != normalize_version(expected_version):
            raise RuntimeError("新版本预检版本号与签名清单不一致")
    return True


class DesktopUpdater:
    """Thread-safe coordinator for checking, staging, pre-checking, and applying updates."""

    def __init__(
        self,
        host_root,
        *,
        idle_blocker=lambda: "",
        request_exit=None,
        on_change=None,
        opener=None,
        public_key=None,
        manifest_url=None,
        current_version=APP_VERSION,
        executable=None,
        frozen=None,
        diagnostic_verifier=verify_staged_executable,
        spawner=subprocess.Popen,
        tk_mode=False,
        auto_start_background=None,
        allow_http=False,
    ):
        self.root = Path(host_root)
        self._idle_blocker = idle_blocker
        self._request_exit = request_exit
        self._on_change = on_change
        self._opener = opener
        self._public_key = RELEASE_PUBLIC_KEY if public_key is None else public_key
        self._manifest_url = manifest_url
        self._current_version = current_version
        self._executable = Path(executable or sys.executable).resolve()
        self._frozen = bool(getattr(sys, "frozen", False)) if frozen is None else bool(frozen)
        self._diagnostic_verifier = diagnostic_verifier
        self._spawner = spawner
        self._tk_mode = bool(tk_mode)
        self._allow_http = bool(allow_http)
        if auto_start_background is None:
            auto_start_background = bool(
                self._frozen or os.environ.get("BILIOSHI_UPDATE_MANIFEST_URL")
            )
        self._auto_start_background = bool(auto_start_background)

        self._lock = threading.RLock()
        self._op_lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread = None
        self._started = False

        self._self_updatable, self._self_update_reason = can_self_update(
            self._executable, frozen=self._frozen
        )
        self._status = "idle"
        self._latest_version = ""
        self._ready_version = ""
        self._staged_path = None
        self._staged_sha256 = ""
        self._notes = ""
        self._error = ""
        self._waiting_reason = ""
        self._last_checked_at = 0.0
        self._restore_saved_state()

    def _restore_saved_state(self):
        prune_staged_updates(self.root, current_version=self._current_version)
        state = load_updater_state(self.root)
        checked = state.get("last_checked_at", 0)
        if isinstance(checked, (int, float)):
            self._last_checked_at = float(checked)
        staged_ver = state.get("staged_version", "")
        staged_sha = state.get("staged_sha256", "")
        staged_file = self.root / "updates" / f"BiliOshi-{staged_ver}.exe" if staged_ver else None
        skipped = state.get("skipped_versions")
        skipped_map = skipped if isinstance(skipped, dict) else {}
        if (
            staged_ver
            and staged_ver not in skipped_map
            and staged_file is not None
            and staged_file.is_file()
            and state.get("staged_verified") is True
        ):
            try:
                if is_newer_version(staged_ver, self._current_version) and sha256_file(staged_file) == staged_sha:
                    self._status = "ready"
                    self._latest_version = staged_ver
                    self._ready_version = staged_ver
                    self._staged_path = staged_file
                    self._staged_sha256 = staged_sha
                    cached = state.get("cached_manifest")
                    if isinstance(cached, dict):
                        self._notes = str(cached.get("notes") or "")
            except (OSError, ValueError):
                pass

    def _notify_change(self):
        if callable(self._on_change):
            try:
                self._on_change()
            except Exception:
                logging.debug("Updater change callback failed", exc_info=True)

    def start(self):
        with self._lock:
            if self._started:
                return
            self._started = True
            if not self._auto_start_background:
                return
            self._thread = threading.Thread(target=self._loop, name="auto-updater", daemon=True)
            self._thread.start()

    def close(self):
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=5)

    def wake(self):
        self._wake.set()

    def settings(self):
        return load_updater_settings(self.root)

    def set_auto_update(self, enabled):
        saved = save_updater_settings(self.root, auto_update=bool(enabled))
        self.wake()
        self._notify_change()
        return saved

    def snapshot(self):
        cfg = load_updater_settings(self.root)
        with self._lock:
            waiting = self._waiting_reason
            if self._status == "ready" and self._self_updatable:
                if not cfg["auto_update"]:
                    waiting = "自动更新已关闭，可点击“立即重启更新”手动安装"
                elif not waiting:
                    waiting = self._safe_idle_blocker()
            return {
                "status": self._status,
                "auto_update": cfg["auto_update"],
                "current_version": self._current_version,
                "latest_version": self._latest_version,
                "ready_version": self._ready_version,
                "notes": self._notes,
                "last_checked_at": self._last_checked_at,
                "error": self._error,
                "can_self_update": self._self_updatable,
                "self_update_reason": self._self_update_reason,
                "waiting_reason": waiting,
            }

    def is_ready(self):
        with self._lock:
            return self._status == "ready" and self._self_updatable

    def _safe_idle_blocker(self):
        try:
            return str(self._idle_blocker() or "")
        except Exception:
            logging.exception("Evaluating updater idle gate failed")
            return "正在确认运行状态，稍后重试"

    def check_now(self, *, download=None):
        """Check latest.json synchronously on caller's worker thread and optionally stage."""
        if not self._op_lock.acquire(blocking=False):
            return {"ok": False, "error": "正在检查或下载更新，请稍候。"}
        try:
            return self._check_and_stage_locked(download=download)
        finally:
            self._op_lock.release()

    def _check_and_stage_locked(self, *, download=None):
        if self._stop.is_set():
            return {"ok": False, "error": "程序正在退出。"}
        cfg = load_updater_settings(self.root)
        if download is None:
            download = bool(cfg["auto_update"] and self._self_updatable)

        with self._lock:
            if self._status == "applying":
                return {"ok": False, "error": "正在重启应用更新。"}
            prev_ready = (self._ready_version, self._staged_path, self._staged_sha256)
            self._status = "checking"
            self._error = ""
        self._notify_change()

        try:
            outcome = fetch_manifest(
                self.root,
                current_version=self._current_version,
                public_key=self._public_key,
                manifest_url=self._manifest_url,
                mirror_prefix=cfg["mirror_prefix"],
                opener=self._opener,
                allow_http=self._allow_http,
            )
        except Exception as exc:
            logging.warning("Update manifest check failed: %s", exc)
            msg = str(exc) if isinstance(exc, ValueError) else "检查更新失败，请检查网络连接后重试。"
            with self._lock:
                if prev_ready[0] and prev_ready[1] and prev_ready[1].is_file():
                    self._status = "ready"
                else:
                    self._status = "error"
                self._error = msg
            update_updater_state(self.root, lambda cur: {**cur, "last_error": msg})
            self._notify_change()
            return {"ok": False, "error": msg}

        manifest = outcome["manifest"]
        ver = manifest["version"]
        with self._lock:
            self._last_checked_at = outcome["checked_at"]
            self._notes = manifest.get("notes", "")
            if not outcome["has_update"]:
                self._latest_version = ver
                self._ready_version = ""
                self._staged_path = None
                self._staged_sha256 = ""
                self._status = "up_to_date"
                self._waiting_reason = ""
                if outcome.get("skipped_reason"):
                    self._error = f"已跳过故障版本 v{ver}：{outcome['skipped_reason']}"
                self._notify_change()
                return {
                    "ok": True,
                    "has_update": False,
                    "version": ver,
                    "message": f"当前已是最新版本（v{self._current_version}）",
                }
            self._latest_version = ver
            if (
                prev_ready[0] == ver
                and prev_ready[1] is not None
                and prev_ready[1].is_file()
                and prev_ready[2] == manifest["exe_sha256"]
            ):
                self._status = "ready"
                self._notify_change()
                self._maybe_auto_apply()
                return {
                    "ok": True,
                    "has_update": True,
                    "ready": True,
                    "version": ver,
                    "message": f"新版本 v{ver} 已就绪",
                }

        if not self._self_updatable or not download:
            with self._lock:
                self._status = "update_available"
            self._notify_change()
            return {
                "ok": True,
                "has_update": True,
                "ready": False,
                "version": ver,
                "message": (
                    f"发现新版本 v{ver}（{self._self_update_reason}）"
                    if not self._self_updatable
                    else f"发现新版本 v{ver}"
                ),
            }

        with self._lock:
            self._status = "downloading"
        self._notify_change()

        try:
            staged = download_release_exe(
                self.root,
                manifest,
                public_key=self._public_key,
                mirror_prefix=cfg["mirror_prefix"],
                opener=self._opener,
                cancel_event=self._stop,
                allow_http=self._allow_http,
            )
            with self._lock:
                self._status = "verifying"
            self._notify_change()
            self._diagnostic_verifier(staged, ver)
        except InterruptedError:
            with self._lock:
                self._status = "idle"
            return {"ok": False, "error": "更新下载已取消。"}
        except RuntimeError as exc:
            logging.warning("Staged update failed diagnostic pre-check version=%s: %s", ver, exc)
            mark_skipped_version(self.root, ver, str(exc))
            try:
                Path(self.root / "updates" / f"BiliOshi-{ver}.exe").unlink(missing_ok=True)
            except OSError:
                pass
            msg = f"新版本 v{ver} 预检未通过，已自动跳过，不影响当前挂机。"
            with self._lock:
                self._status = "error"
                self._error = msg
            self._notify_change()
            return {"ok": False, "error": msg}
        except Exception as exc:
            logging.warning("Update download failed version=%s: %s", ver, exc)
            msg = str(exc) if isinstance(exc, ValueError) else "下载更新包失败，稍后将自动重试。"
            with self._lock:
                self._status = "error"
                self._error = msg
            self._notify_change()
            return {"ok": False, "error": msg}

        update_updater_state(
            self.root,
            lambda cur: {
                **cur,
                "staged_version": ver,
                "staged_sha256": manifest["exe_sha256"],
                "staged_verified": True,
                "last_error": "",
            },
        )
        with self._lock:
            self._status = "ready"
            self._ready_version = ver
            self._staged_path = staged
            self._staged_sha256 = manifest["exe_sha256"]
            self._error = ""
        logging.info("Update staged and verified version=%s path=%s", ver, staged)
        self._notify_change()
        self._maybe_auto_apply()
        return {
            "ok": True,
            "has_update": True,
            "ready": True,
            "version": ver,
            "message": f"新版本 v{ver} 已下载校验就绪",
        }

    def apply_now(self, *, manual=False):
        """Launch staged binary in `--apply-update` mode and request graceful host exit."""
        with self._lock:
            if self._status == "applying":
                return {"ok": True, "applying": True, "message": "正在重启并安装更新…"}
            if self._status != "ready" or not self._staged_path or not self._ready_version:
                if manual and self._self_updatable and self._latest_version:
                    pass
                else:
                    return {"ok": False, "error": "当前没有已就绪的更新包。"}
            if not self._self_updatable:
                return {"ok": False, "error": self._self_update_reason or "当前环境不支持自动替换安装。"}
            staged = self._staged_path
            expected_sha = self._staged_sha256
            ver = self._ready_version

        if staged is None or not staged.is_file():
            with self._lock:
                self._status = "idle"
                self._ready_version = ""
            self._notify_change()
            return {"ok": False, "error": "更新包文件不存在，请重新检查更新。"}

        try:
            if sha256_file(staged) != expected_sha:
                staged.unlink(missing_ok=True)
                with self._lock:
                    self._status = "error"
                    self._ready_version = ""
                    self._error = "本地缓存更新包校验不一致，已清除，请重新检查更新。"
                self._notify_change()
                return {"ok": False, "error": self._error}
        except OSError:
            return {"ok": False, "error": "无法读取更新包文件，请稍后重试。"}

        if not manual:
            blocker = self._safe_idle_blocker()
            with self._lock:
                self._waiting_reason = blocker
            if blocker:
                self._notify_change()
                return {"ok": False, "deferred": True, "error": blocker}

        token = supervisor.begin_update(self.root, seconds=300)
        args = [
            str(staged),
            "--apply-update",
            str(self._executable),
            "--update-token",
            token,
        ]
        if self._tk_mode:
            args.append("--tk")
        if manual:
            args.append("--reopen")
        try:
            self._spawner(
                args,
                cwd=str(staged.parent),
                close_fds=True,
                env=_clean_pyinstaller_env(self.root),
                creationflags=_creation_flags(),
            )
        except OSError as exc:
            supervisor.end_update(self.root, token)
            logging.exception("Cannot spawn --apply-update helper: %s", exc)
            return {"ok": False, "error": "无法启动更新安装程序，请查看日志。"}

        with self._lock:
            self._status = "applying"
            self._waiting_reason = ""
        logging.info("Applying update version=%s target=%s manual=%s", ver, self._executable, manual)
        self._notify_change()
        if callable(self._request_exit):
            self._request_exit()
        return {"ok": True, "applying": True, "version": ver, "message": f"正在重启并更新至 v{ver}…"}

    def _maybe_auto_apply(self):
        cfg = load_updater_settings(self.root)
        if not cfg["auto_update"] or not self._self_updatable:
            return False
        with self._lock:
            if self._status != "ready":
                return False
        result = self.apply_now(manual=False)
        return bool(result.get("applying"))

    def _loop(self):
        if self._stop.wait(STARTUP_DELAY_SECONDS):
            return
        next_poll = 0.0
        while not self._stop.is_set():
            now = time.monotonic()
            cfg = load_updater_settings(self.root)
            if cfg["auto_update"] and now >= next_poll:
                if self._op_lock.acquire(blocking=False):
                    try:
                        self._check_and_stage_locked(download=self._self_updatable)
                    finally:
                        self._op_lock.release()
                next_poll = time.monotonic() + POLL_INTERVAL_SECONDS + random.uniform(0, POLL_JITTER_SECONDS)
            elif not cfg["auto_update"] and next_poll == 0.0:
                next_poll = now + 60.0

            if self._maybe_auto_apply():
                return

            with self._lock:
                wait_seconds = READY_RECHECK_SECONDS if self._status == "ready" else 30.0
            self._wake.wait(timeout=wait_seconds)
            self._wake.clear()


# ---------- Subprocess `--apply-update` Atomic Replacement & Rollback ----------


def _wait_for_mutex_release(name, timeout=45.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        probe = Mutex(name)
        acquired = probe.acquired
        probe.close()
        if acquired:
            return True
        time.sleep(0.25)
    return False


def _retry_fs(operation, *, timeout=30.0, interval=0.25):
    deadline = time.monotonic() + timeout
    last_exc = None
    while True:
        try:
            return operation()
        except OSError as exc:
            last_exc = exc
            if time.monotonic() >= deadline:
                raise last_exc
            time.sleep(interval)


def _prune_backups(directory, stem, suffix, keep=2):
    pattern = f"{stem}.previous-*{suffix}"
    backups = sorted(Path(directory).glob(pattern), key=lambda p: p.name, reverse=True)
    for old in backups[keep:]:
        try:
            old.unlink(missing_ok=True)
        except OSError:
            pass


def _spawn_installed(target_exe, root, *args):
    return subprocess.Popen(
        [str(target_exe), *args],
        cwd=str(Path(target_exe).parent),
        close_fds=True,
        env=_clean_pyinstaller_env(root),
        creationflags=_creation_flags(),
    )


def _wait_for_healthy_launch(root, child, launch_wall, *, timeout=25.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        desired = read_json(root / "supervisor-desired.json", {})
        if isinstance(desired, dict) and desired.get("running") is False:
            return True
        health = read_json(root / "monitor-health.json", {})
        if (
            isinstance(health, dict)
            and type(health.get("pid")) is int
            and not health.get("publish_error")
            and isinstance(health.get("started"), (int, float))
            and health["started"] >= launch_wall - 2.0
            and isinstance(health.get("updated"), (int, float))
            and health["updated"] >= health["started"]
        ):
            ident = process_identity(health["pid"])
            if ident is not None:
                return True
        if child is not None and child.poll() is not None:
            time.sleep(0.8)
            probe = Mutex(instance_name(root))
            free = probe.acquired
            probe.close()
            if not free:
                # Another user-launched instance already owns the UI mutex.
                return True
            if child.returncode != 0:
                return False
        time.sleep(0.4)
    # Process stayed alive without crashing through the startup window.
    return child is None or child.poll() is None


def run_apply_update(
    root,
    target_exe,
    token="",
    *,
    reopen=False,
    tk=False,
    staged_exe=None,
    wait_mutexes=True,
    health_waiter=_wait_for_healthy_launch,
    launcher=_spawn_installed,
    replace_timeout=30.0,
):
    """Replace target_exe from staged_exe, relaunch desktop, and roll back if broken."""
    root = Path(root)
    target_exe = Path(target_exe).resolve()
    source_exe = Path(staged_exe or sys.executable).resolve()
    if source_exe == target_exe:
        logging.error("Refusing self-overwrite: staged and target paths are identical (%s)", target_exe)
        return 2
    if not source_exe.is_file():
        logging.error("Staged executable missing: %s", source_exe)
        return 2

    active_token = token or supervisor.begin_update(root, seconds=300)
    if token:
        write_json(root / "supervisor-update.json", {"token": token, "until": time.time() + 300})

    desired_before = read_json(root / "supervisor-desired.json", {})
    if not isinstance(desired_before, dict):
        desired_before = {}
    should_run = desired_before.get("running", True) is not False
    use_tk = bool(tk or desired_before.get("tk"))

    backup_exe = None
    tmp_exe = target_exe.parent / f"{target_exe.name}.new-{os.getpid()}"
    child = None
    try:
        if wait_mutexes:
            base = instance_name(root)
            _wait_for_mutex_release(base + "-supervisor", timeout=20.0)
            _wait_for_mutex_release(base, timeout=45.0)

        target_exe.parent.mkdir(parents=True, exist_ok=True)
        expected_digest = sha256_file(source_exe)
        shutil.copy2(source_exe, tmp_exe)
        if sha256_file(tmp_exe) != expected_digest:
            raise RuntimeError("临时更新文件写入校验失败")

        if target_exe.is_file():
            stamp = time.strftime("%Y%m%d-%H%M%S")
            backup_exe = target_exe.parent / f"{target_exe.stem}.previous-{stamp}{target_exe.suffix}"
            _retry_fs(lambda: shutil.copy2(target_exe, backup_exe), timeout=replace_timeout)

        _retry_fs(lambda: os.replace(tmp_exe, target_exe), timeout=replace_timeout)
        if backup_exe is not None:
            _prune_backups(target_exe.parent, target_exe.stem, target_exe.suffix, keep=2)

        supervisor.end_update(root, active_token)
        active_token = ""

        if should_run:
            supervisor.request_run(root)
            launch_args = ["--supervised"]
            if use_tk:
                launch_args.append("--tk")
            if reopen:
                launch_args.append("--show")
            launch_wall = time.time()
            child = launcher(target_exe, root, *launch_args)
            if not health_waiter(root, child, launch_wall):
                raise RuntimeError("更新后新进程启动自检未通过")

        update_updater_state(
            root,
            lambda cur: {
                **cur,
                "staged_version": "",
                "staged_sha256": "",
                "staged_verified": False,
                "last_applied": {
                    "version": APP_VERSION,
                    "at": time.time(),
                    "backup": str(backup_exe) if backup_exe else "",
                },
                "last_error": "",
            },
        )
        logging.info("Update applied cleanly version=%s target=%s", APP_VERSION, target_exe)
        return 0
    except Exception as exc:
        logging.exception("Applying update failed; attempting rollback: %s", exc)
        if backup_exe is not None and backup_exe.is_file():
            rb_token = supervisor.begin_update(root, seconds=120)
            try:
                if child is not None and child.poll() is None:
                    ident = process_identity(child.pid)
                    if ident:
                        terminate_verified(ident)
                    else:
                        child.terminate()
                if wait_mutexes:
                    _wait_for_mutex_release(instance_name(root), timeout=15.0)
                _retry_fs(lambda: shutil.copy2(backup_exe, target_exe), timeout=replace_timeout)
                mark_skipped_version(root, APP_VERSION, "更新后启动失败，已自动回退至上一版本")
                logging.warning("Rolled back executable from %s", backup_exe)
            except Exception:
                logging.exception("Rollback failed")
            finally:
                supervisor.end_update(root, rb_token)
            if should_run:
                try:
                    supervisor.request_run(root)
                    launcher(target_exe, root, "--supervised", *(["--tk"] if use_tk else []))
                except Exception:
                    logging.exception("Relaunch after rollback failed")
        return 1
    finally:
        try:
            tmp_exe.unlink(missing_ok=True)
        except OSError:
            pass
        if active_token:
            supervisor.end_update(root, active_token)
