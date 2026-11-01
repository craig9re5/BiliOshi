"""One log layout for every process: readable activity, errors kept apart.

Each role writes its own text log (desktop, supervisor, probe, one per room) so
a restart never mixes two sessions, while every process shares a single
``errors.log`` that only receives WARNING and above. Rotated files are pruned so
the directory cannot grow without bound.
"""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import sys
import time

from .redaction import SafeFormatter, SafeStream

FORMAT = "%(asctime)s %(levelname)s %(message)s"
ROLE_LOG_BYTES = 2_000_000
ERROR_LOG_BYTES = 1_000_000
ERROR_LOG_BACKUPS = 2
RETENTION_DAYS = 30
LEVELS = {"DEBUG": logging.DEBUG, "INFO": logging.INFO, "WARNING": logging.WARNING, "ERROR": logging.ERROR}

# Archives of the structured activity log and per-room text logs. Current role
# logs are refreshed on every start, so anything matching these patterns is
# safely less than a month old or worthless.
PRUNE_PATTERNS = ("room-*.log", "*.previous.log", "activity-*.jsonl")


def role_log(logs, role, worker=None):
    return Path(logs) / (f"room-{worker}.log" if worker else f"{role}.log")


def level_value(name):
    """Unknown names fall back to INFO instead of silently dropping records."""
    return LEVELS.get(str(name or "INFO").upper(), logging.INFO)


def rotate_startup(path, limit=ROLE_LOG_BYTES):
    """Keep one previous file per role so a restart keeps the last session."""
    try:
        if path.stat().st_size < limit:
            return False
    except OSError:
        return False
    try:
        os.replace(path, path.with_suffix(".previous.log"))
        return True
    except OSError:
        return False  # Another instance may still hold the previous file open.


def prune(directory, keep_days=RETENTION_DAYS, now=None):
    """Delete rotated files nobody will read; current role logs stay young."""
    directory = Path(directory)
    cutoff = (time.time() if now is None else now) - keep_days * 86400
    removed, seen = [], set()
    for pattern in PRUNE_PATTERNS:
        for path in directory.glob(pattern):
            if path in seen or not path.is_file():
                continue
            seen.add(path)
            try:
                if path.stat().st_mtime < cutoff:
                    path.unlink()
                    removed.append(path.name)
            except OSError:
                continue
    return removed


def setup(root, role, worker=None, level=None):
    """Redirect the process streams and logging to this role's log files.

    INFO goes to the role log, WARNING and above to both the role log and
    ``errors.log``; both are redacted by the shared formatter.
    """
    logs = Path(root) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    prune(logs)
    path = role_log(logs, role, worker)
    rotate_startup(path)
    stream = SafeStream(path.open("a", encoding="utf-8", buffering=1))
    sys.stdout = sys.stderr = stream
    handlers = [logging.StreamHandler(stream)]
    try:
        errors = RotatingFileHandler(
            logs / "errors.log",
            maxBytes=ERROR_LOG_BYTES,
            backupCount=ERROR_LOG_BACKUPS,
            encoding="utf-8",
        )
        errors.setLevel(logging.WARNING)
        handlers.append(errors)
    except OSError:
        pass  # A full or locked disk must not stop the application from running.
    logging.basicConfig(
        force=True, level=level_value(level or os.environ.get("BILIOSHI_LOG_LEVEL")), handlers=handlers
    )
    for handler in logging.getLogger().handlers:
        handler.setFormatter(SafeFormatter(FORMAT))
    return path
