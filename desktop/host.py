"""Per-account Engine ownership and install-root lifecycle.

The host owns the install root, one Engine/Job per account, the active and
viewed account ids, and an independent health writer. Account Engines never
own supervisor/command/health files.
"""

import json
import logging
import os
import random
import threading
import time
from pathlib import Path

from bilioshi.accounts import ALL_ACCOUNTS, AccountStore, UnknownAccount
from bilioshi.members import load_account_members
from bilioshi.runtime import FileLock, file_stat_signature, read_json, update_json
from bilioshi.safety import blocks_watch, describe_hold
from desktop.engine import Engine
from desktop.storage import initialize
from desktop.windows import Job

MAX_CONCURRENT_ACCOUNTS = 3


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
        self._mirror_sig = None
        self._started = False

    # ---------- lifecycle ----------

    def start(self):
        if self._started:
            return
        self._started = True
        self._start_health()
        if self.store.mode == "concurrent":
            ordered = []
            if self.active_id:
                ordered.append(self.active_id)
            for row in self.store.accounts():
                if row["watch_enabled"] and row["id"] not in ordered:
                    ordered.append(row["id"])
            started_index = 0
            for account_id in ordered:
                if started_index >= MAX_CONCURRENT_ACCOUNTS:
                    break
                try:
                    if self._activate_startup(account_id, stagger_index=started_index):
                        started_index += 1
                except (HostError, OSError, ValueError, RuntimeError):
                    logging.exception("Cannot start concurrent account %s", account_id)
            if self.active_id and self.active_id not in self.engines:
                next_active = next(iter(self.engines), None)
                self.active_id = next_active
                try:
                    self.store.set_active(next_active)
                except Exception:
                    pass
        elif self.active_id:
            try:
                self._activate_startup(self.active_id)
            except (HostError, OSError, ValueError, RuntimeError):
                logging.exception("Cannot start active account %s", self.active_id)
                self.active_id = None

    def _activate_startup(self, account_id, *, stagger_index=0):
        row = self.store.get(account_id)
        if row["status"] != "ok" or not self.store.has_credentials(account_id):
            if row["status"] == "ok":
                self.store.mark_needs_login(account_id)
            return False
        engine = self._ensure_engine(account_id)
        if stagger_index > 0 and hasattr(engine, "stagger_initial_check"):
            engine.stagger_initial_check(stagger_index * 15.0 + random.uniform(1.0, 4.0))
        engine.start()
        if self.global_paused and not engine.paused:
            if account_id not in self._resume_ids:
                self._resume_ids.append(account_id)
            engine.suspend("global_paused")
        elif row["status"] != "ok":
            engine.suspend("account_unavailable")
        return True

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
        source = engine.root / "status.json"
        sig = (str(engine.root), file_stat_signature(source))
        if sig == self._mirror_sig and (self.root / "status.json").exists():
            return
        try:
            status = read_json(source, {})
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
            self._mirror_sig = sig
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

    def active_engine_ids(self):
        with self._state_lock:
            return [
                aid
                for aid, eng in self.engines.items()
                if eng is not None and getattr(eng, "_started", False) and not eng.suspended
            ]

    def view(self, account_id):
        if account_id is not None and account_id != ALL_ACCOUNTS:
            self.store.get(account_id)
        self.store.set_view(account_id)
        self.view_id = account_id
        return self.view_id

    def switch_to(self, account_id, *, exclusive=False):
        """Focus or activate target account; keep background accounts running in concurrent mode."""
        if self.global_paused:
            raise HostError("全局暂停中，请先恢复全部")
        row = self.store.get(account_id)
        if row["status"] == "blocked":
            raise HostError("此账号处于保护暂停状态，请先排查恢复")
        if row["status"] != "ok":
            raise HostError("此账号需要重新登录")
        if not self.store.has_credentials(account_id):
            self.store.mark_needs_login(account_id)
            raise HostError("此账号需要重新登录")
        with self._switch_lock:
            concurrent = self.store.mode == "concurrent" and not exclusive
            if self.active_id == account_id and not exclusive:
                engine = self.active_engine()
                if engine is not None and not engine.suspended:
                    self.view(account_id)
                    return account_id
            if concurrent:
                others = [aid for aid in self.active_engine_ids() if aid != account_id]
                existing_engine = self.engine_for(account_id)
                already_up = existing_engine is not None and not existing_engine.suspended
                if not already_up and len(others) >= MAX_CONCURRENT_ACCOUNTS:
                    raise HostError(
                        f"为降低同网络出口关联风控风险，最多支持 {MAX_CONCURRENT_ACCOUNTS} 个账号同时挂机，请先停止一个运行中的账号"
                    )
                target = self._ensure_engine(account_id)
                if not target._started:
                    if others and hasattr(target, "stagger_initial_check"):
                        target.stagger_initial_check(random.uniform(2.5, 5.0))
                    target.start()
                if target.suspended:
                    target.activate()
                self.store.set_watch_enabled(account_id, True)
                self.store.set_active_view(account_id)
                self.active_id = account_id
                self.view_id = account_id
                if not already_up:
                    target.check_now()
                return account_id

            old_id = self.active_id
            old_engine = self.active_engine()
            other_engines = [
                (aid, eng)
                for aid, eng in list(self.engines.items())
                if aid != account_id and eng is not None and not eng.suspended
            ]
            # Build before suspending so a bad config cannot stop the current account.
            target = self._ensure_engine(account_id)
            for _, eng in other_engines:
                eng.suspend("account_switch")
            try:
                if not target._started:
                    target.start()
                target.activate()
            except Exception:
                for aid, eng in other_engines:
                    try:
                        eng.activate()
                    except Exception:
                        logging.exception("Cannot roll back account %s", aid)
                raise
            try:
                if exclusive and self.store.mode != "single":
                    for item in self.store.accounts():
                        if item["watch_enabled"] != (item["id"] == account_id):
                            self.store.set_watch_enabled(item["id"], item["id"] == account_id)
                    self.store.set_mode("single")
                self.store.set_active_view(account_id)
            except Exception:
                try:
                    if target is not old_engine:
                        target.suspend("switch_failed")
                    for _, eng in other_engines:
                        eng.activate()
                except Exception:
                    logging.exception("Cannot roll back a failed account switch")
                raise
            self.active_id = account_id
            self.view_id = account_id
            target.check_now()
            return account_id

    def set_account_running(self, account_id, enabled):
        """Independently start or stop background watch for one account."""
        enabled = bool(enabled)
        with self._switch_lock:
            row = self.store.get(account_id)
            if enabled:
                if self.global_paused:
                    raise HostError("全局暂停中，请先恢复全部")
                if row["status"] == "blocked":
                    raise HostError("此账号处于保护暂停状态，请先排查恢复")
                if row["status"] != "ok" or not self.store.has_credentials(account_id):
                    if row["status"] == "ok":
                        self.store.mark_needs_login(account_id)
                    raise HostError("此账号需要重新登录")
                others = [aid for aid in self.active_engine_ids() if aid != account_id]
                if len(others) >= MAX_CONCURRENT_ACCOUNTS:
                    raise HostError(
                        f"为降低同网络出口关联风控风险，最多支持 {MAX_CONCURRENT_ACCOUNTS} 个账号同时挂机"
                    )
                target = self._ensure_engine(account_id)
                already_up = bool(target._started and not target.suspended)
                if not target._started:
                    if others and hasattr(target, "stagger_initial_check"):
                        target.stagger_initial_check(random.uniform(2.5, 5.0))
                    target.start()
                if target.suspended:
                    target.activate()
                if target.paused:
                    target.set_paused(False)
                if others:
                    if self.store.mode != "concurrent":
                        self.store.set_mode("concurrent")
                    for aid in others:
                        if not self.store.get(aid).get("watch_enabled"):
                            self.store.set_watch_enabled(aid, True)
                self.store.set_watch_enabled(account_id, True)
                if self.active_id is None or self.view_id in (None, account_id):
                    self.store.set_active_view(account_id)
                    self.active_id = account_id
                    self.view_id = account_id
                if not already_up:
                    target.check_now()
                return account_id

            self.store.set_watch_enabled(account_id, False)
            self._close_engine(account_id)
            self._resume_ids = [item for item in self._resume_ids if item != account_id]
            remaining = self.active_engine_ids()
            if self.active_id == account_id:
                next_active = remaining[0] if remaining else None
                self.active_id = next_active
                self.store.set_active(next_active)
            return self.active_id

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
                # An individually paused account was not running, so it must
                # stay paused rather than becoming suspended; every running
                # engine across concurrent accounts must be suspended cleanly.
                for account_id in running:
                    eng = self.engines.get(account_id)
                    if eng is not None and not eng.suspended and not eng.paused:
                        eng.suspend("global_paused")
            self.global_paused = paused
            self.store.set_global_paused(paused)
            if not paused:
                resume = list(self._resume_ids)
                self._resume_ids = []
                for account_id in resume:
                    try:
                        row = self.store.get(account_id)
                    except UnknownAccount:
                        # The account was removed while globally paused.
                        continue
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
        safety_data = (
            getattr(engine, "safety", None) if engine is not None else status.get("safety")
        ) or {"blocked": False}
        blocked = blocks_watch(safety_data) or (row["status"] == "blocked" and engine is None)
        engine_active = (
            engine is not None
            and getattr(engine, "_started", False)
            and not engine.suspended
            and not self.global_paused
            and row["status"] == "ok"
        )
        running = (
            engine_active
            and not engine.paused
            and not blocks_watch(safety_data)
        )
        paused = bool(engine.paused) if engine is not None else bool(settings.get("paused"))
        if blocked:
            state = "protection"
        elif row["status"] == "needs_login" or not self.store.has_credentials(account_id):
            state = "needs_login"
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
        gain = None
        for item in rows:
            if not isinstance(item, dict):
                continue
            value = item.get("intimacy_gain")
            if isinstance(value, (int, float)):
                gain = value if gain is None else gain + value
        if safety_data.get("blocked") and "steps" not in safety_data:
            safety_data = {**safety_data, **describe_hold(safety_data, members)}
        return {
            **row,
            "signed_in": self.store.has_credentials(account_id),
            "engine_active": engine_active,
            "running": running,
            "paused": paused,
            "global_paused": self.global_paused,
            "state": state,
            "room_count": len(members),
            "live_room_count": live,
            "gain": gain,
            "snapshot_at": status.get("updated", 0),
            "stale": bool(status.get("stale") or status.get("exited")),
            "safety": safety_data,
            "account": status.get("account", ""),
        }

    def summaries(self):
        return [self.account_summary(row["id"]) for row in self.store.accounts()]

    def reload_account(self, account_id):
        """Rebuild an Engine after its credential envelope changed."""
        existing = self.engine_for(account_id)
        was_running = (self.active_id == account_id) or (
            existing is not None and not existing.suspended
        )
        self._close_engine(account_id)
        row = self.store.get(account_id)
        if not self.store.has_credentials(account_id):
            if row.get("watch_enabled"):
                self.store.set_watch_enabled(account_id, False)
            if self.active_id == account_id:
                remaining = self.active_engine_ids()
                if remaining:
                    self.active_id = remaining[0]
                    self.store.set_active_view(self.active_id)
                    self.view_id = self.active_id
            return
        if was_running and row["status"] == "ok":
            engine = self._ensure_engine(account_id)
            engine.start()
            if self.global_paused:
                engine.suspend("global_paused")
            else:
                engine.activate()

    def remove_account(self, account_id):
        with self._switch_lock:
            self.store.get(account_id)
            was_active = self.active_id == account_id
            self._close_engine(account_id)
            self._resume_ids = [item for item in self._resume_ids if item != account_id]
            remaining = self.active_engine_ids()
            if was_active:
                next_active = remaining[0] if remaining else None
                self.active_id = next_active
                self.store.set_active(next_active)
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
