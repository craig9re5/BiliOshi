import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from bilioshi.accounts import AccountStore
from bilioshi.qr_login import PollResult
from bilioshi.runtime import save_login
from bilioshi.secret_store import FORMAT
from desktop.host import AccountHost
from desktop.webui.api import Api


def fake_seal(value):
    if not value:
        return {}
    return {
        "format": FORMAT,
        "version": 1,
        "backend": "offline-test",
        "payload": base64.b64encode(json.dumps(value).encode()).decode(),
    }


def fake_unseal(value):
    return json.loads(base64.b64decode(value["payload"]))


class FakeEngine:
    def __init__(self, root, *, job=None, account_id=""):
        self.root = Path(root)
        self.account_id = account_id
        self.job = job
        self.suspended = False
        self.paused = False
        self.last_tick = time.time()
        self.last_status_publish = time.time()
        self._started = False

    def start(self):
        self._started = True

    def activate(self):
        self.suspended = False

    def suspend(self, reason="suspended"):
        self.suspended = True

    def close(self):
        pass

    def set_paused(self, paused):
        self.paused = bool(paused)

    def check_now(self):
        pass

    def snapshot(self, blocking=True):
        return {
            "account": "账号" + self.account_id[-1],
            "account_confirmed": True,
            "account_checked_at": time.time(),
            "paused": self.paused,
            "safety": {"blocked": False},
            "rows": [{
                "room": 2, "uid": 1, "name": "A", "live_status": 1,
                "active": True, "medal_name": "", "avatar_url": "",
            }],
            "checking": False,
            "error": "",
            "pid": 1,
            "updated": time.time(),
            "stale": False,
        }


class FakeUi:
    def __init__(self):
        self.pushes = 0
        self.applied = 0
        self.events = []

    def push_now(self):
        self.pushes += 1

    def apply_settings(self):
        self.applied += 1

    def emit(self, name, payload):
        self.events.append((name, payload))

    def renderer_ready(self):
        return True


class AccountWebUiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        patch("bilioshi.runtime.seal", side_effect=fake_seal).start()
        self.addCleanup(patch.stopall)
        patch("bilioshi.runtime.unseal", side_effect=fake_unseal).start()
        self.store = AccountStore(self.root)
        for uid in (1, 2):
            row, _ = self.store.upsert(uid, f"账号{uid}")
            self.store.ensure_root(row["id"], uid)
            save_login(f"sess-{uid}", f"csrf-{uid}", self.store.credential_path(row["id"]))
        self.store.set_active("uid-1")
        self.store.set_view("uid-1")
        self.host = AccountHost(
            self.root, self.store, engine_factory=FakeEngine, job_factory=lambda: object())
        self.host.start()
        self.addCleanup(self.host.close)
        self.ui = FakeUi()
        self.api = Api(self.host, self.ui)

    def test_snapshot_keeps_active_top_level_and_adds_inactive_view(self):
        view_root = self.store.account_root("uid-2")
        (view_root / "status.json").write_text(json.dumps({
            "account": "账号2", "updated": time.time(), "safety": {"blocked": False},
            "rows": [{"room": 2, "uid": 1, "name": "A", "live_status": 1}],
        }))
        self.api.set_view_account("uid-2")

        snap = self.api.snapshot()

        self.assertEqual(snap["schema"], 2)
        self.assertEqual(snap["active_account_id"], "uid-1")
        self.assertEqual(snap["view_account_id"], "uid-2")
        self.assertEqual(snap["account"], "账号1")
        self.assertEqual(len(snap["accounts"]), 2)
        self.assertTrue(snap["view"]["inactive"])
        self.assertEqual(snap["view"]["account_id"], "uid-2")
        self.assertIsNone(snap["view"]["rows"][0]["live_status"])
        self.assertTrue(snap["view"]["rows"][0]["status_stale"])

    def test_switch_endpoint_updates_active_and_clears_old_snapshot(self):
        self.api.snapshot()
        result = self.api.switch_account("uid-2")

        self.assertTrue(result["ok"])
        self.assertEqual(self.host.active_id, "uid-2")
        self.assertEqual(self.store.view_id, "uid-2")
        snap = self.api.snapshot()
        self.assertEqual(snap["active_account_id"], "uid-2")
        self.assertEqual(snap["account"], "账号2")
        self.assertNotIn("view", snap)

    def test_settings_are_written_to_the_viewed_account_root(self):
        self.api.set_view_account("uid-2")
        with patch("desktop.windows.set_autostart", return_value=True):
            result = self.api.save_settings({"auto_like": True, "autostart": True})

        self.assertTrue(result["ok"])
        second = json.loads((self.store.account_root("uid-2") / "settings.json").read_text())
        first = json.loads((self.store.account_root("uid-1") / "settings.json").read_text())
        self.assertTrue(second["auto_like"])
        self.assertFalse(first.get("auto_like", False))
        self.assertNotIn("autostart", second)

    def test_adding_an_account_does_not_steal_the_running_slot(self):
        account_id = self.api._complete_login(
            3, "新账号", {"uid": 3, "face": ""},
            {"SESSDATA": "sess-3", "bili_jct": "csrf-3"}, None, None)

        self.assertEqual(account_id, "uid-3")
        self.assertEqual(self.host.active_id, "uid-1")
        self.assertEqual(self.store.view_id, "uid-3")
        self.assertEqual(len(self.store.accounts()), 3)
        self.assertTrue(self.store.has_credentials("uid-3"))

    def test_qr_start_add_account_accepts_empty_target(self):
        session = Mock()
        session.generate.return_value = "https://example.invalid/qr"
        session.poll.return_value = PollResult("waiting")
        with patch("bilioshi.qr_login.QrLoginSession", return_value=session), \
                patch("desktop.webui.api._qr_data_uri", return_value="data:image/png;base64,AA"):
            result = self.api.qr_start("")
            self.api.qr_cancel()

        self.assertTrue(result["ok"])
        self.assertIsNone(result["account_id"])

    def test_inactive_view_blocks_active_account_operations(self):
        self.api.set_view_account("uid-2")
        with patch.object(FakeEngine, "check_now") as check:
            self.assertFalse(self.api.add_member("99")["ok"])
            self.assertFalse(self.api.check_now()["ok"])
            self.assertFalse(self.api.set_paused(True)["ok"])
            check.assert_not_called()
        self.assertFalse(self.host.engine_for("uid-1").paused)

    def test_all_accounts_view_can_check_the_running_account(self):
        self.api.set_view_account("all")
        with patch.object(FakeEngine, "check_now") as check:
            result = self.api.check_now()

        self.assertTrue(result["ok"])
        check.assert_called_once()

    def test_logout_preserves_platform_protection_status(self):
        self.store.update("uid-2", status="blocked")

        self.assertTrue(self.api.logout("uid-2")["ok"])
        self.assertEqual(self.store.get("uid-2")["status"], "blocked")

        self.api._complete_login(
            2, "账号2", {"uid": 2, "face": ""},
            {"SESSDATA": "sess-2b", "bili_jct": "csrf-2b"}, None, "uid-2")
        self.assertEqual(self.store.get("uid-2")["status"], "blocked")

    def test_logout_only_affects_target_account(self):
        result = self.api.logout("uid-2")

        self.assertTrue(result["ok"])
        self.assertEqual(self.store.get("uid-2")["status"], "needs_login")
        self.assertEqual(self.store.get("uid-1")["status"], "ok")
        self.assertTrue(self.store.has_credentials("uid-1"))
        self.assertFalse(self.store.has_credentials("uid-2"))


if __name__ == "__main__":
    unittest.main()
