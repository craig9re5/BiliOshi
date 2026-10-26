"""One daily scheduler/dispatcher shared by GUI and CLI; all IO stays off Tk."""

import hashlib
import logging
from pathlib import Path
import threading
import time
import uuid

from ..runtime import FileLock, read_json
from ..safety import identity
from . import settings, transport
from .. import notifications
from .outbox import Outbox
from .summary import collect, compose, local_time


def fingerprint(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def destination_key(token, config):
    return fingerprint(f"{token}:{config['anonymous']}")


class DailyNotifications:
    def __init__(self, root, *, collector=collect, sender=transport.send, clock=time.time):
        self.root = Path(root)
        self.collector, self.sender, self.clock = collector, sender, clock
        self.stopping = threading.Event()
        self.thread = None
        self.error = ""
        self.next_tick = 0

    def start(self):
        if not notifications.AVAILABLE:
            return
        if self.thread is None:
            self.thread = threading.Thread(target=self.run, name="daily-notifications", daemon=True)
            self.thread.start()

    def stop(self):
        self.stopping.set()

    def join(self, timeout=None):
        if self.thread is not None:
            self.thread.join(timeout)

    def run(self):
        if not notifications.AVAILABLE:
            return
        while not self.stopping.is_set():
            try:
                self.tick()
                self.error = ""
            except Exception as exc:
                # Background boundary: expose only the type, not URLs, responses or secrets.
                self.error = f"每日总结后台异常（{type(exc).__name__}），请检查本机配置"
                logging.warning("Daily notification failed: %s", type(exc).__name__)
            self.stopping.wait(15)

    def _account(self):
        try:
            saved = read_json(self.root / "credentials.json", {})
            return identity(saved["SESSDATA"], self.root) if saved.get("SESSDATA") else "unconfigured"
        except (OSError, ValueError, RuntimeError):
            return "unavailable"

    def preview(self):
        config = settings.load(self.root)
        with FileLock(self.root / "locks/daily-notification.lock") as lease:
            if not lease.acquired:
                raise ValueError("每日总结正在查询或发送，请稍后预览")
            members, result, now, _ = self.collector(self.root)
        return compose(members, result, now, anonymous=config["anonymous"])

    def queue_test(self):
        if not notifications.AVAILABLE:
            raise ValueError(notifications.UNAVAILABLE_REASON)
        with FileLock(self.root / "locks/daily-notification.lock") as lease:
            if not lease.acquired:
                raise ValueError("每日总结正在处理，请稍后测试")
            return self._queue_test()

    def _queue_test(self):
        # Only a deliberate GUI/CLI test calls this. It never queries Bilibili.
        config, saved = settings.load(self.root), settings.token(self.root)
        if not saved:
            raise ValueError("请先保存 PushPlus 消息 Token")
        now = self.clock()
        box = Outbox(self.root)
        if box.control("blocked"):
            raise ValueError("通知通道已暂停，请修复配置后点击恢复通知")
        if box.status(now)["pending"]:
            raise ValueError("已有待发消息，请等待结果后再测试")
        message = {"day": local_time(now).date().isoformat(),
                   "title": "测试日报｜已核验+12｜2/2房",
                   "content": "BiliOshi 每日总结测试（合成数据）\n主播1：今日+7\n主播2：今日+5\n此消息不代表真实收益。请在手机确认 QQ 通知。"}
        box.enqueue("test:" + uuid.uuid4().hex, "test", "test", destination_key(saved, config), message, now, now + 600)
        return "测试已排队；服务受理不代表手机已收到"

    def resume(self):
        if not notifications.AVAILABLE:
            raise ValueError(notifications.UNAVAILABLE_REASON)
        if not settings.token(self.root):
            raise ValueError("请先配置 PushPlus Token")
        Outbox(self.root).set_control("blocked", "")
        return "通知通道已恢复；已受理或结果未知的消息不会重新发送"

    def status(self):
        value = Outbox(self.root).status(self.clock())
        try:
            value.update(config=settings.load(self.root), configured=bool(settings.token(self.root)))
        except (OSError, ValueError, RuntimeError):
            value.update(config=settings.DEFAULTS, configured=False)
            value["error"] = "通知配置无法读取，请重新保存"
        value["error"] = value.get("error") or self.error
        return value

    def tick(self):
        if not notifications.AVAILABLE:
            return
        now = self.clock()
        with FileLock(self.root / "locks/daily-notification.lock") as lease:
            if not lease.acquired:
                return
            self._tick(now)

    def _tick(self, now):
        config, saved = settings.load(self.root), settings.token(self.root)
        if not saved:
            return
        destination, account = destination_key(saved, config), self._account()
        box = Outbox(self.root)
        box.maintain(now, destination, account, config["enabled"])
        if box.control("blocked") or self.stopping.is_set():
            return
        day = local_time(now).date().isoformat()
        key = f"daily:{account}:{day}"
        if config["enabled"] and local_time(now).strftime("%H:%M") >= config["summary_at"] and not box.contains(key):
            self._schedule(box, key, account, destination, config, now)
        # Configuration/login changes during IO invalidate the queued summary.
        if self.stopping.is_set():
            return
        current = settings.load(self.root)
        current_token = settings.token(self.root)
        if current != config or destination_key(current_token, current) != destination or self._account() != account:
            return
        posted_at = self.clock()
        box.maintain(posted_at, destination, account, config["enabled"])
        message = box.claim(posted_at)
        if message is None:
            return
        try:
            outcome = self.sender(saved, message)
        except Exception:
            outcome = {"state": "unknown", "reason": "提交异常，结果未知；不会自动重发"}
        box.finish(message, outcome, self.clock())

    def _schedule(self, box, key, account, destination, config, now):
        try:
            members, result, observed, observed_account = self.collector(self.root)
        except Exception:
            # Daily report still explains unavailable data, without sending error text.
            from ..members import load_members
            members, result, observed, observed_account = load_members(self.root), {"error": True}, self.clock(), account
        if observed_account != account or self._account() != account or local_time(now).date() != local_time(observed).date():
            return
        message = compose(members, result, observed, anonymous=config["anonymous"])
        tomorrow = local_time(observed).replace(hour=0, minute=0, second=0, microsecond=0).timestamp() + 86400
        box.enqueue(key, "daily", account, destination, message, observed, tomorrow)
