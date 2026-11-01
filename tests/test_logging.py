"""Log layout: readable per-role logs, errors apart, activity rotation."""

import json
import logging
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from bilioshi import daily_summary, logging_setup, runtime
from bilioshi.redaction import SafeStream, forget_secrets, register_secrets


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


if __name__ == "__main__":
    unittest.main()
