import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop.engine import Engine
from desktop.storage import initialize


class EngineSuspensionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        initialize(self.root, [{"name": "A", "uid": 1, "room": 2}])
        self.job = Mock()
        self.engine = Engine(self.root, job=self.job, account_id="uid-1")
        self.engine.next_check = float("inf")

    def test_suspend_stops_spawning_and_activate_reuses_engine(self):
        self.engine.suspend()
        generation = self.engine.generation
        self.assertTrue(self.engine.suspended)
        self.assertFalse(self.job.close.called)

        with patch.object(self.engine, "spawn") as spawn:
            self.engine.tick()
            spawn.assert_not_called()

        self.engine.activate()
        self.assertFalse(self.engine.suspended)
        self.assertGreater(self.engine.generation, generation)
        self.assertEqual(self.engine.next_check, 0)

    def test_suspended_apply_probe_spawns_no_worker(self):
        self.engine.suspend()
        with patch.object(self.engine, "spawn") as spawn:
            self.engine._apply_probe({
                "statuses": {"2": {"live_status": 1}},
                "medals": {},
                "tasks": {},
            }, self.engine.last_check or 0)
            spawn.assert_not_called()
            self.assertEqual(self.engine.workers, {})

    def test_stale_probe_generation_is_discarded(self):
        self.engine.activate()
        self.engine.generation = 3
        self.engine.probe_generation = 2
        with patch.object(self.engine, "_apply_probe") as apply:
            self.engine.probe = Mock()
            self.engine.probe.poll.return_value = 1
            self.engine.probe_path = self.root / "state/probe-old.json"
            self.engine.probe_path.write_text("{}")
            self.engine.next_check = float("inf")
            self.engine.tick()
            apply.assert_not_called()


if __name__ == "__main__":
    unittest.main()
