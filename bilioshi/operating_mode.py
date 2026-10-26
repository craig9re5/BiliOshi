"""Shared scheduling profiles; desktop workers read changes without reconnecting."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from .runtime import data_dir, read_json


@dataclass(frozen=True)
class RunProfile:
    check_minutes: int
    like_recheck_seconds: int
    like_send_seconds: int
    danmaku_send_seconds: int
    watch_check_seconds: int
    read_retry_delays: tuple
    recovery_base_seconds: int


PROFILES = {
    "stable": RunProfile(5, 60, 30, 10, 600, (2, 4), 60),
    "aggressive": RunProfile(1, 20, 15, 6, 300, (1, 2), 30),
}
_OVERRIDE = ContextVar("operating_mode", default=None)


def profile_for(mode):
    if not isinstance(mode, str) or mode not in PROFILES:
        raise ValueError("运行模式应为 stable 或 aggressive")
    return PROFILES[mode]


def current_profile():
    mode = _OVERRIDE.get()
    if mode is None:
        try:
            settings = read_json(data_dir() / "settings.json", {})
            mode = settings.get("run_mode", "stable") if isinstance(settings, dict) else "stable"
            return profile_for(mode)
        except (OSError, ValueError):
            return PROFILES["stable"]
    return profile_for(mode)


@contextmanager
def use_mode(mode=None):
    if mode is not None:
        profile_for(mode)
    token = _OVERRIDE.set(mode)
    try:
        yield
    finally:
        _OVERRIDE.reset(token)
