"""Per-account Engine ownership and install-root lifecycle.

The host owns the install root, one Engine/Job per account, the active and
viewed account ids, and an independent health writer. Account Engines never
own supervisor/command/health files.
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from bilioshi.accounts import AccountStore, UnknownAccount
from bilioshi.members import load_account_members
from bilioshi.runtime import FileLock, read_json, update_json
from desktop.engine import Engine
from desktop.storage import initialize
from desktop.windows import Job


class HostError(RuntimeError):
    pass


class AccountBusy(HostError):
    pass


class AccountHost:
    def __init__(self, root, store=None, *, engine_factory=Engine, job_factory=Job):
        self.root = Path(root)
        self.store = store if store is not None else AccountStore(self.root)
        self.engine_factory = engine_factory
        self.job_factory = job_factory
        self.engines = {}
        self.locks = {}
        self.active_id = self.store.active_id
        self.view_id = self.store.view_id
        self.global_paused = self.store.global_paused
        self._resume_ids = []
        self._switch_lock = threading.RLock()
        self._state_lock = threading.RLock()
        self.stopping = threading.Event()
        self.health_thread = None
        self.started_at = time.time()
        self.last_health_publish = 0
        self.last_tick = 0
        self.publish_error = ""
        self._started = False

    # ---------- lifecycle ----------

    def start(self):
        if self._started:
            return
        self._started = True
        self._start_health()
        if self.active_id:
            try:
                self._activate_startup(self.active_id)
            except (HostError, OSError, ValueError, RuntimeError):
                logging.exception("Cannot start active account %s", self.active_id)
                self.active_id = None

    def _activate_startup(self, account_id):
        row = self.store.get(account_id)
        if row["status"] != "ok" or not self.store.has_credentials(account_id):
            if row["status"] == "ok":
                self.store.mark_needs_login(account_id)
            return
        engine = self._ensure_engine(account_id)
        engine.start()
        if self.global_paused or row["status"] != "ok":
            if self.global_paused and not engine.paused:
                self._resume_ids = [account_id]
            engine.suspend("global_paused" if self.global_paused else "account_unavailable")

    def _start_health(self):
        self.health_thread = threading.Thread(
            target=self._health_loop,
            name="account-health",
            daemon=True,
        )
        self.health_thread.start()

    def _health_loop(self):
        while not self.stopping.wait(5):
            self._publish_health()

    def _publish_health(self):
        now = time.time()
        engine = self.engines.get(self.active_id) if self.active_id else None
        # Health fields must stay fresh even while an account is suspended or a
        # long worker shutdown is in progress; the supervisor watches this file
        # and must not mistake an idle account for a dead desktop.
        payload = {
            "pid": os.getpid(),
            "started": self.started_at,
            "updated": now,
            "last_tick": now,
            "last_status_publish": now,
            "publish_error": self.publish_error,
        }
        try:
            from bilioshi.runtime import write_json

            write_json(self.root / "monitor-health.json", payload)
            self.last_health_publish = now
        except OSError:
            logging.warning("Cannot publish host monitor health")
        self._publish_status_mirror(engine)

    def _publish_status_mirror(self, engine):
        if engine is None:
            return
        try:
            status = read_json(engine.root / "status.json", {})
        except (OSError, ValueError):
            return
        if not isinstance(status, dict):
            return
        status = {
            **status,
            "account_id": self.active_id,
            "mirror": True,
        }
        try:
            from bilioshi.runtime import write_json

            write_json(self.root / "status.json", status)
        except OSError:
            logging.warning("Cannot publish host status mirror")

    def _ensure_engine(self, account_id):
        row = self.store.get(account_id)
        engine = self.engines.get(account_id)
        if engine is not None:
            return engine
        account_root = self.store.ensure_root(account_id, row["uid"])
        initialize(account_root, [])
        lock = FileLock(account_root / "locks" / "engine.lock", timeout=0)
        if not lock.acquired:
            lock.close()
            raise AccountBusy("此账号正在被另一个进程使用")
        try:
            engine = self.engine_factory(
                account_root,
                job=self.job_factory(),
                account_id=account_id,
            )
        except Exception:
            lock.close()
            raise
        with self._state_lock:
            self.engines[account_id] = engine
            self.locks[account_id] = lock
        return engine

    def _close_engine(self, account_id):
        with self._state_lock:
            engine = self.engines.pop(account_id, None)
            lock = self.locks.pop(account_id, None)
        if engine is not None:
            try:
                engine.close()
            except Exception:
                logging.exception("Cannot close account engine %s", account_id)
        if lock is not None:
            lock.close()

    def _start_engine(self, account_id):
        engine = self._ensure_engine(account_id)
        if not engine._started:
            engine.start()
        return engine

    # ---------- account selection ----------

    def active_engine(self):
        with self._state_lock:
            return self.engines.get(self.active_id)

    def engine_for(self, account_id):
        with self._state_lock:
            return self.engines.get(account_id)

    def view(self, account_id):
        if account_id is not None:
            self.store.get(account_id)
        self.store.set_view(account_id)
        self.view_id = account_id
        return self.view_id

    def switch_to(self, account_id):
        """Suspend the old account and activate the target without a QR flow."""
        if self.store.mode != "single":
            raise HostError("第一期只支持单账号运行")
        if self.global_paused:
            raise HostError("全局暂停中，请先恢复全部")
        row = self.store.get(account_id)
        if row["status"] != "ok":
            raise HostError("此账号需要重新登录")
        if not self.store.has_credentials(account_id):
            self.store.mark_needs_login(account_id)
            raise HostError("此账号需要重新登录")
        with self._switch_lock:
            if self.active_id == account_id:
                engine = self.active_engine()
                if engine is not None and not engine.suspended:
                    self.view(account_id)
                    return account_id
            old_id = self.active_id
            old_engine = self.active_engine()
            # Build before suspending so a bad config cannot stop the current account.
            target = self._ensure_engine(account_id)
            if old_engine is not None and old_id != account_id:
                old_engine.suspend("account_switch")
            try:
                if not target._started:
                    target.start()
                target.activate()
            except Exception:
                if old_engine is not None and old_id != account_id:
                    try:
                        old_engine.activate()
                    except Exception:
                        logging.exception("Cannot roll back account %s", old_id)
                raise
            self.active_id = account_id
            self.view_id = account_id
            self.store.set_active(account_id)
            self.store.set_view(account_id)
            target.check_now()
            return account_id

    def set_account_paused(self, account_id, paused):
        self.store.get(account_id)
        engine = self.engine_for(account_id)
        if engine is not None:
            engine.set_paused(paused)
            return
        update_json(
            self.store.account_root(account_id) / "settings.json",
            lambda settings: {**(settings or {}), "paused": bool(paused)},
            {},
        )

    def set_global_paused(self, paused):
        paused = bool(paused)
        with self._switch_lock:
            if paused == self.global_paused:
                return
            if paused:
                running = []
                for account_id, engine in list(self.engines.items()):
                    if not engine.suspended and not engine.paused:
                        running.append(account_id)
                self._resume_ids = running
                engine = self.active_engine()
                if engine is not None and not engine.suspended:
                    engine.suspend("global_paused")
            self.global_paused = paused
            self.store.set_global_paused(paused)
            if not paused:
                resume = list(self._resume_ids)
                self._resume_ids = []
                for account_id in resume:
                    row = self.store.get(account_id)
                    if row["status"] != "ok" or not self.store.has_credentials(account_id):
                        continue
                    engine = self.engines.get(account_id)
                    if engine is None:
                        continue
                    if engine.paused:
                        continue
                    try:
                        if not engine._started:
                            engine.start()
                        engine.activate()
                    except Exception:
                        logging.exception("Cannot resume account %s", account_id)

    def keep_alive(self):
        """Compatibility hook for hosts that want a health write on demand."""
        self._publish_health()

    # ---------- accounts ----------

    def account_summary(self, account_id):
        row = self.store.get(account_id)
        root = self.store.account_root(account_id)
        try:
            settings = read_json(root / "settings.json", {})
        except (OSError, ValueError):
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        engine = self.engine_for(account_id)
        status = None
        try:
            status = read_json(root / "status.json", {})
        except (OSError, ValueError):
            status = {}
        if not isinstance(status, dict):
            status = {}
        members = load_account_members(root)
        running = (
            self.active_id == account_id
            and engine is not None
            and not engine.suspended
            and not engine.paused
            and not self.global_paused
            and row["status"] == "ok"
        )
        paused = bool(engine.paused) if engine is not None else bool(settings.get("paused"))
        if row["status"] == "needs_login" or not self.store.has_credentials(account_id):
            state = "needs_login"
        elif row["status"] == "blocked":
            state = "protection"
        elif self.global_paused:
            state = "global_paused"
        elif running:
            state = "running"
        elif paused:
            state = "paused"
        else:
            state = "idle"
        rows = status.get("rows") if isinstance(status.get("rows"), list) else []
        live = sum(
            1 for item in rows
            if isinstance(item, dict) and item.get("live_status") == 1
        )
        return {
            **row,
            "signed_in": self.store.has_credentials(account_id),
            "running": running,
            "paused": paused,
            "state": state,
            "room_count": len(members),
            "live_room_count": live,
            "snapshot_at": status.get("updated", 0),
            "stale": bool(status.get("stale") or status.get("exited")),
            "safety": status.get("safety") or {"blocked": False},
            "account": status.get("account", ""),
        }

    def summaries(self):
        return [self.account_summary(row["id"]) for row in self.store.accounts()]

    def reload_account(self, account_id):
        """Rebuild an Engine after its credential envelope changed."""
        was_active = self.active_id == account_id
        self._close_engine(account_id)
        if was_active:
            row = self.store.get(account_id)
            if row["status"] == "ok" and self.store.has_credentials(account_id):
                engine = self._ensure_engine(account_id)
                engine.start()
                if self.global_paused:
                    engine.suspend("global_paused")
                else:
                    engine.activate()

    def remove_account(self, account_id):
        self.store.get(account_id)
        was_active = self.active_id == account_id
        self._close_engine(account_id)
        if was_active:
            self.active_id = None
            self.store.set_active(None)
        self.store.remove(account_id)
        if self.view_id == account_id:
            self.view_id = self.store.view_id

    # ---------- shutdown ----------

    def close(self):
        self.stopping.set()
        with self._state_lock:
            ids = list(self.engines)
        threads = []
        for account_id in ids:
            thread = threading.Thread(target=self._close_engine, args=(account_id,), daemon=True)
            thread.start()
            threads.append(thread)
        deadline = time.monotonic() + 12
        for thread in threads:
            thread.join(timeout=max(0.1, deadline - time.monotonic()))
        with self._state_lock:
            remaining = list(self.engines)
        for account_id in remaining:
            logging.warning("Account engine did not stop in time: %s", account_id)
            self._close_engine(account_id)
        if self.health_thread is not None and self.health_thread.is_alive():
            self.health_thread.join(timeout=2)
