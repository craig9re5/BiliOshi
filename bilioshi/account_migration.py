"""Fail-closed migration from the legacy single-root account layout.

The old install root is never moved or deleted. Its credential envelope is
backed up, the first account is re-sealed into ``accounts/uid-<mid>/`` and a
registry is written only after the account files can be read back.
"""

import json
import logging
import re
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from .accounts import AccountStore, _account_id
from . import safety
from .members import validate_members
from .runtime import (
    read_json,
    save_login,
    session_fingerprint,
    write_json,
)
from .secret_store import is_envelope


_ROOM_STATE = re.compile(r"^[0-9]+\.json$")


@dataclass
class MigrationResult:
    store: AccountStore
    migrated: bool
    legacy_mode: bool
    account_id: str = ""
    reason: str = ""

    @property
    def has_accounts(self):
        return bool(self.store.accounts())


def validate_credentials_readonly(sessdata, bili_jct):
    """Validate a login in a throwaway root so safety cannot touch a real account."""
    from .application import AppContext

    with tempfile.TemporaryDirectory(prefix="bilioshi-verify-") as folder:
        context = AppContext(Path(folder))
        return context.validate_credentials_profile(sessdata, bili_jct)


def _cached_uid(credentials, legacy_root):
    """Recover the UID without a network call when the old state already knows it."""
    if not isinstance(credentials, dict):
        return 0
    # The QR context belongs to the current SESSDATA; a stale top-level
    # DedeUserID can survive a re-login and must not win over it.
    context = credentials.get("qr_login_context")
    cookies = context.get("cookies") if isinstance(context, dict) else None
    value = cookies.get("DedeUserID") if isinstance(cookies, dict) else None
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
        return int(value)
    for key in ("DedeUserID", "dedeuserid", "uid", "mid"):
        value = credentials.get(key)
        if isinstance(value, str) and value.isascii() and value.isdigit():
            return int(value)
        if type(value) is int and value > 0:
            return value

    candidates = set()
    try:
        bindings = read_json(legacy_root / "state/account-bindings.json", {})
        if isinstance(bindings, dict):
            for value in bindings.values():
                if isinstance(value, str) and value.startswith("uid-") and value[4:].isdigit():
                    candidates.add(int(value[4:]))
    except (OSError, ValueError):
        pass
    try:
        profile = read_json(legacy_root / "state/account-avatar.json", {})
        if isinstance(profile, dict) and type(profile.get("uid")) is int:
            candidates.add(profile["uid"])
    except (OSError, ValueError):
        pass
    if len(candidates) == 1:
        return next(iter(candidates))
    return 0


def _cached_profile(legacy_root):
    profile = {}
    try:
        avatar = read_json(legacy_root / "state/account-avatar.json", {})
        if isinstance(avatar, dict):
            profile["face"] = avatar.get("face", "") if isinstance(avatar.get("face"), str) else ""
    except (OSError, ValueError):
        pass
    try:
        status = read_json(legacy_root / "status.json", {})
        if isinstance(status, dict):
            name = status.get("account")
            if isinstance(name, str) and name.strip():
                profile["name"] = name.strip()
    except (OSError, ValueError):
        pass
    return profile


def _backup_credentials(root, path):
    backup_dir = root / "state" / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"legacy-credentials-{stamp}.json"
    counter = 1
    while target.exists():
        target = backup_dir / f"legacy-credentials-{stamp}-{counter}.json"
        counter += 1
    target.write_bytes(path.read_bytes())
    return target


def _safe_members(path):
    try:
        members = read_json(path, [])
        return validate_members(members)
    except (OSError, ValueError, TypeError):
        logging.warning("Legacy members file is unreadable; migrating an empty list")
        return []


def _safe_settings(path):
    try:
        settings = read_json(path, {})
        return dict(settings) if isinstance(settings, dict) else {}
    except (OSError, ValueError):
        logging.warning("Legacy settings file is unreadable; using defaults")
        return {}


def _copy_file(source, destination):
    if not source.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(source), str(destination))


def _copy_account_state(legacy_root, account_root, account_id, fingerprint):
    source_state = legacy_root / "state"
    destination = account_root / "state"
    uid_key = account_id

    for source in (source_state / "tasks").glob(f"{uid_key}-*.json"):
        _copy_file(source, destination / "tasks" / source.name)
    for name in (f"{uid_key}.json", f"{fingerprint}.json"):
        source = source_state / "safety" / name
        _copy_file(source, destination / "safety" / name)
    _copy_file(
        source_state / f"watch-credit-{uid_key}.json",
        destination / f"watch-credit-{uid_key}.json",
    )

    bindings = source_state / "account-bindings.json"
    if bindings.exists():
        try:
            values = read_json(bindings, {})
        except (OSError, ValueError):
            values = {}
        if isinstance(values, dict):
            kept = {
                key: value
                for key, value in values.items()
                if value == uid_key or key == fingerprint
            }
            if kept:
                write_json(destination / "account-bindings.json", kept)

    room_files = source_state.iterdir() if source_state.exists() else ()
    for room_file in room_files:
        if not _ROOM_STATE.match(room_file.name):
            continue
        try:
            value = read_json(room_file, {})
        except (OSError, ValueError):
            continue
        if not isinstance(value, dict):
            continue
        key = value.get("account_key")
        if key and key != uid_key:
            continue
        _copy_file(room_file, destination / room_file.name)

    activity = legacy_root / "logs" / "activity.jsonl"
    if activity.exists():
        # Do not mix old history into the new account log. Keep it clearly named.
        _copy_file(activity, account_root / "logs" / "legacy-activity.jsonl")


def _copy_avatar_profile(legacy_root, account_root, uid, token):
    try:
        profile = read_json(legacy_root / "state/account-avatar.json", {})
    except (OSError, ValueError):
        profile = {}
    if not isinstance(profile, dict) or profile.get("uid") != uid:
        return
    face = profile.get("face", "")
    write_json(
        account_root / "state/account-avatar.json",
        {"uid": uid, "face": face if isinstance(face, str) else "", "binding": token},
    )


def _create_empty_registry(store, root):
    if not store.path.exists():
        store.save(store._empty())
    _write_marker(store, None)
    return MigrationResult(store=store, migrated=True, legacy_mode=False)


def _write_marker(store, account_id):
    write_json(
        store.marker_path,
        {
            "version": 1,
            "migrated_at": int(time.time()),
            "account": account_id or "",
        },
    )


def ensure_account_store(root, *, validator=None):
    """Migrate the legacy root once; return a store or a legacy-mode marker."""
    root = Path(root)
    store = AccountStore(root)
    validator = validator or validate_credentials_readonly

    if store.path.exists():
        store.load()  # Corrupt primary/backup raises; never scan directories.
        if not store.marker_path.exists():
            _write_marker(store, store.active_id)
        return MigrationResult(store=store, migrated=False, legacy_mode=False)

    # A missing registry after migration must not replay stale legacy data over
    # live account roots. Recover the last valid backup when one exists.
    if store.marker_path.exists() or store.backup_path.exists():
        backup = store._read_file(store.backup_path)
        if backup is not None:
            try:
                state = store._clean_state(backup)
            except Exception:
                state = None
            if state is not None:
                store.save(state)
                _write_marker(store, store.active_id)
                return MigrationResult(
                    store=store, migrated=False, legacy_mode=False,
                    reason="已从备份恢复账号注册表",
                )
        return MigrationResult(
            store=store, migrated=False, legacy_mode=True,
            reason="账号注册表丢失且没有可用备份，请从备份恢复",
        )

    credentials_path = root / "credentials.json"
    if not credentials_path.exists():
        return _create_empty_registry(store, root)

    # Back up the sealed bytes before unsealing or re-sealing anything. A
    # legacy plaintext file is upgraded by read_json first, so the backup never
    # contains a new plaintext copy.
    try:
        raw = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return MigrationResult(
            store=store, migrated=False, legacy_mode=True,
            reason="旧凭证文件无法读取",
        )
    if raw and not is_envelope(raw):
        try:
            read_json(credentials_path, {})
        except (OSError, ValueError, RuntimeError):
            return MigrationResult(
                store=store, migrated=False, legacy_mode=True,
                reason="旧凭证无法转换为受保护格式",
            )
    try:
        _backup_credentials(root, credentials_path)
    except OSError:
        return MigrationResult(
            store=store, migrated=False, legacy_mode=True,
            reason="无法备份旧凭证",
        )

    try:
        credentials = read_json(credentials_path, {})
    except (OSError, ValueError, RuntimeError):
        return MigrationResult(
            store=store, migrated=False, legacy_mode=True,
            reason="旧凭证无法解密",
        )
    if not isinstance(credentials, dict):
        return MigrationResult(
            store=store, migrated=False, legacy_mode=True,
            reason="旧凭证格式无效",
        )
    sessdata = credentials.get("SESSDATA")
    bili_jct = credentials.get("bili_jct")
    if not sessdata or not bili_jct:
        # The legacy session was explicitly logged out; the account list is
        # simply empty and the old root remains available for rollback.
        return _create_empty_registry(store, root)

    uid = _cached_uid(credentials, root)
    profile = _cached_profile(root)
    if not uid:
        try:
            valid, message, remote = validator(sessdata, bili_jct)
        except (OSError, ValueError, RuntimeError):
            valid, message, remote = False, "认证接口请求失败", {}
        if not valid or not isinstance(remote, dict) or not remote.get("uid"):
            return MigrationResult(
                store=store, migrated=False, legacy_mode=True,
                reason=f"无法确认旧账号 UID：{message}",
            )
        uid = int(remote["uid"])
        profile = {
            "name": remote.get("name") or profile.get("name", ""),
            "face": remote.get("face") or profile.get("face", ""),
        }

    account_id = _account_id(uid)
    name = profile.get("name") or f"账号 {uid}"
    face = profile.get("face", "")
    account_root = store.ensure_root(account_id, uid)

    members = _safe_members(root / "members.json")
    write_json(account_root / "members.json", members)

    settings = _safe_settings(root / "settings.json")
    # autostart is a Windows/application concern; it must not become a
    # per-account toggle. Other task switches and paused belong to the account.
    settings.pop("autostart", None)
    write_json(account_root / "settings.json", settings)

    fingerprint = session_fingerprint(sessdata)
    _copy_account_state(root, account_root, account_id, fingerprint)
    store.save_credentials(account_id, sessdata, bili_jct)
    try:
        safety.bind_account(sessdata, uid, account_root)
    except (OSError, ValueError, TimeoutError):
        # The credential is safe on disk; the next authenticated nav can bind.
        logging.warning("Cannot bind migrated account identity")

    try:
        saved = read_json(account_root / "credentials.json", {})
    except (OSError, ValueError, RuntimeError):
        saved = {}
    if saved.get("SESSDATA") != sessdata or saved.get("bili_jct") != bili_jct:
        return MigrationResult(
            store=store, migrated=False, legacy_mode=True,
            reason="新账号凭证回读失败",
        )
    token = store.credential_token(account_id)
    _copy_avatar_profile(root, account_root, uid, token)

    # Registry last: every row must point at an existing, readable account.
    store.upsert(uid, name, face)
    store.set_active(account_id)
    store.set_view(account_id)
    _write_marker(store, account_id)
    return MigrationResult(
        store=store, migrated=True, legacy_mode=False, account_id=account_id
    )
