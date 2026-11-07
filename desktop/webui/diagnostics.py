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
            def completed(task):
                if task.IsFaulted:
                    result["error"] = str(task.Exception)
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


def run(output, screenshot=None):
    """Return a process exit code and a small, account-free verification report."""
    from bilioshi.accounts import AccountStore
    from bilioshi.qr_login import PollResult
    from bilioshi.runtime import task_day
    from desktop.engine import Engine
    from desktop.host import AccountHost
    from desktop.storage import initialize, write_json, send_command
    from .window import WebHost

    output = Path(output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {"ok": False, "renderer": "webview2", "checks": [], "errors": []}
    finished = threading.Event()

    def save():
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def forbidden(*args, **kwargs):
        raise AssertionError("Native diagnostics attempted an account request")

    with tempfile.TemporaryDirectory(prefix="livesupport-webui-") as directory:
        root = Path(directory)
        store = AccountStore(root)
        first_row, _ = store.upsert(123, "示例账号")
        second_row, _ = store.upsert(456, "第二账号")
        first_id, second_id = first_row["id"], second_row["id"]
        first_members = [{"name": "测试主播", "room": 7, "uid": 9}, {"name": "示例主播", "room": 8, "uid": 10}]
        second_members = [{"name": "第二主播", "room": 7, "uid": 11}]
        initialize(root, [])
        for account_id, uid, members in (
            (first_id, 123, first_members), (second_id, 456, second_members),
        ):
            account_root = store.ensure_root(account_id, uid)
            initialize(account_root, [])
            write_json(account_root / "members.json", members)
        store.save_credentials(first_id, "diagnostic-session", "diagnostic-csrf")
        store.save_credentials(second_id, "diagnostic-session-2", "diagnostic-csrf-2")
        first_root = store.account_root(first_id)
        from desktop.avatars import file_token, save_account_profile

        save_account_profile(first_root, 123, "", file_token(first_root / "credentials.json"))
        worker = Mock(pid=os.getpid())
        worker.poll.return_value = None
        engines = []

        def make_engine(account_root, *, job=None, account_id=None):
            engine = Engine(account_root, job=job, account_id=account_id)
            engine.account = "示例账号" if account_id == first_id else "第二账号"
            engine.account_checked_at = time.time()
            engine.last_check = time.time() - 90
            if account_id == first_id:
                engine.statuses = {"7": {"live_status": 1, "title": "桌面窗口与桥接验收"},
                                   "8": {"live_status": 0}}
                engine.status_times = {"7": time.time(), "8": time.time()}
                engine.medals = {9: {"medal_name": "同行者", "level": 9, "today_intimacy": 15,
                                     "day_limit": 1500, "is_lighted": 1}}
                engine.tasks["7"] = {"day": task_day(), "updated": time.time(), "intimacy": 1280,
                    "next_intimacy": 3000, "tasks": [
                        {"title": "发送弹幕", "sub_title": "5 / 5", "is_done": True},
                        {"title": "直播点赞", "sub_title": "8 / 10", "is_done": False},
                        {"title": "观看直播", "sub_title": "30 / 30", "is_done": True}]}
                engine.workers[7] = worker
                write_json(account_root / "state/7.json", {
                    "pid": os.getpid(), "phase": "挂机中", "started": time.time() - 2520,
                    "last_heartbeat": time.time() - 12, "beats": 41})
            else:
                engine.statuses = {"7": {"live_status": 1, "title": "第二账号的直播"}}
                engine.status_times = {"7": time.time()}
            engines.append(engine)
            return engine

        accounts_host = AccountHost(root, store, engine_factory=make_engine, job_factory=Mock)
        qr_session = Mock()
        qr_session.generate.return_value = "https://account.bilibili.com/h5/account-h5/auth/scan-web?key=diagnostic-only"
        qr_session.poll.return_value = PollResult("waiting")
        host = WebHost(accounts_host)

        def check(name, condition):
            if not condition:
                raise AssertionError(name)
            report["checks"].append(name)

        def wait(expression, timeout=12):
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                result = host._window.evaluate_js(expression)
                if result:
                    return result
                time.sleep(0.08)
            raise AssertionError("Timed out waiting for " + expression[:100])

        def click(selector):
            expression = "(function(){const e=document.querySelector(" + json.dumps(selector) + ");if(!e)return false;e.click();return true;})()"
            check("click " + selector, host._window.evaluate_js(expression))

        def drive():
            try:
                wait("Boolean(window.LS && document.querySelectorAll('.room').length === 2)")
                check("two rooms rendered", True)
                wait("document.querySelectorAll('.account-tab[role=\"tab\"]').length === 3")
                check("account tabs rendered", True)
                click("#account-tab-all")
                wait("document.querySelectorAll('.account-card').length === 2")
                check("all-account dashboard rendered", True)
                click(".account-card:nth-of-type(2) .link-btn")
                wait("Boolean(document.querySelector('.modal'))")
                click(".modal .btn.primary")
                wait("document.querySelector('.account-tab.active')?.id === "
                     + json.dumps("account-tab-" + second_id))
                wait("document.querySelectorAll('.room').length === 1")
                wait("document.querySelector('.detail-name')?.textContent === '第二主播'")
                check("switch to second account without QR", True)
                click("#account-tab-all")
                wait("document.querySelectorAll('.account-card').length === 2")
                click(".account-card:nth-of-type(1) .link-btn")
                wait("Boolean(document.querySelector('.modal'))")
                click(".modal .btn.primary")
                wait("document.querySelector('.account-tab.active')?.id === "
                     + json.dumps("account-tab-" + first_id))
                wait("document.querySelectorAll('.room').length === 2")
                wait("document.querySelector('.detail-name')?.textContent === '测试主播'")
                check("switch back without QR", True)
                report["typography"] = host._window.evaluate_js("({body:getComputedStyle(document.body).fontFamily, heading:getComputedStyle(document.querySelector('.chrome-title')).fontFamily})")
                check("account stays a string", isinstance(host._api.snapshot()["account"], str))
                check("single title bar", host._window.evaluate_js(
                    "document.querySelectorAll('.chrome').length === 1 && !document.querySelector('.topbar')"))
                check("drag region present", host._window.evaluate_js(
                    "Boolean(document.querySelector('.chrome.pywebview-drag-region'))"))
                check("window buttons rendered", host._window.evaluate_js(
                    "document.querySelectorAll('.win-btn').length === 3"))
                check("title bar carries only the page title", host._window.evaluate_js(
                    "!document.querySelector('.chrome-sub') && document.querySelector('.chrome-title')?.textContent === '直播总览'"))
                check("status bar reports cadence and last check", host._window.evaluate_js(
                    "/每 5 分钟检查一次/.test(document.querySelector('.statusbar').textContent)"
                    " && /上次检查/.test(document.querySelector('.statusbar').textContent)"))
                state = host._api.window("state")
                check("window state readable", isinstance(state.get("maximized"), bool))
                host._api.window("maximize")
                wait("document.documentElement.dataset.maximized === 'true'")
                check("maximized state follows the window", True)
                host._api.window("maximize")
                wait("document.documentElement.dataset.maximized === 'false'")
                check("restored state follows the window", True)
                # The collapsed state is remembered between runs, so start from open.
                if host._window.evaluate_js("document.querySelector('.app').classList.contains('side-collapsed')"):
                    click('.side-btn')
                    wait("!document.querySelector('.app').classList.contains('side-collapsed')")
                click('.side-btn')
                wait("document.querySelector('.app').classList.contains('side-collapsed')")
                check("sidebar collapses", True)
                click('.side-btn')
                wait("!document.querySelector('.app').classList.contains('side-collapsed')")
                check("sidebar reopens", True)
                wait("document.querySelector('.detail-name')?.textContent === '测试主播'")
                if screenshot:
                    _capture(host._window, screenshot)
                    report["screenshot"] = Path(screenshot).name
                click('button[aria-label="挂机设置"]')
                wait("document.querySelector('.chrome-title')?.textContent === '挂机设置'")
                click('[role="switch"][aria-label="直播点赞"]')
                wait("document.querySelector('[role=\"switch\"][aria-label=\"直播点赞\"]')?.getAttribute('aria-checked') === 'true'")
                wait("!document.querySelector('[role=\"switch\"][aria-label=\"直播点赞\"]').disabled")
                check("setting persisted", json.loads((first_root / "settings.json").read_text(encoding="utf-8"))["auto_like"] is True)
                check("native select removed", host._window.evaluate_js("!document.querySelector('select')"))
                click('.choice-button')
                wait("Boolean(document.querySelector('.choice-menu'))")
                click('.choice-option[data-value="aggressive"]')
                wait("document.querySelector('.choice-label')?.textContent === '激进'")
                wait("!document.querySelector('.choice-menu')")
                deadline = time.monotonic() + 3
                while (time.monotonic() < deadline
                       and json.loads((first_root / "settings.json").read_text(encoding="utf-8"))["run_mode"] != "aggressive"):
                    time.sleep(0.05)
                check("run mode uses themed menu",
                      json.loads((first_root / "settings.json").read_text(encoding="utf-8"))["run_mode"] == "aggressive")
                original_theme = host._window.evaluate_js(
                    "document.documentElement.dataset.theme || 'white'")
                click('.theme-option[data-theme="mist"]')
                wait("document.documentElement.dataset.theme === 'mist'")
                check("theme switch updates surfaces", host._window.evaluate_js(
                    "getComputedStyle(document.documentElement).getPropertyValue('--paper').trim() === '#f2f6f5'"
                    " && document.querySelector('.theme-option[data-theme=\"mist\"]').getAttribute('aria-pressed') === 'true'"))
                click(f'.theme-option[data-theme="{original_theme}"]')
                wait(f"document.documentElement.dataset.theme === {json.dumps(original_theme)}")
                check("theme preference persists", host._window.evaluate_js(
                    f"localStorage.getItem('bilioshi.theme') === {json.dumps(original_theme)}"))
                click('button[aria-label="账号"]')
                wait("document.querySelector('.chrome-title')?.textContent === '账号'")
                check("account rendered", "示例账号" in host._window.evaluate_js("document.body.innerText"))
                check("both accounts listed", host._window.evaluate_js(
                    "document.querySelectorAll('.account-item').length === 2"))
                wait("Boolean(document.querySelector('.account-item .avatar img'))")
                check("account avatar uses the public profile", host._window.evaluate_js(
                    "document.querySelector('.account-item .avatar img').src.startsWith('data:image/png;base64,')"))
                wait("Boolean(document.querySelector('.sidebar-avatar img'))")
                check("sidebar avatar matches the account", True)
                click('.group-head .btn.primary')
                wait("Boolean(document.querySelector('.qr-wrap img'))")
                check("QR has image", True)
                host._window.evaluate_js("document.querySelector('.scrim').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
                # Keyboard events are handled by the dialog itself.
                host._window.evaluate_js("document.querySelector('.modal').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true}))")
                wait("!document.querySelector('.modal')")
                check("QR cancellation", host._api._qr_cancel_event is None)
                click('button[aria-label="直播总览"]')
                wait("document.querySelector('.chrome-title')?.textContent === '直播总览'")
                click('button[data-room="8"]')
                wait("document.querySelector('.detail-name')?.textContent === '示例主播'")
                check("offline action disabled", host._window.evaluate_js("document.querySelector('.detail-foot .primary').disabled"))
                click('button[data-room="7"]')
                # Use the same disk IPC used by a second launch, without touching installed data.
                send_command(root, "pause")
                wait("document.querySelector('.statusbar').textContent.includes('已暂停')")
                check("IPC pause", accounts_host.active_engine().paused)
                send_command(root, "resume")
                wait("!document.querySelector('.statusbar').textContent.includes('已暂停')")
                check("IPC resume", not accounts_host.active_engine().paused)
                if host._has_tray():
                    check("close hides to tray", host.close_window())
                    check("engine remains running", not host._closing.is_set())
                    send_command(root, "show")
                    report["checks"].append("IPC show queued")
                errors = host._window.evaluate_js("window.__errs || []")
                check("no JavaScript errors", not errors)
                report["errors"] = errors
                report["ok"] = True
            except Exception as exc:
                logging.exception("Native Web UI diagnostic failed")
                report["errors"].append(str(exc))
            finally:
                save()
                send_command(root, "exit")
                host.push_now()
                finished.set()

        def loaded():
            threading.Thread(target=drive, name="webui-diagnostic", daemon=True).start()

        def watchdog():
            if not finished.wait(55):
                report["errors"].append("Native window diagnostic timed out")
                save()
                host.quit()

        def mark_started(engine):
            engine._started = True

        host.window_loaded_hook = loaded
        threading.Thread(target=watchdog, daemon=True).start()
        from PIL import Image
        avatar = Image.new("RGB", (64, 64), "#2d6763")
        with patch.dict(os.environ, {"BILIOSHI_APP_DATA": str(root)}), \
             patch.object(Engine, "start", mark_started), \
             patch("urllib.request.urlopen", side_effect=forbidden), \
             patch("urllib.request.OpenerDirector.open", side_effect=forbidden), \
             patch("desktop.avatars.load_avatar", side_effect=lambda *_: avatar.copy()), \
             patch("bilioshi.qr_login.QrLoginSession", return_value=qr_session), \
             patch("desktop.windows.is_autostart_enabled", return_value=False):
            host.run(show=True)
        avatar.close()
        report["checks"].append("native window returned cleanly")
        check("engine shutdown completed", host._closed.is_set()
              and all(item.stopping.is_set() for item in engines))
        check("no pending QR or bridge IO", host._api._active == 0)
        save()
    return 0 if report["ok"] else 1
