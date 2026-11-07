import json
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import desktop.webui.api as api_module
from bilioshi.accounts import AccountStore
from bilioshi.growth import CHINA_TZ, record_samples
from desktop.webui.api import Api


class FakeEngine:
    def __init__(self, root, account_id):
        self.root = Path(root)
        self.account_id = account_id
        self.paused = False
        self.suspended = False
        self.account = "账号1"


class FakeLegacyEngine(FakeEngine):
    def __init__(self, root):
        super().__init__(root, "uid-legacy")
        self.account = "旧账号"


class FakeHost:
    def __init__(self, store):
        self.store = store
        self.root = store.root
        self.active_id = "uid-1"
        self.view_id = "uid-2"
        self.global_paused = False
        self.engines = {"uid-1": FakeEngine(store.account_root("uid-1"), "uid-1")}

    def active_engine(self):
        return self.engines.get(self.active_id)

    def account_summary(self, account_id):
        row = self.store.get(account_id)
        return {
            "name": row.get("name", ""),
            "running": account_id == self.active_id,
            "paused": False,
            "status": "ok",
        }


class FakeUi:
    def push_now(self):
        pass

    def apply_settings(self):
        pass


class GrowthApiTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = AccountStore(self.root)
        for uid in (1, 2):
            row, _ = self.store.upsert(uid, f"账号{uid}")
            self.store.ensure_root(row["id"], uid)
        members = [{"name": "A", "uid": 5, "room": 50}]
        (self.store.account_root("uid-2") / "members.json").write_text(
            json.dumps(members, ensure_ascii=False), encoding="utf-8",
        )
        now = time.time()
        record_samples(self.store.account_root("uid-2"), "uid-2", members,
                       {5: {"today_intimacy": 12}}, now, now=now)
        self.api = Api(FakeHost(self.store), FakeUi())

    def test_growth_reads_the_viewed_account(self):
        data = self.api.growth(7)
        self.assertTrue(data["available"])
        self.assertEqual(data["account_id"], "uid-2")
        self.assertEqual(data["account_name"], "账号2")
        self.assertFalse(data["running"])
        room = next(row for row in data["rooms"] if row["room"] == 50)
        self.assertEqual(room["cells"][-1]["value"], 12)
        self.assertTrue(data["coverage"][data["today"]]["partial"])

    def test_growth_can_target_another_account(self):
        data = self.api.growth(7, "uid-1")
        self.assertTrue(data["available"])
        self.assertEqual(data["account_id"], "uid-1")
        self.assertEqual(data["rooms"], [])

    def test_growth_rejects_unknown_account_and_bad_days(self):
        self.assertFalse(self.api.growth(7, "uid-999")["available"])
        self.assertFalse(self.api.growth(0)["available"])
        self.assertFalse(self.api.growth(91)["available"])

    def test_growth_cache_refreshes_after_file_change(self):
        first = self.api.growth(7)
        self.assertTrue(first["available"])
        members = [{"name": "A", "uid": 5, "room": 50}]
        now = time.time()
        record_samples(self.store.account_root("uid-2"), "uid-2", members,
                       {5: {"today_intimacy": 20}}, now, now=now)
        second = self.api.growth(7)
        room = next(row for row in second["rooms"] if row["room"] == 50)
        self.assertEqual(room["cells"][-1]["value"], 20)

    def test_growth_window_moves_at_midnight_without_new_samples(self):
        before = datetime(2026, 11, 7, 23, 50, tzinfo=CHINA_TZ).timestamp()
        after = before + 20 * 60
        with patch.object(api_module.time, "time", return_value=before):
            first = self.api.growth(7)
        with patch.object(api_module.time, "time", return_value=after):
            second = self.api.growth(7)
        self.assertEqual(first["today"], "2026-11-07")
        self.assertEqual(second["today"], "2026-11-08")
        self.assertEqual(second["days"][-1], "2026-11-08")
        self.assertNotEqual(first["days"][0], second["days"][0])

    def test_growth_works_without_account_store(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = Path(folder.name)
        members = [{"name": "旧主播", "uid": 8, "room": 80}]
        (root / "members.json").write_text(
            json.dumps(members, ensure_ascii=False), encoding="utf-8",
        )
        now = time.time()
        record_samples(root, "uid-legacy", members,
                       {8: {"today_intimacy": 7}}, now, now=now)
        api = Api(FakeLegacyEngine(root), FakeUi())
        data = api.growth(7)
        self.assertTrue(data["available"])
        self.assertEqual(data["account_id"], "uid-legacy")
        self.assertEqual(data["account_name"], "旧账号")
        self.assertTrue(data["running"])
        room = next(row for row in data["rooms"] if row["room"] == 80)
        self.assertEqual(room["cells"][-1]["value"], 7)

    def test_growth_survives_account_removal_and_readd(self):
        path = self.store.account_root("uid-2") / "state" / "growth.json"
        self.assertTrue(path.exists())
        self.store.remove("uid-2")
        self.assertFalse(path.exists())
        retained = (self.store.root / "accounts" / ".retained" / "uid-2"
                    / "state" / "growth.json")
        self.assertTrue(retained.exists())
        row, _ = self.store.upsert(2, "账号2")
        self.assertTrue(self.store.restore_retained(row["id"]))
        self.assertTrue(path.exists())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["account_id"], "uid-2")
        self.assertTrue(data["days"])


if __name__ == "__main__":
    unittest.main()
