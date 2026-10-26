"""Guardian decisions only: temporary lifecycle files, no processes/tasks/accounts."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from desktop import supervisor
from bilioshi.runtime import read_json, write_json


class SupervisorTests(unittest.TestCase):
    def test_health_requires_consecutive_misses_and_termination_rechecks_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            identity = {"pid": 123, "created": 116444736000000000, "executable": "test.exe"}
            supervisor.request_run(root)
            write_json(root / "desktop-process.json", identity)
            # exited is just a projection: desired-running remains authoritative.
            write_json(root / "status.json", {"exited": True})
            guardian = supervisor.Supervisor(root)
            with patch.object(supervisor.os.path, "realpath", return_value="test.exe"), \
                 patch.object(supervisor.os.path, "normcase", side_effect=lambda value: value), \
                 patch.object(supervisor, "process_identity", return_value=identity), \
                 patch.object(supervisor.time, "monotonic", return_value=0) as clock, \
                 patch.object(supervisor, "_spawn") as spawn, \
                 patch.object(supervisor, "send_recovery_exit") as graceful, \
                 patch.object(supervisor, "terminate_verified", return_value=True) as terminate:
                self.assertTrue(guardian.step())
                with patch.object(supervisor.time, "time", return_value=1000):
                    health = {"pid": 123, "started": 10, "updated": 1000,
                              "last_tick": 1000, "last_status_publish": 1000, "publish_error": ""}
                    write_json(root / "monitor-health.json", health)
                    self.assertTrue(guardian._healthy(identity))
                    write_json(root / "monitor-health.json", {**health, "last_status_publish": 800})
                    self.assertFalse(guardian._healthy(identity))
                    write_json(root / "monitor-health.json", {**health, "publish_error": "PermissionError"})
                    self.assertFalse(guardian._healthy(identity))
                for moment in (120, 135):
                    clock.return_value = moment
                    guardian.step()
                graceful.assert_not_called()
                clock.return_value = 150
                guardian.step()
                graceful.assert_called_once_with(root, identity)
                clock.return_value = 165
                guardian.step()
                terminate.assert_not_called()
                clock.return_value = 180
                guardian.step()
                terminate.assert_called_once_with(identity)
                spawn.assert_not_called()

            # A reused PID must not be killed even if the saved target is stale.
            from desktop.windows import terminate_verified
            kernel = Mock()
            kernel.OpenProcess.return_value = 10
            with patch("desktop.windows._process_kernel", return_value=kernel), \
                 patch("desktop.windows._identity_from_handle", return_value={**identity, "created": 1}):
                self.assertFalse(terminate_verified(identity))
                kernel.TerminateProcess.assert_not_called()
                kernel.CloseHandle.assert_called_once_with(10)

    def test_handoff_and_stop_override_saved_exit_and_pending_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            write_json(root / "settings.json", {"paused": True})
            write_json(root / "status.json", {"exited": True})
            supervisor.request_run(root)
            guardian = supervisor.Supervisor(root)
            with patch.object(supervisor.time, "monotonic", return_value=100) as clock, \
                 patch.object(supervisor, "_spawn", return_value=Mock()) as spawn:
                token = supervisor.begin_update(root)
                self.assertFalse(guardian.step())
                self.assertTrue(read_json(root / "supervisor-desired.json")["running"])
                spawn.assert_not_called()
                supervisor.end_update(root, "other-updater")
                self.assertEqual(read_json(root / "supervisor-update.json")["token"], token)
                supervisor.end_update(root, token)
                self.assertTrue(guardian.step())
                spawn.assert_called_once_with(root, "--supervised")
                clock.return_value = 115
                guardian.step()
                self.assertEqual(spawn.call_count, 1)
                supervisor.request_stop(root)
                self.assertFalse(guardian.step())
                identity = {"pid": 1, "created": 2, "executable": "test.exe"}
                with patch.object(supervisor, "process_identity", return_value=identity):
                    self.assertIsNone(supervisor.register_desktop(root, supervised=True))
                self.assertTrue(read_json(root / "settings.json")["paused"])
                self.assertFalse(read_json(root / "supervisor-desired.json")["running"])
                # An old generation's recovery command cannot exit a new UI.
                with patch.object(supervisor.os, "getpid", return_value=1), \
                     patch.object(supervisor, "process_identity", return_value={**identity, "created": 3}):
                    self.assertIsNone(supervisor.command_for_request({
                        "command": "exit", "supervisor_target": identity,
                    }))


if __name__ == "__main__":
    unittest.main()
