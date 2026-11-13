"""Remove credentials from logs, diagnostics and exception messages."""

import logging
from pathlib import Path
import re
import threading
from urllib.parse import quote, unquote

_SECRET_KEYS = re.compile(
    r"^(cookie|set-cookie|authorization|sessdata|bili_jct|csrf(?:_token)?|"
    r"qrcode_key|refresh_token|access_token|pushplus_token|secret_key|qr_login_context|live_like_cookie|"
    r"sid|live_buvid|buvid\w*|w_rid|DedeUserID__ckMd5)$",
    re.I,
)
_ASSIGNMENT = re.compile(
    r"(?i)((?:SESSDATA|bili_jct|csrf(?:_token)?|qrcode_key|refresh_token|access_token|"
    r"sid|live_buvid|buvid\w*|pushplus_token|secret_key|w_rid|DedeUserID__ckMd5)"
    r"(?:\"|'|%22|%27)?\s*(?:[:=]|%3D|%3A)\s*(?:\"|'|%22|%27)?)"
    r"(?:(?!%26|%22|%27)[^\s;&\"'<>])+"
)
_LOG_PREFIX = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}")
_WIN_HOME = re.compile(
    r"[A-Za-z]:(?:\\\\|\\|/)(?:Users|Documents and Settings)(?:\\\\|\\|/)[^\\/\r\n\"'<>|]+",
    re.I,
)
_POSIX_HOME = re.compile(r"/(?:home|Users)/[A-Za-z0-9_.\-]+")
_known = set()
_lock = threading.Lock()


def _secret_variants(item):
    variants = {item}
    try:
        decoded = unquote(item)
        if decoded and decoded != item and len(decoded) >= 12:
            variants.add(decoded)
        encoded = quote(item, safe="")
        if encoded and encoded != item and len(encoded) >= 12:
            variants.add(encoded)
    except Exception:
        pass
    return variants


def register_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEYS.match(key_text) or key_text.lower().startswith(("buvid", "live_buvid")) or key == "sid":
                if isinstance(item, str) and len(item) >= 12:
                    variants = _secret_variants(item)
                    with _lock:
                        _known.update(variants)
            if isinstance(item, (dict, list, tuple)):
                register_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            register_secrets(item)


def forget_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if (_SECRET_KEYS.match(key_text) or key_text.lower().startswith(("buvid", "live_buvid")) or key == "sid") and isinstance(item, str):
                variants = _secret_variants(item)
                with _lock:
                    for variant in variants:
                        _known.discard(variant)
            elif isinstance(item, (dict, list, tuple)):
                forget_secrets(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            forget_secrets(item)


def redact(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if _SECRET_KEYS.match(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if not isinstance(value, str):
        return value
    with _lock:
        secrets = sorted(_known, key=len, reverse=True)
    for secret in secrets:
        value = value.replace(secret, "[REDACTED]")
    value = re.sub(
        r"(?im)((?:set-cookie|cookie|authorization)\s*:\s*)[^\r\n]+", r"\1[REDACTED]", value
    )
    return _ASSIGNMENT.sub(r"\1[REDACTED]", value)


def redact_paths(value):
    """Mask OS user home directory names before sharing logs or diagnostics."""
    if isinstance(value, dict):
        return {key: redact_paths(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_paths(item) for item in value]
    if not isinstance(value, str):
        return value
    try:
        home = str(Path.home())
        if home and len(home) > 3:
            replacement = "%USERPROFILE%" if ":" in home else "~"
            for variant in (home, home.replace("\\", "\\\\"), home.replace("\\", "/")):
                if variant in value:
                    value = value.replace(variant, replacement)
    except OSError:
        pass
    value = _WIN_HOME.sub("%USERPROFILE%", value)
    return _POSIX_HOME.sub("~", value)


class _RedactingWriter:
    def __init__(self, parent):
        self.parent = parent

    def write(self, value):
        return self.parent._write_with(value, add_prefix=False)

    def flush(self):
        return self.parent.flush()

    def close(self):
        return self.parent.close()


class SafeStream:
    """Buffer by line so split writes cannot reveal a credential."""

    def __init__(self, stream, *, line_prefix=None):
        self.stream, self.pending = stream, ""
        self.line_prefix = line_prefix
        self.lock = threading.Lock()

    def raw(self):
        return _RedactingWriter(self)

    def _format_line(self, line, add_prefix):
        cleaned = redact(line)
        if (
            add_prefix
            and self.line_prefix is not None
            and cleaned
            and not cleaned.startswith((" ", "\t"))
            and not _LOG_PREFIX.match(cleaned)
        ):
            cleaned = f"{self.line_prefix()}{cleaned}"
        return cleaned

    def _write_with(self, value, *, add_prefix):
        with self.lock:
            self.pending += value
            while "\n" in self.pending:
                line, self.pending = self.pending.split("\n", 1)
                self.stream.write(self._format_line(line, add_prefix) + "\n")
        return len(value)

    def write(self, value):
        return self._write_with(value, add_prefix=True)

    def flush(self):
        with self.lock:
            if self.pending:
                self.stream.write(self._format_line(self.pending, add_prefix=True))
                self.pending = ""
            self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


class SafeFormatter(logging.Formatter):
    def format(self, record):
        if not hasattr(record, "log_ctx"):
            record.log_ctx = "-"
        return redact(super().format(record))
