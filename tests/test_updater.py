"""Release signature verification, idle-watch auto-update gate, and rollback contracts."""

import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

from bilioshi.runtime import read_json
from bilioshi.updater import (
    build_signed_manifest,
    ed25519_public_key,
    ed25519_sign,
    ed25519_verify,
    fetch_manifest,
    load_updater_state,
    validate_manifest,
)
from desktop import supervisor
from desktop.updater import DesktopUpdater, evaluate_idle_blocker, run_apply_update


class _FakeResponse:
    def __init__(self, body: bytes, *, headers=None):
        self._stream = io.BytesIO(body)
        self.headers = headers or {}

    def read(self, size=-1):
        return self._stream.read(size)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._stream.close()


class UpdaterContractTests(unittest.TestCase):
    def test_ed25519_rfc8032_vector_and_manifest_security_boundaries(self):
        # Official RFC 8032 §7.1 TEST 2 vector (1-byte message 0x72).
        rfc_seed = bytes.fromhex(
            "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb"
        )
        expected_pub = "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c"
        expected_sig = (
            "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
            "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00"
        )
        self.assertEqual(ed25519_public_key(rfc_seed).hex(), expected_pub)
        self.assertEqual(ed25519_sign(rfc_seed, b"\x72").hex(), expected_sig)
        self.assertTrue(ed25519_verify(expected_pub, b"\x72", expected_sig))
        self.assertFalse(ed25519_verify(expected_pub, b"\x73", expected_sig))

        exe_bytes = b"MZ-synthetic-release-binary"
        exe_sha = hashlib.sha256(exe_bytes).hexdigest()
        manifest = build_signed_manifest(
            version="2026.12.1.1",
            exe_url="https://github.com/craig9re5/BiliOshi/releases/download/v2026.12.1.1/BiliOshi.exe",
            exe_sha256=exe_sha,
            exe_size=len(exe_bytes),
            signing_seed=rfc_seed,
            notes="可靠性升级",
        )
        with self.assertRaises(ValueError):
            validate_manifest({**manifest, "version": "2026.12.9.9"}, public_key=expected_pub)
        with self.assertRaises(ValueError):
            validate_manifest(
                {**manifest, "exe_url": "http://example.com/BiliOshi.exe"},
                public_key=expected_pub,
            )

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seen_requests = []

            def opener(req, timeout=15):
                seen_requests.append((req.full_url, dict(req.header_items())))
                if req.get_header("If-none-match") == '"v1-tag"':
                    raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)
                return _FakeResponse(json.dumps(manifest).encode("utf-8"), headers={"ETag": '"v1-tag"'})

            first = fetch_manifest(
                root,
                current_version="2026.10.18.3",
                public_key=expected_pub,
                mirror_prefix="https://mirror.example.com",
                opener=opener,
            )
            self.assertTrue(first["has_update"])
            self.assertTrue(seen_requests[0][0].startswith("https://mirror.example.com/https://github.com/"))

            second = fetch_manifest(
                root,
                current_version="2026.10.18.3",
                public_key=expected_pub,
                opener=opener,
            )
            self.assertTrue(second["has_update"])
            self.assertEqual(second["manifest"]["version"], "2026.12.1.1")
            # Downgrade replay of an older validly-signed manifest must not report an update.
            downgrade = fetch_manifest(
                root,
                current_version="2026.12.2.1",
                public_key=expected_pub,
                opener=opener,
            )
            self.assertFalse(downgrade["has_update"])

    def test_updater_defers_while_room_is_live_and_silently_applies_once_offline(self):
        seed = bytes(range(1, 33))
        pub = ed25519_public_key(seed).hex()
        new_exe_bytes = b"MZ-new-verified-binary"
        manifest = build_signed_manifest(
            version="2026.12.5.1",
            exe_url="https://github.com/craig9re5/BiliOshi/releases/download/v2026.12.5.1/BiliOshi.exe",
            exe_sha256=hashlib.sha256(new_exe_bytes).hexdigest(),
            exe_size=len(new_exe_bytes),
            signing_seed=seed,
        )

        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            install_dir = root / "install"
            install_dir.mkdir()
            installed_exe = install_dir / "BiliOshi.exe"
            installed_exe.write_bytes(b"MZ-old-binary")

            worker_proc = Mock()
            worker_proc.poll.return_value = None
            engine = Mock(
                root=root,
                suspended=False,
                paused=False,
                _started=True,
                probe=None,
                members=[{"name": "测试主播", "room": 101, "uid": 9}],
                last_check=100.0,
                started_at=10.0,
                workers={101: worker_proc},
                safety={"blocked": False},
                statuses={"101": {"live_status": 1}},
            )

            def opener(req, timeout=15):
                if req.full_url.endswith(".json"):
                    return _FakeResponse(json.dumps(manifest).encode("utf-8"))
                return _FakeResponse(new_exe_bytes)

            spawned = []
            exited = []
            with patch("desktop.updater.os.name", "nt"):
                updater = DesktopUpdater(
                    root,
                    idle_blocker=lambda: evaluate_idle_blocker(engine),
                    request_exit=lambda: exited.append(True),
                    opener=opener,
                    public_key=pub,
                    current_version="2026.10.18.3",
                    executable=installed_exe,
                    frozen=True,
                    diagnostic_verifier=lambda path, ver: True,
                    spawner=lambda args, **kw: spawned.append(args) or Mock(),
                    auto_start_background=False,
                )
                result = updater.check_now()
                self.assertTrue(result["ok"])
                self.assertEqual(updater.snapshot()["status"], "ready")
                self.assertIn("下播后静默安装", updater.snapshot()["waiting_reason"])
                self.assertEqual(spawned, [])
                self.assertEqual(exited, [])

                # All live rooms finish streaming -> idle auto-apply launches helper & exits cleanly.
                engine.workers.clear()
                engine.statuses["101"]["live_status"] = 0
                applied = updater.apply_now(manual=False)
                self.assertTrue(applied["applying"])
                self.assertEqual(len(spawned), 1)
                self.assertIn("--apply-update", spawned[0])
                self.assertEqual(spawned[0][spawned[0].index("--apply-update") + 1], str(installed_exe.resolve()))
                self.assertNotIn("--reopen", spawned[0])
                self.assertEqual(exited, [True])
                self.assertIn("token", read_json(root / "supervisor-update.json", {}))

            # Pre-check failure skips the broken version without interrupting live watch.
            bad_manifest = build_signed_manifest(
                version="2026.12.6.1",
                exe_url="https://github.com/craig9re5/BiliOshi/releases/download/v2026.12.6.1/BiliOshi.exe",
                exe_sha256=hashlib.sha256(new_exe_bytes).hexdigest(),
                exe_size=len(new_exe_bytes),
                signing_seed=seed,
            )
            with patch("desktop.updater.os.name", "nt"):
                bad_updater = DesktopUpdater(
                    root,
                    opener=lambda req, timeout=15: _FakeResponse(
                        json.dumps(bad_manifest).encode("utf-8")
                        if req.full_url.endswith(".json")
                        else new_exe_bytes
                    ),
                    public_key=pub,
                    current_version="2026.10.18.3",
                    executable=installed_exe,
                    frozen=True,
                    diagnostic_verifier=Mock(side_effect=RuntimeError("DLL missing")),
                    auto_start_background=False,
                )
                failed = bad_updater.check_now()
                self.assertFalse(failed["ok"])
                self.assertIn("2026.12.6.1", load_updater_state(root).get("skipped_versions", {}))

    def test_apply_update_replaces_binary_and_rolls_back_on_unhealthy_startup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            supervisor.request_run(root)
            install_dir = root / "app"
            install_dir.mkdir()
            target_exe = install_dir / "BiliOshi.exe"
            staged_exe = root / "updates" / "BiliOshi-new.exe"
            staged_exe.parent.mkdir()
            target_exe.write_bytes(b"OLD-EXE-BYTES")
            staged_exe.write_bytes(b"NEW-EXE-BYTES")

            launched = []
            token = supervisor.begin_update(root, seconds=120)
            code = run_apply_update(
                root,
                target_exe,
                token,
                staged_exe=staged_exe,
                wait_mutexes=False,
                health_waiter=lambda *_: True,
                launcher=lambda exe, _root, *args: launched.append((Path(exe).read_bytes(), args)) or Mock(poll=lambda: None),
            )
            self.assertEqual(code, 0)
            self.assertEqual(target_exe.read_bytes(), b"NEW-EXE-BYTES")
            self.assertEqual(read_json(root / "supervisor-update.json", {}), {})
            self.assertEqual(launched, [(b"NEW-EXE-BYTES", ("--supervised",))])
            self.assertEqual(len(list(install_dir.glob("BiliOshi.previous-*.exe"))), 1)

            # Simulate broken post-update startup -> automatic rollback to previous binary.
            broken_staged = root / "updates" / "BiliOshi-broken.exe"
            broken_staged.write_bytes(b"BROKEN-EXE-BYTES")
            rollback_launches = []
            token2 = supervisor.begin_update(root, seconds=120)
            code2 = run_apply_update(
                root,
                target_exe,
                token2,
                staged_exe=broken_staged,
                wait_mutexes=False,
                health_waiter=lambda *_: False,
                launcher=lambda exe, _root, *args: (
                    rollback_launches.append((Path(exe).read_bytes(), args))
                    or Mock(pid=0, poll=lambda: 1, terminate=lambda: None)
                ),
            )
            self.assertEqual(code2, 1)
            self.assertEqual(target_exe.read_bytes(), b"NEW-EXE-BYTES")
            self.assertEqual(read_json(root / "supervisor-update.json", {}), {})
            self.assertEqual(rollback_launches[-1], (b"NEW-EXE-BYTES", ("--supervised",)))
            self.assertTrue(load_updater_state(root).get("skipped_versions"))

    def test_manifest_http_404_is_treated_as_unpublished_without_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            def opener(request, timeout=15):
                raise urllib.error.HTTPError(request.full_url, 404, "Not Found", {}, None)

            updater = DesktopUpdater(
                root,
                current_version="2026.10.18.3",
                public_key=ed25519_public_key(b"\x11" * 32).hex(),
                manifest_url="https://example.test/latest.json",
                opener=opener,
                self_updatable=True,
                executable=root / "BiliOshi.exe",
            )
            result = updater.check_now(download=False)
            self.assertTrue(result["ok"])
            self.assertFalse(result["has_update"])
            self.assertTrue(result.get("not_published"))
            snap = updater.snapshot()
            self.assertEqual(snap["status"], "up_to_date")
            self.assertEqual(snap["error"], "")

    def test_read_json_retries_transient_permission_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "monitor-health.json"
            target.write_text('{"ok": true}', encoding="utf-8")
            real_read_text = Path.read_text
            calls = {"n": 0}

            def flaky_read(self_path, *args, **kwargs):
                if self_path == target and calls["n"] < 2:
                    calls["n"] += 1
                    raise PermissionError(13, "Permission denied", str(self_path))
                return real_read_text(self_path, *args, **kwargs)

            with patch.object(Path, "read_text", flaky_read):
                self.assertEqual(read_json(target, {}), {"ok": True})
            self.assertEqual(calls["n"], 2)


if __name__ == "__main__":
    unittest.main()
