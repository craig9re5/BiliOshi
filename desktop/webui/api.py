"""Deliberate JSON-only endpoints for the local WebView renderer.

pywebview recursively inspects public attributes, so every object owned by this
bridge is private. Network calls stay in AppContext and accepted IO is drained
before the host closes the Engine.
"""

import base64
from collections import OrderedDict
from contextlib import nullcontext
import copy
from datetime import datetime
import io
import json
import logging
import math
import os
import re
import threading
import time
import webbrowser
from pathlib import Path

from bilioshi.accounts import ALL_ACCOUNTS, AccountStoreError
from bilioshi.growth import CHINA_TZ, load_history
from bilioshi.members import load_account_members, load_members
from bilioshi.operating_mode import PROFILES, profile_for
from bilioshi.redaction import redact
from bilioshi.runtime import read_json, update_json
from bilioshi.secret_store import is_envelope
from desktop.interaction import action_reason, recovery_route
from desktop.storage import load_config


_EXCEPTION_NAME = re.compile(r"[（(][\w.]*?(?:Error|Exception)[）)]|[：:]\s*[\w.]*?(?:Error|Exception)\b")
_SECRET_FIELDS = {
    "sessdata", "bili_jct", "cookie", "cookies", "set-cookie", "authorization",
    "qrcode_key", "qr_login_context", "live_like_cookie", "pushplus_token",
    "access_token", "refresh_token", "secret_key",
}
_SETTING_FLAGS = (
    "auto_revive", "auto_danmaku_intimacy", "auto_like", "notify_on_live", "autostart", "paused",
)
_PENDING_MESSAGES = {
    "redo": "正在补齐任务", "wear": "正在佩戴粉丝牌", "reconnect": "正在请求重连",
    "remove": "正在移除主播", "settings": "正在保存并应用设置", "pause": "正在调整挂机状态",
    "check": "正在请求检查", "safety": "正在检查账号并解除保护暂停", "logout": "正在退出登录",
    "add": "正在添加主播", "import": "正在导入粉丝牌主播",
}
# These operations always touch the active Engine. A view of another account
# must stay read-only rather than silently mutating the running account.
_ACTIVE_VIEW_ONLY = {"add", "import", "resolve", "medals", "check", "pause", "safety", "remove"}


def _public(value):
    """Only JSON data crosses the boundary; secrets and raw exception names do not."""
    value = redact(value)
    if isinstance(value, dict):
        return {str(key): _public(item) for key, item in value.items()
                if str(key).lower() not in _SECRET_FIELDS}
    if isinstance(value, (list, tuple)):
        return [_public(item) for item in value]
    if isinstance(value, str):
        return _EXCEPTION_NAME.sub("（详情见日志）", value)
    if value is None or type(value) in (bool, int):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    raise TypeError("Bridge responses must contain JSON data")


def _positive_id(value):
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
        return int(value)
    raise ValueError("Invalid identifier")


def _signature(path):
    try:
        stat = path.stat()
        return stat.st_mtime_ns, stat.st_size
    except FileNotFoundError:
        return None


def _png_uri(image):
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


def _qr_data_uri(url):
    import qrcode
    from qrcode.image.pil import PilImage

    return _png_uri(qrcode.make(url, box_size=8, border=3, image_factory=PilImage))


class Api:
    """Exposed as window.pywebview.api; public members are endpoints only."""

    def __init__(self, engine, ui):
        self._host = engine if hasattr(engine, "active_engine") and hasattr(engine, "store") else None
        self._host_root = Path(engine.root)
        self._store = self._host.store if self._host is not None else None
        self._engine = self._host.active_engine() if self._host is not None else engine
        self._ui = ui
        self._root = Path(self._engine.root) if self._engine is not None else self._host_root
        self._mutations = threading.RLock()
        self._control_mutations = threading.RLock()
        self._state = threading.Condition(threading.RLock())
        self._closing = threading.Event()
        self._active = 0
        self._room_operations, self._controls = {}, {}
        self._snapshot_lock = threading.Lock()
        self._cache_lock = threading.RLock()
        self._last_snapshot = None
        self._ui_error = ""
        self._settings_signature = object()
        self._settings_cache = {}
        self._credentials_signature = object()
        self._credentials_cache = (False, "")
        self._medals_cache = None
        self._growth_signature = None
        self._growth_cache = None
        self._avatars = OrderedDict()
        self._qr_lock = threading.RLock()
        self._qr_generation = 0
        self._qr_session = None
        self._qr_cancel_event = None
        self._qr_target = None

    def _sync_active(self):
        if self._host is None:
            return
        engine = self._host.active_engine()
        if engine is self._engine:
            return
        self._engine = engine
        self._root = Path(engine.root) if engine is not None else self._host_root
        with self._cache_lock:
            self._last_snapshot = None
            self._settings_signature = object()
            self._settings_cache = {}
            self._credentials_signature = object()
            self._credentials_cache = (False, "")
            self._medals_cache = None
            self._growth_signature = None
            self._growth_cache = None
            self._avatars.clear()

    def _active_account_id(self):
        if self._host is not None:
            return self._host.active_id
        return getattr(self._engine, "account_id", "") or ""

    def _view_account_id(self):
        if self._host is not None:
            return self._host.view_id
        return self._active_account_id()

    def _account_root(self, account_id=None):
        account_id = account_id or self._view_account_id()
        if self._store is not None and account_id and account_id != ALL_ACCOUNTS:
            return self._store.account_root(account_id)
        return self._root

    def _view_is_active(self):
        if self._host is None:
            return True
        return self._host.view_id in (None, self._host.active_id)

    def _view_allows_active_action(self, kind):
        """The all-accounts dashboard may check the running account."""
        if self._host is None:
            return True
        if self._host.view_id == ALL_ACCOUNTS:
            return kind == "check"
        return self._view_is_active()

    def _empty_snapshot(self):
        return {
            "account": "",
            "account_confirmed": False,
            "account_checked_at": 0,
            "paused": False,
            "safety": {"blocked": False},
            "rows": [],
            "checking": False,
            "error": "",
            "active": False,
            "inactive": True,
        }

    # Snapshot construction never waits for the Engine's monitor/control lock.
    def snapshot(self):
        self._sync_active()
        if self._host is not None:
            return self._multi_snapshot()
        busy, failed = True, False
        if self._snapshot_lock.acquire(blocking=False):
            try:
                try:
                    fresh = self._engine.snapshot(blocking=False)
                    if fresh is not None:
                        with self._cache_lock:
                            self._last_snapshot = copy.deepcopy(fresh)
                        busy = False
                except Exception:
                    logging.exception("Web snapshot failed")
                    failed = True
            finally:
                self._snapshot_lock.release()
        with self._cache_lock:
            snap = copy.deepcopy(self._last_snapshot) if self._last_snapshot is not None else {
                "account": "", "account_confirmed": False, "account_checked_at": 0,
                "paused": bool(self._engine.paused), "safety": {"blocked": False},
                "rows": [], "checking": False, "error": "",
            }
        with self._state:
            controls = copy.deepcopy(self._controls)
            rooms = copy.deepcopy(self._room_operations)
            ui_error = self._ui_error
        if failed:
            ui_error = "界面刷新失败，正在自动重试。"
        snap.update(engine_busy=busy, closing=self._closing.is_set(), ui_error=ui_error)
        try:
            snap["settings"] = self.settings()
        except Exception:
            logging.exception("Web settings read failed")
            snap["settings"] = dict(self._settings_cache)
            snap["ui_error"] = "设置无法读取，请检查本机配置后重试界面。"
        snap["accountInfo"] = self._account_info(snap)
        snap["operations"] = {"controls": controls, "rooms": {str(k): v for k, v in rooms.items()}}
        for row in snap.get("rows", []):
            operation = rooms.get(row.get("room"), {})
            row["operation"] = operation
            row["actions"] = {action: self._room_reason(snap, row, action, operation.get("pending", False))
                              for action in ("open", "redo", "reconnect", "wear", "remove")}
        snap["recovery"] = recovery_route(snap)
        snap["notifications"] = {"available": False}
        return _public(snap)

    def _read_settings(self, root):
        config, _ = load_config(root)
        value = {key: config.get(key, False) for key in _SETTING_FLAGS}
        value["run_mode"] = config.get("run_mode", "stable")
        value["check_minutes"] = profile_for(value["run_mode"]).check_minutes
        try:
            from desktop.windows import is_autostart_enabled

            value["autostart"] = bool(is_autostart_enabled())
        except Exception:
            logging.exception("Cannot read Windows autostart status")
        return value

    def settings(self, account_id=None):
        root = self._account_root(account_id) if account_id else self._root
        if self._store is not None and not (root / "settings.json").exists():
            from desktop.storage import initialize

            initialize(root, [])
        if account_id and self._store is not None and account_id not in (
            self._active_account_id(), ALL_ACCOUNTS
        ):
            return self._read_settings(root)
        with self._cache_lock:
            signature = (_signature(root / "settings.json"), _signature(root / "members.json"))
            if signature != self._settings_signature:
                value = self._read_settings(root)
                self._settings_cache = value
                self._settings_signature = signature
            return dict(self._settings_cache)

    def _summary_public(self, summary):
        value = {key: summary.get(key) for key in (
            "id", "uid", "name", "face", "created_at", "last_used_at",
            "last_checked_at", "status", "watch_enabled", "credential_token",
            "signed_in", "running", "paused", "global_paused", "state", "room_count",
            "live_room_count", "gain", "snapshot_at", "stale", "safety", "account",
        )}
        return _public(value)

    def _multi_snapshot(self):
        busy, failed = True, False
        fresh = None
        if self._engine is not None and self._snapshot_lock.acquire(blocking=False):
            try:
                try:
                    fresh = self._engine.snapshot(blocking=False)
                    if fresh is not None:
                        with self._cache_lock:
                            self._last_snapshot = copy.deepcopy(fresh)
                        busy = False
                except Exception:
                    logging.exception("Web snapshot failed")
                    failed = True
            finally:
                self._snapshot_lock.release()
        with self._cache_lock:
            snap = (copy.deepcopy(self._last_snapshot)
                    if self._last_snapshot is not None else self._empty_snapshot())
        with self._state:
            controls = copy.deepcopy(self._controls)
            rooms = copy.deepcopy(self._room_operations)
            ui_error = self._ui_error
        if failed:
            ui_error = "界面刷新失败，正在自动重试。"
        snap.update(
            schema=2,
            active_account_id=self._host.active_id,
            view_account_id=self._host.view_id,
            mode=self._store.mode,
            global_paused=self._host.global_paused,
            active=snap.get("active", bool(self._host.active_id)),
            inactive=False,
            engine_busy=busy,
            closing=self._closing.is_set(),
            ui_error=ui_error,
        )
        snap["accounts"] = [self._summary_public(item) for item in self._host.summaries()]
        view_id = self._host.view_id
        viewing_other = bool(view_id) and view_id not in (self._host.active_id, ALL_ACCOUNTS)
        try:
            snap["settings"] = self.settings(None if viewing_other else view_id)
        except Exception:
            logging.exception("Web settings read failed")
            snap["settings"] = dict(self._settings_cache)
            snap["ui_error"] = "设置无法读取，请检查本机配置后重试界面。"
        snap["accountInfo"] = self._account_info(snap)
        snap["operations"] = {
            "controls": controls,
            "rooms": {str(key): value for key, value in rooms.items()},
        }
        for row in snap.get("rows", []):
            row["account_id"] = self._host.active_id or ""
            operation = rooms.get(row.get("room"), {})
            row["operation"] = operation
            row["actions"] = {
                action: self._room_reason(snap, row, action, operation.get("pending", False))
                for action in ("open", "redo", "reconnect", "wear", "remove")
            }
        snap["recovery"] = recovery_route(snap)
        snap["notifications"] = {"available": False}
        if self._host.view_id and self._host.view_id not in (self._host.active_id, ALL_ACCOUNTS):
            snap["view"] = self._view_snapshot(self._host.view_id)
        return _public(snap)

    def _view_snapshot(self, account_id):
        root = self._store.account_root(account_id)
        try:
            status = read_json(root / "state/last-snapshot.json", {})
            if not isinstance(status, dict) or not status.get("rows"):
                status = read_json(root / "status.json", {})
        except (OSError, ValueError):
            status = {}
        if not isinstance(status, dict):
            status = {}
        summary = self._host.account_summary(account_id)
        try:
            settings = self._read_settings(root)
        except (OSError, ValueError):
            settings = {key: False for key in _SETTING_FLAGS}
            settings["run_mode"] = "stable"
            settings["check_minutes"] = 5
        rows = copy.deepcopy(status.get("rows") or [])
        for row in rows:
            row.update(
                account_id=account_id,
                active=False,
                live_status=None,
                status_stale=True,
                tasks_stale=True,
                inactive=True,
            )
        hold = status.get("safety")
        if not isinstance(hold, dict):
            hold = {"blocked": False}
        if summary.get("state") == "protection" and not hold.get("blocked"):
            hold = {"blocked": True, "kind": "review", "reason": "账号保护暂停"}
        view = {
            **self._empty_snapshot(),
            **status,
            "schema": 2,
            "account_id": account_id,
            "account": status.get("account") or summary.get("name", ""),
            "account_confirmed": bool(status.get("account_checked_at") or summary.get("account")),
            "account_checked_at": status.get("account_checked_at", 0),
            "paused": bool(settings.get("paused")),
            "safety": hold,
            "rows": rows,
            "settings": _public(settings),
            "accountInfo": {
                "signed_in": summary.get("signed_in", False),
                "name": summary.get("name", ""),
                "confirmed": bool(status.get("account")),
                "checked_at": status.get("account_checked_at", 0),
                "safety": hold,
                "credentials_error": "",
            },
            "operations": {"controls": {}, "rooms": {}},
            "active": False,
            "inactive": True,
            "engine_busy": False,
            "closing": self._closing.is_set(),
            "ui_error": "",
            "notifications": {"available": False},
        }
        for row in view["rows"]:
            row["operation"] = {}
            row["actions"] = {
                action: self._room_reason(view, row, action, False)
                for action in ("open", "redo", "reconnect", "wear", "remove")
            }
        view["recovery"] = recovery_route(view)
        return _public(view)

    def _credentials_present(self):
        # Inspect only the protected envelope/presence. Refreshing a page must not
        # unseal a login, migrate it, or repeatedly register secrets.
        with self._cache_lock:
            path = self._root / "credentials.json"
            signature = _signature(path)
            if signature != self._credentials_signature:
                saved = json.loads(path.read_text(encoding="utf-8-sig")) if signature else {}
                if not isinstance(saved, dict):
                    raise ValueError("Invalid credentials object")
                present = (bool(saved.get("payload") or saved.get("reference")) if is_envelope(saved)
                           else bool(saved.get("SESSDATA") and saved.get("bili_jct")))
                self._credentials_cache = present, ""
                self._credentials_signature = signature
            return self._credentials_cache

    def _account_info(self, snap):
        error = ""
        try:
            present, error = self._credentials_present()
        except (OSError, ValueError):
            logging.exception("Cannot inspect saved login")
            present, error = False, "登录信息无法读取，请重新扫码登录。"
        hold = snap.get("safety", {})
        if hold.get("kind") == "credentials":
            error = "登录信息无法读取，请重新扫码登录。"
        return {
            "signed_in": present, "name": snap.get("account", "") or "",
            "confirmed": bool(snap.get("account_confirmed")),
            "checked_at": snap.get("account_checked_at", 0), "safety": hold,
            "credentials_error": error,
        }

    def account(self):
        with self._cache_lock:
            snap = copy.deepcopy(self._last_snapshot)
        if snap is None:
            return self.snapshot()["accountInfo"]
        return _public(self._account_info(snap))

    def growth(self, days=7, account_id=None):
        """Daily fan-medal growth for one account; never merged across accounts."""
        self._sync_active()
        if isinstance(days, str) and days.isascii() and days.isdigit():
            days = int(days)
        if type(days) is not int or isinstance(days, bool) or not 1 <= days <= 90:
            return {"available": False, "error": "时间范围需为 1 到 90 天。"}

        target = account_id if isinstance(account_id, str) and account_id else None
        if target in (None, "", ALL_ACCOUNTS):
            target = self._view_account_id()
        if target in (None, "", ALL_ACCOUNTS):
            target = self._active_account_id()
        if not target and self._store is not None:
            try:
                rows = self._store.accounts()
                target = rows[0]["id"] if rows else ""
            except AccountStoreError:
                target = ""

        root = self._root
        account_name = ""
        running = False
        paused = False
        status = ""
        if self._store is not None:
            if not target:
                return {"available": False, "error": "没有可读取的账号，请先登录。"}
            try:
                row = self._store.get(target)
                root = self._store.account_root(target)
                account_name = row.get("name", "") if isinstance(row, dict) else ""
            except (AccountStoreError, OSError, ValueError):
                return {"available": False, "error": "账号不存在或已被移除。"}
            if self._host is not None:
                try:
                    summary = self._host.account_summary(target)
                    running = bool(summary.get("running"))
                    paused = bool(summary.get("paused"))
                    state = summary.get("state") or summary.get("status")
                    status = state if isinstance(state, str) else ""
                except Exception:
                    logging.exception("Reading growth account summary failed")
        else:
            active = self._active_account_id() or ""
            if target and active and target != active:
                return {"available": False, "error": "账号不存在或已被移除。"}
            target = active or target or ""
            account_name = getattr(self._engine, "account", "") if self._engine is not None else ""
            running = bool(
                self._engine is not None
                and not self._engine.paused
                and not self._engine.suspended
            )
            paused = bool(self._engine.paused) if self._engine is not None else False

        try:
            if self._store is not None:
                members = load_account_members(root)
            else:
                members = load_members(root)
        except (OSError, ValueError, TypeError):
            members = []

        # Include the UTC+8 date so the window moves at midnight even when the
        # account is not running and no new sample rewrites the file. Both the
        # signature and the payload use one timestamp to avoid a midnight race.
        now = time.time()
        today = datetime.fromtimestamp(now, CHINA_TZ).date().isoformat()
        signature = (
            target, days, today,
            _signature(root / "state" / "growth.json"),
            _signature(root / "members.json"),
        )
        with self._cache_lock:
            cached = copy.deepcopy(self._growth_cache) if signature == self._growth_signature else None
        if cached is None:
            try:
                cached = load_history(root, target, days, members=members, now=now)
            except (OSError, ValueError, TypeError) as exc:
                logging.warning("Reading fan-medal growth failed: %s", exc)
                return {"available": False, "error": "成长记录暂时无法读取，请查看日志。"}
            with self._cache_lock:
                self._growth_signature = signature
                self._growth_cache = copy.deepcopy(cached)
        cached.update({
            "account_id": target or cached.get("account_id", ""),
            "account_name": account_name if isinstance(account_name, str) else "",
            "running": running,
            "paused": paused,
            "status": status,
            "generated_at": time.time(),
        })
        return _public(cached)

    def set_view_account(self, account_id):
        if self._host is None:
            return {"ok": False, "error": "当前版本只支持单账号。"}
        try:
            self._host.view(account_id or ALL_ACCOUNTS)
        except Exception:
            return {"ok": False, "error": "账号不存在或已被移除。"}
        self._ui.push_now()
        return {"ok": True, "view": self._host.view_id}

    def switch_account(self, account_id):
        if self._host is None:
            return {"ok": False, "error": "当前版本只支持单账号。"}
        try:
            with self._mutations, self._control_mutations:
                self._host.switch_to(account_id)
        except Exception as exc:
            message = str(exc) if str(exc) else "切换账号失败，请稍后重试。"
            return {"ok": False, "error": message}
        self._sync_active()
        self._ui.push_now()
        return {"ok": True, "active": self._host.active_id}

    def set_account_paused(self, account_id, paused):
        if self._host is None:
            return {"ok": False, "error": "当前版本只支持单账号。"}
        if type(paused) is not bool:
            return {"ok": False, "error": "暂停状态必须为 true 或 false。"}
        try:
            self._host.set_account_paused(account_id, paused)
        except Exception:
            return {"ok": False, "error": "无法保存此账号的暂停状态。"}
        self._ui.push_now()
        return {"ok": True, "paused": paused}

    def set_global_paused(self, paused):
        if self._host is None:
            return {"ok": False, "error": "当前版本只支持单账号。"}
        if type(paused) is not bool:
            return {"ok": False, "error": "暂停状态必须为 true 或 false。"}
        try:
            self._host.set_global_paused(paused)
        except Exception:
            return {"ok": False, "error": "无法切换全局暂停。"}
        self._sync_active()
        self._ui.push_now()
        return {"ok": True, "global_paused": paused}

    def remove_account(self, account_id):
        if self._host is None:
            return {"ok": False, "error": "当前版本只支持单账号。"}
        try:
            with self._mutations, self._control_mutations:
                self._host.remove_account(account_id)
        except Exception:
            return {"ok": False, "error": "账号不存在或无法移除。"}
        self._sync_active()
        self._ui.push_now()
        return {"ok": True}

    def ready(self):
        try:
            return {"ok": bool(self._ui.renderer_ready())}
        except Exception:
            logging.exception("Renderer ready handshake failed")
            return {"ok": False, "error": "界面尚未就绪，请重试界面。"}

    def refresh(self):
        with self._state:
            self._ui_error = ""
        self._ui.push_now()
        return {"ok": True}

    # Room writes and controls have separate serial lanes. Reservations happen
    # first so duplicate room actions cannot queue behind a slow network call.
    def _run(self, kind, operation, *, room=None, policy=None, mutating=True,
             allow_without_engine=False):
        self._sync_active()
        if self._engine is None and not allow_without_engine:
            return {"ok": False, "error": "当前没有正在运行的账号。"}
        if (room is not None and self._host is not None and not self._view_is_active()) or (
                kind in _ACTIVE_VIEW_ONLY and not self._view_allows_active_action(kind)):
            return {"ok": False, "error": "此账号当前未运行，切换到该账号后才能执行操作。"}
        with self._state:
            if self._closing.is_set():
                return {"ok": False, "error": "正在退出，当前不接受新操作。"}
            states, key = (self._room_operations, room) if room is not None else (self._controls, kind)
            if states.get(key, {}).get("pending"):
                return {"ok": False, "error": "该直播间已有操作正在执行，请等待结果。" if room is not None
                        else "该操作正在执行，请等待结果。"}
            states[key] = {"kind": kind, "pending": True,
                           "message": _PENDING_MESSAGES.get(kind, "正在处理，请稍候"), "started": time.time()}
            self._active += 1
        self._ui.push_now()
        result = {"ok": False, "error": "操作未成功，请重试或查看活动记录。"}
        try:
            # Pause/reconnect/check remain usable while a room task waits on IO.
            # Engine and task services own the actual shared-data locks.
            control = kind in {"pause", "check", "settings", "safety", "reconnect", "remove", "logout"}
            lock = self._control_mutations if control else self._mutations
            with lock if mutating else nullcontext():
                if self._closing.is_set():
                    result = {"ok": False, "error": "程序正在退出，尚未开始的操作已取消。"}
                else:
                    row = None
                    reason = ""
                    if room is not None:
                        snap = self.snapshot()
                        row = next((item for item in snap.get("rows", []) if item.get("room") == room), {})
                        reason = self._room_reason(snap, row, policy or kind)
                    returned = ({"ok": False, "error": reason} if reason else
                                operation(row) if room is not None else operation())
                    result = _public(returned)
        except Exception:
            logging.exception("Web action failed action=%s room=%s", kind, room)
            result = {"ok": False, "error": "操作未成功，请重试或查看活动记录。"}
        finally:
            with self._state:
                states[key].update(pending=False, ok=bool(result.get("ok")),
                                   message=result.get("message") or result.get("error", ""))
                # Reads need no persistent operation history, and avatar queries
                # must not grow controls without bound.
                if not mutating:
                    states.pop(key, None)
                self._active -= 1
                self._state.notify_all()
            self._ui.push_now()
        return result

    @staticmethod
    def _room_reason(snap, row, action, pending=False):
        if action != "remove":
            return action_reason(snap, row, action, pending=pending)
        if not row or not row.get("room"):
            return "请先选择主播。"
        if snap.get("closing"):
            return "正在退出，当前不接受新操作。"
        return "该直播间已有操作正在执行，请等待结果。" if pending else ""

    def _room_action(self, room, kind, operation):
        try:
            room = _positive_id(room)
        except ValueError:
            return {"ok": False, "error": "直播间编号无效，请重新选择主播。"}
        return self._run(kind, operation, room=room)

    def save_settings(self, changes, account_id=None):
        if not isinstance(changes, dict) or set(changes) - {*_SETTING_FLAGS, "run_mode", "check_minutes"}:
            return {"ok": False, "error": "设置格式无效，请重新打开设置。"}
        for key in _SETTING_FLAGS:
            if key in changes and type(changes[key]) is not bool:
                return {"ok": False, "error": "设置开关必须为 true 或 false。"}
        target_id = account_id or self._view_account_id() or self._active_account_id()
        if target_id == ALL_ACCOUNTS:
            target_id = self._active_account_id()
        try:
            target_root = self._account_root(target_id) if target_id else self._root
            if target_id and self._store is not None:
                self._store.get(target_id)
        except Exception:
            return {"ok": False, "error": "账号不存在或已被移除。"}
        payload = dict(changes)
        app_autostart = payload.pop("autostart", None)
        if self._store is None and app_autostart is not None:
            # Legacy single-root settings historically stored this flag too.
            payload["autostart"] = app_autostart
        if "run_mode" in payload and (
            not isinstance(payload["run_mode"], str) or payload["run_mode"] not in PROFILES
        ):
            return {"ok": False, "error": "运行模式必须为稳健或激进。"}
        if "check_minutes" in payload:
            value = payload["check_minutes"]
            if isinstance(value, str) and value.isascii() and value.isdigit():
                value = int(value)
            if type(value) is not int or not 1 <= value <= 1440:
                return {"ok": False, "error": "检查间隔需为 1 到 1440 之间的整数分钟。"}
            payload["check_minutes"] = value
        if "run_mode" in payload:
            payload["check_minutes"] = profile_for(payload["run_mode"]).check_minutes

        def save():
            if self._store is not None and not (target_root / "settings.json").exists():
                from desktop.storage import initialize

                initialize(target_root, [])

            def change(_):
                # Normalize legacy danmaku/live_likes before removing their keys.
                config, _members = load_config(target_root)
                if self._store is not None:
                    config.pop("autostart", None)
                return {**config, **payload}

            try:
                update_json(target_root / "settings.json", change, {})
            except (OSError, ValueError, RuntimeError):
                logging.exception("Saving web settings failed")
                return {"ok": False, "error": "设置未能保存，请检查本机文件权限和配置。"}
            warning = ""
            if app_autostart is not None:
                try:
                    from desktop.windows import set_autostart

                    if not set_autostart(app_autostart):
                        warning = "设置已保存并应用，但 Windows 自启动未能修改。"
                except Exception:
                    logging.exception("Autostart change failed")
                    warning = "设置已保存并应用，但 Windows 自启动未能修改。"
            active_id = self._active_account_id()
            if target_id == active_id:
                try:
                    self._ui.apply_settings()
                except Exception:
                    logging.exception("Applying saved web settings failed")
                    return {"ok": False, "saved": True, "error": "设置已保存，但应用失败，请重试保存或查看活动记录。"}
            else:
                self._ui.push_now()
            result = {"ok": True}
            if warning:
                result["warning"] = warning
            return result

        return self._run("settings", save, allow_without_engine=True)

    def set_paused(self, paused):
        if type(paused) is not bool:
            return {"ok": False, "error": "暂停状态必须为 true 或 false。"}
        return self._pause(paused)

    def toggle_pause(self):
        return self._pause(None)

    def _pause(self, value):
        def change():
            paused = not bool(self._engine.paused) if value is None else value
            self._engine.set_paused(paused)
            return {"ok": True, "paused": paused}

        return self._run("pause", change)

    def check_now(self):
        def check():
            self._engine.check_now()
            return {"ok": True}

        return self._run("check", check)

    def resume_safety(self):
        def resume():
            ok, message = self._engine.resume_safety(confirmed=True)
            return {"ok": bool(ok), "message" if ok else "error": message}

        return self._run("safety", resume)

    def redo(self, room, task_type="all"):
        if task_type not in ("all", "danmaku", "like"):
            return {"ok": False, "error": "未知任务类型，请重新选择。"}

        def redo(row):
            result = self._engine.application.redo(row["room"], row.get("uid"), task_type) or {}
            ok = bool(result.get("success"))
            errors = [result.get("error")] + [(result.get(key) or {}).get("error") for key in ("danmaku", "like")]
            detail = "；".join(str(error) for error in errors if error) or "任务进度尚未确认完成"
            message = f"【{row.get('name', room)}】" + ("所选任务已确认完成" if ok else "任务未完成：" + detail)
            if ok:
                self._engine.check_now()
            return {"ok": ok, "message" if ok else "error": message}

        return self._room_action(room, "redo", redo)

    def reconnect(self, room):
        def reconnect(row):
            ok, message = self._engine.reconnect_room(row["room"])
            return {"ok": bool(ok), "message" if ok else "error": message}

        return self._room_action(room, "reconnect", reconnect)

    def wear_medal(self, room):
        def wear(row):
            result = self._engine.application.wear(row.get("uid"))
            if result == "ok":
                self._engine.check_now()
                return {"ok": True, "message": "粉丝牌已佩戴。"}
            return {"ok": False, "error": "没有可佩戴的粉丝牌，请先同步粉丝牌。" if result == "no_medal"
                    else "佩戴失败，请核对登录状态后重试。"}

        return self._room_action(room, "wear", wear)

    def remove_member(self, room):
        def remove(row):
            self._engine.application.remove_member(row["room"])
            self._ui.apply_settings()
            self._engine.check_now()
            return {"ok": True}

        return self._room_action(room, "remove", remove)

    def remove_members(self, rooms):
        if not isinstance(rooms, (list, tuple, set)):
            return {"ok": False, "error": "请选择要移除的主播。"}
        clean = []
        for r in rooms:
            try:
                clean.append(_positive_id(r))
            except Exception:
                pass
        if not clean:
            return {"ok": False, "error": "没有有效的主播房间号。"}

        def remove_all():
            removed = 0
            for room in clean:
                try:
                    self._engine.application.remove_member(room)
                    removed += 1
                except Exception:
                    logging.exception("Removing member failed: %s", room)
            self._ui.apply_settings()
            self._engine.check_now()
            return {"ok": True, "count": removed}

        return self._run(remove_all, kind="remove")

    def open_room(self, room):
        try:
            room = _positive_id(room)
            ok = webbrowser.open(f"https://live.bilibili.com/{room}")
        except Exception:
            logging.exception("Opening live room failed")
            ok = False
        return {"ok": bool(ok), **({} if ok else {"error": "无法打开直播间，请检查默认浏览器。"})}

    def open_logs(self, account_id=None):
        try:
            if not account_id or account_id == ALL_ACCOUNTS:
                root = self._host_root if self._host is not None else self._root
            else:
                root = self._account_root(account_id)
        except Exception:
            return {"ok": False, "error": "账号不存在或已被移除。"}
        try:
            os.startfile(str(root / "logs"))
        except (OSError, AttributeError):
            logging.exception("Opening log directory failed")
            return {"ok": False, "error": "无法打开日志目录。"}
        return {"ok": True}

    def resolve_member(self, query):
        if not isinstance(query, str) or not query.strip():
            return {"ok": False, "error": "请输入房间号、短号、UID 或直播间链接。"}

        def resolve():
            info = self._engine.application.resolve(query.strip())
            return {"ok": True, "member": info} if info else {
                "ok": False, "error": "没有找到对应主播，请核对房间号或链接。"}

        return self._run("resolve", resolve, mutating=False)

    def add_member(self, query):
        if not isinstance(query, str) or not query.strip():
            return {"ok": False, "error": "请输入房间号、短号、UID 或直播间链接。"}

        def add():
            info = self._engine.application.resolve(query.strip())
            if not info:
                return {"ok": False, "error": "没有找到对应主播，请核对房间号或链接。"}
            self._engine.application.add_members([info])
            self._ui.apply_settings()
            self._engine.check_now()
            return {"ok": True, "member": info}

        return self._run("add", add)

    def _fetch_medals(self):
        signature = _signature(self._root / "credentials.json")
        medals = self._engine.application.medals()
        if signature != _signature(self._root / "credentials.json"):
            raise ValueError("Login changed while fetching medals")
        members = read_json(self._root / "members.json", [])
        watched = {member["room"] for member in members}
        rows = [{**member, "watched": member["room"] in watched} for member in medals]
        rows.sort(key=lambda row: (row["watched"], -int(row.get("level") or 0), row["room"]))
        with self._cache_lock:
            self._medals_cache = signature, rows
        return rows

    def medals(self):
        def fetch():
            try:
                return {"ok": True, "medals": self._fetch_medals()}
            except (ValueError, RuntimeError):
                logging.exception("Fetching medal list failed")
                return {"ok": False, "need_login": True, "error": "粉丝牌读取失败，请检查登录和网络后重试。"}

        return self._run("medals", fetch, mutating=False)

    def import_medals(self, uids):
        try:
            if not isinstance(uids, list) or not uids:
                raise ValueError("No selection")
            selected = {_positive_id(uid) for uid in uids}
        except ValueError:
            return {"ok": False, "error": "请选择有效的粉丝牌主播。"}

        def import_selected():
            with self._cache_lock:
                cached = self._medals_cache
            rows = (cached[1] if cached and cached[0] == _signature(self._root / "credentials.json")
                    else self._fetch_medals())
            members = read_json(self._root / "members.json", [])
            watched = {member["room"] for member in members}
            additions = [member for member in rows if member["uid"] in selected and member["room"] not in watched]
            if not additions:
                return {"ok": False, "error": "没有可导入的新主播。"}
            self._engine.application.add_members(additions)
            self._ui.apply_settings()
            self._engine.check_now()
            return {"ok": True, "count": len(additions)}

        return self._run("import", import_selected)

    def avatar(self, uid, url="", account_id=None):
        try:
            uid = _positive_id(uid)
        except ValueError:
            return {"ok": False, "error": "主播编号无效。"}
        target_id = account_id or self._view_account_id()
        root = self._account_root(target_id)

        def fetch():
            # The renderer cannot turn this endpoint into arbitrary URL/UID IO.
            try:
                _config, members = load_config(root)
            except (OSError, ValueError):
                return {"ok": False, "error": "账号设置无法读取。"}
            if not any(member.get("uid") == uid for member in members):
                return {"ok": False, "error": "该主播已不在关注列表中。"}
            key = (target_id, uid)
            with self._cache_lock:
                cached = self._avatars.get(key)
                snap = self._last_snapshot or {}
                public_url = next((row.get("avatar_url", "") for row in snap.get("rows", [])
                                   if row.get("uid") == uid), "")
                if cached and time.monotonic() - cached[0] < 86400:
                    self._avatars.move_to_end(key)
                    return {"ok": True, "data_uri": cached[1]}
            from desktop.avatars import load_avatar

            image = load_avatar(root, uid, public_url or url)
            try:
                data_uri = _png_uri(image)
            finally:
                image.close()
            with self._cache_lock:
                self._avatars[key] = time.monotonic(), data_uri
                while len(self._avatars) > 64:
                    self._avatars.popitem(last=False)
            return {"ok": True, "data_uri": data_uri}

        return self._run(f"avatar:{target_id}:{uid}", fetch, mutating=False)

    def account_avatar(self, account_id=None):
        """The requested account's public avatar; the renderer never supplies a UID."""
        target_id = account_id or self._view_account_id() or self._active_account_id()
        if target_id == ALL_ACCOUNTS:
            target_id = self._active_account_id()
        try:
            root = self._account_root(target_id)
        except Exception:
            return {"ok": False, "error": "账号不存在或已被移除。"}

        def fetch():
            try:
                if self._store is not None and target_id:
                    present = self._store.has_credentials(target_id)
                else:
                    present, _error = self._credentials_present()
            except (OSError, ValueError, RuntimeError):
                return {"ok": False}
            if not present:
                return {"ok": False}
            from desktop.avatars import file_token, load_avatar, read_account_profile, save_account_profile

            binding = file_token(root / "credentials.json")
            profile = read_account_profile(root, binding)
            if not profile and self._engine is not None and target_id == self._active_account_id():
                approved = self._engine.application.account_profile()
                if approved and approved.get("uid"):
                    profile = {"uid": approved["uid"], "face": approved.get("face", "")}
                    save_account_profile(root, profile["uid"], profile["face"], binding)
            if not profile:
                return {"ok": False}
            uid = profile["uid"]
            key = (target_id, "account", uid)
            with self._cache_lock:
                cached = self._avatars.get(key)
                if cached and time.monotonic() - cached[0] < 86400:
                    self._avatars.move_to_end(key)
                    return {"ok": True, "data_uri": cached[1]}
            image = load_avatar(root, uid, profile["face"])
            try:
                data_uri = _png_uri(image)
            finally:
                image.close()
            with self._cache_lock:
                self._avatars[key] = (time.monotonic(), data_uri)
                while len(self._avatars) > 64:
                    self._avatars.popitem(last=False)
            return {"ok": True, "data_uri": data_uri}

        return self._run(f"account_avatar:{target_id}", fetch, mutating=False)

    # Cancellation invalidates a generation before waiting for any network IO.
    def _cancel_qr(self):
        with self._qr_lock:
            self._qr_generation += 1
            cancel, session = self._qr_cancel_event, self._qr_session
            if cancel is not None:
                cancel.set()
            self._qr_session = self._qr_cancel_event = None
            self._qr_target = None
            generation = self._qr_generation
        if session is not None:
            self._dispose_qr(session)
        return generation

    @staticmethod
    def _dispose_qr(session):
        try:
            session.cancel()
        except Exception:
            logging.exception("QR session cleanup failed")

    def _qr_current(self, generation, session, cancel):
        return (not self._closing.is_set() and not cancel.is_set()
                and generation == self._qr_generation and session is self._qr_session)

    def qr_start(self, account_id=None):
        account_id = account_id or None
        if account_id is not None:
            try:
                if self._store is not None:
                    self._store.get(account_id)
                elif account_id != getattr(self._engine, "account_id", ""):
                    raise ValueError("unknown account")
            except Exception:
                return {"ok": False, "error": "账号不存在或已被移除。"}
        with self._state:
            if self._closing.is_set():
                return {"ok": False, "error": "正在退出，当前不接受新操作。"}
            self._active += 1
        generation = self._cancel_qr()
        session = None
        started = False
        cancel = threading.Event()
        try:
            from bilioshi.qr_login import QrLoginSession

            session = QrLoginSession()
            with self._qr_lock:
                if self._closing.is_set() or generation != self._qr_generation:
                    return {"ok": False, "cancelled": True, "generation": generation}
                self._qr_session, self._qr_cancel_event = session, cancel
                self._qr_target = account_id
            data_uri = _qr_data_uri(session.generate())
            with self._qr_lock:
                if not self._qr_current(generation, session, cancel):
                    return {"ok": False, "cancelled": True, "generation": generation}
                with self._state:
                    self._active += 1
                try:
                    threading.Thread(target=self._qr_poll, args=(generation, session, cancel),
                                     name="web-qr", daemon=True).start()
                    started = True
                except Exception:
                    self._io_finished()
                    raise
            return {
                "ok": True,
                "data_uri": data_uri,
                "generation": generation,
                "account_id": account_id,
            }
        except Exception:
            logging.exception("QR session creation failed")
            return {"ok": False, "generation": generation,
                    "error": "无法连接 B 站登录服务，请检查网络后刷新二维码。"}
        finally:
            if session is not None and not started:
                with self._qr_lock:
                    if session is self._qr_session:
                        self._qr_session = self._qr_cancel_event = None
                self._dispose_qr(session)
            self._io_finished()

    def qr_refresh(self, account_id=None):
        return self.qr_start(account_id)

    def _emit_qr(self, generation, session, cancel, payload):
        with self._qr_lock:
            if self._qr_current(generation, session, cancel):
                self._ui.emit("qr_state", _public({
                    "generation": generation,
                    "account_id": self._qr_target,
                    **payload,
                }))

    def _complete_login(self, uid, account, profile, cookies, context, target_id):
        target_id = target_id or None
        sessdata, bili_jct = cookies["SESSDATA"], cookies["bili_jct"]
        face = profile.get("face", "")
        if self._store is None:
            from bilioshi.runtime import save_login
            from desktop.avatars import file_token, save_account_profile

            options = {"context": context} if context else {}
            save_login(sessdata, bili_jct, self._root / "credentials.json", **options)
            save_account_profile(
                self._root, uid, face,
                file_token(self._root / "credentials.json"),
            )
            self._ui.apply_settings()
            self._ui.push_now()
            return getattr(self._engine, "account_id", "")

        from bilioshi import safety
        from bilioshi.accounts import UnknownAccount
        from desktop.avatars import file_token, save_account_profile
        from desktop.storage import initialize

        try:
            existing = self._store.by_uid(uid)
        except UnknownAccount:
            existing = None
        if target_id is not None:
            target = self._store.get(target_id)
            if target["uid"] != uid:
                raise ValueError("扫码账号与目标账号不一致")
            account_id = target_id
            existing = target
        elif existing is not None:
            account_id = existing["id"]
        else:
            account_id = f"uid-{uid}"
            self._store.ensure_root(account_id, uid)
            self._store.restore_retained(account_id)
            initialize(self._store.path_for_id(account_id), [])

        root = self._store.path_for_id(account_id)
        options = {"context": context} if context else {}
        self._store.save_credentials(account_id, sessdata, bili_jct, **options)
        safety.bind_account(sessdata, uid, root)
        save_account_profile(root, uid, face, file_token(root / "credentials.json"))
        if existing is None:
            self._store.upsert(uid, account, face)
        else:
            self._store.update(account_id, name=account or existing.get("name", ""), face=face)
        # A QR refresh must not clear a platform protection hold that was
        # retained across logout or remove/re-add.
        if safety.status(sessdata, root).get("blocked"):
            self._store.update(account_id, status="blocked")
        if self._host is not None:
            if account_id == self._active_account_id():
                self._host.reload_account(account_id)
            self._host.view(account_id)
        else:
            self._ui.apply_settings()
        self._ui.push_now()
        return account_id

    def _qr_poll(self, generation, session, cancel):
        from bilioshi.qr_login import POLL_INTERVAL

        try:
            while not cancel.wait(POLL_INTERVAL):
                result = session.poll()
                with self._qr_lock:
                    if not self._qr_current(generation, session, cancel):
                        return
                if result.state == "confirmed":
                    cookies = result.credentials
                    from bilioshi import safety

                    if self._store is None and self._engine is not None:
                        # Legacy single-root mode keeps the historical validation
                        # seam; account mode validates in a throwaway root below.
                        valid, account, profile = (
                            self._engine.application.validate_credentials_profile(
                                cookies["SESSDATA"], cookies["bili_jct"])
                        )
                    else:
                        from bilioshi.account_migration import validate_credentials_readonly

                        valid, account, profile = validate_credentials_readonly(
                            cookies["SESSDATA"], cookies["bili_jct"])
                    if not valid or not isinstance(profile, dict) or not profile.get("uid"):
                        self._emit_qr(generation, session, cancel, {
                            "state": "error", "message": "扫码已确认，但登录验证未通过，请重新扫码。"})
                        return
                    uid = int(profile["uid"])
                    with self._mutations:
                        with self._qr_lock:
                            if not self._qr_current(generation, session, cancel):
                                return
                            target_id = self._qr_target
                        try:
                            account_id = self._complete_login(
                                uid, account, profile, cookies, result.context, target_id)
                        except Exception:
                            logging.exception("Saving QR login failed")
                            self._emit_qr(generation, session, cancel, {
                                "state": "error",
                                "message": "扫码成功，但账号保存失败，请检查本机权限后重试。",
                            })
                            return
                        self._sync_active()
                        if self._engine is not None and account_id == self._active_account_id():
                            self._engine.confirm_account(account)
                        self._emit_qr(generation, session, cancel, {
                            "state": "confirmed",
                            "account": account,
                            "account_id": account_id,
                        })
                    return
                if result.state not in ("waiting", "scanned", "expired"):
                    raise ValueError("Unexpected QR state")
                self._emit_qr(generation, session, cancel, {"state": result.state})
                if result.state == "expired":
                    return
        except Exception:
            logging.exception("QR polling failed")
            self._emit_qr(generation, session, cancel, {
                "state": "error", "message": "扫码登录失败，请刷新二维码重试。"})
        finally:
            self._dispose_qr(session)
            self._io_finished()

    def qr_cancel(self):
        return {"ok": True, "generation": self._cancel_qr()}

    def logout(self, account_id=None):
        self._cancel_qr()

        def logout():
            self._cancel_qr()
            if self._store is not None:
                target = account_id or self._active_account_id() or self._view_account_id()
                if not target:
                    return {"ok": False, "error": "当前没有可退出的账号。"}
                try:
                    self._store.clear_credentials(target)
                except Exception:
                    return {"ok": False, "error": "退出登录失败，请稍后重试。"}
                from desktop.avatars import clear_account_profile

                clear_account_profile(self._store.account_root(target))
                if self._host is not None:
                    self._host.reload_account(target)
                    self._sync_active()
                with self._cache_lock:
                    self._avatars.clear()
                self._ui.push_now()
                return {"ok": True}
            from bilioshi.runtime import save_login
            from desktop.avatars import clear_account_profile

            save_login("", "", self._root / "credentials.json")
            clear_account_profile(self._root)
            with self._cache_lock:
                for key in [key for key in self._avatars if isinstance(key, tuple)]:
                    self._avatars.pop(key, None)
            self._ui.apply_settings()
            return {"ok": True}

        return self._run("logout", logout, allow_without_engine=True)

    def _set_ui_error(self, message):
        with self._state:
            self._ui_error = message

    def _io_finished(self):
        with self._state:
            self._active -= 1
            self._state.notify_all()

    def _begin_shutdown(self):
        # Match _run's admission lock so shutdown cannot overlook an accepted call.
        with self._state:
            self._closing.set()
        self._cancel_qr()

    def _wait_for_io(self):
        with self._state:
            self._state.wait_for(lambda: self._active == 0)

    def window(self, action):
        try:
            if action == "state":
                return self._ui.window_state()
            methods = {"minimize": self._ui.minimize, "maximize": self._ui.toggle_maximize,
                       "close": self._ui.close_window, "show": self._ui.show,
                       "exit": self._ui.quit, "quit": self._ui.quit}
            method = methods.get(action)
            if method is None:
                return {"ok": False, "error": "未知窗口操作。"}
            result = method()
            return {"ok": result is not False}
        except Exception:
            logging.exception("Window action failed")
            return {"ok": False, "error": "窗口操作失败，请重试。"}

    def quit(self):
        return self.window("quit")

    def version(self):
        from bilioshi.runtime import APP_VERSION

        return {"version": APP_VERSION}
