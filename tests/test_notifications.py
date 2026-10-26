import json
import socket
import tempfile
import threading
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

from bilioshi.notifications import settings, transport
from bilioshi.notifications.outbox import Outbox
from bilioshi.notifications.service import DailyNotifications, destination_key
from bilioshi.notifications.summary import ZONE, collect, compose, local_time
from bilioshi.runtime import FileLock, read_json, write_json
from bilioshi.redaction import redact
from bilioshi.safety import identity


def instant(text="2026-10-12 23:50:00"):
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZONE).timestamp()


MEMBERS = [{"name": "测试主播A", "uid": 1, "room": 2}, {"name": "测试主播B", "uid": 3, "room": 4}]


def observation(now):
    return {"observed": now, "medals": {"1": {"today_intimacy": 7}, "3": {"today_intimacy": 5}},
            "statuses": {"2": {"live_status": 1}},
            "tasks": {"2": {"day": local_time(now).date().isoformat(), "updated": now,
                            "intimacy": 9999,
                            "tasks": [{"jump_type": "watchLive", "sub_title": "每日上限 1/10", "title": "观看直播", "is_done": False},
                                      {"title": "发弹幕", "is_done": True}]}}}


class SummaryTests(unittest.TestCase):
    def test_verified_daily_counters_and_task_progress_are_separate(self):
        result = compose(MEMBERS, observation(instant()), instant())
        self.assertEqual(result["total"], 12)
        self.assertEqual(result["verified"], 2)
        self.assertIn("看播1/10", result["content"])
        self.assertIn("仍在播", result["content"])
        self.assertNotIn("9999", result["content"])

    def test_missing_counter_is_unknown_even_when_all_tasks_complete(self):
        data = observation(instant())
        data["medals"]["1"] = {"today_intimacy": None}
        result = compose(MEMBERS, data, instant())
        self.assertEqual((result["total"], result["verified"]), (5, 1))
        self.assertIn("测试主播A：今日待核验", result["content"])
        self.assertIn("待核验", result["title"])

    def test_cross_day_and_stale_data_do_not_become_zero_income(self):
        for observed in (instant() - 14 * 60, instant("2026-10-11 23:59:59")):
            result = compose(MEMBERS, observation(observed), instant())
            self.assertEqual(result["verified"], 0)
            self.assertIn("今日待核验", result["content"])

    def test_bad_counters_tasks_and_anonymity(self):
        data = observation(instant())
        data["medals"]["1"]["today_intimacy"] = True
        data["medals"]["3"]["today_intimacy"] = -1
        data["tasks"]["2"]["tasks"] = None
        result = compose(MEMBERS, data, instant(), anonymous=True)
        self.assertEqual(result["verified"], 0)
        self.assertNotIn("测试主播", result["content"])
        self.assertIn("主播1", result["content"])

    def test_duplicate_medals_and_long_summary(self):
        result = compose(MEMBERS + MEMBERS, observation(instant()), instant())
        self.assertEqual((result["rooms"], result["total"]), (2, 12))
        members = [{"name": "长名称" * 30, "uid": i, "room": i} for i in range(100)]
        result = compose(members, {"observed": instant()}, instant())
        self.assertLessEqual(len(result["content"]), 1200)
        self.assertIn("任务完成不等于收益到账", result["content"])


class Isolated(unittest.TestCase):
    def setUp(self):
        available = patch("bilioshi.notifications.AVAILABLE", True)
        available.start()
        self.addCleanup(available.stop)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        self.now = instant()
        self.saved_token = "T" * 32
        write_json(self.root / "settings.json", {"check_minutes": 30})
        write_json(self.root / "members.json", MEMBERS)
        write_json(self.root / "credentials.json", {"SESSDATA": "fake-session", "bili_jct": "fake-csrf"})
        self.key = identity("fake-session", self.root)
        self.collector = Mock(side_effect=lambda root: (MEMBERS, observation(self.now), self.now, self.key))
        self.sender = Mock(return_value={"state": "accepted", "reason": "服务已受理", "short_code": "sample123"})
        self.service = DailyNotifications(self.root, collector=self.collector, sender=self.sender, clock=lambda: self.now)

    def configure(self, enabled=True):
        settings.save(self.root, {"enabled": enabled}, self.saved_token)


class GrayBuildTests(Isolated):
    def test_old_enabled_config_and_direct_send_remain_disabled(self):
        self.configure()
        with patch("bilioshi.notifications.AVAILABLE", False):
            self.service.start()
            self.service.tick()
            self.assertIsNone(self.service.thread)
            self.collector.assert_not_called()
            self.sender.assert_not_called()
            with self.assertRaises(ValueError):
                self.service.queue_test()
            with self.assertRaises(ValueError):
                settings.save(self.root, {"enabled": True})
            opener = Mock()
            result = transport.send(self.saved_token, {}, opener=opener)
            self.assertTrue(result["blocked"])
            opener.open.assert_not_called()


class SettingsTests(Isolated):
    def test_secret_is_encrypted_and_preserved_on_blank_configuration(self):
        self.configure()
        raw = (self.root / "pushplus.credentials.json").read_text(encoding="utf-8")
        self.assertNotIn(self.saved_token, raw)
        self.assertEqual(settings.token(self.root), self.saved_token)
        settings.save(self.root, {"enabled": True, "summary_at": "22:00"})
        self.assertEqual(settings.token(self.root), self.saved_token)
        self.assertEqual(read_json(self.root / "settings.json")["check_minutes"], 30)
        settings.save(self.root, {"enabled": True}, "")
        self.assertFalse(settings.load(self.root)["enabled"])
        self.assertEqual(settings.token(self.root), "")

    def test_invalid_time_and_unconfigured_enable_rejected(self):
        for value in ("24:00", "9:30", "23:60", 42):
            with self.assertRaises(ValueError):
                settings.validate({"summary_at": value})
        with self.assertRaises(ValueError):
            settings.save(self.root, {"enabled": True})

    def test_redaction_covers_pushplus_secret(self):
        self.assertEqual(redact({"pushplus_token": "sensitive"})["pushplus_token"], "[REDACTED]")
        self.assertNotIn("sensitive", redact("pushplus_token=sensitive"))


class SchedulerTests(Isolated):
    def test_disabled_never_queries_or_sends_and_before_due_waits(self):
        self.configure(False)
        self.service.tick()
        self.collector.assert_not_called()
        self.sender.assert_not_called()
        self.configure(True)
        self.now = instant("2026-10-12 23:49:00")
        self.service.tick()
        self.collector.assert_not_called()

    def test_one_daily_summary_across_ticks_restart_and_date_change(self):
        self.configure()
        self.service.tick()
        self.service.tick()
        restarted = DailyNotifications(self.root, collector=self.collector, sender=self.sender, clock=lambda: self.now)
        restarted.tick()
        self.sender.assert_called_once()
        self.assertEqual(self.sender.call_args.args[1]["kind"], "daily")
        self.now = instant("2026-10-13 23:50:00")
        restarted.tick()
        self.assertEqual(self.sender.call_count, 2)
        # Neither credential is written to message payloads.
        with Outbox(self.root).connect() as db:
            text = str([tuple(row) for row in db.execute("SELECT title,content FROM messages")])
        self.assertNotIn(self.saved_token, text)
        self.assertNotIn("fake-session", text)

    def test_cross_midnight_during_collection_does_not_send_old_day(self):
        self.configure()
        def slow(root):
            self.now = instant("2026-10-13 00:01:00")
            return MEMBERS, observation(self.now), self.now, self.key
        self.collector.side_effect = slow
        self.service.tick()
        self.sender.assert_not_called()

    def test_account_switch_and_privacy_change_during_collection_discard_result(self):
        self.configure()
        def change(root):
            settings.save(root, {"enabled": True, "anonymous": True})
            return MEMBERS, observation(self.now), self.now, self.key
        self.collector.side_effect = change
        self.service.tick()
        self.sender.assert_not_called()
        self.service.tick()
        self.sender.assert_called_once()
        self.assertNotIn("测试主播", self.sender.call_args.args[1]["content"])
        self.assertIn("主播1", self.sender.call_args.args[1]["content"])

    def test_unknown_result_not_replayed_after_restart(self):
        self.configure()
        self.sender.return_value = {"state": "unknown", "reason": "timeout"}
        self.service.tick()
        self.now += 60
        self.service.tick()
        self.sender.assert_called_once()

    def test_inflight_crash_recovers_as_unknown_without_sending(self):
        self.configure()
        box = Outbox(self.root)
        config = settings.load(self.root)
        box.enqueue(f"daily:{self.key}:2026-10-12", "daily", self.key,
                    destination_key(self.saved_token, config), compose(MEMBERS, observation(self.now), self.now), self.now, self.now + 600)
        self.assertIsNotNone(box.claim(self.now))
        self.service.tick()
        self.sender.assert_not_called()
        self.assertEqual(box.status(self.now)["recent"][0]["state"], "unknown")

    def test_dns_retry_limited_and_budget_counts_attempts(self):
        self.configure()
        self.sender.return_value = {"state": "retry", "reason": "dns"}
        self.service.tick()
        self.now += 60
        self.service.tick()
        self.now += 300
        self.service.tick()
        self.now += 120
        self.service.tick()
        self.assertEqual(self.sender.call_count, 3)
        status = self.service.status()
        self.assertEqual(status["attempts_today"], 3)
        self.assertEqual(status["recent"][0]["state"], "failed")

    def test_provider_rejection_persists_until_manual_resume(self):
        self.configure()
        self.sender.return_value = {"state": "failed", "reason": "invalid token", "blocked": True}
        self.service.tick()
        self.now = instant("2026-10-13 23:50:00")
        self.service.tick()
        self.sender.assert_called_once()
        self.service.resume()
        self.service.tick()
        self.assertEqual(self.sender.call_count, 2)

    def test_synthetic_test_works_while_daily_off_without_account_query(self):
        self.configure(False)
        self.service.queue_test()
        with self.assertRaises(ValueError):
            self.service.queue_test()
        self.service.tick()
        self.collector.assert_not_called()
        self.sender.assert_called_once()
        self.assertIn("合成", self.sender.call_args.args[1]["content"])

    def test_unreadable_bilibili_login_does_not_block_synthetic_test(self):
        self.configure(False)
        (self.root / "credentials.json").write_text("broken", encoding="utf-8")
        self.service.queue_test()
        self.service.tick()
        self.collector.assert_not_called()
        self.sender.assert_called_once()

    def test_rate_spacing_and_attempt_cap_are_persistent(self):
        self.configure(False)
        self.service.queue_test()
        self.service.tick()
        self.service.queue_test()
        self.now += 10
        self.service.tick()
        self.sender.assert_called_once()
        self.now += 20
        self.service.tick()
        self.assertEqual(self.sender.call_count, 2)
        self.service.queue_test()
        box = Outbox(self.root)
        with box.connect() as db:
            db.execute("UPDATE attempts SET count=100")
        self.now += 30
        self.service.tick()
        self.assertEqual(self.sender.call_count, 2)
        self.assertEqual(box.status(self.now)["recent"][0]["state"], "failed")

    def test_query_failure_sends_daily_unavailable_snapshot(self):
        self.configure()
        self.collector.side_effect = RuntimeError("private cookie")
        self.service.tick()
        message = self.sender.call_args.args[1]
        self.assertIn("无法核验", message["content"])
        self.assertNotIn("private cookie", message["content"])

    def test_dispatcher_lease_excludes_concurrent_producer(self):
        self.configure()
        with FileLock(self.root / "locks/daily-notification.lock"):
            thread = threading.Thread(target=self.service.tick)
            thread.start()
            thread.join(2)
            self.assertFalse(thread.is_alive())
        self.sender.assert_not_called()

    def test_clear_keeps_dedup_and_attempt_budget(self):
        self.configure()
        self.sender.return_value = {"state": "retry", "reason": "dns"}
        self.service.tick()
        box = Outbox(self.root)
        box.clear_pending()
        self.now += 60
        self.service.tick()
        self.sender.assert_called_once()
        self.assertEqual(box.status(self.now)["attempts_today"], 1)

    def test_account_switch_after_queue_supersedes_old_account(self):
        self.configure()
        self.sender.return_value = {"state": "retry", "reason": "dns"}
        self.service.tick()
        write_json(self.root / "credentials.json", {"SESSDATA": "different-session", "bili_jct": "different-csrf"})
        self.now += 60
        self.service.tick()
        self.sender.assert_called_once()
        self.assertEqual(self.service.status()["recent"][0]["state"], "superseded")

    def test_readonly_collector_rejects_login_changes_and_uses_query_start(self):
        app = Mock()
        app.credentials.return_value = ("fake-session", "fake-csrf")
        app.probe.return_value = observation(self.now)
        ticks = iter((self.now - 20, self.now))
        _, data, _, _ = collect(self.root, application=app, clock=lambda: next(ticks))
        self.assertEqual(data["observed"], self.now - 20)
        app.credentials.side_effect = [("fake-session", "fake-csrf"), ("changed", "other")]
        with self.assertRaises(ValueError):
            collect(self.root, application=app, clock=lambda: self.now)


class TransportTests(unittest.TestCase):
    def setUp(self):
        available = patch("bilioshi.notifications.AVAILABLE", True)
        available.start()
        self.addCleanup(available.stop)

    def send_response(self, body):
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        response.read.return_value = body
        opener = Mock()
        opener.open.return_value = response
        message = {"title": "日报", "content": "合成", "expires": instant() + 60}
        return transport.send("T" * 32, message, opener=opener), opener

    def test_fixed_destination_body_secret_and_accepted_not_delivered(self):
        outcome, opener = self.send_response(b'{"code":200,"data":"abc123"}')
        self.assertEqual(outcome["state"], "accepted")
        req = opener.open.call_args.args[0]
        self.assertEqual(req.full_url, transport.URL)
        self.assertFalse(req.has_header("Cookie"))
        self.assertFalse(req.has_header("Authorization"))
        payload = json.loads(req.data)
        self.assertEqual(payload["channel"], "qq")
        self.assertEqual(payload["template"], "txt")
        self.assertIsInstance(payload["timestamp"], int)
        self.assertNotIn("token", req.full_url)

    def test_bad_responses_and_provider_errors_are_sanitized(self):
        for body in (b"broken", b"[]", b'{"code":200,"data":{}}', b"x" * 65537):
            self.assertEqual(self.send_response(body)[0]["state"], "unknown")
        outcome, _ = self.send_response(b'{"code":903,"message":"private token"}')
        self.assertTrue(outcome["blocked"])
        self.assertNotIn("private token", str(outcome))

    def test_only_dns_failure_is_retryable_redirect_and_timeout_are_unknown(self):
        message = {"title": "test", "content": "test", "expires": instant() + 60}
        for error, state in ((TimeoutError(), "unknown"),
                             (urllib.error.URLError(socket.gaierror()), "retry"),
                             (urllib.error.HTTPError(transport.URL, 302, "redirect", {}, None), "unknown")):
            opener = Mock()
            opener.open.side_effect = error
            self.assertEqual(transport.send("T" * 32, message, opener=opener)["state"], state)
        self.assertIsNone(transport.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.com"))


if __name__ == "__main__":
    unittest.main()
