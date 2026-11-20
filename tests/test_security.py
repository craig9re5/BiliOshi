"""Account protection, uncertainty, vault migration and cross-process contracts."""

import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bilioshi import safety, http, heartbeat, secret_store
from bilioshi.context import RuntimeContext, use_context
from bilioshi.runtime import (
    write_json,
    read_json,
    save_login,
    session_fingerprint,
    task_day,
    append_event,
)
from bilioshi.redaction import SafeStream, SafeFormatter, register_secrets, redact
from bilioshi.session_headers import session_headers
from desktop.engine import Engine
from desktop.storage import initialize

SESSION = "synthetic-security-session-A"
CSRF = "synthetic-security-csrf-A"
HEADERS = {"Cookie": f"SESSDATA={SESSION}; bili_jct={CSRF}"}
URL = "https://api.live.bilibili.com/msg/send"


class SecurityTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        scope = use_context(RuntimeContext(self.root))
        scope.__enter__()
        self.addCleanup(scope.__exit__, None, None, None)
        safety.bind_account(SESSION, 123)

    def test_like_single_batches_finish_ten_rounds_despite_legacy_flow_counter(self):
        from bilioshi.services import likes
        path = self.root / "state/tasks/uid-123-1.json"
        write_json(path, {"day": task_day(), "like_attempted": 3})
        current = [0]

        def transport(*args, **kwargs):
            current[0] += 1
            return {"code": 0}

        def progress(*args):
            return {"current": current[0], "limit": 10, "per_round": 30, "done": current[0] == 10}

        with (patch.object(heartbeat, "get_viewer_uid", return_value=123),
              patch.object(heartbeat, "_live_like_headers", return_value=HEADERS),
              patch.object(heartbeat, "get_live_like_progress", side_effect=progress),
              patch.object(heartbeat, "get_mixin_key", return_value="key"),
              patch.object(heartbeat, "_sign_wbi", side_effect=lambda params, key: params),
              patch.object(likes, "send_paced", side_effect=lambda send, **kw: send()),
              patch.object(likes.time, "sleep"), patch.object(http, "_once", side_effect=transport) as send):
            for _ in range(11):
                runner = heartbeat.DailyTaskRunner(1, 2, SESSION, CSRF,
                                                  auto_revive=False, auto_intimacy=False, auto_like=True)
                result = runner.check()
        self.assertTrue(result["success"])
        self.assertEqual(send.call_count, 10)
        self.assertEqual(read_json(self.root / "state/safety/uid-123.json")["counts"][f"{task_day()}:1:like"], 10)

    def test_like_verification_deadline_persists_pending_without_replay(self):
        from bilioshi.task_window import task_window
        now = [0]
        gateway = heartbeat

        def accepted(*args, **kwargs):
            now[0] = 9
            return {"success": True, "code": 0}

        with (patch.object(gateway, "get_viewer_uid", return_value=123),
              patch.object(gateway, "_live_like_headers", return_value=HEADERS),
              patch.object(gateway, "get_live_like_progress", return_value={
                  "current": 0, "limit": 10, "per_round": 30, "done": False}),
              patch.object(gateway, "report_live_likes", side_effect=accepted) as send,
              patch("bilioshi.task_window.time.monotonic", side_effect=lambda: now[0])):
            runner = gateway.DailyTaskRunner(1, 2, SESSION, CSRF,
                                            auto_revive=False, auto_intimacy=False, auto_like=True)
            result = runner.check(deadline=10)
            self.assertTrue(result["like"]["deferred"])
            self.assertEqual(result["like"]["reported"], 30)
            self.assertEqual(read_json(runner.path)["like_pending"], 0)
            with task_window(20):
                result = runner.check()
            self.assertTrue(result["like"]["needs_confirmation"])
            send.assert_called_once()

    def test_task_window_caps_http_and_pacing_without_hiding_uncertain_write(self):
        from bilioshi.task_window import task_window, TaskDeferred
        from bilioshi.danmaku_pacing import send_paced
        now = [0]
        with patch("bilioshi.task_window.time.monotonic", side_effect=lambda: now[0]):
            with task_window(2), patch.object(http, "_once", return_value={"code": 0}) as send:
                http.get_json(http.NAV_URL, HEADERS)
                self.assertEqual(send.call_args.kwargs["timeout"], 2)
                now[0] = 1.5
                with self.assertRaises(TaskDeferred):
                    http.get_json("https://api.live.bilibili.com/progress", HEADERS)
                now[0] = 2
                with self.assertRaises(TaskDeferred):
                    http.post_form(URL, {"roomid": 1}, HEADERS)
                self.assertEqual(send.call_count, 1)
            # Tail-end write budget (< MIN_WRITE_WINDOW) defers without sending or setting uncertain.
            with task_window(3), patch.object(http, "_once", return_value={
                    "code": -1, "error_kind": "network"}) as send:
                with self.assertRaises(TaskDeferred):
                    http.post_form(URL, {"roomid": 1}, HEADERS)
                send.assert_not_called()
                self.assertFalse(safety.status(SESSION)["blocked"])
                self.assertEqual(read_json(self.root / "state/safety/uid-123.json", {}).get("counts", {}), {})
            # With enough write budget remaining, a real transport failure still marks uncertain.
            with task_window(8), patch.object(http, "_once", return_value={
                    "code": -1, "error_kind": "network"}) as send:
                http.post_form(URL, {"roomid": 1}, HEADERS)
                send.assert_called_once()
                self.assertEqual(send.call_args.kwargs["timeout"], 6)
                self.assertEqual(safety.status(SESSION)["kind"], "uncertain")
            path = self.root / "pace.lock"
            path.write_text(str(time.time()), encoding="ascii")
            with task_window(3), self.assertRaises(TaskDeferred):
                send_paced(lambda: self.fail("Must not send before the pacing wait fits"),
                           lock_path=path, min_interval=15)

    def test_uncertain_write_is_not_retried_and_blocks_another_room(self):
        with patch.object(
            http, "_once", return_value={"code": -1, "error_kind": "network"}
        ) as send:
            result = http.post_form(URL, {"roomid": "1"}, HEADERS)
            blocked = http.post_form(URL, {"roomid": "2"}, HEADERS)
        self.assertEqual(send.call_count, 1)
        self.assertEqual(result["error_kind"], "network")
        self.assertEqual(blocked["error_kind"], "safety")
        self.assertEqual(safety.status(SESSION)["kind"], "uncertain")
        with patch.object(http, "_once", return_value={"code": 0}) as read:
            self.assertEqual(
                http.get_json("https://api.live.bilibili.com/progress", HEADERS)["code"], 0
            )
        read.assert_called_once()

    def test_heartbeat_transport_failures_cool_down_without_replaying(self):
        failures = [
            {"code": -1, "error_kind": "network"},
            {"code": -1, "error_kind": "data"},
            {"code": 503, "error_kind": "http"},
            {"code": 408, "error_kind": "http"},
        ]
        for path in safety.HEARTBEAT_PATHS:
            for failure in failures:
                with self.subTest(path=path, failure=failure):
                    safety.resume(SESSION, confirmed=True)
                    with patch.object(http, "_once", return_value=failure) as send:
                        http.post_form("https://live-trace.bilibili.com" + path,
                                       {"room_id": "1"}, HEADERS)
                    send.assert_called_once()
                    hold = safety.status(SESSION)
                    self.assertEqual(hold["kind"], "network")
                    self.assertEqual(hold["until"] - hold["since"], 60)
                    self.assertEqual(hold["operation"]["kind"], "heartbeat")
                    self.assertEqual(hold["operation"]["room"], "1")
                    with patch.object(safety.time, "time", return_value=hold["until"] + 1):
                        self.assertFalse(safety.status(SESSION)["blocked"])
                        self.assertTrue(safety.resume(SESSION, confirmed=True)[0])

    def test_heartbeat_platform_rejections_keep_stronger_protection(self):
        url = "https://live-trace.bilibili.com/xlive/data-interface/v1/x25Kn/X"
        for code, kind in ((-352, "review"), (-101, "auth"), (403, "permission"), (429, "rate")):
            with self.subTest(code=code):
                write_json(self.root / "state/safety/uid-123.json", {})
                with patch.object(http, "_once", return_value={"code": code}):
                    http.post_form(url, {"room_id": "1"}, HEADERS)
                self.assertEqual(safety.status(SESSION)["kind"], kind)

    def test_engine_reprobes_when_network_cooldown_expires(self):
        initialize(self.root, [{"room": 1, "uid": 2, "name": "test"}])
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine = Engine(self.root, job=Mock())
        engine.next_check = 99999999999
        process = Mock()
        process.poll.return_value = None
        engine.workers[1] = process
        safety.hold_account(SESSION, "network", "temporary", seconds=60)
        hold = safety.status(SESSION)
        with patch.object(engine, "spawn") as spawn:
            engine.tick()
            process.terminate.assert_called_once()
            spawn.assert_not_called()
            with patch.object(safety.time, "time", return_value=hold["until"] + 1):
                engine.tick()
            self.assertEqual(spawn.call_args.args[0], "--probe")
            self.assertFalse(engine.safety["blocked"])

    def test_http_500_write_has_unknown_outcome(self):
        with patch.object(http, "_once", return_value={"code": 500, "error_kind": "http"}):
            http.post_form(URL, {"roomid": "1"}, HEADERS)
        self.assertEqual(safety.status(SESSION)["kind"], "uncertain")

    def test_reads_have_bounded_backoff_then_account_cooldown(self):
        with (
            patch.object(http, "_once", return_value={"code": -1, "error_kind": "network"}) as read,
            patch.object(http.time, "sleep") as sleep,
        ):
            http.get_json("https://api.bilibili.com/read", HEADERS)
        self.assertEqual(read.call_count, 3)
        self.assertEqual(
            [c.args[0] for c in sleep.call_args_list],
            list(http.current_profile().read_retry_delays),
        )
        self.assertEqual(safety.status(SESSION)["kind"], "network")

    def test_rate_obeys_retry_after_and_cannot_be_resumed_early(self):
        with patch.object(
            http, "_once", return_value={"code": 429, "error_kind": "http", "retry_after": 600}
        ):
            http.get_json("https://api.bilibili.com/read", HEADERS)
        hold = safety.status(SESSION)
        self.assertGreaterEqual(hold["until"] - hold["since"], 600)
        self.assertFalse(safety.resume(SESSION, confirmed=True)[0])
        with patch.object(safety.time, "time", return_value=hold["until"] + 1):
            self.assertFalse(safety.status(SESSION)["blocked"])

    def test_352_requires_review_and_reauthentication_does_not_clear_it(self):
        safety.observe(SESSION, URL, {"code": -352})
        safety.bind_account(SESSION, 123)
        self.assertEqual(safety.status(SESSION)["kind"], "review")
        self.assertFalse(safety.resume(SESSION)[0])
        self.assertTrue(safety.resume(SESSION, confirmed=True)[0])

    def test_auth_expiry_clears_only_after_successful_authentication(self):
        safety.observe(SESSION, URL, {"code": -101})
        self.assertFalse(safety.resume(SESSION, confirmed=True)[0])
        safety.observe(SESSION, http.NAV_URL, {"code": 0, "data": {"isLogin": True, "mid": 123}})
        self.assertFalse(safety.status(SESSION)["blocked"])

    def test_new_qr_session_same_uid_keeps_hold_and_budget(self):
        op = {"kind": "danmaku", "room": "1"}
        self.assertIsNone(safety.reserve(SESSION, op))
        safety.observe(SESSION, URL, {"code": 403})
        new = "synthetic-security-session-B"
        safety.bind_account(new, 123)
        self.assertEqual(safety.identity(new), safety.identity(SESSION))
        self.assertTrue(safety.status(new)["blocked"])
        counts = read_json(self.root / "state/safety/uid-123.json")["counts"]
        self.assertEqual(counts[f"{task_day()}:1:danmaku"], 1)

    def test_legacy_budget_migrates_once_without_session_reset(self):
        legacy = "synthetic-legacy-session"
        old = session_fingerprint(legacy)
        path = self.root / "state/tasks" / f"{old}-1.json"
        write_json(path, {"room": 1, "day": task_day(), "attempted": 35, "like_attempted": 2})
        safety.bind_account(legacy, 321)
        safety.bind_account(legacy, 321)
        current = read_json(self.root / "state/tasks/uid-321-1.json")
        self.assertEqual(current["attempted"], 35)
        self.assertFalse(path.exists())
        denied = safety.reserve(legacy, {"kind": "danmaku", "room": "1"})
        self.assertEqual(denied["error_kind"], "safety")

    def test_parallel_workers_share_request_budget(self):
        op = {"kind": "danmaku", "room": "1"}

        def reserve(_):
            with use_context(RuntimeContext(self.root)):
                return safety.reserve(SESSION, op)

        with patch.object(safety, "DANMAKU_SESSION_ATTEMPT_LIMIT", 3):
            with ThreadPoolExecutor(max_workers=4) as workers:
                results = list(workers.map(reserve, range(8)))
        self.assertEqual(sum(r is None for r in results), 3)

    def test_separate_processes_share_request_budget(self):
        program = (
            "from bilioshi import safety; import sys; "
            "safety.DANMAKU_SESSION_ATTEMPT_LIMIT=1; "
            "print(int(safety.reserve(sys.argv[1], {'kind':'danmaku','room':'2'}) is None))"
        )
        processes = [
            subprocess.Popen(
                [sys.executable, "-c", program, SESSION],
                cwd=Path(__file__).resolve().parents[1],
                env={**os.environ, "BILIOSHI_APP_DATA": str(self.root)},
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for _ in range(2)
        ]
        outputs = [p.communicate(timeout=15) for p in processes]
        self.assertTrue(all(p.returncode == 0 for p in processes), outputs)
        self.assertEqual(sum(int(out.strip()) for out, _ in outputs), 1)

    def test_unknown_identity_must_authenticate_before_write(self):
        headers = {"Cookie": "SESSDATA=unverified; bili_jct=synthetic"}
        with patch.object(http, "_once", return_value={"code": -101}) as transport:
            result = http.post_form(URL, {"roomid": "1"}, headers)
        self.assertEqual(result["code"], -101)
        self.assertEqual(transport.call_count, 1)
        self.assertEqual(transport.call_args.args[0], http.NAV_URL)

    def test_fixed_count_checkin_uses_daily_runner(self):
        from bilioshi import checkin

        with patch.object(heartbeat, "DailyTaskRunner") as runner:
            runner.return_value.check.return_value = {"success": True, "danmaku": {"done": True}}
            checkin.batch_checkin(
                [{"room": 1, "uid": 2, "name": "test"}],
                ["hello"],
                SESSION,
                CSRF,
                count=1000,
                auto_medal=False,
            )
        self.assertEqual(runner.call_args.kwargs["requested_count"], 1000)

    def test_engine_stops_all_workers_and_reports_protection(self):
        initialize(self.root, [{"room": 1, "uid": 2, "name": "test"}])
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine = Engine(self.root, job=Mock())
        process = Mock()
        process.poll.return_value = None
        engine.workers[1] = process
        safety.observe(SESSION, URL, {"code": -352})
        with patch.object(engine, "spawn") as spawn:
            engine.tick()
        process.terminate.assert_called_once()
        spawn.assert_not_called()
        snapshot = engine.snapshot()
        self.assertTrue(snapshot["safety"]["blocked"])
        self.assertEqual(snapshot["rows"][0]["phase"], "账号保护暂停")
        self.assertFalse(snapshot["rows"][0]["active"])

    def test_reencrypting_same_credentials_does_not_restart_workers(self):
        initialize(self.root, [{"room": 1, "uid": 2, "name": "test"}])
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine = Engine(self.root, job=Mock())
        process = Mock()
        process.poll.return_value = None
        engine.workers[1] = process
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine.reload_settings()
        process.terminate.assert_not_called()

    def test_engine_allows_bounded_reconciliation_then_stops_uncertain_worker(self):
        initialize(self.root, [{"room": 1, "uid": 2, "name": "test"}])
        save_login(SESSION, CSRF, self.root / "credentials.json")
        engine = Engine(self.root, job=Mock())
        process = Mock()
        process.poll.return_value = None
        engine.workers[1] = process
        safety.hold_account(SESSION, "uncertain", "结果未知")
        engine.tick()
        process.terminate.assert_not_called()
        hold = safety.status(SESSION)
        with patch.object(safety.time, "time", return_value=hold["since"] + 21):
            engine.tick()
        process.terminate.assert_called_once()

    def test_cannot_send_auth_to_other_host_or_redirect(self):
        with patch.object(http, "_once") as send:
            result = http.post_form("https://example.test/send", {}, HEADERS)
        send.assert_not_called()
        self.assertEqual(result["error_kind"], "safety")
        request = urllib.request.Request(URL, headers=HEADERS)
        with self.assertRaises(urllib.error.HTTPError):
            http.SameOriginRedirect().redirect_request(
                request, None, 302, "", {}, "https://example.test/"
            )

    def test_existing_heartbeat_and_dynamic_hosts_remain_available(self):
        with patch.object(http, "_once", return_value={"code": 0}) as send:
            for url in (
                heartbeat._X25KN_E_URL,
                heartbeat._X25KN_X_URL,
                "https://api.vc.bilibili.com/dynamic_like/v1/dynamic_like/thumb",
            ):
                self.assertEqual(http.post_form(url, {}, HEADERS)["code"], 0)
        self.assertEqual(send.call_count, 3)

    def test_uncertain_like_queries_progress_without_repeating_batch(self):
        from bilioshi.services.likes import like_live_room

        gateway = Mock(LIVE_LIKE_PROGRESS_DELAY=3)
        gateway.get_viewer_uid.return_value = 123
        gateway._live_like_headers.return_value = HEADERS
        gateway.get_live_like_progress.side_effect = [
            {"current": 0, "limit": 2, "per_round": 30, "done": False},
            {"current": 1, "limit": 2, "per_round": 30, "done": False},
        ]

        def unknown(*args, **kwargs):
            safety.hold_account(SESSION, "uncertain", "操作结果未知")
            return {"success": False, "code": -1, "message": "timeout"}

        gateway.report_live_likes.side_effect = unknown
        with patch("bilioshi.services.likes.time.sleep"):
            result = like_live_room(1, 2, SESSION, CSRF, _gateway=gateway)
        self.assertEqual(result["progress"], "1/2")
        self.assertTrue(result["needs_confirmation"])
        gateway.report_live_likes.assert_called_once()
        self.assertTrue(safety.status(SESSION)["blocked"])

    def test_logout_clears_session_aliases_but_preserves_uid_hold_and_budget(self):
        save_login(SESSION, CSRF, self.root / "credentials.json")
        safety.reserve(SESSION, {"kind": "danmaku", "room": "1"})
        safety.observe(SESSION, URL, {"code": -352})
        save_login("", "", self.root / "credentials.json")
        self.assertEqual(read_json(self.root / "state/account-bindings.json"), {})
        safety.bind_account("synthetic-new-session", 123)
        self.assertTrue(safety.status("synthetic-new-session")["blocked"])
        self.assertEqual(
            read_json(self.root / "state/safety/uid-123.json")["counts"][f"{task_day()}:1:danmaku"],
            1,
        )


class VaultTests(unittest.TestCase):
    def test_confirmed_qr_can_replace_unreadable_vault(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            save_login(SESSION, CSRF, path)
            context = {
                "cookies": {
                    "SESSDATA": "synthetic-qr-new-session",
                    "bili_jct": "synthetic-replacement-csrf",
                },
                "user_agent": "QR UA",
            }
            with patch("bilioshi.runtime.unseal", side_effect=RuntimeError("unreadable")):
                save_login(
                    context["cookies"]["SESSDATA"],
                    context["cookies"]["bili_jct"],
                    path,
                    context=context,
                )
            self.assertEqual(read_json(path)["SESSDATA"], "synthetic-qr-new-session")

    def test_legacy_plaintext_removed_only_after_verified_protection(self):
        from bilioshi.runtime import protect_credentials

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            legacy = root / ".asoul-support-data/.cookies.json"
            legacy.parent.mkdir()
            legacy.write_text(json.dumps({"SESSDATA": SESSION, "bili_jct": CSRF}))
            result = protect_credentials(root / "new", legacy)
            self.assertTrue(result["protected"])
            self.assertTrue(result["legacy_removed"])
            self.assertFalse(legacy.exists())
            self.assertEqual(read_json(root / "new/credentials.json")["SESSDATA"], SESSION)

    def test_saved_credentials_are_protected_and_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            save_login(SESSION, CSRF, path)
            self.assertTrue(secret_store.is_envelope(json.loads(path.read_text())))
            self.assertNotIn(SESSION, path.read_text())
            self.assertEqual(read_json(path)["SESSDATA"], SESSION)
            save_login("", "", path)
            self.assertEqual(read_json(path), {})

    def test_plaintext_migration_is_atomic_and_does_not_make_plaintext_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            path.write_text(json.dumps({"SESSDATA": SESSION, "bili_jct": CSRF}))
            with patch("bilioshi.runtime.seal", side_effect=RuntimeError("vault unavailable")):
                with self.assertRaises(RuntimeError):
                    read_json(path)
            self.assertIn(SESSION, path.read_text())
            self.assertEqual(read_json(path)["SESSDATA"], SESSION)
            self.assertNotIn(SESSION, path.read_text())
            self.assertFalse(list(Path(folder).glob("*.tmp")))

    @unittest.skipUnless(os.name == "nt", "real Windows user DPAPI")
    def test_dpapi_tampering_fails_closed(self):
        envelope = secret_store.seal({"SESSDATA": SESSION})
        envelope["payload"] = "invalid!"
        with self.assertRaises(RuntimeError) as error:
            secret_store.unseal(envelope)
        self.assertNotIn(SESSION, str(error.exception))

    def test_unavailable_os_vault_never_writes_plaintext(self):
        with (
            patch.object(secret_store.os, "name", "posix"),
            patch.object(secret_store, "_keyring", side_effect=RuntimeError("unavailable")),
        ):
            with self.assertRaises(RuntimeError):
                secret_store.seal({"SESSDATA": SESSION})

    def test_redacts_nested_events_urls_tracebacks_and_split_stream_writes(self):
        register_secrets({"SESSDATA": SESSION, "bili_jct": CSRF})
        value = redact(
            {
                "Cookie": f"SESSDATA={SESSION}",
                "message": f"https://api.bilibili.com/?csrf={CSRF}&SESSDATA={SESSION}",
            }
        )
        self.assertNotIn(SESSION, json.dumps(value))
        self.assertNotIn(CSRF, json.dumps(value))
        stream = io.StringIO()
        safe = SafeStream(stream)
        safe.write(SESSION[:10])
        safe.write(SESSION[10:] + "\n")
        self.assertNotIn(SESSION, stream.getvalue())
        import logging

        record = logging.LogRecord("test", 40, "", 1, SESSION, (), None)
        self.assertNotIn(SESSION, SafeFormatter().format(record))

    def test_all_modules_reuse_qr_session_and_user_agent(self):
        from bilioshi import videos, dynamics

        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            context = {
                "cookies": {
                    "SESSDATA": SESSION,
                    "bili_jct": CSRF,
                    "DedeUserID": "123",
                    "buvid3": "synthetic-device",
                },
                "user_agent": "QR UA",
            }
            save_login(SESSION, CSRF, Path(folder) / "credentials.json", context=context)
            for module in (heartbeat, videos, dynamics):
                headers = module._make_headers(SESSION, CSRF)
                self.assertEqual(headers["User-Agent"], "QR UA")
                self.assertIn("buvid3=synthetic-device", headers["Cookie"])
            with patch.object(heartbeat, "_post_form", return_value={"code": 0}) as post:
                heartbeat._x25kn_post(URL, {"ua": "old"}, SESSION, CSRF, URL)
            self.assertEqual(post.call_args.args[1]["ua"], "QR UA")


class SafetyAutoRecoveryTests(unittest.TestCase):
    def test_describe_hold_exposes_context_and_redacts_secrets(self):
        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            root = Path(folder)
            register_secrets({"SESSDATA": SESSION, "bili_jct": CSRF})
            save_login(SESSION, CSRF, root / "credentials.json")
            safety.bind_account(SESSION, 123)
            hold = safety.hold_account(
                SESSION,
                "review",
                "请先完成平台安全验证后恢复",
                code=-352,
                operation={"room": "1", "kind": "danmaku"},
                raw_message=f"风控拦截 SESSDATA={SESSION}",
                root=root,
            )
            info = safety.describe_hold(hold, [{"name": "测试主播", "uid": 999, "room": 1}])
            self.assertEqual(info["kind_label"], "安全验证 / 风控拦截")
            self.assertEqual(info["room_label"], "「测试主播」（房间 1）")
            self.assertEqual(info["operation_label"], "发送弹幕")
            self.assertEqual(hold["code"], -352)
            self.assertNotIn(SESSION, hold["raw_message"])
            self.assertIn("[REDACTED]", hold["raw_message"])
            self.assertGreaterEqual(len(info["steps"]), 2)

    def test_probe_safety_bypasses_hold_for_readonly_checks_and_auto_recovers(self):
        from bilioshi.application import AppContext
        from desktop.storage import initialize

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [{"room": 1, "uid": 1001, "name": "主播A"}])
            save_login(SESSION, CSRF, root / "credentials.json")
            safety.bind_account(SESSION, 123, root=root)
            safety.hold_account(
                SESSION,
                "review",
                "请先完成平台安全验证后恢复",
                code=-352,
                operation={"room": "1", "kind": "danmaku"},
                root=root,
            )
            app = AppContext(root)

            def fail_once(*args, **kwargs):
                return {"code": -352, "message": "风控校验失败"}

            with patch.object(app, "validate_credentials_profile", return_value=(True, "测试账号", {"uid": 123})), \
                 patch.object(http, "_once", side_effect=[{"code": -352, "message": "风控校验失败"}, {"code": 0}]):
                first = app.probe_safety(auto=True)
            self.assertFalse(first["passed"])
            self.assertFalse(first["resumed"])
            self.assertEqual(first["hold"]["auto_attempts"], 1)
            self.assertIsNotNone(first["hold"]["next_probe_at"])

            with patch.object(app, "validate_credentials_profile", return_value=(True, "测试账号", {"uid": 123})), \
                 patch.object(http, "_once", return_value={"code": 0, "data": {}}):
                second = app.probe_safety(auto=True)
            self.assertTrue(second["passed"])
            self.assertTrue(second["resumed"])
            self.assertFalse(second["hold"]["blocked"])
            self.assertFalse(safety.status(SESSION, root)["blocked"])

    def test_uncertain_auto_recovery_via_engine_tick(self):
        from desktop.storage import initialize

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [{"room": 1, "uid": 1001, "name": "主播A"}])
            save_login(SESSION, CSRF, root / "credentials.json")
            safety.bind_account(SESSION, 123, root=root)
            safety.hold_account(
                SESSION,
                "uncertain",
                "操作结果未知，已停止重复发送；请核对服务端进度",
                code=-1,
                operation={"room": "1", "kind": "like"},
                root=root,
            )
            # Backdate hold past 20s grace and trigger immediate next_probe_at.
            path = root / "state/safety/uid-123.json"
            raw = read_json(path, {})
            raw["hold"]["since"] = time.time() - 180
            raw["hold"]["next_probe_at"] = time.time() - 5
            write_json(path, raw)

            engine = Engine(root, job=Mock())
            with patch.object(engine.application, "validate_credentials_profile", return_value=(True, "测试账号", {"uid": 123})), \
                 patch.object(http, "_once", return_value={"code": 0, "data": {}}), \
                 patch.object(engine, "_watch_workers") as watch, \
                 patch.object(engine, "spawn", return_value=Mock(poll=Mock(return_value=None))):
                engine.tick()
            watch.assert_called_once()
            self.assertFalse(engine.safety["blocked"])
            self.assertEqual(engine.error, "")

    def test_room_permission_isolates_single_room_and_skips_daily_tasks(self):
        from bilioshi.services.daily_tasks import DailyTaskRunner

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BILIOSHI_APP_DATA": folder}):
            root = Path(folder)
            safety.bind_account(SESSION, 123, root=root)
            url = "https://api.live.bilibili.com/msg/send"
            op = safety.operation(url, b"roomid=1001&msg=hi", "POST")
            safety.observe(SESSION, url, {"code": 403, "message": "你已被该直播间禁言"}, mutation=True, op=op)

            self.assertFalse(safety.status(SESSION, root)["blocked"])
            block = safety.room_capability_blocked(SESSION, 1001, "danmaku", root=root)
            self.assertEqual(block.get("room"), "1001")
            self.assertEqual(block.get("kind"), "danmaku")
            self.assertEqual(safety.room_capability_blocked(SESSION, 1001, "like", root=root), {})
            self.assertEqual(safety.room_capability_blocked(SESSION, 1002, "danmaku", root=root), {})

            self.assertIsNotNone(safety.reserve(SESSION, {"room": "1001", "kind": "danmaku"}))
            self.assertIsNone(safety.reserve(SESSION, {"room": "1001", "kind": "like"}))
            self.assertIsNone(safety.reserve(SESSION, {"room": "1002", "kind": "danmaku"}))
            self.assertIsNone(safety.reserve(SESSION, {"room": "1001", "kind": "heartbeat"}))

            from bilioshi.runtime import FileLock

            (root / "state/tasks").mkdir(parents=True, exist_ok=True)
            (root / "locks").mkdir(parents=True, exist_ok=True)
            gateway = Mock()
            gateway.DANMAKU_SESSION_ATTEMPT_LIMIT = 10
            gateway._runtime_path.side_effect = lambda name: (
                root / "state/tasks" if name == "_TASK_STATE_DIR" else root / "locks"
            )
            gateway.task_day = safety.task_day
            gateway.FileLock = FileLock
            gateway.read_json = read_json
            gateway.write_json = write_json
            runner = DailyTaskRunner(
                1001,
                888,
                SESSION,
                CSRF,
                auto_revive=True,
                auto_intimacy=False,
                auto_like=False,
                _gateway=gateway,
            )
            out = runner.check()
            self.assertFalse(out["success"])
            self.assertTrue(out["danmaku"]["skipped"])
            self.assertTrue(out["danmaku"]["room_blocked"])
            gateway.send_medal_danmaku_tasks.assert_not_called()

            self.assertTrue(safety.clear_room_block(SESSION, 1001, "danmaku", root=root))
            self.assertEqual(safety.room_blocks(SESSION, root), {})
            self.assertIsNone(safety.reserve(SESSION, {"room": "1001", "kind": "danmaku"}))

    def test_adaptive_pace_multiplier_increases_on_same_day_risk_hits(self):
        from bilioshi.application import AppContext
        from desktop.storage import initialize

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BILIOSHI_APP_DATA": folder}):
            root = Path(folder)
            initialize(root, [{"room": 1, "uid": 1001, "name": "主播A"}])
            save_login(SESSION, CSRF, root / "credentials.json")
            safety.bind_account(SESSION, 123, root=root)
            self.assertEqual(safety.pace_multiplier(SESSION, root), 1.0)

            safety.hold_account(SESSION, "rate", "请求频繁", code=429, root=root)
            self.assertEqual(safety.pace_multiplier(SESSION, root), 2.0)
            safety.resume(SESSION, confirmed=True, root=root)
            self.assertEqual(safety.pace_multiplier(SESSION, root), 2.0)

            safety.hold_account(SESSION, "review", "风控验证", code=-352, root=root)
            self.assertEqual(safety.pace_multiplier(SESSION, root), 3.0)
            safety.resume(SESSION, confirmed=True, root=root)
            status = AppContext(root).safety_status()
            self.assertFalse(status["blocked"])
            self.assertEqual(status["pace_multiplier"], 3.0)

    def test_format_task_errors_deduplicates_and_retires_resolved_safety_holds(self):
        from desktop.storage import initialize

        reason = "操作结果未知，已停止重复发送；请核对服务端进度"
        duplicate_result = {
            "day": task_day(),
            "success": False,
            "error": reason,
            "like": {
                "success": False,
                "needs_confirmation": True,
                "error": reason,
                "safety": {"blocked": True, "kind": "uncertain", "reason": reason},
            },
            "safety": {"blocked": True, "kind": "uncertain", "reason": reason},
        }
        self.assertEqual(safety.format_task_errors(duplicate_result), reason)
        self.assertEqual(safety.format_task_errors(duplicate_result, suppress_safety=True), "")

        mixed_result = {
            "day": task_day(),
            "success": False,
            "error": "弹幕失败",
            "danmaku": {"done": False, "error": "弹幕失败"},
            "like": {"success": False, "error": "点赞失败"},
        }
        self.assertEqual(safety.format_task_errors(mixed_result), "弹幕失败；点赞失败")

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BILIOSHI_APP_DATA": folder}):
            root = Path(folder)
            initialize(root, [{"room": 1, "uid": 1001, "name": "主播A"}])
            save_login(SESSION, CSRF, root / "credentials.json")
            safety.bind_account(SESSION, 123, root=root)
            safety.hold_account(SESSION, "uncertain", reason, code=-1, root=root)

            write_json(root / "state/1.json", {"room": 1, "task_result": duplicate_result})
            engine = Engine(root, job=Mock())
            with patch.object(engine.application, "validate_credentials", return_value=(True, "ok")):
                ok, _ = engine.resume_safety(confirmed=True)
            self.assertTrue(ok)
            snap = engine.snapshot()
            self.assertEqual(snap["rows"][0]["task_error"], "")

    def test_interaction_scoped_holds_keep_watch_heartbeats_alive_while_blocking_writes(self):
        from desktop.interaction import action_reason
        from desktop.storage import initialize

        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"BILIOSHI_APP_DATA": folder}):
            root = Path(folder)
            with use_context(RuntimeContext(root)):
                initialize(root, [{"room": 1, "uid": 1001, "name": "主播A"}])
                save_login(SESSION, CSRF, root / "credentials.json")
                safety.bind_account(SESSION, 123, root=root)

                op = safety.operation(URL, b"roomid=1&msg=hi", "POST")
                safety.observe(SESSION, URL, {"code": -509, "message": "发言过于频繁"}, mutation=True, op=op)
                hold = safety.status(SESSION, root)
                self.assertTrue(hold["blocked"])
                self.assertEqual(hold["kind"], "rate")
                self.assertEqual(hold["scope"], "interaction")
                self.assertFalse(safety.blocks_watch(hold))

                # Heartbeats and room entry remain allowed; danmaku writes stay blocked.
                with patch.object(http, "_once", return_value={"code": 0}) as send:
                    self.assertEqual(
                        http.post_form(heartbeat._X25KN_X_URL, {"room_id": "1"}, HEADERS)["code"], 0
                    )
                    self.assertEqual(
                        http.post_form(
                            "https://api.live.bilibili.com/xlive/web-room/v1/index/roomEntryAction",
                            {"room_id": "1"},
                            HEADERS,
                        )["code"],
                        0,
                    )
                    blocked_write = http.post_form(URL, {"roomid": "1", "msg": "hi"}, HEADERS)
                self.assertEqual(send.call_count, 2)
                self.assertEqual(blocked_write["error_kind"], "safety")

                # Engine keeps running workers alive and displays healthy watching instead of full stop.
                engine = Engine(root, job=Mock())
                engine.account = "测试账号"
                engine.account_checked_at = time.time()
                engine.statuses = {"1": {"live_status": 1}}
                engine.status_times = {"1": time.time()}
                proc = Mock(pid=77)
                proc.poll.return_value = None
                engine.workers[1] = proc
                write_json(
                    root / "state/1.json",
                    {"room": 1, "pid": 77, "phase": "挂机中", "started": time.time() - 60, "last_heartbeat": time.time() - 5},
                )
                with patch.object(engine, "spawn", return_value=Mock(poll=Mock(return_value=None))):
                    engine.tick()
                proc.terminate.assert_not_called()
                snap = engine.snapshot()
                row = snap["rows"][0]
                self.assertEqual(row["phase"], "挂机中")
                self.assertTrue(row["heartbeat_healthy"])
                self.assertEqual(action_reason(snap, row, "reconnect"), "")
                self.assertIn("看播正常继续", action_reason(snap, row, "redo"))

                # Watch loops keep beating under interaction-only holds instead of exiting with safety.
                from bilioshi.services.watch import _watch_until_offline, _watch_duration
                watch_gateway = Mock(DANMAKU_RECHECK_INTERVAL=600, DANMAKU_WORK_BUDGET=90)
                watch_gateway.task_day.return_value = task_day()
                watch_gateway._get_single_room_status.side_effect = [{"live_status": 1}, {"live_status": 0}]
                chain = Mock(last_response_at=time.monotonic(), heartbeat_interval=60)
                chain.beat.return_value = {"ok": True}
                runner = Mock()
                runner.check.return_value = {"success": False, "safety": hold}
                until_res = _watch_until_offline(
                    chain, runner, "主播A", 1, "", 60, 0, False, False, SESSION, CSRF, watch_gateway
                )
                self.assertTrue(until_res["success"])
                self.assertEqual(until_res["stopped_reason"], "offline")
                self.assertEqual(until_res["beats_ok"], 2)

                clock = [1000.0]
                dur_chain = Mock(last_response_at=1000.0, heartbeat_interval=60)
                def _beat_once():
                    clock[0] += 60.0
                    dur_chain.last_response_at = clock[0]
                    return {"ok": True}
                dur_chain.beat.side_effect = _beat_once
                with patch("bilioshi.services.watch.time.monotonic", side_effect=lambda: clock[0]):
                    dur_res = _watch_duration(
                        dur_chain, runner, "主播A", 1, "", 60, 1, False, False, SESSION, CSRF, watch_gateway
                    )
                self.assertTrue(dur_res["success"])
                self.assertNotIn("stopped_reason", dur_res)
                self.assertEqual(dur_res["beats_ok"], 1)

                # Room entry transport blips must not poison other rooms with an account hold,
                # while wear/daily-exp timeouts stay interaction-scoped (never blocking watch).
                room_entry_url = "https://api.live.bilibili.com/xlive/web-room/v1/index/roomEntryAction"
                write_json(root / "state/safety/uid-123.json", {})
                with patch.object(http, "_once", return_value={"code": -1, "error_kind": "network"}):
                    http.post_form(room_entry_url, {"room_id": "1"}, HEADERS)
                self.assertFalse(safety.status(SESSION, root)["blocked"])
                with patch.object(http, "_once", return_value={"code": -352, "message": "风控校验失败"}):
                    http.post_form(room_entry_url, {"room_id": "1"}, HEADERS)
                self.assertTrue(safety.blocks_watch(safety.status(SESSION, root)))

                for aux_url, payload in (
                    ("https://api.live.bilibili.com/xlive/web-room/v1/fansMedal/wear", {"medal_id": "1"}),
                    ("https://api.bilibili.com/x/web-interface/coin/add", {"aid": "1"}),
                ):
                    write_json(root / "state/safety/uid-123.json", {})
                    with patch.object(http, "_once", return_value={"code": -1, "error_kind": "network"}):
                        http.post_form(aux_url, payload, HEADERS)
                    aux_hold = safety.status(SESSION, root)
                    self.assertEqual(aux_hold["kind"], "uncertain")
                    self.assertEqual(aux_hold["scope"], "interaction")
                    self.assertFalse(safety.blocks_watch(aux_hold))

    def test_auth_expiry_escalates_over_permanent_holds_and_account_escalates_interaction(self):
        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            root = Path(folder)
            safety.bind_account(SESSION, 123, root=root)
            for prior_kind in ("uncertain", "review", "permission"):
                write_json(root / "state/safety/uid-123.json", {})
                safety.hold_account(SESSION, prior_kind, "前置保护", code=-1, root=root)
                safety.hold_account(SESSION, "auth", "登录已失效，请重新扫码登录", code=-101, root=root)
                current = safety.status(SESSION, root)
                self.assertEqual(current["kind"], "auth")
                self.assertEqual(current["scope"], "account")

            # Interaction-scoped uncertain hold escalates to account-scoped heartbeat network cooldown.
            write_json(root / "state/safety/uid-123.json", {})
            safety.hold_account(
                SESSION, "uncertain", "弹幕未知", code=-1, operation={"room": "1", "kind": "danmaku"}, root=root
            )
            self.assertEqual(safety.status(SESSION, root)["scope"], "interaction")
            safety.hold_account(
                SESSION, "network", "心跳异常", code=-1, seconds=60, operation={"room": "1", "kind": "heartbeat"}, root=root
            )
            escalated = safety.status(SESSION, root)
            self.assertEqual(escalated["kind"], "network")
            self.assertEqual(escalated["scope"], "account")

    def test_auto_resume_enters_probation_caps_trial_batch_and_clears_on_clean_write(self):
        from bilioshi.services.danmaku import send_danmaku_batch

        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            root = Path(folder)
            safety.bind_account(SESSION, 123, root=root)
            safety.hold_account(
                SESSION, "review", "风控验证", code=-352, operation={"room": "1", "kind": "danmaku"}, root=root
            )
            ok, msg = safety.auto_resume(SESSION, [{"name": "只读", "ok": True}], root=root)
            self.assertTrue(ok)
            self.assertIn("观察期", msg)
            self.assertGreater(safety.probation_until(SESSION, root), 0)
            self.assertEqual(safety.pace_multiplier(SESSION, root), 3.0)

            gateway = Mock(_DANMAKU_MSGS=["a", "b", "c"])
            gateway._send_danmaku.return_value = True
            sent_ok, _, attempted = send_danmaku_batch(1, 5, SESSION, CSRF, _gateway=gateway)
            self.assertEqual((sent_ok, attempted), (1, 1))

            # Clean write at HTTP boundary clears probation immediately.
            op = safety.operation(URL, b"roomid=1&msg=a", "POST")
            safety.observe(SESSION, URL, {"code": 0, "message": ""}, mutation=True, op=op)
            self.assertEqual(safety.probation_until(SESSION, root), 0.0)

    def test_silent_danmaku_shields_and_http_412_edge_limit_classification(self):
        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            root = Path(folder)
            safety.bind_account(SESSION, 123, root=root)

            # Silent anti-spam code=0 msg="fire" immediately blocks room danmaku without stopping account.
            with patch.object(heartbeat, "send_paced", side_effect=lambda fn, **kw: fn()), \
                 patch.object(heartbeat, "_post_form", return_value={"code": 0, "msg": "fire"}):
                self.assertFalse(heartbeat._send_danmaku(1001, "hi", SESSION, CSRF))
            self.assertFalse(safety.status(SESSION, root)["blocked"])
            self.assertTrue(safety.room_capability_blocked(SESSION, 1001, "danmaku", root=root))

            # 3 consecutive silent keyword shields ("f" / "k") isolate room 1002; clean send resets streak.
            with patch.object(heartbeat, "send_paced", side_effect=lambda fn, **kw: fn()):
                with patch.object(heartbeat, "_post_form", return_value={"code": 0, "msg": "f"}):
                    self.assertFalse(heartbeat._send_danmaku(1002, "hi", SESSION, CSRF))
                    self.assertFalse(heartbeat._send_danmaku(1002, "hi", SESSION, CSRF))
                self.assertFalse(safety.room_capability_blocked(SESSION, 1002, "danmaku", root=root))
                with patch.object(heartbeat, "_post_form", return_value={"code": 0, "msg": ""}):
                    self.assertTrue(heartbeat._send_danmaku(1002, "ok", SESSION, CSRF))
                with patch.object(heartbeat, "_post_form", return_value={"code": 0, "msg": "k"}):
                    for _ in range(3):
                        self.assertFalse(heartbeat._send_danmaku(1002, "bad", SESSION, CSRF))
                self.assertTrue(safety.room_capability_blocked(SESSION, 1002, "danmaku", root=root))

            # Edge HTTP 412 gets short auto-cooldown; HTTP 412 carrying bili_code=-352 stays review.
            self.assertEqual(
                safety.classify({"code": 412, "http_status": 412, "message": "HTTP 412", "error_kind": "http"})[0],
                "edge_limit",
            )
            self.assertEqual(
                safety.classify({"code": 412, "bili_code": -352, "message": "HTTP 412: 风控", "error_kind": "http"})[0],
                "review",
            )

    def test_pacing_jitter_and_proxy_bypass_openers(self):
        from bilioshi.danmaku_pacing import send_paced

        for opener in (http._AUTH_OPENER, http._PLAIN_OPENER):
            proxy_handlers = [h for h in opener.handlers if isinstance(h, urllib.request.ProxyHandler)]
            self.assertEqual(proxy_handlers, [])

        waited = []
        with tempfile.TemporaryDirectory() as folder:
            lock_file = Path(folder) / "jitter.lock"
            lock_file.write_text(f"{time.time():.6f}", encoding="ascii")
            with patch("bilioshi.danmaku_pacing.task_wait", side_effect=waited.append), \
                 patch("bilioshi.danmaku_pacing.random.uniform", return_value=0.15):
                send_paced(lambda: "ok", lock_path=lock_file, min_interval=10.0, jitter_ratio=0.2)
        self.assertEqual(len(waited), 1)
        self.assertGreater(waited[0], 10.5)
        self.assertLessEqual(waited[0], 11.6)
