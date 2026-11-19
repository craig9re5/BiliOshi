"""Contract tests covering P0 WebUI integrity, P1 caching/pooling, and P2 cleanups."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    tomllib = None
import unittest
from unittest.mock import Mock, patch
import urllib.error
import urllib.request

from bilioshi import heartbeat, http as http_mod, operating_mode, runtime, safety
from bilioshi.application import AppContext
from bilioshi.context import RuntimeContext, use_context
from desktop.engine import Engine
from desktop.storage import initialize
from desktop.webui.window import SNAPSHOT_KEEPALIVE_SECONDS, WebHost


REPO_ROOT = Path(__file__).resolve().parent.parent


class WebUIAndPackageContractTests(unittest.TestCase):
    def test_versions_are_synchronized(self):
        pyproject_path = REPO_ROOT / "pyproject.toml"
        if tomllib is not None:
            with pyproject_path.open("rb") as fh:
                pyproject_version = tomllib.load(fh)["project"]["version"]
        else:
            match = re.search(
                r'(?ms)^\[project\]\s+.*?^version\s*=\s*"([^"]+)"',
                pyproject_path.read_text(encoding="utf-8"),
            )
            self.assertIsNotNone(match, "version not found under [project] in pyproject.toml")
            pyproject_version = match.group(1)
        pkg_version = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["version"]
        self.assertEqual(runtime.APP_VERSION, pyproject_version)
        self.assertEqual(runtime.APP_VERSION, pkg_version)

    def test_webui_compiled_assets_and_html_refs(self):
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tools" / "build_webui.py"), "--check"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, msg=proc.stderr or proc.stdout)

        assets_dir = REPO_ROOT / "desktop" / "webui" / "assets"
        html = (assets_dir / "index.html").read_text(encoding="utf-8")
        refs = re.findall(r'(?:src|href)="([^"]+)"', html)
        self.assertTrue(refs)
        for ref in refs:
            if ref.startswith(("http://", "https://", "data:")):
                continue
            target = (assets_dir / ref).resolve()
            self.assertTrue(target.is_file(), msg=f"Missing WebUI asset referenced by index.html: {ref}")

        node = shutil.which("node")
        if node:
            for js_file in sorted((assets_dir / "js").glob("*.js")):
                check = subprocess.run(
                    [node, "--check", str(js_file)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(check.returncode, 0, msg=f"Syntax check failed for {js_file.name}: {check.stderr}")


class WebHostSnapshotPushTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        initialize(self.root, [{"room": 7, "uid": 9, "name": "测试主播"}])
        self.engine = Engine(self.root, job=Mock())

    def test_push_snapshot_deduplicates_and_respects_force_and_keepalive(self):
        host = WebHost(self.engine)
        host._window = Mock()
        host._eval = Mock(return_value=True)
        host._update_tray = Mock()
        host._notify = Mock(return_value=True)

        base = {"updated": 100.0, "paused": False, "rows": [{"room": 7, "beats": 1}]}
        self.assertTrue(host._push_snapshot(dict(base), now=10.0))
        self.assertEqual(host._eval.call_count, 1)

        # Changing only the volatile "updated" timestamp within keepalive is skipped.
        self.assertFalse(host._push_snapshot({**base, "updated": 101.0}, now=11.0))
        self.assertEqual(host._eval.call_count, 1)

        # push_now sets the wake flag for the pump loop; force pushes immediately.
        host.push_now()
        self.assertTrue(host._snapshot_requested.is_set())
        self.assertTrue(host._push_snapshot({**base, "updated": 101.5}, force=True, now=11.5))
        self.assertEqual(host._eval.call_count, 2)

        # Keepalive interval triggers a refresh even when snapshot content is stable.
        self.assertTrue(
            host._push_snapshot(
                {**base, "updated": 120.0},
                now=11.5 + SNAPSHOT_KEEPALIVE_SECONDS + 0.1,
            )
        )
        self.assertEqual(host._eval.call_count, 3)

        # Content mutation triggers immediately.
        self.assertTrue(host._push_snapshot({**base, "paused": True, "updated": 121.0}, now=28.0))
        self.assertEqual(host._eval.call_count, 4)


class RuntimeStatCacheTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)
        initialize(self.root, [{"room": 1, "uid": 10, "name": "一号"}, {"room": 2, "uid": 20, "name": "二号"}, {"room": 3, "uid": 30, "name": "三号"}])

    def test_file_stat_signature_tracks_lifecycle(self):
        path = self.root / "sample.json"
        self.assertIsNone(runtime.file_stat_signature(path))
        runtime.write_json(path, {"v": 1})
        sig1 = runtime.file_stat_signature(path)
        self.assertIsNotNone(sig1)
        runtime.write_json(path, {"v": 22})
        sig2 = runtime.file_stat_signature(path)
        self.assertNotEqual(sig1, sig2)
        path.unlink()
        self.assertIsNone(runtime.file_stat_signature(path))

    def test_operating_mode_cache_hits_and_invalidates_on_write(self):
        settings_path = self.root / "settings.json"
        runtime.write_json(settings_path, {"run_mode": "aggressive"})
        with use_context(RuntimeContext(root=self.root)), patch(
            "bilioshi.runtime._read_json", wraps=runtime._read_json
        ) as spy:
            self.assertEqual(operating_mode.current_profile(), operating_mode.PROFILES["aggressive"])
            first_calls = spy.call_count
            self.assertEqual(operating_mode.current_profile(), operating_mode.PROFILES["aggressive"])
            self.assertEqual(operating_mode.current_profile(), operating_mode.PROFILES["aggressive"])
            self.assertEqual(spy.call_count, first_calls)

            runtime.write_json(settings_path, {"run_mode": "stable"})
            self.assertEqual(operating_mode.current_profile(), operating_mode.PROFILES["stable"])
            self.assertEqual(spy.call_count, first_calls + 1)

    def test_app_context_read_credentials_caches_unseal_and_invalidates(self):
        runtime.write_json(self.root / "credentials.json", {"SESSDATA": "s1", "bili_jct": "j1"})
        ctx = AppContext(self.root)
        with patch("bilioshi.runtime.unseal", wraps=runtime.unseal) as spy:
            creds = ctx.credentials()
            self.assertEqual(creds, ("s1", "j1"))
            self.assertEqual(ctx.credentials(), ("s1", "j1"))
            self.assertEqual(ctx.safety_status().get("blocked"), False)
            self.assertEqual(spy.call_count, 1)

            runtime.write_json(self.root / "credentials.json", {"SESSDATA": "s2", "bili_jct": "j2"})
            self.assertEqual(ctx.credentials(), ("s2", "j2"))
            self.assertEqual(spy.call_count, 2)

    def test_app_context_query_tasks_concurrent_and_error_isolated(self):
        ctx = AppContext(self.root)
        members = [
            {"room": 1, "uid": 10, "name": "一号"},
            {"room": 2, "uid": 20, "name": "二号"},
            {"room": 3, "uid": 30, "name": "三号"},
        ]
        lock = threading.Lock()
        seen_threads = set()

        def fake_task_info(room, up_id, sessdata, bili_jct):
            with lock:
                seen_threads.add(threading.get_ident())
            if room == 2:
                return None
            return {
                "task_info": [{"kind": "watch", "done": True}],
                "intimacy": room * 10,
                "next_intimacy": 100,
                "task_light_days": 5,
                "is_lighted": True,
            }

        ctx.gateway = Mock()
        ctx.gateway.get_fans_club_task_info.side_effect = fake_task_info
        tasks, errors = ctx._query_tasks(members, ("sess", "jct"))
        self.assertEqual(set(tasks.keys()), {"1", "3"})
        self.assertEqual(tasks["1"]["tasks"][0]["kind"], "watch")
        self.assertIn("2", errors)
        self.assertGreaterEqual(len(seen_threads), 1)


class HttpConnectionPoolTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(http_mod._POOL.close_all)
        http_mod._POOL.close_all()

    def test_pooled_http_handler_reuses_keepalive_and_discards_500(self):
        tcp_setups = 0

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def setup(self):
                nonlocal tcp_setups
                tcp_setups += 1
                super().setup()

            def log_message(self, format, *args):
                return

            def do_GET(self):
                status = 500 if self.path == "/err" else 200
                body = b'{"code":0}' if status == 200 else b'{"code":-1}'
                self.send_response(status)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "keep-alive")
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)

        handler = http_mod._PooledHTTPHandler()
        for _ in range(3):
            req = urllib.request.Request(f"http://127.0.0.1:{port}/ok", method="GET")
            resp = handler.http_open(req)
            try:
                self.assertEqual(resp.status, 200)
                self.assertEqual(resp.read(), b'{"code":0}')
            finally:
                resp.close()
        self.assertEqual(tcp_setups, 1)

        err_req = urllib.request.Request(f"http://127.0.0.1:{port}/err", method="GET")
        err_resp = handler.http_open(err_req)
        try:
            self.assertEqual(err_resp.status, 500)
            err_resp.read()
        finally:
            err_resp.close()

        req_after = urllib.request.Request(f"http://127.0.0.1:{port}/ok", method="GET")
        resp_after = handler.http_open(req_after)
        try:
            self.assertEqual(resp_after.status, 200)
            resp_after.read()
        finally:
            resp_after.close()
        self.assertEqual(tcp_setups, 2)

    def test_pooled_open_retries_get_once_never_post(self):
        pool = http_mod._ConnectionPool()
        stale_get = Mock()
        stale_get.sock = Mock()
        stale_get.request.side_effect = http.client.RemoteDisconnected("eof")
        fresh_resp = Mock()
        fresh_resp.status = 200
        fresh_resp.reason = "OK"
        fresh_resp.isclosed.return_value = True
        fresh_resp.will_close = True
        fresh_conn = Mock()
        fresh_conn.sock = Mock()
        fresh_conn.getresponse.return_value = fresh_resp
        http_factory = Mock(return_value=fresh_conn)

        class DummyHandler(http_mod._PooledOpenMixin):
            _debuglevel = 0

        handler = DummyHandler()
        req_get = urllib.request.Request("http://example.invalid/ping", method="GET")
        pool_key = ("http", "example.invalid", id(None))
        with patch.object(http_mod, "_POOL", pool), patch.object(http_mod, "_socket_unusable", return_value=False):
            pool._idle[pool_key] = http_mod.deque([(stale_get, http_mod.time.monotonic())])
            resp = handler.do_open(http_factory, req_get)
            resp.close()
        self.assertIs(resp, fresh_resp)
        http_factory.assert_called_once()

        stale_post = Mock()
        stale_post.sock = Mock()
        stale_post.request.side_effect = http.client.RemoteDisconnected("eof")
        post_factory = Mock()
        req_post = urllib.request.Request("http://example.invalid/post", data=b"x=1", method="POST")
        with patch.object(http_mod, "_POOL", pool), patch.object(http_mod, "_socket_unusable", return_value=False):
            pool._idle[pool_key] = http_mod.deque([(stale_post, http_mod.time.monotonic())])
            with self.assertRaises(urllib.error.URLError):
                handler.do_open(post_factory, req_post)
        post_factory.assert_not_called()


class HeartbeatNotificationTests(unittest.TestCase):
    def test_notify_forwards_without_openclaw_subprocess(self):
        self.assertFalse(hasattr(heartbeat, "_DISCORD_TARGET"))
        self.assertFalse(hasattr(heartbeat, "subprocess"))
        received = []
        with use_context(RuntimeContext(root=Path("."), notify=received.append)):
            heartbeat._notify("开播提醒")
        self.assertEqual(received, ["开播提醒"])
        # Without an active context, _notify is a safe no-op.
        heartbeat._notify("无上下文")


if __name__ == "__main__":
    unittest.main()
