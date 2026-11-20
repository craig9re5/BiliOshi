"""A cooperative deadline shared by task IO, pacing and settlement waits."""

from contextlib import contextmanager
from contextvars import ContextVar
import time

_WINDOW = ContextVar("task_window", default=None)

# Leave enough socket budget inside a cooperative task window so tail-end
# requests defer cleanly instead of timing out mid-flight (especially writes,
# where a client-side read timeout leaves server state uncertain).
MIN_READ_WINDOW = 2.0
MIN_WRITE_WINDOW = 5.0


class TaskDeferred(RuntimeError):
    """No new request was started because its task window has ended."""


@contextmanager
def task_window(deadline):
    previous = _WINDOW.get()
    if previous is not None and previous[0] is not None:
        deadline = previous[0] if deadline is None else min(previous[0], deadline)
    token = _WINDOW.set((deadline, previous[1] if previous is not None else {}))
    try:
        yield
    finally:
        _WINDOW.reset(token)


def remaining():
    window = _WINDOW.get()
    return None if window is None or window[0] is None else max(0, window[0] - time.monotonic())


def check_window(required=0):
    left = remaining()
    if left is not None and left <= required:
        raise TaskDeferred("本轮任务时间不足，等待下次检查")


def require_window(minimum):
    """Defer when remaining window time is strictly less than ``minimum``."""
    check_window()
    left = remaining()
    if left is not None and minimum > 0 and left < minimum:
        raise TaskDeferred("本轮任务时间不足，等待下次检查")


def request_timeout(timeout, *, minimum=0):
    check_window()
    left = remaining()
    if left is None:
        return timeout
    required = min(timeout, minimum) if minimum > 0 else 0
    if required > 0 and left < required:
        raise TaskDeferred("本轮任务时间不足，等待下次检查")
    return min(timeout, left)


def wait(seconds):
    check_window(seconds)
    time.sleep(seconds)
    check_window()


def read_cache():
    window = _WINDOW.get()
    return None if window is None else window[1]
