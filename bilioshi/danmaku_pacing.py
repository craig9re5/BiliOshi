"""Coordinate danmaku sends from this machine's B 站 worker processes."""

import errno
import os
import random
import time
from pathlib import Path
from typing import Callable, TypeVar
from .runtime import data_dir
from .task_window import check_window, wait as task_wait

MIN_SEND_INTERVAL = 6.0
LOCK_WAIT_TIMEOUT = 45.0
_LOCK_FILE = data_dir() / "locks" / "danmaku-send.lock"
_Result = TypeVar("_Result")


def _try_lock(stream) -> bool:
    stream.seek(0)
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as exc:
        if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            raise
        return False


def _unlock(stream) -> None:
    stream.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def shared_lock_path(lock_dir: Path, name: str):
    """Return install-root shared lock path when running inside an account root."""
    account_root = Path(lock_dir).parent
    if (account_root / "account.json").is_file() and account_root.parent.name == "accounts":
        return account_root.parent.parent / "locks" / name
    return None


def _pace_on_file(
    sender: Callable[[], _Result],
    *,
    lock_path: Path,
    min_interval: float,
    jitter_ratio: float,
    deadline: float,
) -> _Result:
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)
    with lock_path.open("r+b") as stream:
        while not _try_lock(stream):
            check_window()
            if time.monotonic() >= deadline:
                raise TimeoutError("等待发送锁超时")
            task_wait(0.1)
        try:
            check_window()
            stream.seek(0)
            try:
                last_sent = float(stream.read(32).strip() or b"0")
            except ValueError:
                last_sent = 0.0
            elapsed = max(0.0, time.time() - last_sent)
            effective_interval = (
                min_interval * (1.0 + random.uniform(0.0, jitter_ratio))
                if jitter_ratio > 0 and last_sent > 0
                else min_interval
            )
            wait = max(0.0, effective_interval - elapsed)
            if wait > 0:
                task_wait(wait)
            check_window()
            stream.seek(0)
            stream.write(f"{time.time():.6f}".encode("ascii").ljust(32, b" "))
            stream.flush()
            return sender()
        finally:
            _unlock(stream)


def send_paced(
    sender: Callable[[], _Result],
    *,
    lock_path: Path = None,
    min_interval: float = MIN_SEND_INTERVAL,
    jitter_ratio: float = 0.0,
    lock_timeout: float = LOCK_WAIT_TIMEOUT,
    global_lock_path: Path = None,
    global_min_interval: float = 0.0,
    global_jitter_ratio: float = 0.0,
) -> _Result:
    """Serialize sends and reserve a minimum interval between attempts.

    The timestamp is written before sending so a failed request is paced too.
    When ``global_lock_path`` is set (multi-account install root), per-account
    pacing acquires first and install-root cross-account pacing second.
    """
    primary = (
        Path(lock_path) if lock_path is not None else data_dir() / "locks" / "danmaku-send.lock"
    )
    deadline = time.monotonic() + lock_timeout
    inner = sender
    if global_lock_path is not None and global_min_interval > 0:
        inner = lambda: _pace_on_file(
            sender,
            lock_path=Path(global_lock_path),
            min_interval=global_min_interval,
            jitter_ratio=global_jitter_ratio,
            deadline=deadline,
        )
    return _pace_on_file(
        inner,
        lock_path=primary,
        min_interval=min_interval,
        jitter_ratio=jitter_ratio,
        deadline=deadline,
    )
