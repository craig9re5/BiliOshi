from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

from bilioshi import http as bili_http
from bilioshi import policies
from bilioshi.accounts import AccountStore
from bilioshi.danmaku_pacing import send_paced, shared_lock_path
from bilioshi.services.danmaku import send_danmaku_batch
from desktop.engine import Engine
from desktop.storage import initialize


class EngineSuspensionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        initialize(self.root, [{"name": "A", "uid": 1, "room": 2}])
        self.job = Mock()
        self.engine = Engine(self.root, job=self.job, account_id="uid-1")
        self.engine.next_check = float("inf")

    def test_suspend_stops_spawning_and_activate_reuses_engine(self):
        self.engine.suspend()
        generation = self.engine.generation
        self.assertTrue(self.engine.suspended)
        self.assertFalse(self.job.close.called)

        with patch.object(self.engine, "spawn") as spawn:
            self.engine.tick()
            spawn.assert_not_called()

        self.engine.activate()
        self.assertFalse(self.engine.suspended)
        self.assertGreater(self.engine.generation, generation)
        self.assertEqual(self.engine.next_check, 0)

    def test_suspended_apply_probe_spawns_no_worker(self):
        self.engine.suspend()
        with patch.object(self.engine, "spawn") as spawn:
            self.engine._apply_probe({
                "statuses": {"2": {"live_status": 1}},
                "medals": {},
                "tasks": {},
            }, self.engine.last_check or 0)
            spawn.assert_not_called()
            self.assertEqual(self.engine.workers, {})

    def test_suspended_status_stays_stale_and_not_running(self):
        self.engine.statuses = {"2": {"live_status": 1}}
        self.engine.status_times = {"2": time.time()}
        self.engine.suspend()
        before = json.loads((self.root / "status.json").read_text())
        self.engine.cycle()
        after = json.loads((self.root / "status.json").read_text())

        self.assertTrue(after["stale"])
        self.assertFalse(after["running"])
        self.assertTrue(after["suspended"])
        self.assertEqual(after["updated"], before["updated"])

    def test_stale_probe_generation_is_discarded(self):
        self.engine.activate()
        self.engine.generation = 3
        self.engine.probe_generation = 2
        with patch.object(self.engine, "_apply_probe") as apply:
            self.engine.probe = Mock()
            self.engine.probe.poll.return_value = 1
            self.engine.probe_path = self.root / "state/probe-old.json"
            self.engine.probe_path.write_text("{}")
            self.engine.next_check = float("inf")
            self.engine.tick()
            apply.assert_not_called()

    def test_http_pool_isolates_tcp_sockets_across_accounts_and_reuses_same_session(self):
        seen = []

        class EchoHandler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):
                body = b'{"code":0,"data":{"ok":true}}'
                seen.append((self.client_address[1], self.headers.get("Cookie", "")))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        class PooledHttp(bili_http._PooledOpenMixin):
            _debuglevel = 0

        handler = PooledHttp()
        bili_http._POOL.close_all()
        server = ThreadingHTTPServer(("127.0.0.1", 0), EchoHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/nav"
            for cookie in (
                "SESSDATA=sess-A; buvid3=dev-A",
                "SESSDATA=sess-B; buvid3=dev-B",
                "SESSDATA=sess-A; buvid3=dev-A",
            ):
                req = urllib.request.Request(url, headers={"Cookie": cookie})
                resp = handler.do_open(http.client.HTTPConnection, req)
                resp.read()
                resp.close()
        finally:
            bili_http._POOL.close_all()
            server.shutdown()
            server.server_close()

        self.assertEqual(len(seen), 3)
        self.assertNotEqual(seen[0][0], seen[1][0])
        self.assertEqual(seen[0][0], seen[2][0])

    def test_cross_account_shared_lock_and_disjoint_danmaku_slices(self):
        store = AccountStore(self.root)
        r1 = store.ensure_root("uid-10001", 10001)
        r2 = store.ensure_root("uid-10002", 10002)
        g1 = shared_lock_path(r1 / "locks", "global-room-entry.lock")
        g2 = shared_lock_path(r2 / "locks", "global-room-entry.lock")
        self.assertIsNotNone(g1)
        self.assertEqual(g1, g2)

        t1 = send_paced(
            time.time,
            lock_path=r1 / "locks" / "room-entry.lock",
            min_interval=0.05,
            global_lock_path=g1,
            global_min_interval=0.22,
        )
        t2 = send_paced(
            time.time,
            lock_path=r2 / "locks" / "room-entry.lock",
            min_interval=0.05,
            global_lock_path=g2,
            global_min_interval=0.22,
        )
        self.assertGreaterEqual(t2 - t1, 0.18)

        # Find two sessions that hash into opposite slots (0 vs 1) in room 2101
        sent_by = {}
        for tag in ("sess-alpha", "sess-beta", "sess-gamma", "sess-delta"):
            picked = []
            gw = Mock(_DANMAKU_MSGS=list(policies._DANMAKU_MSGS))
            gw._send_danmaku.side_effect = lambda _r, m, _s, _j, out=picked: (out.append(m) or True)
            with patch("bilioshi.services.danmaku.safety.probation_until", return_value=0), \
                 patch("bilioshi.services.danmaku.safety.pace_multiplier", return_value=1.0), \
                 patch("bilioshi.services.danmaku.safety.status", return_value={"blocked": False}), \
                 patch("bilioshi.services.danmaku.safety.room_capability_blocked", return_value=False):
                send_danmaku_batch(2101, 10, tag, "csrf", delay=0, _gateway=gw)
            sent_by[tag] = set(picked)

        min_overlap = min(
            len(sent_by[a] & sent_by[b])
            for i, a in enumerate(sent_by)
            for b in list(sent_by)[i + 1 :]
        )
        self.assertEqual(min_overlap, 0)


if __name__ == "__main__":
    unittest.main()
