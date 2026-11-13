"""One log layout for every process: readable activity, errors kept apart.

Each role writes its own text log (desktop, supervisor, probe, one per room) so
a restart never mixes two sessions, while every process shares a single
``errors.log`` that only receives WARNING and above. Rotated files are pruned so
the directory cannot grow without bound.
"""

import logging
import os
from pathlib import Path
import sys
import threading
import time

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows runtime
    msvcrt = None

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows runtime
    fcntl = None

from .redaction import SafeFormatter, SafeStream

FORMAT = "%(asctime)s %(levelname)s [%(log_ctx)s %(name)s:%(lineno)d] %(message)s"
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


def _context_label(root, role, worker=None):
    parts = [f"pid={os.getpid()}", f"role={role}"]
    if worker:
        parts.append(f"room={worker}")
    root_path = Path(root)
    if root_path.parent.name == "accounts" and root_path.name.startswith("uid-"):
        parts.append(root_path.name)
    return " ".join(parts)


class _ContextFilter(logging.Filter):
    def __init__(self, label):
        super().__init__()
        self.label = label

    def filter(self, record):
        if not getattr(record, "log_ctx", None):
            record.log_ctx = self.label
        return True


class _FileGuard:
    """Short-lived inter-process lock so errors.log rotation never holds Windows handles open."""

    def __init__(self, path, timeout=0.35):
        self.path = Path(path)
        self.timeout = timeout
        self._fp = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self.path.open("a+b")
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if msvcrt is not None:
                    self._fp.seek(0)
                    msvcrt.locking(self._fp.fileno(), msvcrt.LK_NBLCK, 1)
                elif fcntl is not None:  # pragma: no cover
                    fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    return self
                time.sleep(0.01)

    def __exit__(self, *_):
        if self._fp is None:
            return
        try:
            if msvcrt is not None:
                self._fp.seek(0)
                msvcrt.locking(self._fp.fileno(), msvcrt.LK_UNLCK, 1)
            elif fcntl is not None:  # pragma: no cover
                fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self._fp.close()
            self._fp = None


class _SharedErrorFileHandler(logging.Handler):
    """Append WARNING+ records without holding persistent open handles across processes."""

    def __init__(self, path, *, max_bytes=ERROR_LOG_BYTES, backups=ERROR_LOG_BACKUPS):
        super().__init__(level=logging.WARNING)
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.max_bytes = max_bytes
        self.backups = backups
        self._io_lock = threading.Lock()

    def _rollover_if_needed(self):
        try:
            if self.path.stat().st_size < self.max_bytes:
                return
        except OSError:
            return
        for index in range(self.backups - 1, 0, -1):
            src = Path(f"{self.path}.{index}")
            dst = Path(f"{self.path}.{index + 1}")
            if src.exists():
                try:
                    os.replace(src, dst)
                except OSError:
                    pass
        if self.backups > 0 and self.path.exists():
            try:
                os.replace(self.path, Path(f"{self.path}.1"))
            except OSError:
                pass

    def emit(self, record):
        try:
            line = self.format(record)
            with self._io_lock, _FileGuard(self.lock_path):
                self._rollover_if_needed()
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
        except OSError:
            pass


_PREV_EXCEPTHOOK = sys.excepthook
_PREV_THREAD_EXCEPTHOOK = getattr(threading, "excepthook", None)


def _install_excepthooks():
    def handle_exception(exc_type, exc_value, exc_tb):
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            _PREV_EXCEPTHOOK(exc_type, exc_value, exc_tb)
            return
        try:
            logging.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_tb))
            sys.stderr.flush()
        except Exception:
            _PREV_EXCEPTHOOK(exc_type, exc_value, exc_tb)

    def handle_thread_exception(args):
        if issubclass(args.exc_type, SystemExit):
            if _PREV_THREAD_EXCEPTHOOK is not None:
                _PREV_THREAD_EXCEPTHOOK(args)
            return
        try:
            name = getattr(args.thread, "name", "?")
            logging.critical(
                "Unhandled thread exception thread=%s",
                name,
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )
            sys.stderr.flush()
        except Exception:
            if _PREV_THREAD_EXCEPTHOOK is not None:
                _PREV_THREAD_EXCEPTHOOK(args)

    sys.excepthook = handle_exception
    if hasattr(threading, "excepthook"):
        threading.excepthook = handle_thread_exception


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
    ctx = _context_label(root, role, worker)
    stream = SafeStream(
        path.open("a", encoding="utf-8", buffering=1),
        line_prefix=lambda: f"{time.strftime('%Y-%m-%d %H:%M:%S')},000 [{ctx}] ",
    )
    sys.stdout = sys.stderr = stream
    handlers = [logging.StreamHandler(stream.raw())]
    try:
        errors = _SharedErrorFileHandler(
            logs / "errors.log",
            max_bytes=ERROR_LOG_BYTES,
            backups=ERROR_LOG_BACKUPS,
        )
        handlers.append(errors)
    except OSError:
        pass  # A full or locked disk must not stop the application from running.
    logging.basicConfig(
        force=True, level=level_value(level or os.environ.get("BILIOSHI_LOG_LEVEL")), handlers=handlers
    )
    ctx_filter = _ContextFilter(ctx)
    formatter = SafeFormatter(FORMAT)
    for handler in logging.getLogger().handlers:
        handler.addFilter(ctx_filter)
        handler.setFormatter(formatter)
    _install_excepthooks()
    return path
