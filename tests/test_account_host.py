import base64
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from bilioshi.accounts import AccountStore
from bilioshi.runtime import save_login
from bilioshi.secret_store import FORMAT
from desktop.host import AccountHost, HostError


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
        self.job = job
        self.account_id = account_id
        self.suspended = False
        self.paused = False
        self.last_tick = time.time()
        self.last_status_publish = time.time()
        self._started = False
        self.calls = []

    def start(self):
        self.calls.append("start")
        self._started = True

    def activate(self):
        self.calls.append("activate")
        self.suspended = False

    def suspend(self, reason="suspended"):
        self.calls.append("suspend:" + reason)
        self.suspended = True

    def close(self):
        self.calls.append("close")

    def set_paused(self, paused):
        self.calls.append("paused:" + str(bool(paused)))
        self.paused = bool(paused)

    def check_now(self):
        self.calls.append("check")


class AccountHostTests(unittest.TestCase):
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
            self.root,
            self.store,
            engine_factory=FakeEngine,
            job_factory=lambda: object(),
        )
        self.addCleanup(self.host.close)

    def test_switch_suspends_old_activates_target_and_updates_registry(self):
        self.host.start()
        old = self.host.engine_for("uid-1")
        target = self.host.switch_to("uid-2")

        self.assertEqual(target, "uid-2")
        self.assertIn("suspend:account_switch", old.calls)
        self.assertFalse(self.host.engine_for("uid-2").suspended)
        self.assertEqual(self.store.active_id, "uid-2")
        self.assertEqual(self.store.view_id, "uid-2")
        self.assertEqual(self.host.view_id, "uid-2")

    def test_global_pause_resumes_only_accounts_running_before_it(self):
        self.host.start()
        self.host.switch_to("uid-2")
        engine = self.host.engine_for("uid-2")

        self.host.set_global_paused(True)
        self.assertTrue(engine.suspended)
        self.assertTrue(self.store.global_paused)

        self.host.set_global_paused(False)
        self.assertFalse(engine.suspended)
        self.assertFalse(self.store.global_paused)

    def test_global_pause_does_not_suspend_an_individually_paused_engine(self):
        self.host.start()
        engine = self.host.engine_for("uid-1")
        engine.set_paused(True)

        self.host.set_global_paused(True)
        self.assertFalse(engine.suspended)

        self.host.set_global_paused(False)
        self.assertFalse(engine.suspended)
        self.assertTrue(engine.paused)

    def test_view_does_not_start_an_engine(self):
        self.host.start()
        self.host.view("uid-2")

        self.assertIsNone(self.host.engine_for("uid-2"))
        self.assertEqual(self.store.view_id, "uid-2")
        self.assertEqual(self.store.active_id, "uid-1")

    def test_health_is_written_by_the_host_root(self):
        self.host.start()
        self.host._publish_health()

        health = json.loads((self.root / "monitor-health.json").read_text())
        self.assertEqual(health["pid"], __import__("os").getpid())
        self.assertLess(abs(health["last_tick"] - time.time()), 2)

    def test_remove_active_does_not_start_the_other_account(self):
        self.host.start()
        self.host.remove_account("uid-1")

        self.assertIsNone(self.host.engine_for("uid-1"))
        self.assertIsNone(self.store.active_id)
        self.assertEqual([row["id"] for row in self.store.accounts()], ["uid-2"])

    def test_concurrent_watch_keeps_multiple_engines_running_and_isolates_faults(self):
        for uid in (3, 4):
            row, _ = self.store.upsert(uid, f"账号{uid}")
            self.store.ensure_root(row["id"], uid)
            save_login(f"sess-{uid}", f"csrf-{uid}", self.store.credential_path(row["id"]))

        self.host.start()
        self.host.set_account_running("uid-2", True)

        self.assertEqual(self.store.mode, "concurrent")
        self.assertTrue(self.store.get("uid-1")["watch_enabled"])
        self.assertTrue(self.store.get("uid-2")["watch_enabled"])
        self.assertFalse(self.host.engine_for("uid-1").suspended)
        self.assertFalse(self.host.engine_for("uid-2").suspended)

        # Switching view/focus in concurrent mode must not suspend background accounts.
        self.host.switch_to("uid-1")
        self.assertFalse(self.host.engine_for("uid-2").suspended)
        by_id = {item["id"]: item for item in self.host.summaries()}
        self.assertTrue(by_id["uid-1"]["running"])
        self.assertTrue(by_id["uid-2"]["running"])

        # Soft cap at 3 concurrent accounts.
        self.host.set_account_running("uid-3", True)
        with self.assertRaises(HostError):
            self.host.set_account_running("uid-4", True)

        # Global pause suspends all 3 running engines and resumes all 3.
        self.host.set_global_paused(True)
        for aid in ("uid-1", "uid-2", "uid-3"):
            self.assertTrue(self.host.engine_for(aid).suspended)
        self.host.set_global_paused(False)
        for aid in ("uid-1", "uid-2", "uid-3"):
            self.assertFalse(self.host.engine_for(aid).suspended)

        # Single-account platform hold (-352) isolates to uid-1 only.
        self.host.engine_for("uid-1").safety = {"blocked": True, "kind": "review", "scope": "account"}
        by_id = {item["id"]: item for item in self.host.summaries()}
        self.assertEqual(by_id["uid-1"]["state"], "protection")
        self.assertFalse(by_id["uid-1"]["running"])
        self.assertEqual(by_id["uid-2"]["state"], "running")
        self.assertTrue(by_id["uid-2"]["running"])

        # Stopping uid-3 closes its engine while uid-2 continues running.
        self.host.set_account_running("uid-3", False)
        self.assertIsNone(self.host.engine_for("uid-3"))
        self.assertFalse(self.store.get("uid-3")["watch_enabled"])
        self.assertTrue(self.host.account_summary("uid-2")["running"])


if __name__ == "__main__":
    unittest.main()
