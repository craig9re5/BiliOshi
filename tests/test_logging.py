"""Log layout: readable per-role logs, errors apart, activity rotation."""

import json
import logging
import os
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from bilioshi import daily_summary, logging_setup, runtime
from bilioshi.accounts import AccountStore
from bilioshi.diagnostics_bundle import export_diagnostic_bundle
from bilioshi.redaction import SafeStream, forget_secrets, redact, redact_paths, register_secrets


class LoggingSetupTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.saved = (sys.stdout, sys.stderr)
        self.addCleanup(self.restore)

    def restore(self):
        for stream in {sys.stdout, sys.stderr}:
            if isinstance(stream, SafeStream):
                try:
                    stream.flush()
                    stream.stream.close()
                except (OSError, ValueError):
                    pass
        sys.stdout, sys.stderr = self.saved
        root = logging.getLogger()
        for handler in list(root.handlers):
            handler.close()
            root.removeHandler(handler)
        root.setLevel(logging.WARNING)

    def flush(self):
        for handler in logging.getLogger().handlers:
            handler.flush()

    def test_role_log_names_are_separate(self):
        logs = self.root / "logs"
        self.assertEqual(logging_setup.role_log(logs, "desktop").name, "desktop.log")
        self.assertEqual(logging_setup.role_log(logs, "supervisor").name, "supervisor.log")
        self.assertEqual(logging_setup.role_log(logs, "worker", worker=456).name, "room-456.log")

    def test_errors_log_only_gets_warnings(self):
        path = logging_setup.setup(self.root, "desktop")
        logging.info("routine cycle finished")
        logging.warning("worker could not start")
        self.flush()
        text = path.read_text(encoding="utf-8")
        self.assertIn("routine cycle finished", text)
        self.assertIn("worker could not start", text)
        errors = (self.root / "logs" / "errors.log").read_text(encoding="utf-8")
        self.assertIn("worker could not start", errors)
        self.assertNotIn("routine cycle finished", errors)

    def test_worker_log_is_named_after_the_room(self):
        path = logging_setup.setup(self.root, "worker", worker=456)
        self.assertEqual(path.name, "room-456.log")
        logging.info("heartbeat ok")
        self.flush()
        self.assertIn("heartbeat ok", path.read_text(encoding="utf-8"))

    def test_credentials_never_reach_log_files(self):
        secret = "sess-" + "a" * 24
        register_secrets({"SESSDATA": secret})
        self.addCleanup(forget_secrets, {"SESSDATA": secret})
        path = logging_setup.setup(self.root, "desktop")
        logging.info("cookie SESSDATA=%s", secret)
        logging.error("raw value %s", secret)
        self.flush()
        for file in (path, self.root / "logs" / "errors.log"):
            text = file.read_text(encoding="utf-8")
            self.assertNotIn(secret, text)
            self.assertIn("[REDACTED]", text)

    def test_restart_keeps_one_previous_role_log(self):
        logs = self.root / "logs"
        logs.mkdir()
        path = logs / "desktop.log"
        path.write_text("x" * 10, encoding="utf-8")
        self.assertTrue(logging_setup.rotate_startup(path, limit=5))
        self.assertTrue((logs / "desktop.previous.log").exists())
        self.assertFalse(logging_setup.rotate_startup(path, limit=5))

    def test_prune_removes_stale_files_and_keeps_fresh_ones(self):
        logs = self.root / "logs"
        logs.mkdir()
        stale_room = logs / "room-1.log"
        fresh_room = logs / "room-2.log"
        stale_archive = logs / "activity-20251201-000000.jsonl"
        current = logs / "activity.jsonl"
        for path in (stale_room, fresh_room, stale_archive, current):
            path.write_text("{}\n", encoding="utf-8")
        old = time.time() - 40 * 86400
        for path in (stale_room, stale_archive):
            os.utime(path, (old, old))
        removed = logging_setup.prune(logs, keep_days=30)
        self.assertIn("room-1.log", removed)
        self.assertIn(stale_archive.name, removed)
        self.assertTrue(fresh_room.exists())
        self.assertTrue(current.exists())


class ActivityRotationTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.path = self.root / "logs" / "activity.jsonl"
        self.path.parent.mkdir(parents=True)

    def test_large_activity_log_rolls_into_a_timestamped_segment(self):
        self.path.write_text(json.dumps({"type": "old", "ts": int(time.time())}) + "\n", encoding="utf-8")
        with patch.object(runtime, "ACTIVITY_ROTATE_BYTES", 1):
            runtime.append_event(self.path, {"type": "new"})
        archives = runtime.activity_archives(self.path)
        self.assertEqual(len(archives), 1)
        self.assertIn('"old"', archives[0].read_text(encoding="utf-8"))
        rows = [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(rows[-1]["type"], "new")

    def test_small_activity_log_stays_in_place(self):
        self.path.write_text(json.dumps({"type": "old", "ts": int(time.time())}) + "\n", encoding="utf-8")
        runtime.append_event(self.path, {"type": "new"})
        self.assertEqual(runtime.activity_archives(self.path), [])
        self.assertEqual(len(self.path.read_text(encoding="utf-8").splitlines()), 2)

    def test_summary_reads_rotated_segments(self):
        now = int(time.time())
        archive = self.path.parent / "activity-20260101-000000.jsonl"
        archive.write_text(
            json.dumps({"type": "check", "live": [], "offline": ["A"], "unknown": [], "ts": now - 60}) + "\n",
            encoding="utf-8",
        )
        self.path.write_text(
            json.dumps({"type": "check", "live": [], "offline": ["A"], "unknown": [], "ts": now - 30}) + "\n",
            encoding="utf-8",
        )
        with patch.object(daily_summary, "_LOG_FILE", self.path):
            rows = daily_summary.load_recent(24)
        self.assertEqual(len(rows), 2)

    def test_segments_older_than_the_window_are_skipped(self):
        archive = self.path.parent / "activity-20250101-000000.jsonl"
        archive.write_text(
            json.dumps({"type": "check", "live": [], "offline": [], "unknown": [], "ts": int(time.time())}) + "\n",
            encoding="utf-8",
        )
        old = time.time() - 3 * 86400
        os.utime(archive, (old, old))
        with patch.object(daily_summary, "_LOG_FILE", self.path):
            self.assertEqual(daily_summary.load_recent(24), [])


class DiagnosticsAndContextTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.saved = (sys.stdout, sys.stderr, sys.excepthook)
        self.addCleanup(self.restore)

    def restore(self):
        for stream in {sys.stdout, sys.stderr}:
            if isinstance(stream, SafeStream):
                try:
                    stream.flush()
                    stream.stream.close()
                except OSError:
                    pass
        sys.stdout, sys.stderr, sys.excepthook = self.saved
        logging.basicConfig(force=True, handlers=[])

    def test_worker_context_timestamps_stdout_and_captures_live_buvid_and_encoded_secrets(self):
        acc_root = self.root / "accounts" / "uid-12345"
        path = logging_setup.setup(acc_root, "worker", worker=67890)
        print("raw heartbeat stdout line")
        logging.warning(
            "query failed LIVE_BUVID=buv-secret-987654 url=%s",
            "https://example.invalid/?SESSDATA%3Dsess-secret-987654%26a=1",
        )
        sys.stdout.flush()

        text = path.read_text(encoding="utf-8")
        self.assertIn("role=worker", text)
        self.assertIn("room=67890", text)
        self.assertIn("uid-12345", text)
        self.assertRegex(text, r"(?m)^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} \[.*raw heartbeat stdout line$")
        self.assertNotIn("buv-secret-987654", text)
        self.assertNotIn("sess-secret-987654", text)
        self.assertIn("[REDACTED]", text)
        self.assertIn("%26a=1", text)  # did not swallow subsequent non-secret query params

        err_log = (acc_root / "logs" / "errors.log").read_text(encoding="utf-8")
        self.assertIn("LIVE_BUVID=[REDACTED]", err_log)

        win_sample = "C:" + os.sep + "Users" + os.sep + "sampleowner" + os.sep + "AppData"
        posix_sample = "/" + "home" + "/" + "sampleowner" + "/logs"
        self.assertEqual(redact_paths(win_sample), "%USERPROFILE%" + os.sep + "AppData")
        self.assertEqual(redact_paths(posix_sample), "~/logs")
        self.assertIn("[REDACTED]", redact("Cookie: SESSDATA=tok1234567890ab; LIVE_BUVID=lb1234567890ab"))

    def test_export_diagnostic_bundle_excludes_secrets_and_anonymizes_multi_account(self):
        store = AccountStore(self.root)
        row, _ = store.upsert(987654, "私密昵称")
        aid = row["id"]
        acc_root = store.ensure_root(aid, 987654)
        (self.root / "logs").mkdir(parents=True, exist_ok=True)
        (acc_root / "logs").mkdir(parents=True, exist_ok=True)
        secret_val = "sec-" + "998877665544"
        push_val = "push-" + "aabbccddeeff"
        (acc_root / "credentials.json").write_text(
            json.dumps({"SESSDATA": secret_val, "bili_jct": "csrf-secret-value"}), encoding="utf-8"
        )
        (acc_root / "pushplus.credentials.json").write_text(
            json.dumps({"pushplus_token": push_val}), encoding="utf-8"
        )
        (acc_root / "notifications.sqlite3").write_bytes(b"sqlite-private")
        (acc_root / "members.json").write_text(
            json.dumps([{"name": "测试主播甲", "room": 555666, "uid": 777888}]), encoding="utf-8"
        )
        win_path = "C:" + os.sep + "Users" + os.sep + "localowner" + os.sep + "run.log"
        (self.root / "logs" / "errors.log").write_text(
            f"2026-11-13 10:00:00 ERROR host path={win_path} token={secret_val}\n", encoding="utf-8"
        )
        (acc_root / "logs" / "room-555666.log").write_text(
            "2026-11-13 10:01:00 INFO connecting room=555666 name=测试主播甲 account=私密昵称\n",
            encoding="utf-8",
        )
        (acc_root / "logs" / "activity.jsonl").write_text(
            json.dumps({"type": "watch_end", "room_id": 555666, "success": False, "ts": 100}) + "\n",
            encoding="utf-8",
        )

        exported = export_diagnostic_bundle(self.root, anonymize=True, include_state=True, ui_mode="cli")
        self.assertTrue(exported["ok"])
        zip_path = Path(exported["zip_path"])
        self.assertTrue(zip_path.is_file())
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
            self.assertFalse(any("credentials.json" in n or "notifications.sqlite3" in n for n in names))
            self.assertIn("environment.json", names)
            self.assertIn("summary.md", names)
            self.assertIn("manifest.json", names)
            self.assertTrue(any(n.startswith("host/logs/errors.log") for n in names))
            self.assertFalse(any("uid-987654" in n or "555666" in n for n in names))
            corpus = "\n".join(zf.read(n).decode("utf-8", errors="replace") for n in names)
            self.assertNotIn(secret_val, corpus)
            self.assertNotIn(push_val, corpus)
            self.assertNotIn("localowner", corpus)
            self.assertNotIn("私密昵称", corpus)
            self.assertNotIn("测试主播甲", corpus)
            self.assertNotIn("987654", corpus)
            self.assertNotIn("555666", corpus)


if __name__ == "__main__":
    unittest.main()
