"""Exercise the actual WebView2 window with isolated data and blocked account IO."""

import json
import logging
import os
from pathlib import Path
import tempfile
import threading
import time
import urllib.request
from unittest.mock import Mock, patch


def _forbidden(*_args, **_kwargs):
    raise AssertionError("Native diagnostics attempted an account request")


def _mark_started(engine):
    engine._started = True


def _capture(window, destination):
    # PrintWindow cannot capture WebView2's composited surface reliably. Ask the
    # renderer itself, marshalling the COM call to its WinForms UI thread.
    from System import Action, Object, Func
    from System.IO import FileStream, FileMode, FileAccess
    from Microsoft.Web.WebView2.Core import CoreWebView2CapturePreviewImageFormat

    done = threading.Event()
    result = {}
    stream = FileStream(str(Path(destination).resolve()), FileMode.Create, FileAccess.Write)

    def capture():
        try:
            core = window.native.browser.webview.CoreWebView2
            task = core.CapturePreviewAsync(CoreWebView2CapturePreviewImageFormat.Png, stream)

            def completed(completed_task):
                if completed_task.IsFaulted:
                    result["error"] = str(completed_task.Exception)
                stream.Dispose()
                done.set()

            task.ContinueWith(Action[Object](completed))
        except Exception as exc:
            result["error"] = str(exc)
            stream.Dispose()
            done.set()
        return None

    window.native.Invoke(Func[Object](capture))
    if not done.wait(12):
        raise RuntimeError("Native renderer screenshot timed out")
    if result.get("error"):
        raise RuntimeError(result["error"])


def _seed_diagnostic_store(root: Path):
    from bilioshi.accounts import AccountStore
    from desktop.avatars import file_token, save_account_profile
    from desktop.storage import initialize, write_json

    store = AccountStore(root)
    first_row, _ = store.upsert(123, "示例账号")
    second_row, _ = store.upsert(456, "第二账号")
    first_id, second_id = first_row["id"], second_row["id"]
    first_members = [
        {"name": "测试主播", "room": 7, "uid": 9},
        {"name": "示例主播", "room": 8, "uid": 10},
    ]
    second_members = [{"name": "第二主播", "room": 7, "uid": 11}]
    initialize(root, [])
    for account_id, uid, members in (
        (first_id, 123, first_members),
        (second_id, 456, second_members),
    ):
        account_root = store.ensure_root(account_id, uid)
        initialize(account_root, [])
        write_json(account_root / "members.json", members)
    store.save_credentials(first_id, "diagnostic-session", "diagnostic-csrf")
    store.save_credentials(second_id, "diagnostic-session-2", "diagnostic-csrf-2")
    first_root = store.account_root(first_id)
    save_account_profile(first_root, 123, "", file_token(first_root / "credentials.json"))
    return store, first_id, second_id, first_root


def _seed_first_engine_state(engine, account_root: Path, worker) -> None:
    from bilioshi.runtime import task_day
    from desktop.storage import write_json

    now = time.time()
    engine.statuses = {
        "7": {"live_status": 1, "title": "桌面窗口与桥接验收"},
        "8": {"live_status": 0},
    }
    engine.status_times = {"7": now, "8": now}
    engine.medals = {
        9: {
            "medal_name": "同行者",
            "level": 9,
            "today_intimacy": 15,
            "day_limit": 1500,
            "is_lighted": 1,
        }
    }
    engine.tasks["7"] = {
        "day": task_day(),
        "updated": now,
        "intimacy": 1280,
        "next_intimacy": 3000,
        "tasks": [
            {"title": "发送弹幕", "sub_title": "5 / 5", "is_done": True},
            {"title": "直播点赞", "sub_title": "8 / 10", "is_done": False},
            {"title": "观看直播", "sub_title": "30 / 30", "is_done": True},
        ],
    }
    engine.workers[7] = worker
    write_json(
        account_root / "state/7.json",
        {
            "pid": os.getpid(),
            "phase": "挂机中",
            "started": now - 2520,
            "last_heartbeat": now - 12,
            "beats": 41,
        },
    )


def _create_engine_factory(first_id: str, worker, engines: list):
    from desktop.engine import Engine

    def make_engine(account_root, *, job=None, account_id=None):
        engine = Engine(account_root, job=job, account_id=account_id)
        engine.account = "示例账号" if account_id == first_id else "第二账号"
        engine.account_checked_at = time.time()
        engine.last_check = time.time() - 90
        if account_id == first_id:
            _seed_first_engine_state(engine, account_root, worker)
        else:
            engine.statuses = {"7": {"live_status": 1, "title": "第二账号的直播"}}
            engine.status_times = {"7": time.time()}
        engines.append(engine)
        return engine

    return make_engine


class _DiagnosticSession:
    """Drives UI checks inside the live WebView2 window and records structured output."""

    def __init__(self, *, root: Path, host, accounts_host, first_id: str, second_id: str,
                 first_root: Path, output: Path, screenshot):
        self.root = root
        self.host = host
        self.accounts_host = accounts_host
        self.first_id = first_id
        self.second_id = second_id
        self.first_root = first_root
        self.output = output
        self.screenshot = screenshot
        self.report = {"ok": False, "renderer": "webview2", "checks": [], "errors": []}
        self.finished = threading.Event()

    def save(self) -> None:
        self.output.write_text(json.dumps(self.report, ensure_ascii=False, indent=2), encoding="utf-8")

    def check(self, name: str, condition) -> None:
        if not condition:
            raise AssertionError(name)
        self.report["checks"].append(name)

    def wait(self, expression: str, timeout: float = 12):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.host._window.evaluate_js(expression)
            if result:
                return result
            time.sleep(0.08)
        raise AssertionError("Timed out waiting for " + expression[:100])

    def click(self, selector: str) -> None:
        expression = (
            "(function(){const e=document.querySelector("
            + json.dumps(selector)
            + ");if(!e)return false;e.click();return true;})()"
        )
        self.check("click " + selector, self.host._window.evaluate_js(expression))

    def _verify_account_switching(self) -> None:
        self.wait("Boolean(window.LS && document.querySelectorAll('.room').length === 2)")
        self.check("two rooms rendered", True)
        self.wait('document.querySelectorAll(\'.account-tab[role="tab"]\').length === 2')
        self.check("account tabs rendered", True)
        self.click("#account-tab-" + self.second_id)
        self.wait("document.querySelector('.account-tab.active')?.id === " + json.dumps("account-tab-" + self.second_id))
        self.wait("document.querySelectorAll('.room').length === 1")
        self.wait("document.querySelector('.detail-name')?.textContent === '第二主播'")
        self.check("switch to second account without QR", True)
        self.click("#account-tab-" + self.first_id)
        self.wait("document.querySelector('.account-tab.active')?.id === " + json.dumps("account-tab-" + self.first_id))
        self.wait("document.querySelectorAll('.room').length === 2")
        self.wait("document.querySelector('.detail-name')?.textContent === '测试主播'")
        self.check("switch back without QR", True)

    def _verify_window_chrome(self) -> None:
        eval_js = self.host._window.evaluate_js
        self.report["typography"] = eval_js(
            "({body:getComputedStyle(document.body).fontFamily,"
            "heading:getComputedStyle(document.querySelector('.chrome-title')).fontFamily})"
        )
        self.check("account stays a string", isinstance(self.host._api.snapshot()["account"], str))
        self.check("single title bar", eval_js(
            "document.querySelectorAll('.chrome').length === 1 && !document.querySelector('.topbar')"))
        self.check("drag region present", eval_js("Boolean(document.querySelector('.chrome.pywebview-drag-region'))"))
        self.check("window buttons rendered", eval_js("document.querySelectorAll('.win-btn').length === 3"))
        self.check("title bar carries only the page title", eval_js(
            "!document.querySelector('.chrome-sub') && document.querySelector('.chrome-title')?.textContent === '直播总览'"))
        self.check("status bar reports cadence and last check", eval_js(
            "/每 5 分钟检查一次/.test(document.querySelector('.statusbar').textContent)"
            " && /上次检查/.test(document.querySelector('.statusbar').textContent)"))
        state = self.host._api.window("state")
        self.check("window state readable", isinstance(state.get("maximized"), bool))
        self.host._api.window("maximize")
        self.wait("document.documentElement.dataset.maximized === 'true'")
        self.check("maximized state follows the window", True)
        self.host._api.window("maximize")
        self.wait("document.documentElement.dataset.maximized === 'false'")
        self.check("restored state follows the window", True)
        # The collapsed state is remembered between runs, so start from open.
        if eval_js("document.querySelector('.app').classList.contains('side-collapsed')"):
            self.click(".side-btn")
            self.wait("!document.querySelector('.app').classList.contains('side-collapsed')")
        self.click(".side-btn")
        self.wait("document.querySelector('.app').classList.contains('side-collapsed')")
        self.check("sidebar collapses", True)
        self.click(".side-btn")
        self.wait("!document.querySelector('.app').classList.contains('side-collapsed')")
        self.check("sidebar reopens", True)
        self.wait("document.querySelector('.detail-name')?.textContent === '测试主播'")
        if self.screenshot:
            _capture(self.host._window, self.screenshot)
            self.report["screenshot"] = Path(self.screenshot).name

    def _verify_settings_and_theme(self) -> None:
        eval_js = self.host._window.evaluate_js
        settings_path = self.first_root / "settings.json"
        self.click('button[aria-label="设置"]')
        self.wait("document.querySelector('.chrome-title')?.textContent === '设置'")
        self.click('[role="switch"][aria-label="直播点赞"]')
        self.wait("document.querySelector('[role=\"switch\"][aria-label=\"直播点赞\"]')?.getAttribute('aria-checked') === 'true'")
        self.wait("!document.querySelector('[role=\"switch\"][aria-label=\"直播点赞\"]').disabled")
        self.check("setting persisted", json.loads(settings_path.read_text(encoding="utf-8"))["auto_like"] is True)
        self.check("native select removed", eval_js("!document.querySelector('select')"))
        self.click(".choice-button")
        self.wait("Boolean(document.querySelector('.choice-menu'))")
        self.click('.choice-option[data-value="aggressive"]')
        self.wait("document.querySelector('.choice-label')?.textContent === '激进'")
        self.wait("!document.querySelector('.choice-menu')")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and json.loads(settings_path.read_text(encoding="utf-8"))["run_mode"] != "aggressive":
            time.sleep(0.05)
        self.check("run mode uses themed menu", json.loads(settings_path.read_text(encoding="utf-8"))["run_mode"] == "aggressive")
        original_theme = eval_js("document.documentElement.dataset.theme || 'system'")
        self.click('.theme-option[data-theme="mist"]')
        self.wait("document.documentElement.dataset.theme === 'mist'")
        self.check("theme switch updates surfaces", eval_js(
            "getComputedStyle(document.documentElement).getPropertyValue('--paper').trim() === '#f2f6f5'"
            " && document.querySelector('meta[name=\"color-scheme\"]')?.content === 'light'"
            " && document.querySelector('.theme-option[data-theme=\"mist\"]').getAttribute('aria-pressed') === 'true'"))
        self.click('.theme-option[data-theme="dark"]')
        self.wait("document.documentElement.dataset.theme === 'dark'")
        self.check("dark theme updates surfaces", eval_js(
            "getComputedStyle(document.documentElement).getPropertyValue('--paper').trim() === '#141716'"
            " && document.querySelector('meta[name=\"color-scheme\"]')?.content === 'dark'"
            " && localStorage.getItem('bilioshi.theme') === 'dark'"))
        self.click('.theme-option[data-theme="system"]')
        self.wait("document.documentElement.dataset.theme === 'system'")
        self.check("system theme clears stored override", eval_js(
            "document.querySelector('meta[name=\"color-scheme\"]')?.content === 'light dark'"
            " && localStorage.getItem('bilioshi.theme') === null"))
        self.click('.theme-option[data-day-theme="mist"]')
        self.wait("document.documentElement.dataset.dayTheme === 'mist'")
        self.check("system day theme updates attribute", eval_js("localStorage.getItem('bilioshi.dayTheme') === 'mist'"))
        self.click('.theme-option[data-day-theme="white"]')
        self.wait("document.documentElement.dataset.dayTheme === 'white'")
        self.check("default day theme clears stored override", eval_js("localStorage.getItem('bilioshi.dayTheme') === null"))
        self.click(f'.theme-option[data-theme="{original_theme}"]')
        self.wait(f"document.documentElement.dataset.theme === {json.dumps(original_theme)}")
        expected_storage = "null" if original_theme == "system" else json.dumps(original_theme)
        self.check("theme preference persists", eval_js(f"localStorage.getItem('bilioshi.theme') === {expected_storage}"))

    def _verify_account_page_and_qr(self) -> None:
        eval_js = self.host._window.evaluate_js
        self.click('button[aria-label="账号"]')
        self.wait("document.querySelector('.chrome-title')?.textContent === '账号'")
        self.check("account rendered", "示例账号" in eval_js("document.body.innerText"))
        self.check("both accounts listed", eval_js("document.querySelectorAll('.account-item').length === 2"))
        self.wait("Boolean(document.querySelector('.account-item .avatar img'))")
        self.check("account avatar uses the public profile", eval_js(
            "document.querySelector('.account-item .avatar img').src.startsWith('data:image/png;base64,')"))
        self.wait("Boolean(document.querySelector('.sidebar-avatar img'))")
        self.check("sidebar avatar matches the account", True)
        self.click(".group-head .btn.primary")
        self.wait("Boolean(document.querySelector('.qr-wrap img'))")
        self.check("QR has image", True)
        eval_js("document.querySelector('.scrim').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        # Keyboard events are handled by the dialog itself.
        eval_js("document.querySelector('.modal').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
        self.wait("!document.querySelector('.modal')")
        self.check("QR cancellation", self.host._api._qr_cancel_event is None)

    def _verify_ipc_and_tray(self) -> None:
        from desktop.storage import send_command

        self.click('button[aria-label="直播总览"]')
        self.wait("document.querySelector('.chrome-title')?.textContent === '直播总览'")
        self.click('button[data-room="8"]')
        self.wait("document.querySelector('.detail-name')?.textContent === '示例主播'")
        self.check("offline action disabled", self.host._window.evaluate_js("document.querySelector('.detail-foot .primary').disabled"))
        self.click('button[data-room="7"]')
        # Use the same disk IPC used by a second launch, without touching installed data.
        send_command(self.root, "pause")
        self.wait("document.querySelector('.statusbar').textContent.includes('已暂停')")
        self.check("IPC pause", self.accounts_host.active_engine().paused)
        send_command(self.root, "resume")
        self.wait("!document.querySelector('.statusbar').textContent.includes('已暂停')")
        self.check("IPC resume", not self.accounts_host.active_engine().paused)
        if self.host._has_tray():
            self.check("close hides to tray", self.host.close_window())
            self.check("engine remains running", not self.host._closing.is_set())
            send_command(self.root, "show")
            self.report["checks"].append("IPC show queued")

    def drive(self) -> None:
        from desktop.storage import send_command

        try:
            self._verify_account_switching()
            self._verify_window_chrome()
            self._verify_settings_and_theme()
            self._verify_account_page_and_qr()
            self._verify_ipc_and_tray()
            errors = self.host._window.evaluate_js("window.__errs || []")
            self.check("no JavaScript errors", not errors)
            self.report["errors"] = errors
            self.report["ok"] = True
        except Exception as exc:
            logging.exception("Native Web UI diagnostic failed")
            self.report["errors"].append(str(exc))
        finally:
            self.save()
            send_command(self.root, "exit")
            self.host.push_now()
            self.finished.set()

    def on_loaded(self) -> None:
        threading.Thread(target=self.drive, name="webui-diagnostic", daemon=True).start()

    def watchdog(self) -> None:
        if not self.finished.wait(55):
            self.report["errors"].append("Native window diagnostic timed out")
            self.save()
            self.host.quit()


def _launch_isolated(host, root: Path, qr_session) -> None:
    from PIL import Image
    from desktop.engine import Engine

    avatar = Image.new("RGB", (64, 64), "#2d6763")
    try:
        with patch.dict(os.environ, {"BILIOSHI_APP_DATA": str(root)}), \
             patch.object(Engine, "start", _mark_started), \
             patch("urllib.request.urlopen", side_effect=_forbidden), \
             patch("urllib.request.OpenerDirector.open", side_effect=_forbidden), \
             patch("desktop.avatars.load_avatar", side_effect=lambda *_: avatar.copy()), \
             patch("bilioshi.qr_login.QrLoginSession", return_value=qr_session), \
             patch("desktop.windows.is_autostart_enabled", return_value=False):
            host.run(show=True)
    finally:
        avatar.close()


def run(output, screenshot=None):
    """Return a process exit code and a small, account-free verification report."""
    from bilioshi.qr_login import PollResult
    from desktop.host import AccountHost
    from .window import WebHost

    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="livesupport-webui-") as directory:
        root = Path(directory)
        store, first_id, second_id, first_root = _seed_diagnostic_store(root)
        worker = Mock(pid=os.getpid())
        worker.poll.return_value = None
        engines = []
        accounts_host = AccountHost(
            root, store,
            engine_factory=_create_engine_factory(first_id, worker, engines),
            job_factory=Mock,
        )
        qr_session = Mock()
        qr_session.generate.return_value = "https://account.bilibili.com/h5/account-h5/auth/scan-web?key=diagnostic-only"
        qr_session.poll.return_value = PollResult("waiting")
        host = WebHost(accounts_host)
        session = _DiagnosticSession(
            root=root, host=host, accounts_host=accounts_host,
            first_id=first_id, second_id=second_id, first_root=first_root,
            output=output, screenshot=screenshot,
        )
        host.window_loaded_hook = session.on_loaded
        threading.Thread(target=session.watchdog, daemon=True).start()
        _launch_isolated(host, root, qr_session)
        session.report["checks"].append("native window returned cleanly")
        session.check("engine shutdown completed", host._closed.is_set() and all(item.stopping.is_set() for item in engines))
        session.check("no pending QR or bridge IO", host._api._active == 0)
        session.save()
        return 0 if session.report["ok"] else 1
