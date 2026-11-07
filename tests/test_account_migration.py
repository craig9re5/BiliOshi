import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bilioshi.account_migration import ensure_account_store
from bilioshi.accounts import AccountStore
from bilioshi.runtime import read_json, save_login, session_fingerprint
from bilioshi.secret_store import FORMAT, is_envelope


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


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        patcher = patch("bilioshi.runtime.seal", side_effect=fake_seal)
        patcher.start()
        self.addCleanup(patcher.stop)
        unpatcher = patch("bilioshi.runtime.unseal", side_effect=fake_unseal)
        unpatcher.start()
        self.addCleanup(unpatcher.stop)

    def legacy(self, uid=123, name="夜航星"):
        self.root.joinpath("state/safety").mkdir(parents=True)
        self.root.joinpath("state/tasks").mkdir(parents=True)
        self.root.joinpath("logs").mkdir(parents=True)
        self.root.joinpath("members.json").write_text(json.dumps([
            {"name": "A", "uid": 1, "room": 2},
        ]))
        self.root.joinpath("settings.json").write_text(json.dumps({
            "run_mode": "aggressive",
            "autostart": True,
            "paused": True,
            "auto_like": True,
        }))
        save_login("sess-123", "csrf-123", self.root / "credentials.json")
        fingerprint = session_fingerprint("sess-123")
        self.root.joinpath("state/account-bindings.json").write_text(
            json.dumps({fingerprint: f"uid-{uid}"})
        )
        self.root.joinpath(f"state/safety/uid-{uid}.json").write_text(
            json.dumps({"hold": {}, "counts": {"2026-11-06:2:danmaku": 1}})
        )
        self.root.joinpath(f"state/tasks/uid-{uid}-2.json").write_text(
            json.dumps({"room": 2, "day": "2026-11-06", "attempted": 1})
        )
        self.root.joinpath(f"state/watch-credit-uid-{uid}.json").write_text(
            json.dumps({"minutes": 9})
        )
        self.root.joinpath("state/2.json").write_text(json.dumps({"account_key": ""}))
        self.root.joinpath("state/3.json").write_text(json.dumps({"account_key": "uid-999"}))
        self.root.joinpath("state/account-avatar.json").write_text(json.dumps({
            "uid": uid, "face": "https://i0.hdslb.com/bfs/face/a.jpg", "binding": "old",
        }))
        self.root.joinpath("status.json").write_text(json.dumps({"account": name}))
        self.root.joinpath("logs/activity.jsonl").write_text('{"type":"legacy"}\n')
        return fingerprint

    def test_migrates_one_account_and_preserves_legacy_root(self):
        self.legacy()
        credential_bytes = (self.root / "credentials.json").read_bytes()

        result = ensure_account_store(self.root, validator=lambda *_: self.fail("network used"))

        self.assertTrue(result.migrated)
        self.assertFalse(result.legacy_mode)
        store = AccountStore(self.root)
        rows = store.accounts()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "uid-123")
        self.assertEqual(store.active_id, "uid-123")
        self.assertEqual(store.view_id, "uid-123")

        account_root = store.account_root("uid-123")
        self.assertEqual(read_json(account_root / "credentials.json", {})["SESSDATA"], "sess-123")
        self.assertTrue(is_envelope(json.loads((account_root / "credentials.json").read_text())))
        self.assertEqual((self.root / "credentials.json").read_bytes(), credential_bytes)
        self.assertTrue(any((self.root / "state/backup").glob("legacy-credentials-*.json")))

        members = json.loads((account_root / "members.json").read_text())
        self.assertEqual(members[0]["name"], "A")
        settings = json.loads((account_root / "settings.json").read_text())
        self.assertEqual(settings["run_mode"], "aggressive")
        self.assertNotIn("autostart", settings)
        self.assertTrue(settings["paused"])

        self.assertTrue((account_root / "state/safety/uid-123.json").exists())
        self.assertTrue((account_root / "state/tasks/uid-123-2.json").exists())
        self.assertTrue((account_root / "state/watch-credit-uid-123.json").exists())
        self.assertTrue((account_root / "state/2.json").exists())
        self.assertFalse((account_root / "state/3.json").exists())
        self.assertTrue((account_root / "logs/legacy-activity.jsonl").exists())
        self.assertFalse((account_root / "logs/activity.jsonl").exists())
        self.assertTrue((account_root / "state/account-avatar.json").exists())
        self.assertEqual(
            json.loads((self.root / "settings.json").read_text())["autostart"],
            True,
        )

        again = ensure_account_store(self.root, validator=lambda *_: self.fail("network used"))
        self.assertFalse(again.migrated)
        self.assertEqual(len(AccountStore(self.root).accounts()), 1)

    def test_missing_registry_recovers_backup_without_replaying_legacy(self):
        self.legacy()
        first = ensure_account_store(self.root, validator=lambda *_: self.fail("network used"))
        store = first.store
        row, _ = store.upsert(456, "第二账号")
        store.ensure_root(row["id"], 456)
        save_login("sess-456", "csrf-456", store.credential_path(row["id"]))
        store.set_global_paused(True)
        store.set_global_paused(False)
        store.path.unlink()

        result = ensure_account_store(self.root, validator=lambda *_: self.fail("network used"))

        self.assertFalse(result.migrated)
        self.assertFalse(result.legacy_mode)
        self.assertEqual({row["id"] for row in result.store.accounts()}, {"uid-123", "uid-456"})

    def test_corrupt_members_do_not_seed_defaults(self):
        self.legacy()
        (self.root / "members.json").write_text("{broken")

        result = ensure_account_store(self.root, validator=lambda *_: self.fail("network used"))

        self.assertFalse(result.legacy_mode)
        account_root = AccountStore(self.root).account_root("uid-123")
        self.assertEqual(json.loads((account_root / "members.json").read_text()), [])

    def test_unknown_uid_without_network_stays_in_legacy_mode(self):
        self.legacy()
        (self.root / "state/account-bindings.json").unlink()
        (self.root / "state/account-avatar.json").unlink()
        (self.root / "status.json").unlink()
        (self.root / "credentials.json").unlink()
        save_login("sess-unknown", "csrf-unknown", self.root / "credentials.json")

        result = ensure_account_store(
            self.root,
            validator=lambda *_: (False, "network", {}),
        )

        self.assertTrue(result.legacy_mode)
        self.assertFalse(result.migrated)
        self.assertFalse((self.root / "state/accounts.json").exists())
        self.assertTrue((self.root / "credentials.json").exists())

    def test_rollback_restores_only_the_selected_account(self):
        self.legacy()
        ensure_account_store(self.root, validator=lambda *_: self.fail("network used"))
        from tools.restore_legacy_account import main

        status = main(["--account", "uid-123", "--root", str(self.root)])

        self.assertEqual(status, 0)
        self.assertEqual(read_json(self.root / "credentials.json", {})["SESSDATA"], "sess-123")
        self.assertTrue(any((self.root / "state/backup").glob("pre-rollback-credentials-*.json")))
        self.assertEqual(len(AccountStore(self.root).accounts()), 1)
        self.assertEqual(main(["--account", "uid-999", "--root", str(self.root)]), 2)

    def test_logged_out_legacy_root_becomes_empty_account_registry(self):
        save_login("", "", self.root / "credentials.json")

        result = ensure_account_store(self.root, validator=lambda *_: self.fail("network used"))

        self.assertTrue(result.migrated)
        self.assertFalse(result.legacy_mode)
        self.assertEqual(AccountStore(self.root).accounts(), [])


if __name__ == "__main__":
    unittest.main()
