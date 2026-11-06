import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from bilioshi.accounts import AccountStore, AccountStoreError
from bilioshi.runtime import save_login
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


class AccountStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = AccountStore(self.root)
        patcher = patch("bilioshi.runtime.seal", side_effect=fake_seal)
        patcher.start()
        self.addCleanup(patcher.stop)
        unpatcher = patch("bilioshi.runtime.unseal", side_effect=fake_unseal)
        unpatcher.start()
        self.addCleanup(unpatcher.stop)

    def make_account(self, uid=123, name="夜航星"):
        row, created = self.store.upsert(uid, name)
        self.store.ensure_root(row["id"], uid)
        self.store.save_credentials(row["id"], f"sess-{uid}", f"csrf-{uid}")
        return self.store.get(row["id"]), created

    def test_create_reload_and_no_decrypt_listing(self):
        row, created = self.make_account()
        self.assertTrue(created)
        self.assertEqual(row["id"], "uid-123")
        self.assertEqual(row["data_dir"], "accounts/uid-123")
        self.assertTrue(self.store.has_credentials(row["id"]))
        self.assertTrue(is_envelope(json.loads(self.store.credential_path(row["id"]).read_text())))

        reloaded = AccountStore(self.root)
        with patch(
            "bilioshi.runtime.unseal",
            side_effect=AssertionError("listing must not decrypt"),
        ):
            self.assertEqual(reloaded.accounts()[0]["name"], "夜航星")
            self.assertTrue(reloaded.has_credentials(row["id"]))
            self.assertEqual(
                reloaded.credential_token(row["id"]),
                reloaded.accounts()[0]["credential_token"],
            )

        same, created_again = self.store.upsert(123, "新名字")
        self.assertFalse(created_again)
        self.assertEqual(same["name"], "新名字")
        self.assertEqual(len(self.store.accounts()), 1)

    def test_clear_credentials_only_removes_its_fingerprint(self):
        row, _ = self.make_account()
        from bilioshi.runtime import session_fingerprint

        fingerprint = session_fingerprint("sess-123")
        bindings = self.store.account_root(row["id"]) / "state/account-bindings.json"
        bindings.write_text(json.dumps({fingerprint: "uid-123", "other": "uid-999"}))

        self.store.clear_credentials(row["id"])

        self.assertFalse(self.store.credential_path(row["id"]).exists())
        self.assertEqual(self.store.get(row["id"])["status"], "needs_login")
        self.assertEqual(json.loads(bindings.read_text()), {"other": "uid-999"})

    def test_remove_retains_quotas_and_restores_on_readd(self):
        row, _ = self.make_account()
        account_root = self.store.account_root(row["id"])
        (account_root / "members.json").write_text(json.dumps([{"name": "A", "uid": 1, "room": 2}]))
        (account_root / "settings.json").write_text(json.dumps({"run_mode": "aggressive"}))
        (account_root / "state/tasks/uid-123-2.json").write_text(json.dumps({"attempted": 2}))
        (account_root / "state/safety/uid-123.json").write_text(json.dumps({"hold": {}}))
        (account_root / "state/watch-credit-uid-123.json").write_text(json.dumps({"minutes": 9}))
        bindings = account_root / "state/account-bindings.json"
        bindings.write_text(json.dumps({"fingerprint": "uid-123"}))

        removed = self.store.remove(row["id"])

        self.assertEqual(removed["uid"], 123)
        self.assertEqual(self.store.accounts(), [])
        retained = self.root / "accounts/.retained/uid-123"
        self.assertTrue((retained / "members.json").exists())
        self.assertTrue((retained / "state/tasks/uid-123-2.json").exists())
        self.assertTrue((retained / "state/safety/uid-123.json").exists())
        self.assertTrue((retained / "state/watch-credit-uid-123.json").exists())
        self.assertTrue((retained / "state/account-bindings.json").exists())

        again, created = self.store.upsert(123, "夜航星")
        self.assertTrue(created)
        self.store.restore_retained(again["id"])
        restored = self.store.account_root(again["id"])
        self.assertEqual(
            json.loads((restored / "settings.json").read_text())["run_mode"],
            "aggressive",
        )
        self.assertTrue((restored / "state/tasks/uid-123-2.json").exists())
        self.assertFalse(retained.exists())

    def test_corrupt_registry_uses_backup_and_double_corruption_fails(self):
        self.make_account()
        self.store.set_global_paused(True)
        # The .bak is the previous valid version; write once more so the
        # backup contains the state we then recover.
        self.store.set_global_paused(True)
        self.assertTrue(self.store.backup_path.exists())
        self.store.path.write_text("{not json", encoding="utf-8")
        recovered = AccountStore(self.root)
        self.assertTrue(recovered.global_paused)
        self.assertEqual(len(recovered.accounts()), 1)

        self.store.backup_path.write_text("{also broken", encoding="utf-8")
        with self.assertRaises(AccountStoreError):
            AccountStore(self.root).load()


if __name__ == "__main__":
    unittest.main()
