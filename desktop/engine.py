from desktop.health import check_progress, recovery_delay, number
from desktop.snapshot import project_snapshot
from bilioshi.application import AppContext
import logging
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from desktop.storage import load_config, read_json, write_json, read_status
from desktop.windows import Job
from bilioshi.runtime import update_json, append_event, task_day
from bilioshi.safety import format_task_errors
from bilioshi.growth import record_samples
from bilioshi.operating_mode import profile_for
try:
    from bilioshi.notifications.service import DailyNotifications
except ImportError:
    DailyNotifications = None

# The GUI reads Engine.snapshot() directly; status.json only serves other processes,
# and read_status accepts 15 seconds of age. Publishing every tick was pure disk churn.
STATUS_PUBLISH_SECONDS = 5.0


def command(*args):
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / "tray_app.py"), *args]


class Engine:

    def __init__(self, root, *, job=None, account_id=""):
        self.root = root
        self.account_id = str(account_id or "")
        self.application = AppContext(root)
        from bilioshi.notifications import AVAILABLE
        self.notifications = DailyNotifications(root) if AVAILABLE and DailyNotifications else None
        self.lock = threading.RLock()
        self.stopping = threading.Event()
        self.job = job if job is not None else Job()
        self.suspended = False
        self.generation = 0
        self.probe_generation = 0
        self.force_probe = False
        self._started = False
        self._notifications_started = False
        self.workers = {}
        self.worker_health = {}
        self.worker_retries = {}
        self.manual_reconnects = {}
        self.started_at = time.time()
        self.last_tick = 0
        self.last_status_publish = 0
        self.last_health_publish = 0
        self.publish_error = ""
        self.state_errors = {}
        self.probe = None
        self.probe_path = None
        self.probe_started = 0
        self.next_check = 0
        self.last_check = 0
        self.error = ""
        self.account = ""
        self.account_checked_at = 0
        self.safety = {"blocked": False}
        self.room_blocks = {}
        self.statuses = {}
        self.status_times = {}
        self.status_errors = {}
        self.task_errors = {}
        status = read_status(root)
        self.medals = status.get("medals", {})
        self.tasks = status.get("tasks", {})
        self.known_live = set()
        self.notify_callback = None
        try:
            self.config, self.members = load_config(root)
        except ValueError as exc:
            self.config, self.members = ({"check_minutes": 30}, [])
            self.error = f"配置错误：{exc}"
        self.paused = bool(self.config.get("paused", False))
        self.credentials_signature = self._credentials_signature()
        self.thread = threading.Thread(target=self.run, name="monitor", daemon=True)

    def start(self):
        if self._started:
            return
        self._started = True
        logging.info(
            "Engine starting account=%s members=%s paused=%s check_minutes=%s",
            self.account_id,
            len(self.members),
            self.paused,
            self.config.get("check_minutes"),
        )
        if not self.suspended:
            self._start_notifications()
        self.thread.start()

    def _start_notifications(self):
        if self.notifications is not None and not self._notifications_started:
            self.notifications.start()
            self._notifications_started = True

    def _stop_notifications(self):
        if self.notifications is not None and self._notifications_started:
            self.notifications.stop()
            self._notifications_started = False

    def confirm_account(self, name):
        """A freshly validated QR login is authoritative until the next probe."""
        with self.lock:
            self.account = str(name or "")
            self.account_checked_at = time.time()
            logging.info("Account confirmed via QR login user=%s", self.account)

    def _credentials_signature(self):
        path = self.root / "credentials.json"
        if not path.exists():
            return ""
        try:
            value = json.dumps(read_json(path, {}), sort_keys=True).encode("utf-8")
        except (RuntimeError, ValueError):
            value = path.read_bytes()
        return hashlib.sha256(value).hexdigest()

    def reload_settings(self):
        """Apply settings before another worker can continue with an old policy."""
        with self.lock:
            try:
                config, members = load_config(self.root)
                signature = self._credentials_signature()
            except (OSError, ValueError):
                self.stop_children("invalid_config")
                raise
            policy_changed = any(
                (
                    config.get(k) != self.config.get(k)
                    for k in ("auto_revive", "auto_danmaku_intimacy", "auto_like")
                )
            )
            credentials_changed = signature != self.credentials_signature
            changed = config != self.config or members != self.members or credentials_changed
            if policy_changed or credentials_changed:
                self.stop_children("settings_changed")
                self.manual_reconnects.clear()
            if credentials_changed:
                self.account = ""
                self.account_checked_at = 0
                from desktop.avatars import clear_account_profile

                clear_account_profile(self.root)
                self.medals, self.tasks, self.statuses = ({}, {}, {})
                self.status_times, self.status_errors, self.task_errors = ({}, {}, {})
            keep = {m["room"] for m in members}
            self.manual_reconnects = {room: request for room, request in self.manual_reconnects.items() if room in keep}
            self.worker_retries = {room: retry for room, retry in self.worker_retries.items() if room in keep}
            for room in list(self.workers):
                if room not in keep:
                    proc = self.workers.pop(room)
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                    self._record_interruption(room, "member_removed")
            self.config, self.members = (config, members)
            self.credentials_signature = signature
            paused = bool(config.get("paused", False))
            if paused and (not self.paused):
                self.stop_children("paused")
            self.paused = paused
            if changed:
                self.next_check = 0
            return changed

    def spawn(self, *args):
        env = {**os.environ, "BILIOSHI_APP_DATA": str(self.root), "PYTHONIOENCODING": "utf-8"}
        proc = subprocess.Popen(
            command(*args),
            creationflags=subprocess.CREATE_NO_WINDOW,
            env=env,
            cwd=str(Path(sys.executable).parent),
        )
        self.job.add(proc)
        return proc

    def stop_children(self, reason="stopped"):
        rooms = list(self.workers)
        if rooms:
            logging.info("Stopping room workers rooms=%s reason=%s", rooms, reason)
        processes = list(self.workers.values()) + ([self.probe] if self.probe else [])
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        for room in rooms:
            try:
                self._record_interruption(room, reason)
            except (OSError, ValueError, TimeoutError):
                logging.exception("Cannot record worker interruption")
        self.workers.clear()
        self.worker_health.clear()
        self.probe = None

    def _record_interruption(self, room, reason, expected_pid=None):
        try:
            state = read_json(self.root / "state" / f"{room}.json", {})
        except (OSError, ValueError):
            logging.warning("Cannot read interrupted room state room=%s", room)
            return
        if not isinstance(state, dict) or (expected_pid is not None and state.get("pid") != expected_pid):
            return
        session_id = state.get("session_id")
        if session_id and (not state.get("result")):
            append_event(
                self.root / "logs" / "activity.jsonl",
                {
                    "type": "watch_interrupted",
                    "session_id": session_id,
                    "account_key": state.get("account_key"),
                    "room": room,
                    "member": state.get("name", str(room)),
                    "stopped_reason": reason,
                    "minutes": max(0, int((time.time() - number(state.get("started"), time.time())) / 60)),
                    "beats_ok": state.get("beats", 0),
                    "success": False,
                },
            )

    def set_paused(self, paused):
        with self.lock:
            update_json(
                self.root / "settings.json",
                lambda settings: {**settings, "paused": bool(paused)},
                {},
            )
            self.paused = bool(paused)
            logging.info("Monitoring %s", "paused" if paused else "resumed")
            if paused:
                self.stop_children("paused")
                self.error = ""
            else:
                self.next_check = 0
            self.persist()

    def check_now(self):
        with self.lock:
            self.next_check = 0
            self.force_probe = True

    def suspend(self, reason="account_suspended"):
        """Stop this account's IO but keep its Engine, thread and Job alive."""
        with self.lock:
            if self.suspended:
                return
            self.suspended = True
            self.generation += 1
            self.force_probe = False
            self._stop_notifications()
            self.stop_children(reason)
            try:
                self._write_last_snapshot()
            except (OSError, ValueError):
                logging.exception("Cannot write last account snapshot")
            try:
                self.persist()
            except (OSError, ValueError):
                logging.exception("Cannot persist suspended account status")
            logging.info("Engine suspended account=%s reason=%s", self.account_id, reason)

    def activate(self):
        """Resume a suspended Engine without rebuilding it or reading a QR code."""
        with self.lock:
            if not self.suspended:
                self.next_check = 0
                self.force_probe = True
                return
            self.suspended = False
            self.generation += 1
            self.next_check = 0
            self.force_probe = True
            try:
                self.reload_settings()
            except (OSError, ValueError):
                self.suspended = True
                raise
            self._start_notifications()
            self.persist()
            logging.info("Engine activated account=%s", self.account_id)

    def _status_snapshot(self):
        """A suspended account keeps a stale snapshot instead of looking live."""
        snapshot = self.snapshot()
        if self.suspended:
            snapshot.update({
                "account_id": self.account_id,
                "active": False,
                "running": False,
                "stale": True,
                "suspended": True,
            })
        return snapshot

    def _write_last_snapshot(self):
        write_json(self.root / "state" / "last-snapshot.json", self._status_snapshot())

    def reconnect_room(self, room):
        """Replace only the selected worker, after a fresh live-status probe."""
        with self.lock:
            if self.suspended:
                return False, "账号当前未运行，请先切换到此账号。"
            if not any(member["room"] == room for member in self.members):
                return False, "该直播间已不在关注列表中。"
            self.safety = self.application.safety_status()
            if self.safety.get("blocked"):
                return False, "账号保护暂停中，请先处理账号异常。"
            if self.paused:
                return False, "挂机已暂停，请先点击恢复挂机。"
            previous = self.manual_reconnects.get(room, {})
            now = time.time()
            if previous.get("cooldown_until", 0) > now:
                return False, "重连请求已提交，请稍后再试。"
            proc = self.workers.get(room)
            if proc:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=5)
                self._record_interruption(room, "manual_reconnect", expected_pid=proc.pid)
                self.workers.pop(room, None)
                self.worker_health.pop(room, None)
            self.worker_retries.pop(room, None)
            self.manual_reconnects[room] = {"state": "checking", "requested_at": now,
                                           "cooldown_until": now + 60, "skip_actions": True}
            self.next_check = 0
            self.force_probe = True
            append_event(self.root / "logs/activity.jsonl", {"type": "manual_reconnect", "room": room})
            self.persist()
            return True, "已请求重连，正在确认直播状态；只恢复看播连接。"

    def resume_safety(self, confirmed=False):
        with self.lock:
            ok, message = self.application.resume_safety(confirmed)
            self.safety = self.application.safety_status()
            if ok:
                self._was_safety_blocked = False
                self.error = ""
                self.next_check = 0
                self._clear_safety_task_results()
            self.persist()
            return ok, message

    def check_safety(self, *, auto_resume=False):
        with self.lock:
            result = self.application.probe_safety(auto=False, auto_resume=auto_resume)
            self.safety = result.get("hold") or self.application.safety_status()
            self.room_blocks = self.application.room_safety_blocks()
            if not self.safety.get("blocked"):
                self._was_safety_blocked = False
                self.error = ""
                self.next_check = 0
                self._clear_safety_task_results()
            self.persist()
            return result

    def _update_room_task_result(self, room, updater):
        path = self.root / "state" / f"{room}.json"
        if not path.is_file():
            return False

        def change(current):
            if not isinstance(current, dict):
                return current
            task_result = current.get("task_result")
            if not isinstance(task_result, dict):
                return current
            updated = updater(dict(task_result))
            return {**current, "task_result": updated}

        try:
            update_json(path, change, {})
            return True
        except (OSError, ValueError):
            logging.warning("Cannot update room task result room=%s", room)
            return False

    def _clear_safety_task_results(self):
        def strip_safety(task_result):
            if not format_task_errors(task_result):
                return task_result
            remaining = format_task_errors(task_result, suppress_safety=True)
            if not remaining:
                return {**task_result, "error": "", "dismissed": True}
            out = {**task_result, "error": remaining}
            for key in ("danmaku", "like"):
                branch = out.get(key)
                if isinstance(branch, dict) and branch.get("error"):
                    if not format_task_errors({key: branch}, suppress_safety=True):
                        out[key] = {**branch, "error": ""}
            return out

        for member in list(self.members):
            self._update_room_task_result(member["room"], strip_safety)

    def record_task_result(self, room, result):
        with self.lock:
            path = self.root / "state" / f"{room}.json"
            payload = dict(result or {})
            payload.setdefault("day", task_day())

            def change(current):
                base = dict(current) if isinstance(current, dict) else {"room": room}
                base["task_result"] = payload
                base["task_updated"] = time.time()
                return base

            try:
                update_json(path, change, {})
            except (OSError, ValueError):
                logging.warning("Cannot save room task result room=%s", room)

    def dismiss_task_error(self, room):
        with self.lock:
            if not any(m["room"] == room for m in self.members):
                return False, "该直播间已不在关注列表中。"

            def clear_error(task_result):
                out = {**task_result, "dismissed": True}
                out.pop("error", None)
                for key in ("danmaku", "like"):
                    branch = out.get(key)
                    if isinstance(branch, dict) and "error" in branch:
                        updated_branch = dict(branch)
                        updated_branch.pop("error", None)
                        out[key] = updated_branch
                return out

            self._update_room_task_result(room, clear_error)
            self.persist()
            return True, "已清除该直播间的任务提示。"

    def clear_room_block(self, room, capability=None):
        with self.lock:
            ok, message = self.application.clear_room_safety_block(room, capability)
            self.room_blocks = self.application.room_safety_blocks()
            if ok:
                targets = (capability,) if capability else ("danmaku", "like")

                def strip_room_block(task_result):
                    out = dict(task_result)
                    for key in targets:
                        branch = out.get(key)
                        if isinstance(branch, dict) and branch.get("room_blocked"):
                            if out.get("error") == branch.get("error"):
                                out.pop("error", None)
                            cleaned = dict(branch)
                            cleaned.pop("error", None)
                            cleaned.pop("room_blocked", None)
                            out[key] = cleaned
                    return out

                self._update_room_task_result(room, strip_room_block)
            self.persist()
            return ok, message

    def close(self):
        self.stopping.set()
        self._stop_notifications()
        with self.lock:
            self.suspended = True
            self.generation += 1
            self.stop_children("exited")
            self.job.close()
            self.persist(exited=True)
        if self.thread.is_alive():
            self.thread.join(timeout=5)
        # This runs in the control executor, not Tk. Finish any accepted IO before exit.
        if self.notifications is not None:
            self.notifications.join(timeout=5)

    def _read_room_state(self, room):
        try:
            value = read_json(self.root / "state" / f"{room}.json", {})
            if not isinstance(value, dict):
                raise ValueError("Room state must be an object")
        except (OSError, ValueError) as exc:
            error = type(exc).__name__
            if self.state_errors.get(room) != error:
                logging.warning("Room state unreadable room=%s error=%s", room, error)
            self.state_errors[room] = error
            return {"state_error": "房间状态无法读取，等待重新发布"}
        self.state_errors.pop(room, None)
        health = self.worker_health.get(room)
        if health and value.get("pid") != health["pid"]:
            return {"state_error": "等待当前进程发布状态", "started": self.started_at}
        return value

    def snapshot(self, *, blocking=True):
        if not self.lock.acquire(blocking=blocking):
            return None
        try:
            states = {m["room"]: self._read_room_state(m["room"]) for m in self.members}
            result = project_snapshot(self, states, time.time())
            result.update({
                "account_id": self.account_id,
                "suspended": self.suspended,
                "generation": self.generation,
            })
            if self.publish_error:
                result["error"] = "运行快照发布失败：" + self.publish_error
            return result
        finally:
            self.lock.release()

    def persist(self, exited=False):
        write_json(self.root / "status.json", {**self._status_snapshot(), "exited": exited})
        self.last_status_publish = time.time()
        self.publish_error = ""

    def cycle(self):
        """A publish failure must not disable scheduling or erase its diagnostics."""
        try:
            self.tick()
            self.last_tick = time.time()
        except Exception as exc:
            logging.exception("Monitor cycle failed")
            self.error = f"配置或运行错误：{type(exc).__name__}"
            self.next_check = time.time() + 60
        now = time.time()
        # A suspended account keeps its suspend-time status; refreshing it would
        # make stale rows look like a live connection to the dashboard.
        if not self.suspended and (
            self.publish_error or now - self.last_status_publish >= STATUS_PUBLISH_SECONDS
        ):
            try:
                # Recovery clears the previous publication error only after an actual write.
                snapshot = self._status_snapshot()
                snapshot["error"] = self.error
                write_json(self.root / "status.json", {**snapshot, "exited": False})
                self.last_status_publish = time.time()
                self.publish_error = ""
            except Exception as exc:
                error = type(exc).__name__
                if error != self.publish_error:
                    logging.exception("Status publication failed")
                self.publish_error = error
        if now - self.last_health_publish >= STATUS_PUBLISH_SECONDS:
            try:
                write_json(self.root / "monitor-health.json", {
                    "pid": os.getpid(), "started": self.started_at, "updated": time.time(),
                    "last_tick": self.last_tick, "last_status_publish": self.last_status_publish,
                    "publish_error": self.publish_error,
                })
                self.last_health_publish = time.time()
            except OSError:
                logging.warning("Cannot publish monitor health")

    def _watch_workers(self, now):
        clock = time.monotonic()
        for room, proc in list(self.workers.items()):
            if proc.poll() is not None:
                if proc.returncode:
                    logging.warning("Room worker exited unexpectedly room=%s code=%s", room, proc.returncode)
                else:
                    logging.info("Room worker exited room=%s code=%s", room, proc.returncode)
                self._record_interruption(room, "worker_exited")
                del self.workers[room]
                self.worker_health.pop(room, None)
                self.next_check = min(self.next_check, now + 300)
                continue
            state = self._read_room_state(room)
            record = self.worker_health.setdefault(room, {
                "pid": proc.pid, "started": clock, "progress": clock,
            })
            if "signature" in record:
                record.setdefault("beat_signature", record["signature"][0])
            record.setdefault("beat_progress", record.get("progress", record["started"]))
            if not check_progress(state, record, clock):
                if state.get("pid") == proc.pid and number(state.get("beats")) >= 5:
                    self.worker_retries.pop(room, None)
                continue
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            del self.workers[room]
            self.worker_health.pop(room, None)
            attempt = self.worker_retries.get(room, {}).get("attempt", 0) + 1
            profile = profile_for(self.config.get("run_mode", "stable"))
            delay = recovery_delay(attempt) * profile.recovery_base_seconds // 60
            logging.warning("Room worker stalled room=%s attempt=%s retry_minutes=%s", room, attempt, delay)
            self.worker_retries[room] = {"attempt": attempt, "until": clock + delay}
            self._record_interruption(room, "worker_timeout", expected_pid=proc.pid)
            append_event(self.root / "logs/activity.jsonl", {
                "type": "worker_recovery", "room": room, "attempt": attempt,
                "delay": delay, "reason": "progress_timeout",
            })
            self.next_check = min(self.next_check, now + delay)
        for room, retry in self.worker_retries.items():
            if room not in self.workers and self.probe is None:
                self.next_check = min(self.next_check, now + max(0, retry["until"] - clock))

    def tick(self):
        if self.suspended:
            return
        self.reload_settings()
        now = time.time()
        self.safety = self.application.safety_status()
        self.room_blocks = self.application.room_safety_blocks()
        if self.safety["blocked"]:
            self._was_safety_blocked = True
            if self.safety.get("kind") in ("auth", "credentials"):
                self.account = ""
                self.account_checked_at = 0
            # IO guards block new writes immediately; let a bounded read finish.
            grace = (
                self.safety.get("kind") == "uncertain" and now - self.safety.get("since", 0) < 20
            )
            if (self.workers or self.probe) and not grace:
                self.stop_children("account_safety")
            next_probe = self.safety.get("next_probe_at") or 0
            if (
                not self.paused
                and not grace
                and self.safety.get("kind") in ("uncertain", "review")
                and not self.safety.get("until")
                and next_probe
                and now >= next_probe
            ):
                result = self.application.probe_safety(auto=True)
                self.safety = result.get("hold") or self.application.safety_status()
                if not self.safety.get("blocked"):
                    self._was_safety_blocked = False
                    self.error = ""
                    self.next_check = 0
                    self._clear_safety_task_results()
                    self.persist()
                    self._watch_workers(now)
                    return
            self.error = self.safety["reason"]
            candidates = [
                t
                for t in (
                    self.safety.get("until"),
                    self.safety.get("next_probe_at"),
                    (self.safety.get("since", 0) + 20) if grace else None,
                    now + 300,
                )
                if t
            ]
            self.next_check = min(candidates)
            self.force_probe = False
            return
        if getattr(self, "_was_safety_blocked", False):
            self._was_safety_blocked = False
            self.error = ""
            self.next_check = 0
            self._clear_safety_task_results()
            self.persist()
        self._watch_workers(now)
        if self.probe:
            if self.probe.poll() is None and now - self.probe_started > 180:
                logging.warning("Probe timed out after 180s pid=%s", self.probe.pid)
                self.probe.kill()
                self.probe.wait()
                self.error = "网络检查超时，稍后重试。"
            if self.probe.poll() is not None:
                result = read_json(self.probe_path, {})
                self.probe_path.unlink(missing_ok=True)
                self.probe = None
                self.last_check = now
                if self.probe_generation == self.generation:
                    self._apply_probe(result, now)
        if (
            not self.suspended
            and not self.probe
            and now >= self.next_check
            and (not self.paused or getattr(self, "force_probe", False))
        ):
            self.force_probe = False
            self.probe_path = self.root / "state" / f"probe-{uuid.uuid4().hex}.json"
            self.probe_generation = self.generation
            try:
                self.probe = self.spawn("--probe", str(self.probe_path))
            except OSError:
                for request in self.manual_reconnects.values():
                    if request.get("state") == "checking":
                        request.update(state="failed", message="无法启动直播检查，请检查程序安装后重试。")
                raise
            self.probe_started = now
            self.next_check = now + self.config["check_minutes"] * 60

    def run(self):
        while not self.stopping.is_set():
            with self.lock:
                self.cycle()
            self.stopping.wait(1)

    def _apply_probe(self, result, now):
        if self.suspended:
            return
        message = result.get("error") or result.get("warning", "")
        if message and message != self.error:
            logging.warning("Status check reported: %s", message)
        self.error = message
        if "statuses" not in result:
            for request in self.manual_reconnects.values():
                if request["state"] == "checking":
                    request.update(state="failed", message="重连检查失败，请检查网络后再试。")
            for retry in self.worker_retries.values():
                retry["until"] = max(retry["until"], time.monotonic() + 300)
            self.error = self.error or "检查进程未返回结果，请查看日志。"
            self.status_errors = {str(m["room"]): self.error for m in self.members}
            if result.get("auth_invalid"):
                logging.warning("Bilibili credentials were rejected; signing out")
                self.account = ""
                self.account_checked_at = 0
                self.stop_children("auth_invalid")
            self.next_check = now + 300
            return
        self.account = result.get("account", "")
        self.account_checked_at = now
        observed = result.get("observed", now)
        received = {str(k): v for k, v in result["statuses"].items()}
        self.status_errors = {}
        failed_rooms = []
        for member in self.members:
            key = str(member["room"])
            if received.get(key, {}).get("live_status") in (0, 1, 2):
                self.status_times[key] = observed
                self.statuses[key] = received[key]
            else:
                self.status_errors[key] = "直播状态查询失败"
                failed_rooms.append(key)
        if failed_rooms:
            logging.warning("Probe missing live_status for rooms=%s", failed_rooms)
        if "medals" in result and isinstance(result["medals"], dict):
            self.medals = result["medals"]
            try:
                record_samples(
                    self.root,
                    self.account_id,
                    self.members,
                    self.medals,
                    result.get("medals_at") or self.probe_started,
                    now=now,
                )
            except Exception:
                logging.exception("Recording fan-medal growth failed")
        if "tasks" in result and isinstance(result["tasks"], dict):
            self.tasks.update(result["tasks"])
        self.task_errors = result.get("task_errors", {})
        for member in self.members:
            key = str(member["room"])
            status = received.get(key)
            request = self.manual_reconnects.get(member["room"], {})
            manual = request.get("state") == "checking"
            if manual and observed < request["requested_at"]:
                self.next_check = 0
                continue
            if manual and (not status or status.get("live_status") not in (0, 1, 2)):
                request.update(state="failed", message="直播状态无法确认，请检查网络后重试。")
            if status and status.get("live_status") in (0, 2):
                if request:
                    request.update(state="offline", message="房间已下播，无需重连。", skip_actions=False)
                self.worker_retries.pop(member["room"], None)
            elif not status or status.get("live_status") not in (0, 1, 2):
                retry = self.worker_retries.get(member["room"])
                if retry:
                    retry["until"] = max(retry["until"], time.monotonic() + 300)
            if status and status.get("live_status") == 1:
                if member["room"] not in self.known_live:
                    self.known_live.add(member["room"])
                    logging.info("Room went live room=%s name=%s", member["room"], member["name"])
                    if self.config.get("notify_on_live", True) and callable(self.notify_callback):
                        try:
                            self.notify_callback(member["name"], status.get("title", ""))
                        except Exception:
                            logging.exception("Desktop notification failed")
            elif status and status.get("live_status") in (0, 2):
                if member["room"] in self.known_live:
                    logging.info("Room went offline room=%s name=%s", member["room"], member["name"])
                self.known_live.discard(member["room"])
            if (
                not self.suspended
                and not self.paused
                and not self.safety.get("blocked")
                and status
                and (status.get("live_status") == 1)
                and (member["room"] not in self.workers)
                and time.monotonic() >= self.worker_retries.get(member["room"], {}).get("until", 0)
            ):
                args = ["--worker", key]
                skip_actions = request.get("skip_actions", False)
                if skip_actions:
                    args.append("--watch-only")
                try:
                    proc = self.spawn(*args)
                except OSError:
                    if request:
                        request.update(state="failed", message="无法启动看播连接，请检查程序安装后重试。")
                    self.worker_retries[member["room"]] = {"attempt": 1, "until": time.monotonic() + 60}
                    logging.exception("Cannot start room worker room=%s", member["room"])
                    continue
                self.workers[member["room"]] = proc
                logging.info(
                    "Room worker started room=%s name=%s pid=%s watch_only=%s",
                    member["room"], member["name"], proc.pid, skip_actions,
                )
                self.worker_health[member["room"]] = {
                    "pid": proc.pid, "started": time.monotonic(), "progress": time.monotonic(),
                }
                if skip_actions:
                    request.update(state="starting", message="已启动新连接，等待成功心跳。")
