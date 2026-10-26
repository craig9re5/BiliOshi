"""Focused contracts for hot profile selection and work between heartbeats."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from bilioshi.context import RuntimeContext, use_context
from bilioshi.operating_mode import current_profile, profile_for, use_mode
from bilioshi.runtime import write_json
from bilioshi.services.watch import HeartbeatChain, TaskSchedule


class OperatingModeTests(unittest.TestCase):
    def test_profiles_follow_saved_changes_and_cli_override_is_scoped(self):
        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            path = Path(folder) / "settings.json"
            self.assertEqual(current_profile(), profile_for("stable"))
            write_json(path, {"run_mode": "aggressive"})
            self.assertEqual(current_profile(), profile_for("aggressive"))
            with use_mode("stable"):
                self.assertEqual(current_profile().like_send_seconds, 30)
            self.assertEqual(current_profile().like_send_seconds, 15)
            with self.assertRaises(ValueError):
                profile_for("unknown")
            self.assertEqual((profile_for("stable").check_minutes,
                              profile_for("aggressive").check_minutes), (5, 1))

    def test_desktop_mode_change_keeps_existing_workers(self):
        from desktop.engine import Engine
        from desktop.storage import initialize

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [{"name": "test", "room": 1, "uid": 2}])
            engine = Engine(root, job=Mock())
            worker = Mock()
            engine.workers[1] = worker
            write_json(root / "settings.json", {**engine.config, "run_mode": "aggressive"})
            self.assertTrue(engine.reload_settings())
            self.assertEqual(engine.config["check_minutes"], 1)
            self.assertEqual(engine.next_check, 0)
            self.assertIs(engine.workers[1], worker)
            worker.terminate.assert_not_called()

    def test_aggressive_tasks_use_idle_windows_without_early_heartbeats(self):
        clock, checks, beats = [0.0], [], []
        gateway = Mock(HEARTBEAT_INTERVAL=60, DANMAKU_WORK_BUDGET=90,
                       DANMAKU_RECHECK_INTERVAL=600)
        gateway.task_day.return_value = "day"
        gateway.x25kn_heartbeat.side_effect = lambda *args: beats.append(clock[0]) or {"ok": True}
        gateway._wait_for_heartbeat_window.side_effect = lambda start, interval: clock.__setitem__(
            0, max(clock[0], start + interval))

        def check(**options):
            checks.append((clock[0], options))
            return {"success": True, "like": {"success": True, "done": False}}

        with use_mode("aggressive"), \
             patch("bilioshi.services.watch.time.monotonic", side_effect=lambda: clock[0]), \
             patch("bilioshi.services.watch.time.sleep",
                   side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)), \
             patch("bilioshi.services.watch.safety.status", return_value={"blocked": False}):
            chain = HeartbeatChain(1, 2, 3, 4, "device", "uuid", "fake", "csrf",
                                   {"secret_key": "key", "secret_rule": [1], "timestamp": 1},
                                   60, gateway)
            schedule = TaskSchedule(Mock(check=check), 1, gateway, enabled=True, likes=True)
            schedule.check(chain)
            chain.beat()
            schedule.check(chain)
            chain.beat()
        self.assertEqual(beats, [60, 120])
        self.assertEqual([stamp for stamp, _ in checks], [0, 20, 40, 60, 80, 100])
        self.assertTrue(all(options["like_batches"] == 1 for _, options in checks))
        self.assertTrue(all(options.get("likes_only") for _, options in checks[1:]))
        for stamp, options in checks:
            self.assertEqual(options["deadline"], (stamp // 60 + 1) * 60 - 15)


if __name__ == "__main__":
    unittest.main()
