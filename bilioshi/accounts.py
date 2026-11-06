"""Account registry and per-account data roots.

The install root owns only application state. Every Bilibili account gets a
separate ``accounts/uid-<mid>/`` data root so credentials, members, task
budgets, safety holds and room state cannot leak between accounts.

This module is intentionally independent from ``desktop``; the desktop host and
the bridge consume the plain dictionaries returned here.
"""

import json
import logging
import re
import shutil
import threading
import time
from pathlib import Path

from . import safety
from .runtime import (
    FileLock,
    credentials_path,
    read_json,
    save_login,
    session_fingerprint,
    update_json,
    write_json,
)
from .secret_store import discard, is_envelope

REGISTRY_VERSION = 1
ACCOUNT_MARKER = "account.json"
ACCOUNT_ROOT = "accounts"
RETAINED_ROOT = "accounts/.retained"
VALID_STATUSES = {"ok", "needs_login", "blocked"}
VALID_MODES = {"single", "concurrent"}
_ID_PATTERN = re.compile(r"^uid-([1-9][0-9]*)$")


class AccountStoreError(RuntimeError):
    """The registry or an account record cannot be used safely."""


class UnknownAccount(AccountStoreError):
    pass


def _now():
    return int(time.time())


def _positive_int(value):
    return type(value) is int and value > 0


def _account_id(uid):
    return f"uid-{int(uid)}"


def _data_dir(account_id):
    return f"{ACCOUNT_ROOT}/{account_id}"


def _validate_account_id(value):
    if not isinstance(value, str) or not _ID_PATTERN.match(value):
        raise UnknownAccount("未知账号")
    return value


class AccountStore:
    """Atomic access to ``<install_root>/state/accounts.json``.

    Writes are serialized with the same OS file lease used by the rest of the
    application. The previous valid registry is kept as ``.bak``; a corrupt
    registry is never repaired by scanning directories.
    """

    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / "state" / "accounts.json"
        self.backup_path = self.path.with_suffix(".json.bak")
        self.marker_path = self.root / "state" / "accounts-v1.json"
        self._lock = threading.RLock()
        self._state = None
        self._loaded = False

    # ---------- loading ----------

    @staticmethod
    def _empty():
        return {
            "version": REGISTRY_VERSION,
            "mode": "single",
            "global_paused": False,
            "active": None,
            "view": None,
            "accounts": [],
        }

    @staticmethod
    def _read_file(path):
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError, UnicodeError):
            return None
        return raw

    @staticmethod
    def _clean_row(row):
        if not isinstance(row, dict):
            raise AccountStoreError("账号记录损坏")
        account_id = _validate_account_id(row.get("id"))
        uid = row.get("uid")
        if not _positive_int(uid) or account_id != _account_id(uid):
            raise AccountStoreError("账号 UID 与目录不一致")
        name = row.get("name")
        if not isinstance(name, str):
            raise AccountStoreError("账号名称损坏")
        face = row.get("face", "")
        if not isinstance(face, str):
            face = ""
        status = row.get("status", "ok")
        if status not in VALID_STATUSES:
            raise AccountStoreError("账号状态损坏")
        data_dir = row.get("data_dir", _data_dir(account_id))
        if data_dir != _data_dir(account_id):
            raise AccountStoreError("账号目录越界")
        return {
            "id": account_id,
            "uid": uid,
            "name": name.strip() or f"账号 {uid}",
            "face": face,
            "created_at": int(row.get("created_at") or 0),
            "last_used_at": int(row.get("last_used_at") or 0),
            "last_checked_at": int(row.get("last_checked_at") or 0),
            "status": status,
            "watch_enabled": bool(row.get("watch_enabled", False)),
            "credential_token": str(row.get("credential_token") or ""),
            "data_dir": data_dir,
        }

    @classmethod
    def _clean_state(cls, value):
        if not isinstance(value, dict):
            raise AccountStoreError("账号注册表损坏")
        if value.get("version") != REGISTRY_VERSION:
            raise AccountStoreError("账号注册表版本不支持")
        mode = value.get("mode", "single")
        if mode not in VALID_MODES:
            raise AccountStoreError("运行模式损坏")
        accounts = []
        ids, uids = set(), set()
        for raw in value.get("accounts", []):
            row = cls._clean_row(raw)
            if row["id"] in ids or row["uid"] in uids:
                raise AccountStoreError("账号注册表存在重复账号")
            ids.add(row["id"])
            uids.add(row["uid"])
            accounts.append(row)
        active = value.get("active")
        view = value.get("view")
        if active is not None and active not in ids:
            raise AccountStoreError("当前账号不在注册表中")
        if view is not None and view not in ids:
            raise AccountStoreError("查看账号不在注册表中")
        return {
            "version": REGISTRY_VERSION,
            "mode": mode,
            "global_paused": bool(value.get("global_paused", False)),
            "active": active,
            "view": view,
            "accounts": accounts,
        }

    def load(self, *, force=False):
        """Return the current registry. Missing file means a fresh install."""
        with self._lock:
            if self._loaded and not force:
                return self._state
            raw = self._read_file(self.path)
            if raw is None and not self.path.exists():
                self._state = self._empty()
                self._loaded = True
                return self._state
            try:
                self._state = self._clean_state(raw)
            except AccountStoreError:
                backup = self._read_file(self.backup_path)
                if backup is None:
                    raise
                logging.warning("Account registry is corrupt; using backup")
                self._state = self._clean_state(backup)
            self._loaded = True
            return self._state

    def _copy(self):
        return json.loads(json.dumps(self.load()))

    def _write_locked(self, state):
        # Only back up a parseable registry. A corrupt file must not replace a
        # known-good backup.
        current = self._read_file(self.path)
        if current is not None:
            try:
                self._clean_state(current)
            except AccountStoreError:
                pass
            else:
                self.backup_path.parent.mkdir(parents=True, exist_ok=True)
                self.backup_path.write_bytes(self.path.read_bytes())
        write_json(self.path, state)
        self._state = state
        self._loaded = True

    def save(self, state):
        with self._lock:
            clean = self._clean_state(state)
            with FileLock(str(self.path) + ".guard", timeout=5) as lock:
                if not lock.acquired:
                    raise TimeoutError("等待账号注册表写入锁超时")
                self._write_locked(clean)
            return self._copy()

    def _mutate(self, change):
        with self._lock:
            with FileLock(str(self.path) + ".guard", timeout=5) as lock:
                if not lock.acquired:
                    raise TimeoutError("等待账号注册表写入锁超时")
                # Re-read inside the lease so two hosts cannot overwrite each
                # other's account list.
                if self.path.exists():
                    raw = self._read_file(self.path)
                    if raw is None:
                        raise AccountStoreError("账号注册表无法读取")
                    state = self._clean_state(raw)
                else:
                    state = self._empty()
                state = self._clean_state(change(state))
                self._write_locked(state)
            return self._copy()

    # ---------- reads ----------

    @property
    def mode(self):
        return self.load()["mode"]

    @property
    def global_paused(self):
        return self.load()["global_paused"]

    @property
    def active_id(self):
        return self.load()["active"]

    @property
    def view_id(self):
        return self.load()["view"]

    def accounts(self):
        return [dict(row) for row in self.load()["accounts"]]

    def get(self, account_id):
        account_id = _validate_account_id(account_id)
        for row in self.load()["accounts"]:
            if row["id"] == account_id:
                return dict(row)
        raise UnknownAccount("未知账号")

    def by_uid(self, uid):
        if not _positive_int(uid):
            raise UnknownAccount("未知账号")
        for row in self.load()["accounts"]:
            if row["uid"] == uid:
                return dict(row)
        raise UnknownAccount("未知账号")

    def has(self, account_id):
        try:
            self.get(account_id)
            return True
        except UnknownAccount:
            return False

    def path_for_id(self, account_id):
        """Resolve a registry-shaped id to its root without touching disk."""
        account_id = _validate_account_id(account_id)
        return self.root / ACCOUNT_ROOT / account_id

    def account_root(self, account_id):
        return self.path_for_id(self.get(account_id)["id"])

    def credential_path(self, account_id):
        # Registry row is not required: account creation computes its token
        # before the row is appended, and removal needs to delete the file
        # after the row is gone.
        return credentials_path(self.path_for_id(account_id))

    def credential_token(self, account_id):
        path = self.credential_path(account_id)
        try:
            stat = path.stat()
        except OSError:
            return ""
        return f"{stat.st_mtime_ns}:{stat.st_size}"

    def has_credentials(self, account_id):
        """Inspect envelope metadata only; never decrypt while listing."""
        path = self.credential_path(account_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            return False
        if is_envelope(raw):
            return bool(raw.get("payload") or raw.get("reference"))
        return bool(raw.get("SESSDATA") and raw.get("bili_jct"))

    def credentials(self, account_id):
        saved = read_json(self.credential_path(account_id), {})
        if not isinstance(saved, dict) or not saved.get("SESSDATA") or not saved.get("bili_jct"):
            raise UnknownAccount("此账号尚未登录")
        return saved["SESSDATA"], saved["bili_jct"]

    def public(self):
        return {
            "version": REGISTRY_VERSION,
            "mode": self.mode,
            "global_paused": self.global_paused,
            "active": self.active_id,
            "view": self.view_id,
            "accounts": self.accounts(),
        }

    # ---------- registry updates ----------

    def upsert(self, uid, name, face="", *, status="ok"):
        """Create or refresh a public account row. Credentials are separate."""
        if not _positive_int(uid):
            raise UnknownAccount("账号 UID 无效")
        if status not in VALID_STATUSES:
            raise ValueError("账号状态无效")
        account_id = _account_id(uid)
        created = [False]
        now = _now()

        def change(state):
            for row in state["accounts"]:
                if row["uid"] == uid:
                    row["name"] = str(name).strip() or row["name"]
                    row["face"] = str(face or row["face"])
                    row["last_used_at"] = now
                    row["status"] = status
                    row["credential_token"] = self.credential_token(account_id)
                    return state
            state["accounts"].append({
                "id": account_id,
                "uid": uid,
                "name": str(name).strip() or f"账号 {uid}",
                "face": str(face or ""),
                "created_at": now,
                "last_used_at": now,
                "last_checked_at": 0,
                "status": status,
                "watch_enabled": False,
                "credential_token": self.credential_token(account_id),
                "data_dir": _data_dir(account_id),
            })
            created[0] = True
            if state["active"] is None:
                state["active"] = account_id
            if state["view"] is None:
                state["view"] = account_id
            return state

        self._mutate(change)
        return self.get(account_id), created[0]

    def update(self, account_id, **fields):
        account_id = _validate_account_id(account_id)
        allowed = {
            "name", "face", "status", "watch_enabled",
            "last_used_at", "last_checked_at", "credential_token",
        }
        unknown = set(fields) - allowed
        if unknown:
            raise ValueError("不能修改账号字段：" + ", ".join(sorted(unknown)))

        def change(state):
            for row in state["accounts"]:
                if row["id"] != account_id:
                    continue
                for key, value in fields.items():
                    row[key] = value
                return state
            raise UnknownAccount("未知账号")

        self._mutate(change)
        return self.get(account_id)

    def set_active(self, account_id):
        if account_id is not None:
            self.get(account_id)

        def change(state):
            state["active"] = account_id
            if account_id is not None:
                for row in state["accounts"]:
                    if row["id"] == account_id:
                        row["last_used_at"] = _now()
            return state

        self._mutate(change)

    def set_view(self, account_id):
        if account_id is not None:
            self.get(account_id)

        def change(state):
            state["view"] = account_id
            return state

        self._mutate(change)

    def set_mode(self, mode):
        if mode not in VALID_MODES:
            raise ValueError("运行模式无效")

        def change(state):
            state["mode"] = mode
            return state

        self._mutate(change)

    def set_global_paused(self, paused):
        def change(state):
            state["global_paused"] = bool(paused)
            return state

        self._mutate(change)

    def set_watch_enabled(self, account_id, enabled):
        self.update(account_id, watch_enabled=bool(enabled))

    def touch_checked(self, account_id):
        self.update(account_id, last_checked_at=_now())

    # ---------- account roots and credentials ----------

    def ensure_root(self, account_id, uid=None):
        """Create the account data root and its fail-closed marker.

        Settings/members files are left to ``desktop.storage.initialize`` so the
        core package does not depend on desktop defaults.
        """
        account_id = _validate_account_id(account_id)
        if uid is not None and _account_id(uid) != account_id:
            raise UnknownAccount("账号 UID 与目录不一致")
        root = self.root / ACCOUNT_ROOT / account_id
        for sub in ("logs", "state", "locks", "commands", "state/tasks", "state/safety"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        marker = root / ACCOUNT_MARKER
        if not marker.exists():
            value = {"id": account_id, "uid": int(account_id.split("-", 1)[1])}
            write_json(marker, value)
        return root

    def save_credentials(self, account_id, sessdata, bili_jct, *, context=None):
        """Seal a validated pair into this account root (exactly once)."""
        account_id = _validate_account_id(account_id)
        root = self.root / ACCOUNT_ROOT / account_id
        root.mkdir(parents=True, exist_ok=True)
        save_login(sessdata, bili_jct, credentials_path(root), context=context)
        token = self.credential_token(account_id)
        if self.has(account_id):
            row = self.get(account_id)
            fields = {"credential_token": token}
            # Authentication never clears a platform protection hold.
            if row["status"] != "blocked":
                fields["status"] = "ok"
            self.update(account_id, **fields)
        return token

    def _delete_credential_file(self, account_id):
        account_id = _validate_account_id(account_id)
        path = credentials_path(self.path_for_id(account_id))
        raw = self._read_file(path)
        try:
            if is_envelope(raw):
                discard(raw)
            path.unlink()
        except FileNotFoundError:
            return
        return raw

    def clear_credentials(self, account_id):
        """Sign out one account without touching any other root or account row."""
        account_id = _validate_account_id(account_id)
        path = credentials_path(self.path_for_id(account_id))
        fingerprint = None
        try:
            saved = read_json(path, {})
            if isinstance(saved, dict) and saved.get("SESSDATA"):
                fingerprint = session_fingerprint(saved["SESSDATA"])
        except (OSError, ValueError, RuntimeError):
            fingerprint = None
        self._delete_credential_file(account_id)
        root = self.path_for_id(account_id)
        if fingerprint:
            bindings = root / "state" / "account-bindings.json"
            if bindings.exists():
                update_json(bindings, lambda value: {
                    key: val for key, val in value.items() if key != fingerprint
                }, {})
        if self.has(account_id):
            self.update(account_id, status="needs_login", credential_token="")

    def mark_needs_login(self, account_id):
        self.update(
            account_id,
            status="needs_login",
            credential_token=self.credential_token(account_id),
        )

    def mark_ok(self, account_id):
        self.update(account_id, status="ok", credential_token=self.credential_token(account_id))

    # ---------- lifecycle ----------

    def _retained_root(self, account_id):
        return self.root / RETAINED_ROOT / account_id

    @staticmethod
    def _merge_move(source, destination):
        if not source.exists():
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            for child in source.iterdir():
                AccountStore._merge_move(child, destination / child.name)
            try:
                source.rmdir()
            except OSError:
                pass
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                destination.unlink()
            shutil.move(str(source), str(destination))

    def retain_data(self, account_id):
        """Keep data that must survive removal; never retain credentials."""
        account_id = _validate_account_id(account_id)
        root = self.root / ACCOUNT_ROOT / account_id
        if not root.exists():
            return
        target = self._retained_root(account_id)
        target.mkdir(parents=True, exist_ok=True)
        for name in ("members.json", "settings.json"):
            self._merge_move(root / name, target / name)
        for name in ("tasks", "safety"):
            self._merge_move(root / "state" / name, target / "state" / name)
        self._merge_move(
            root / "state" / "account-bindings.json",
            target / "state" / "account-bindings.json",
        )
        for credit in (root / "state").glob("watch-credit-*.json"):
            self._merge_move(credit, target / "state" / credit.name)

    def restore_retained(self, account_id):
        """Restore preserved data when the same UID is added again."""
        account_id = _validate_account_id(account_id)
        source = self._retained_root(account_id)
        if not source.exists():
            return False
        root = self.ensure_root(account_id)
        for name in ("members.json", "settings.json"):
            self._merge_move(source / name, root / name)
        for name in ("tasks", "safety"):
            self._merge_move(source / "state" / name, root / "state" / name)
        self._merge_move(
            source / "state" / "account-bindings.json",
            root / "state" / "account-bindings.json",
        )
        for credit in (source / "state").glob("watch-credit-*.json"):
            self._merge_move(credit, root / "state" / credit.name)
        try:
            shutil.rmtree(source)
        except OSError:
            logging.warning("Cannot remove retained account data for %s", account_id)
        return True

    def remove(self, account_id):
        """Remove a row; keep quotas/protection in ``.retained`` for re-add."""
        row = self.get(account_id)

        def change(state):
            state["accounts"] = [item for item in state["accounts"] if item["id"] != account_id]
            if state["active"] == account_id:
                state["active"] = None
            if state["view"] == account_id:
                state["view"] = state["active"] or (
                    state["accounts"][0]["id"] if state["accounts"] else None
                )
            return state

        self._mutate(change)
        try:
            self._delete_credential_file(account_id)
        except (AccountStoreError, OSError, ValueError, RuntimeError):
            logging.warning("Cannot clear credentials for removed account %s", account_id)
        self.retain_data(account_id)
        root = self.root / ACCOUNT_ROOT / account_id
        try:
            shutil.rmtree(root)
        except FileNotFoundError:
            pass
        except OSError:
            logging.warning("Cannot remove account directory for %s", account_id)
        return row
