"""Contracts at the local renderer boundary; no browser or account requests."""

import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from desktop.avatars import file_token, save_account_profile
from desktop.engine import Engine
from desktop.storage import initialize, read_json, write_json, send_command
from desktop.webui.api import Api
from desktop.webui.window import ASSETS, WebHost, _initial_background_color


class WebUiTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        initialize(self.root, [{"room": 7, "uid": 9, "name": "测试主播"}])
        self.engine = Engine(self.root, job=Mock())
        self.ui = Mock()
        self.ui.apply_settings.side_effect = self.engine.reload_settings
        self.api = Api(self.engine, self.ui)

    def confirmed_room(self):
        self.engine.account = "测试账号"
        self.engine.account_checked_at = time.time()
        self.engine.statuses["7"] = {"live_status": 1}
        self.engine.status_times["7"] = time.time()
        self.engine.application.redo = Mock(return_value={"success": True})

    def test_snapshot_preserves_account_and_never_exposes_owned_objects_or_credentials(self):
        self.confirmed_room()
        write_json(self.root / "credentials.json", {"SESSDATA": "synthetic-session", "bili_jct": "synthetic-csrf"})
        with patch("bilioshi.runtime.unseal", side_effect=AssertionError("UI must not decrypt")):
            snap = self.api.snapshot()
        self.assertEqual(snap["account"], "测试账号")
        self.assertTrue(snap["accountInfo"]["signed_in"])
        self.assertEqual(snap["rows"][0]["actions"]["redo"], "")
        self.assertNotIn("synthetic-session", json.dumps(snap))
        self.assertTrue(all(callable(getattr(self.api, name)) for name in dir(self.api) if not name.startswith("_")))
        with patch.object(self.engine, "snapshot", return_value=None):
            cached = self.api.snapshot()
        self.assertTrue(cached["engine_busy"])
        self.assertEqual(cached["rows"][0]["name"], "测试主播")

    def test_avatar_refresh_failure_falls_back_to_the_cached_image(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")

        path = self.root / "cache/avatars/9.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (8, 8), "#2d6763").save(path)
        stale = time.time() - 2 * 86400
        os.utime(path, (stale, stale))
        with patch("desktop.avatars._read", side_effect=OSError("network down")):
            result = self.api.avatar(9)
        self.assertTrue(result["ok"])
        self.assertTrue(result["data_uri"].startswith("data:image/png;base64,"))

    def test_account_avatar_uses_only_the_server_side_public_profile(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("PIL not installed")

        write_json(self.root / "credentials.json", {"SESSDATA": "synthetic-session", "bili_jct": "synthetic-csrf"})
        save_account_profile(self.root, 123, "https://i0.hdslb.com/bfs/face/example.jpg",
                             file_token(self.root / "credentials.json"))
        image = Image.new("RGB", (8, 8), "#2d6763")
        with patch("desktop.avatars.load_avatar", return_value=image) as load:
            result = self.api.account_avatar()
        self.assertTrue(result["ok"])
        self.assertTrue(result["data_uri"].startswith("data:image/png;base64,"))
        load.assert_called_once_with(self.root, 123, "https://i0.hdslb.com/bfs/face/example.jpg")
        self.assertNotIn("synthetic-session", json.dumps(result))

    def test_settings_normalize_legacy_policy_and_apply_despite_autostart_failure(self):
        write_json(self.root / "settings.json", {"danmaku": False, "live_likes": True, "check_minutes": 15})
        with patch("desktop.windows.set_autostart", return_value=False), \
             patch("desktop.windows.is_autostart_enabled", return_value=False):
            result = self.api.save_settings({"autostart": True, "notify_on_live": True})
        self.assertTrue(result["ok"])
        self.assertTrue(result["warning"])
        saved = read_json(self.root / "settings.json")
        self.assertFalse(saved["auto_revive"])
        self.assertFalse(saved["auto_danmaku_intimacy"])
        self.assertTrue(self.engine.config["auto_like"])
        for changes in ({"auto_like": "false"}, {"check_minutes": 1.5}, {"check_minutes": True}):
            self.assertFalse(self.api.save_settings(changes)["ok"])

    def test_duplicate_room_writes_are_rejected_while_pause_remains_responsive(self):
        self.confirmed_room()
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def slow_redo(*_):
            entered.set()
            release.wait(4)
            return {"success": True}
        self.engine.application.redo.side_effect = slow_redo
        worker = threading.Thread(target=lambda: self.api.redo(7))
        worker.start()
        try:
            self.assertTrue(entered.wait(2))
            self.assertFalse(self.api.redo(7)["ok"])
            with patch.object(self.engine, "set_paused") as pause:
                self.assertTrue(self.api.set_paused(True)["ok"])
                pause.assert_called_once_with(True)
        finally:
            release.set()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.engine.application.redo = Mock(return_value={"success": False, "error": "任务尚未完成"})
        self.assertFalse(self.api.redo(7)["ok"])

    def test_sync_import_uses_resolved_members_and_retains_existing(self):
        self.engine.application.medals = Mock(return_value=[
            {"uid": 9, "room": 7, "name": "测试主播", "medal_name": "牌", "level": 8},
            {"uid": 10, "room": 8, "name": "新主播", "medal_name": "新牌", "level": 4},
        ])
        result = self.api.medals()
        self.assertTrue(result["ok"])
        self.assertTrue(next(row for row in result["medals"] if row["uid"] == 9)["watched"])
        self.assertEqual(self.api.import_medals([9, 10])["count"], 1)
        self.assertEqual({row["room"] for row in read_json(self.root / "members.json")}, {7, 8})

    def test_cancelled_qr_cannot_save_after_validation_returns(self):
        from bilioshi.qr_login import PollResult
        session = Mock()
        cancel = threading.Event()
        with self.api._qr_lock:
            generation = self.api._qr_generation
            self.api._qr_session, self.api._qr_cancel_event = session, cancel
        with self.api._state:
            self.api._active += 1
        session.poll.return_value = PollResult("confirmed", credentials={"SESSDATA": "test", "bili_jct": "test"})
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def validate(*_):
            entered.set()
            release.wait(3)
            return True, "测试账号", {"name": "测试账号", "uid": 123, "face": ""}
        self.engine.application.validate_credentials_profile = validate
        with patch("bilioshi.qr_login.POLL_INTERVAL", 0.001), \
             patch("bilioshi.runtime.save_login") as save:
            worker = threading.Thread(target=self.api._qr_poll, args=(generation, session, cancel))
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                self.api.qr_cancel()
            finally:
                release.set()
                worker.join(4)
            save.assert_not_called()
        self.assertFalse(worker.is_alive())
        self.assertEqual(self.api._active, 0)

    def test_shutdown_waits_for_accepted_io_and_processes_ipc(self):
        host = WebHost(self.engine)
        host._window = Mock()
        send_command(self.root, "show")
        send_command(self.root, "login")
        host._read_commands()
        host._window.show.assert_called()
        self.assertEqual(host._queue.get_nowait(), ("open_login", {}))
        self.assertFalse(list((self.root / "commands").glob("*.json")))
        drained = threading.Event()
        def wait_io():
            drained.wait(3)
        host._api._wait_for_io = wait_io
        self.engine.close = Mock()
        host.quit()
        self.assertFalse(host._closed.wait(0.05))
        self.assertFalse(host._api.save_settings({"auto_like": False})["ok"])
        drained.set()
        self.assertTrue(host._closed.wait(3))
        host._shutdown_thread.join(3)
        self.engine.close.assert_called_once()
        host._window.destroy.assert_called_once()

    def test_diagnostic_bundle_and_client_error_endpoints(self):
        with patch("desktop.webui.api.logging.warning") as warn:
            res = self.api.report_client_error(["TypeError at app.js:12 SESSDATA=secret-1234567890"])
        self.assertEqual(res, {"ok": True, "count": 1})
        logged_text = str(warn.call_args.args)
        self.assertNotIn("secret-1234567890", logged_text)
        self.assertIn("[REDACTED]", logged_text)

        preview = self.api.diagnostic_preview()
        self.assertTrue(preview["ok"])
        self.assertIn("summary_markdown", preview)

        exported = self.api.export_diagnostic({"anonymize": True, "include_state": True})
        self.assertTrue(exported["ok"])
        self.assertTrue(Path(exported["zip_path"]).is_file())

    def test_initial_background_color_follows_windows_theme(self):
        with patch("desktop.webui.window.sys.platform", "linux"):
            self.assertEqual(_initial_background_color(), "#fcfcfb")

        fake_key = Mock()
        fake_key.__enter__ = Mock(return_value=fake_key)
        fake_key.__exit__ = Mock(return_value=False)
        with patch("desktop.webui.window.sys.platform", "win32"), \
             patch("winreg.OpenKey", return_value=fake_key), \
             patch("winreg.QueryValueEx", return_value=(0, 4)):
            self.assertEqual(_initial_background_color(), "#141716")
        with patch("desktop.webui.window.sys.platform", "win32"), \
             patch("winreg.OpenKey", return_value=fake_key), \
             patch("winreg.QueryValueEx", return_value=(1, 4)):
            self.assertEqual(_initial_background_color(), "#fcfcfb")

    def test_dark_and_system_theme_assets(self):
        html = (ASSETS / "index.html").read_text(encoding="utf-8")
        css = (ASSETS / "style.css").read_text(encoding="utf-8")
        theme_js = (ASSETS / "js/theme.js").read_text(encoding="utf-8")
        self.assertIn('<meta name="color-scheme" content="light dark">', html)
        self.assertIn("@media (prefers-color-scheme: dark)", css)
        self.assertIn('html[data-theme="dark"]', css)
        for key in ("system", "white", "paper", "mist", "apricot", "dark"):
            self.assertIn(key, theme_js)

    def test_safety_check_syncs_blocked_account_status_and_notifications(self):
        from bilioshi.accounts import AccountStore
        from bilioshi import safety
        from bilioshi.runtime import save_login

        store = AccountStore(self.root)
        created, _ = store.upsert(uid=99, name="风控测试账号", status="blocked")
        acc_root = store.account_root(created["id"])
        initialize(acc_root, [{"room": 7, "uid": 9, "name": "测试主播"}])
        save_login("synthetic-session-99", "synthetic-csrf-99", acc_root / "credentials.json")
        safety.bind_account("synthetic-session-99", 99, root=acc_root)
        safety.hold_account(
            "synthetic-session-99",
            "review",
            "请先完成平台安全验证后恢复",
            code=-352,
            operation={"room": "7", "kind": "danmaku"},
            root=acc_root,
        )

        engine = Engine(acc_root, job=Mock())
        host = SimpleNamespace(
            root=self.root,
            store=store,
            active_id=created["id"],
            view_id=created["id"],
            global_paused=False,
            active_engine=lambda: engine,
        )
        api = Api(host, self.ui)
        with patch.object(engine.application, "validate_credentials_profile", return_value=(True, "风控测试账号", {"uid": 99})), \
             patch("bilioshi.http._once", return_value={"code": 0, "data": {}}):
            result = api.check_safety(True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["passed"])
        self.assertTrue(result["resumed"])
        self.assertEqual(store.get(created["id"])["status"], "ok")

        with patch("desktop.webui.api.webbrowser.open", return_value=True) as open_url:
            link_res = api.open_safety_link("security", None)
        self.assertTrue(link_res["ok"])
        open_url.assert_called_once_with("https://account.bilibili.com/account/home")

        web_host = WebHost(self.engine)
        web_host._notify = Mock(return_value=True)
        web_host.emit = Mock()
        blocked_snap = {
            "active_account_id": created["id"],
            "account": "风控测试账号",
            "safety": {"blocked": True, "kind": "review", "code": -352, "since": 1000, "reason": "触发风控"},
        }
        web_host._notify_safety_events(blocked_snap)
        web_host._notify_safety_events(blocked_snap)
        self.assertEqual(web_host._notify.call_count, 1)
        self.assertEqual(web_host.emit.call_count, 1)
        self.assertEqual(web_host.emit.call_args.args[0], "toast")

        recovered_snap = {"active_account_id": created["id"], "account": "风控测试账号", "safety": {"blocked": False}}
        web_host._notify_safety_events(recovered_snap)
        self.assertEqual(web_host._notify.call_count, 2)
        self.assertEqual(web_host.emit.call_count, 2)


if __name__ == "__main__":
    unittest.main()
