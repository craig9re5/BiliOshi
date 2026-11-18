"""Shared scheduling profiles; desktop workers read changes without reconnecting."""

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
import threading
from .runtime import data_dir, file_stat_signature, read_json

_DEFAULT_READ_JSON = read_json
_PROFILE_CACHE = {}
_PROFILE_CACHE_LOCK = threading.Lock()


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
        path = data_dir() / "settings.json"
        if read_json is _DEFAULT_READ_JSON:
            sig = file_stat_signature(path)
            if sig is None:
                return PROFILES["stable"]
            key = str(path)
            with _PROFILE_CACHE_LOCK:
                cached = _PROFILE_CACHE.get(key)
                if cached is not None and cached[0] == sig:
                    return cached[1]
        try:
            settings = read_json(path, {})
            mode = settings.get("run_mode", "stable") if isinstance(settings, dict) else "stable"
            profile = profile_for(mode)
        except (OSError, ValueError):
            profile = PROFILES["stable"]
        if read_json is _DEFAULT_READ_JSON:
            with _PROFILE_CACHE_LOCK:
                if len(_PROFILE_CACHE) >= 64:
                    _PROFILE_CACHE.clear()
                _PROFILE_CACHE[str(path)] = (file_stat_signature(path), profile)
        return profile
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
