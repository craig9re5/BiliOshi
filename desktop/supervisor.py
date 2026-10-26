"""Independent desktop guardian; pause policy remains owned by Engine/settings.

Only the desktop mutex owner calls register_desktop/request_run. Updaters can
hold begin_update's expiring lease and clear it with end_update after replacing
the executable. All process actions verify both image path and creation time.
"""

import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import time

from bilioshi.runtime import FileLock, read_json, update_json, write_json
from desktop.windows import Mutex, instance_name, process_identity, terminate_verified

POLL_SECONDS = 15
STARTUP_GRACE = 120
HEALTH_TIMEOUT = 90
STALE_CHECKS = 3
EXIT_GRACE = 30
MAX_BACKOFF = 900


def _read(path):
    value = read_json(path, {})
    if not isinstance(value, dict):
        raise ValueError(f"Invalid lifecycle record: {path.name}")
    return value


def app_command(*args):
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, str(Path(__file__).resolve().parents[1] / "tray_app.py"), *args]


def _spawn(root, *args):
    # Never use Engine.spawn: the guardian must remain outside its worker Job.
    return subprocess.Popen(
        app_command(*args), cwd=str(Path(sys.executable).parent), close_fds=True,
        env={**os.environ, "BILIOSHI_APP_DATA": str(root), "PYTHONIOENCODING": "utf-8",
             "PYINSTALLER_RESET_ENVIRONMENT": "1"},
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
    )


def request_run(root):
    """Record start intent independently of paused/exited status."""
    return update_json(root / "supervisor-desired.json", lambda state: {
        **(state or {}), "running": True, "updated": time.time(),
    }, {})


def request_stop(root):
    """Explicit user exit, including when only the guardian remains alive."""
    return update_json(root / "supervisor-desired.json", lambda state: {
        **(state or {}), "running": False, "updated": time.time(),
    }, {})


def register_desktop(root, *, tk=False, supervised=False):
    """Publish after taking the UI mutex; delayed recovery cannot undo user exit."""
    identity = process_identity(os.getpid())
    if identity is None:
        raise OSError("Cannot identify the desktop process")

    def register(state):
        if supervised and (state or {}).get("running") is not True:
            return state or {}
        write_json(root / "desktop-process.json", identity)
        return {**(state or {}), "running": True, "tk": bool(tk), "updated": time.time()}

    state = update_json(root / "supervisor-desired.json", register, {})
    return identity if state.get("running") is True else None


def ensure_supervisor(root):
    """Launch a separate singleton guardian without adding it to the worker Job."""
    mutex = Mutex(instance_name(root) + "-supervisor")
    try:
        if mutex.acquired:
            # The child acquires its own mutex after this short probe is released.
            mutex.close()
            _spawn(root, "--supervisor")
    finally:
        mutex.close()


def begin_update(root, *, seconds=600):
    """Ask the guardian to release its image; updater must relaunch in finally."""
    token = os.urandom(16).hex()
    seconds = max(30, min(1800, float(seconds)))
    write_json(root / "supervisor-update.json", {
        "token": token, "until": time.time() + seconds,
    })
    return token


def end_update(root, token):
    """Clear only the caller's handoff, leaving newer updater leases intact."""
    return update_json(root / "supervisor-update.json", lambda state:
        {} if state.get("token") == token else state, {})


def send_recovery_exit(root, identity):
    """Ask only this process generation to exit, preserving desired start intent."""
    write_json(root / "commands" / f"{time.time_ns()}.json", {
        "command": "exit", "created": time.time(), "supervisor_target": identity,
    })


def command_for_request(request):
    """Map guardian IPC to a separate exit path; never replay it into a new UI."""
    command = request.get("command")
    if command == "exit" and "supervisor_target" in request:
        target = request["supervisor_target"]
        if isinstance(target, dict) and target.get("pid") == os.getpid():
            if process_identity(os.getpid()) == target:
                return "supervisor_exit"
        return None
    return command


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


class Supervisor:
    """One nonblocking observation step per poll, with bounded restart attempts."""

    def __init__(self, root):
        self.root = root
        self.target = None
        self.observed_at = 0
        self.stale_checks = 0
        self.exit_requested = None
        self.next_start = 0
        self.failures = 0
        self.last_poll = -POLL_SECONDS
        self.child = None

    def _backoff(self, now):
        self.failures += 1
        self.next_start = now + min(MAX_BACKOFF, POLL_SECONDS * 2 ** min(self.failures - 1, 6))

    def _healthy(self, identity):
        health = _read(self.root / "monitor-health.json")
        # FILETIME creation is a generation identity, unlike PID alone. Engine's
        # started timestamp prevents an old health file from validating PID reuse.
        created = identity["created"] / 10_000_000 - 11_644_473_600
        wall = time.time()
        return (health.get("pid") == identity["pid"]
                and not health.get("publish_error")
                and all(_number(health.get(key)) for key in (
                    "started", "updated", "last_tick", "last_status_publish",
                ))
                and created - 1 <= health["started"] <= health["updated"]
                and all(0 <= wall - health[key] <= HEALTH_TIMEOUT for key in (
                    "updated", "last_tick", "last_status_publish",
                )))

    def step(self):
        """Return False on stop/update handoff; observation errors never kill."""
        desired = _read(self.root / "supervisor-desired.json")
        if desired.get("running") is not True:
            return False
        now = time.monotonic()
        update = _read(self.root / "supervisor-update.json")
        until = update.get("until", 0)
        if _number(until) and time.time() < until:
            # Release the installed image so an updater can replace it. The
            # updater clears its lease and relaunches in a finally block.
            return False
        if now - self.last_poll < POLL_SECONDS:
            return True
        self.last_poll = now
        if self.child is not None:
            if self.child.poll() is not None:
                self.child = None
        record = _read(self.root / "desktop-process.json")
        identity = None
        if (type(record.get("pid")) is int and type(record.get("created")) is int
                and record.get("executable") == os.path.normcase(os.path.realpath(sys.executable))):
            identity = process_identity(record["pid"])
        if not identity or identity != record:
            if self.target is not None:
                self._backoff(now)
                self.target = None
            self.stale_checks = 0
            self.exit_requested = None
            if now >= self.next_start:
                # Recheck intent/lease before every launch; the main mutex also
                # rejects duplicates if a user launch wins this race.
                if _read(self.root / "supervisor-desired.json").get("running") is not True:
                    return False
                lease = _read(self.root / "supervisor-update.json").get("until", 0)
                if _number(lease) and time.time() < lease:
                    return False
                self._backoff(now)
                if self.child is None:
                    logging.info("Guardian restarting desktop attempt=%s", self.failures)
                    self.child = _spawn(self.root, "--supervised", *(["--tk"] if desired.get("tk") else []))
                    self.next_start = max(self.next_start, now + STARTUP_GRACE)
            return True
        if identity != self.target:
            self.target = identity
            self.observed_at = now
            self.stale_checks = 0
            self.exit_requested = None
        if self.exit_requested is not None:
            if now - self.exit_requested >= EXIT_GRACE:
                # terminate_verified opens once, checks identity, then uses the
                # same handle to terminate; a reused PID cannot be killed.
                if terminate_verified(identity):
                    logging.warning("Guardian terminated unresponsive desktop pid=%s", identity["pid"])
                    self._backoff(now)
                    self.exit_requested = now
            return True
        if now - self.observed_at < STARTUP_GRACE:
            return True
        if self._healthy(identity):
            self.stale_checks = 0
            if now - self.observed_at >= 300:
                self.failures = 0
            return True
        self.stale_checks += 1
        if self.stale_checks >= STALE_CHECKS:
            logging.warning("Guardian requesting stalled desktop exit pid=%s", identity["pid"])
            send_recovery_exit(self.root, identity)
            self.exit_requested = now
        return True


def run(root, *, start=False):
    mutex = Mutex(instance_name(root) + "-supervisor")
    try:
        if start:
            request_run(root)
        if not mutex.acquired:
            return 0
        guardian = Supervisor(root)
        identity = process_identity(os.getpid())
        if identity is None:
            raise OSError("Cannot identify the guardian process")
        last_health = -POLL_SECONDS
        while True:
            try:
                if not guardian.step():
                    # Serialize the final decision/release with UI start intent.
                    # A quick exit followed by a new launch must not strand the
                    # new UI after ensure_supervisor saw our still-held mutex.
                    with FileLock(str(root / "supervisor-desired.json") + ".guard", timeout=5) as lock:
                        if not lock.acquired:
                            raise TimeoutError("Guardian intent lock unavailable")
                        desired = _read(root / "supervisor-desired.json")
                        until = _read(root / "supervisor-update.json").get("until", 0)
                        if (desired.get("running") is True
                                and not (_number(until) and time.time() < until)):
                            continue
                        write_json(root / "supervisor-health.json", {
                            **identity, "updated": time.time(), "exited": True,
                        })
                        mutex.close()
                        return 0
                if time.monotonic() - last_health >= POLL_SECONDS:
                    write_json(root / "supervisor-health.json", {
                        **identity, "updated": time.time(), "exited": False,
                        "desktop_pid": guardian.target["pid"] if guardian.target else None,
                        "stale_checks": guardian.stale_checks, "failures": guardian.failures,
                    })
                    last_health = time.monotonic()
            except (OSError, ValueError, TypeError, TimeoutError):
                logging.exception("Guardian observation failed; waiting before retry")
                guardian.last_poll = time.monotonic()
            # Control intent is cheap to observe once a second; process and
            # health inspection still run only every POLL_SECONDS.
            time.sleep(1)
    finally:
        mutex.close()
