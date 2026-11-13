"""One-click diagnostic archive builder with strict credential and path scrubbing.

This module intentionally stays independent from ``desktop`` so CLI helpers,
headless diagnostics, and desktop UI bridges share identical redaction rules.
"""

from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import sys
import tempfile
import time
from urllib.parse import quote, unquote
import zipfile

from .accounts import ALL_ACCOUNTS, AccountStore, AccountStoreError
from .redaction import _SECRET_KEYS, redact, redact_paths
from .runtime import APP_VERSION
from .secret_store import is_envelope, unseal

DEFAULT_MAX_LOG_BYTES = 512_000
DEFAULT_MAX_ACTIVITY_LINES = 200
MAX_EXPORT_ARCHIVES = 10

_SENSITIVE_FILENAMES = {
    "credentials.json",
    "pushplus.credentials.json",
    "credential-migration.json",
    "notifications.sqlite3",
    ".cookies.json",
    ".env",
    "auth.json",
}
_SENSITIVE_JSON_KEYS = {
    "sessdata",
    "bili_jct",
    "cookie",
    "cookies",
    "set-cookie",
    "authorization",
    "qrcode_key",
    "qr_login_context",
    "live_like_cookie",
    "live_like_user_agent",
    "pushplus_token",
    "access_token",
    "refresh_token",
    "secret_key",
    "credential_token",
    "destination_key",
    "live_buvid",
}
_EXTRA_SECRET_KEYS = re.compile(
    r"^(?:SESSDATA|bili_jct|csrf(?:_token)?|refresh_token|access_token|"
    r"pushplus_token|qrcode_key|DedeUserID__ckMd5|LIVE_BUVID|buvid\w*|sid|w_rid)$",
    re.I,
)
_AVATAR_URL_RE = re.compile(r"https?://[^\s\"'<>]*?/bfs/face/[^\s\"'<>]+", re.I)
_KEYED_NUMBER_RE = re.compile(
    r"(\b(?:uid|room|room_id|anchor_id|anchor_uid)[=:\-\s]+)(\d{1,16})\b",
    re.I,
)


def _short_hash(kind, value):
    digest = hashlib.sha256(f"{kind}:{value}".encode("utf-8", errors="replace")).hexdigest()[:6].upper()
    return digest


def _is_sensitive_file(path):
    name = path.name.lower()
    return (
        name in _SENSITIVE_FILENAMES
        or name.startswith("notifications.sqlite3")
        or name.endswith(".lock")
        or path.suffix.lower() in {".pem", ".pfx", ".har", ".sqlite3", ".db"}
    )


def _read_json_safe(path, default=None):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, UnicodeError):
        return default
    return raw


def _collect_secret_values(root_dirs):
    """Gather exact token literals in-memory solely to strip any stray occurrence."""
    values = set()

    def walk(node):
        if isinstance(node, dict):
            for key, item in node.items():
                key_text = str(key)
                if (
                    _SECRET_KEYS.match(key_text)
                    or _EXTRA_SECRET_KEYS.match(key_text)
                    or key_text.lower() in _SENSITIVE_JSON_KEYS
                ) and isinstance(item, (str, int)):
                    text = str(item)
                    if len(text) >= 8:
                        values.add(text)
                        try:
                            dec = unquote(text)
                            if len(dec) >= 8:
                                values.add(dec)
                            enc = quote(dec, safe="")
                            if len(enc) >= 8:
                                values.add(enc)
                        except Exception:
                            pass
                elif isinstance(item, (dict, list)):
                    walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for folder in root_dirs:
        for filename in ("credentials.json", "pushplus.credentials.json"):
            candidate = Path(folder) / filename
            if not candidate.is_file():
                continue
            raw = _read_json_safe(candidate)
            if not raw:
                continue
            walk(raw)
            if is_envelope(raw):
                try:
                    walk(unseal(raw))
                except Exception:
                    pass
    return sorted(values, key=len, reverse=True)


class _Anonymizer:
    """Consistent pseudonym mapping for accounts, anchors, rooms, and titles."""

    def __init__(self, enabled=True):
        self.enabled = bool(enabled)
        self._account_ids = {}
        self._uids = {}
        self._rooms = {}
        self._names = {}

    def register_account(self, account_id=None, uid=None, name=None):
        if account_id:
            tag = f"uid-{_short_hash('uid', account_id)}"
            self._account_ids.setdefault(str(account_id), tag)
        if uid is not None and str(uid).isdigit():
            uid_s = str(uid)
            tag = _short_hash("uid", f"uid-{uid_s}")
            self._uids.setdefault(uid_s, f"U{tag}")
            self._account_ids.setdefault(f"uid-{uid_s}", f"uid-{tag}")
        if isinstance(name, str) and len(name.strip()) >= 2:
            clean = name.strip()
            tag = _short_hash("name", clean)
            self._names.setdefault(clean, f"账号#{tag}")

    def register_member(self, room=None, uid=None, name=None):
        if room is not None and str(room).isdigit():
            room_s = str(room)
            self._rooms.setdefault(room_s, f"R{_short_hash('room', room_s)}")
        if uid is not None and str(uid).isdigit():
            uid_s = str(uid)
            self._uids.setdefault(uid_s, f"U{_short_hash('uid', uid_s)}")
        if isinstance(name, str) and len(name.strip()) >= 2:
            clean = name.strip()
            self._names.setdefault(clean, f"主播#{_short_hash('member', clean)}")

    def alias_account_id(self, account_id):
        if not self.enabled or not account_id:
            return account_id
        text = str(account_id)
        return self._account_ids.get(text, f"uid-{_short_hash('uid', text)}")

    def alias_room(self, room):
        if not self.enabled or room is None:
            return room
        text = str(room)
        return self._rooms.get(text, f"R{_short_hash('room', text)}")

    def alias_uid(self, uid):
        if not self.enabled or uid is None:
            return uid
        text = str(uid)
        return self._uids.get(text, f"U{_short_hash('uid', text)}")

    def mask_path(self, rel_path):
        if not self.enabled:
            return rel_path
        text = str(rel_path).replace("\\", "/")
        for orig, alias in sorted(self._account_ids.items(), key=lambda kv: len(kv[0]), reverse=True):
            text = text.replace(orig, alias)
        for orig, alias in sorted(self._rooms.items(), key=lambda kv: len(kv[0]), reverse=True):
            text = re.sub(rf"(?i)\broom-{re.escape(orig)}\b", f"room-{alias}", text)
            text = re.sub(rf"(?i)\b{re.escape(orig)}\.json$", f"{alias}.json", text)
        return text

    def scrub_text(self, text):
        if not self.enabled or not isinstance(text, str) or not text:
            return text
        out = _AVATAR_URL_RE.sub("[AVATAR_URL]", text)
        for orig, alias in sorted(self._account_ids.items(), key=lambda kv: len(kv[0]), reverse=True):
            out = out.replace(orig, alias)
        for orig, alias in sorted(self._names.items(), key=lambda kv: len(kv[0]), reverse=True):
            out = out.replace(orig, alias)

        def replace_keyed(match):
            prefix, num = match.group(1), match.group(2)
            if "room" in prefix.lower():
                return prefix + self.alias_room(num)
            return prefix + self.alias_uid(num)

        out = _KEYED_NUMBER_RE.sub(replace_keyed, out)
        # Replace longer numeric IDs standalone without corrupting timestamps/codes.
        for orig, alias in sorted(self._rooms.items(), key=lambda kv: len(kv[0]), reverse=True):
            if len(orig) >= 4:
                out = re.sub(rf"(?<!\d){re.escape(orig)}(?!\d)", alias, out)
        for orig, alias in sorted(self._uids.items(), key=lambda kv: len(kv[0]), reverse=True):
            if len(orig) >= 4:
                out = re.sub(rf"(?<!\d){re.escape(orig)}(?!\d)", alias, out)
        return out

    def scrub_json(self, value, *, key_name=""):
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                key_l = str(key).lower()
                if key_l in _SENSITIVE_JSON_KEYS or _SECRET_KEYS.match(str(key)):
                    continue
                if self.enabled and key_l == "face":
                    cleaned[key] = "[AVATAR_URL]" if item else ""
                    continue
                if self.enabled and key_l in {"title", "account"} and isinstance(item, str):
                    cleaned[key] = self.scrub_text(item) if key_l == "account" else (
                        f"[TITLE#{_short_hash('title', item)}]" if item else ""
                    )
                    continue
                cleaned[key] = self.scrub_json(item, key_name=key_l)
            return cleaned
        if isinstance(value, list):
            return [self.scrub_json(item, key_name=key_name) for item in value]
        if not self.enabled:
            return value
        if key_name == "id" and isinstance(value, str) and value.startswith("uid-"):
            return self.alias_account_id(value)
        if key_name in {"uid", "anchor_uid", "active"}:
            if isinstance(value, str) and value.startswith("uid-"):
                return self.alias_account_id(value)
            if isinstance(value, int):
                return self.alias_uid(value)
        if key_name in {"room", "room_id"} and isinstance(value, (int, str)) and str(value).isdigit():
            return self.alias_room(value)
        if key_name == "name" and isinstance(value, str):
            return self._names.get(value.strip(), f"名称#{_short_hash('name', value)}")
        if key_name == "account_key" and isinstance(value, str) and len(value) >= 8:
            return f"key-{value[:8]}"
        if isinstance(value, str):
            return self.scrub_text(value)
        return value


def _scrub_line(text, secrets, anonymizer):
    for secret in secrets:
        text = text.replace(secret, "[REDACTED]")
    text = redact(text)
    text = redact_paths(text)
    text = anonymizer.scrub_text(text)
    return text


def _scrub_json_obj(value, secrets, anonymizer):
    def walk(node):
        if isinstance(node, dict):
            out = {}
            for key, item in node.items():
                if str(key).lower() in _SENSITIVE_JSON_KEYS or _SECRET_KEYS.match(str(key)):
                    continue
                out[key] = walk(item)
            return out
        if isinstance(node, list):
            return [walk(item) for item in node]
        if isinstance(node, str):
            for secret in secrets:
                node = node.replace(secret, "[REDACTED]")
            return redact_paths(redact(node))
        return node

    sanitized = walk(value)
    return anonymizer.scrub_json(sanitized)


def _read_tail_text(path, max_bytes):
    size = path.stat().st_size
    truncated = size > max_bytes
    with path.open("rb") as fp:
        if truncated:
            fp.seek(size - max_bytes)
            fp.readline()  # align cleanly to next newline
        raw = fp.read()
    text = raw.decode("utf-8", errors="replace")
    if truncated:
        text = f"[truncated to last ~{max_bytes} bytes of {size} bytes]\n" + text
    return text, size


def _discover_accounts(host_root, account_id=None, account_roots=None):
    host = Path(host_root)
    accounts = []
    registry = None
    try:
        registry = AccountStore(host).load()
    except AccountStoreError:
        registry = _read_json_safe(host / "state" / "accounts.json")
    rows = registry.get("accounts", []) if isinstance(registry, dict) else []
    selected_id = None if account_id in (None, "", ALL_ACCOUNTS) else str(account_id)

    for row in rows:
        aid = row.get("id")
        if not aid:
            continue
        if selected_id and aid != selected_id:
            continue
        acc_root = (
            Path(account_roots[aid])
            if account_roots and aid in account_roots
            else host / row.get("data_dir", f"accounts/{aid}")
        )
        accounts.append((row, acc_root))

    if not accounts and selected_id and account_roots and selected_id in account_roots:
        accounts.append(({"id": selected_id, "status": "unknown"}, Path(account_roots[selected_id])))
    return registry, accounts


def _build_anonymizer(host_root, registry, accounts, anonymize):
    anon = _Anonymizer(enabled=anonymize)
    if isinstance(registry, dict):
        for row in registry.get("accounts", []):
            anon.register_account(row.get("id"), row.get("uid"), row.get("name"))
    for row, acc_root in accounts:
        anon.register_account(row.get("id"), row.get("uid"), row.get("name"))
        members = _read_json_safe(Path(acc_root) / "members.json")
        if isinstance(members, list):
            for member in members:
                if isinstance(member, dict):
                    anon.register_member(member.get("room"), member.get("uid"), member.get("name"))
    legacy_members = _read_json_safe(Path(host_root) / "members.json")
    if isinstance(legacy_members, list):
        for member in legacy_members:
            if isinstance(member, dict):
                anon.register_member(member.get("room"), member.get("uid"), member.get("name"))
    return anon


def _recent_error_lines(log_sources, secrets, anonymizer, limit=120):
    merged = []
    for source_label, error_path in log_sources:
        if not error_path.is_file():
            continue
        try:
            text, _ = _read_tail_text(error_path, 128_000)
        except OSError:
            continue
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("[truncated"):
                continue
            merged.append(f"[{source_label}] {_scrub_line(line, secrets, anonymizer)}")
    return merged[-limit:]


def _recent_activity_failures(activity_sources, secrets, anonymizer, limit=15):
    events = []
    for source_label, act_path in activity_sources:
        if not act_path.is_file():
            continue
        try:
            lines = act_path.read_text(encoding="utf-8", errors="replace").splitlines()[-300:]
        except OSError:
            continue
        for raw in lines:
            raw = raw.strip()
            if not raw:
                continue
            try:
                item = json.loads(raw)
            except ValueError:
                continue
            event_type = str(item.get("type", ""))
            has_failure = (
                "error" in event_type
                or "fail" in event_type
                or "recovery" in event_type
                or "safety" in event_type
                or item.get("success") is False
                or (isinstance(item.get("code"), int) and item.get("code") != 0)
            )
            if has_failure:
                clean_item = _scrub_json_obj(item, secrets, anonymizer)
                clean_item["_source"] = source_label
                events.append(clean_item)
    return events[-limit:]


def _render_summary_markdown(host, env_info, account_summaries, recent_errors, recent_failures):
    summary_lines = [
        "# BiliOshi 诊断报告摘要",
        "",
        f"- **软件版本**: `{env_info['app_version']}`",
        f"- **导出时间**: `{env_info['exported_at']}`",
        f"- **系统环境**: `{env_info['platform']}` | Python `{env_info['python_version']}` | Frozen `{env_info['frozen']}` | UI `{env_info['ui_mode']}`",
        f"- **运行模式**: `{env_info['multi_account_mode']}` | 账号数 `{env_info['account_count']}` | 身份脱敏 `{env_info['anonymized']}`",
        "- **隐私声明**: 已剔除登录凭证（`credentials.json`）、通知 Token（`pushplus.credentials.json`）、Cookie、CSRF 与本地用户名路径。",
        "",
        "## 账号状态概览",
    ]
    if account_summaries:
        for item in account_summaries:
            summary_lines.append(
                f"- `{item.get('id')}`: status=`{item.get('status')}`, "
                f"watch_enabled=`{item.get('watch_enabled')}`, has_credentials=`{item.get('has_credentials')}`"
            )
    else:
        cred_legacy = (host / "credentials.json").is_file()
        summary_lines.append(f"- 单账号/未配置多账号目录 (`has_credentials={cred_legacy}`)")

    summary_lines.extend(["", "## 最近告警与错误 (errors.log 节选)"])
    if recent_errors:
        summary_lines.append("```text")
        summary_lines.extend(recent_errors[-25:])
        summary_lines.append("```")
    else:
        summary_lines.append("- 最近 `errors.log` 中无 WARNING/ERROR 记录。")

    summary_lines.extend(["", "## 最近异常活动事件 (activity.jsonl)"])
    if recent_failures:
        summary_lines.append("```json")
        for evt in recent_failures[-10:]:
            summary_lines.append(json.dumps(evt, ensure_ascii=False))
        summary_lines.append("```")
    else:
        summary_lines.append("- 最近活动记录中无失败事件。")
    return "\n".join(summary_lines) + "\n"


def _prepare_context(host_root, *, account_id=None, account_roots=None, anonymize=True, ui_mode="unknown"):
    host = Path(host_root)
    registry, accounts = _discover_accounts(host, account_id=account_id, account_roots=account_roots)
    anon = _build_anonymizer(host, registry, accounts, anonymize)
    secrets = _collect_secret_values([host] + [acc_root for _, acc_root in accounts])

    account_summaries = [
        _scrub_json_obj(
            {
                "id": row.get("id"),
                "name": row.get("name"),
                "status": row.get("status", "unknown"),
                "watch_enabled": bool(row.get("watch_enabled", False)),
                "has_credentials": (Path(acc_root) / "credentials.json").is_file(),
                "last_used_at": row.get("last_used_at", 0),
                "last_checked_at": row.get("last_checked_at", 0),
            },
            secrets,
            anon,
        )
        for row, acc_root in accounts
    ]
    env_info = {
        "app_version": APP_VERSION,
        "exported_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "exported_epoch": int(time.time()),
        "ui_mode": ui_mode,
        "anonymized": bool(anonymize),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "frozen": bool(getattr(sys, "frozen", False)),
        "multi_account_mode": (registry or {}).get("mode", "legacy" if not accounts else "single"),
        "global_paused": bool((registry or {}).get("global_paused", False)),
        "active_account": anon.alias_account_id((registry or {}).get("active")),
        "account_count": len(account_summaries),
        "accounts": account_summaries,
        "excluded_files": sorted(_SENSITIVE_FILENAMES),
    }

    error_sources = [("host", host / "logs" / "errors.log")]
    activity_sources = [("host", host / "logs" / "activity.jsonl")]
    for row, acc_root in accounts:
        label = anon.alias_account_id(row.get("id"))
        error_sources.append((label, Path(acc_root) / "logs" / "errors.log"))
        activity_sources.append((label, Path(acc_root) / "logs" / "activity.jsonl"))

    recent_errors = _recent_error_lines(error_sources, secrets, anon)
    recent_failures = _recent_activity_failures(activity_sources, secrets, anon)
    summary_markdown = _render_summary_markdown(host, env_info, account_summaries, recent_errors, recent_failures)

    return {
        "host": host,
        "registry": registry,
        "accounts": accounts,
        "anonymizer": anon,
        "secrets": secrets,
        "environment": env_info,
        "recent_errors": recent_errors,
        "recent_failures": recent_failures,
        "summary_markdown": summary_markdown,
    }


def collect_diagnostic_preview(
    host_root, *, account_id=None, account_roots=None, anonymize=True, ui_mode="unknown"
):
    """Return lightweight redacted environment & recent errors for UI display."""
    ctx = _prepare_context(
        host_root,
        account_id=account_id,
        account_roots=account_roots,
        anonymize=anonymize,
        ui_mode=ui_mode,
    )
    exports_dir = Path(host_root) / "exports"
    return {
        "ok": True,
        "environment": ctx["environment"],
        "recent_errors": ctx["recent_errors"][-20:],
        "recent_error_count": len(ctx["recent_errors"]),
        "recent_failures": ctx["recent_failures"][-5:],
        "summary_markdown": ctx["summary_markdown"],
        "exports_dir": str(exports_dir),
    }


def _collect_root_entries(base_dir, prefix, *, include_state, max_log_bytes, max_activity_lines):
    base = Path(base_dir)
    entries = []

    logs_dir = base / "logs"
    if logs_dir.is_dir():
        for item in sorted(logs_dir.iterdir()):
            if not item.is_file() or _is_sensitive_file(item):
                continue
            if item.name == "activity.jsonl":
                entries.append(("jsonl_tail", f"{prefix}/logs/{item.name}", item))
            elif item.suffix.lower() == ".log" or ".log." in item.name.lower():
                entries.append(("log_tail", f"{prefix}/logs/{item.name}", item))

    for name in ("monitor-health.json", "supervisor-health.json", "diagnostic.json"):
        path = base / name
        if path.is_file() and not _is_sensitive_file(path):
            entries.append(("json", f"{prefix}/{name}", path))

    if include_state:
        for name in ("settings.json", "members.json"):
            path = base / name
            if path.is_file():
                entries.append(("json", f"{prefix}/{name}", path))
        state_dir = base / "state"
        if state_dir.is_dir():
            for path in sorted(state_dir.iterdir()):
                if path.is_file() and path.suffix.lower() == ".json" and not _is_sensitive_file(path):
                    if path.name.startswith("accounts"):
                        continue
                    entries.append(("json", f"{prefix}/state/{path.name}", path))
            tasks_dir = state_dir / "tasks"
            if tasks_dir.is_dir():
                for path in sorted(tasks_dir.glob("*.json")):
                    if path.is_file():
                        entries.append(("json", f"{prefix}/state/tasks/{path.name}", path))
    return entries


def _prune_old_exports(exports_dir, keep=MAX_EXPORT_ARCHIVES):
    archives = sorted(
        (p for p in Path(exports_dir).glob("bilioshi-diagnostic-*.zip") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in archives[keep:]:
        try:
            stale.unlink(missing_ok=True)
        except OSError:
            pass


def _render_entry_payload(kind, src_path, secrets, anon, max_log_bytes, max_activity_lines):
    if kind == "log_tail":
        text, _ = _read_tail_text(src_path, max_log_bytes)
        return _scrub_line(text, secrets, anon), None
    if kind == "jsonl_tail":
        raw_lines = src_path.read_text(encoding="utf-8", errors="replace").splitlines()
        out_lines = []
        for line in raw_lines[-max_activity_lines:]:
            cleaned = line.strip()
            if not cleaned:
                continue
            try:
                out_lines.append(json.dumps(_scrub_json_obj(json.loads(cleaned), secrets, anon), ensure_ascii=False))
            except ValueError:
                out_lines.append(_scrub_line(cleaned, secrets, anon))
        return "\n".join(out_lines) + ("\n" if out_lines else ""), None
    parsed = _read_json_safe(src_path)
    if parsed is None:
        return None, "unreadable_json"
    return json.dumps(_scrub_json_obj(parsed, secrets, anon), ensure_ascii=False, indent=2), None


def export_diagnostic_bundle(
    host_root,
    *,
    account_id=None,
    account_roots=None,
    output_dir=None,
    anonymize=True,
    include_state=True,
    ui_mode="unknown",
    max_log_bytes=DEFAULT_MAX_LOG_BYTES,
    max_activity_lines=DEFAULT_MAX_ACTIVITY_LINES,
):
    """Build an atomic, credential-free ZIP bundle containing logs, state, and summary."""
    ctx = _prepare_context(
        host_root, account_id=account_id, account_roots=account_roots, anonymize=anonymize, ui_mode=ui_mode
    )
    host, anon, secrets = ctx["host"], ctx["anonymizer"], ctx["secrets"]
    exports_dir = Path(output_dir) if output_dir else host / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    candidates = _collect_root_entries(
        host, "host", include_state=include_state, max_log_bytes=max_log_bytes, max_activity_lines=max_activity_lines
    )
    registry_path = host / "state" / "accounts.json"
    if registry_path.is_file():
        candidates.append(("json", "host/state/accounts.json", registry_path))
    for row, acc_root in ctx["accounts"]:
        candidates.extend(
            _collect_root_entries(
                acc_root, f"accounts/{row.get('id', 'unknown')}",
                include_state=include_state, max_log_bytes=max_log_bytes, max_activity_lines=max_activity_lines,
            )
        )

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"bilioshi-diagnostic-{stamp}.zip"
    target = exports_dir / filename
    if target.exists():
        filename = f"bilioshi-diagnostic-{stamp}-{int(time.time() * 1000) % 1000:03d}.zip"
        target = exports_dir / filename

    included, skipped = [], []
    fd, tmp_name = tempfile.mkstemp(prefix=".diag-", suffix=".zip", dir=str(exports_dir))
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("environment.json", json.dumps(ctx["environment"], ensure_ascii=False, indent=2))
            included.append("environment.json")
            archive.writestr("summary.md", ctx["summary_markdown"])
            included.append("summary.md")
            if ctx["recent_errors"]:
                archive.writestr("recent_errors.txt", "\n".join(ctx["recent_errors"]) + "\n")
                included.append("recent_errors.txt")

            seen = set(included)
            for kind, raw_arcname, src_path in candidates:
                arcname = anon.mask_path(raw_arcname)
                if arcname in seen:
                    continue
                try:
                    payload, skip_reason = _render_entry_payload(
                        kind, src_path, secrets, anon, max_log_bytes, max_activity_lines
                    )
                    if skip_reason:
                        skipped.append({"path": arcname, "reason": skip_reason})
                        continue
                    archive.writestr(arcname, payload)
                    seen.add(arcname)
                    included.append(arcname)
                except OSError as exc:
                    skipped.append({"path": arcname, "reason": type(exc).__name__})

            manifest = {
                "included_count": len(included) + 1,
                "included": included + ["manifest.json"],
                "skipped": skipped,
                "excluded_notice": sorted(_SENSITIVE_FILENAMES),
            }
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        os.replace(tmp_path, target)
    finally:
        tmp_path.unlink(missing_ok=True)

    _prune_old_exports(exports_dir)
    return {
        "ok": True,
        "zip_path": str(target),
        "exports_dir": str(exports_dir),
        "filename": filename,
        "size_bytes": target.stat().st_size,
        "included_files": included + ["manifest.json"],
        "skipped": skipped,
        "anonymized": bool(anonymize),
        "summary_markdown": ctx["summary_markdown"],
        "recent_errors": ctx["recent_errors"][-20:],
    }
