"""Pure-stdlib release manifest verification, ETag polling, and safe staging.

Core module: zero third-party dependencies, never imports desktop or scripts.
"""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from .runtime import APP_VERSION, read_json, update_json, write_json

DEFAULT_REPO = "craig9re5/BiliOshi"
DEFAULT_MANIFEST_URL = f"https://github.com/{DEFAULT_REPO}/releases/latest/download/latest.json"
# Replaced or rotated via `python tools/release_update.py --generate-keypair --update-public`.
RELEASE_PUBLIC_KEY = "21685ed46654d76988154998a934cfa4ce12c5a7813697aeda33f0f386f9e3b8"

MANIFEST_DOMAIN = "bilioshi-release-v1"
MAX_MANIFEST_BYTES = 65_536
MAX_EXE_BYTES = 250 * 1024 * 1024
DOWNLOAD_CHUNK_BYTES = 65_536
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX_RE = re.compile(r"^[0-9a-f]+$")

# ---------- RFC 8032 Ed25519 (pure standard library) ----------

_ED_P = (1 << 255) - 19
_ED_L = (1 << 252) + 27742317777372353535851937790883648493
_ED_D = (-121665 * pow(121666, _ED_P - 2, _ED_P)) % _ED_P
_ED_I = pow(2, (_ED_P - 1) // 4, _ED_P)


def _ed_recover_x(y, sign):
    if y >= _ED_P:
        return None
    y2 = (y * y) % _ED_P
    u = (y2 - 1) % _ED_P
    v = (_ED_D * y2 + 1) % _ED_P
    v3 = (v * v * v) % _ED_P
    v7 = (v3 * v3 * v) % _ED_P
    x = (u * v3 * pow(u * v7 % _ED_P, (_ED_P - 5) // 8, _ED_P)) % _ED_P
    vx2 = (v * x * x) % _ED_P
    if vx2 == u:
        pass
    elif vx2 == (-u) % _ED_P:
        x = (x * _ED_I) % _ED_P
    else:
        return None
    if x == 0 and sign:
        return None
    if (x & 1) != sign:
        x = _ED_P - x
    return x


_ED_BY = (4 * pow(5, _ED_P - 2, _ED_P)) % _ED_P
_ED_BX = _ed_recover_x(_ED_BY, 0)
_ED_BASE = (_ED_BX, _ED_BY, 1, (_ED_BX * _ED_BY) % _ED_P)
_ED_ZERO = (0, 1, 1, 0)


def _ed_add(p1, p2):
    x1, y1, z1, t1 = p1
    x2, y2, z2, t2 = p2
    a = ((y1 - x1) * (y2 - x2)) % _ED_P
    b = ((y1 + x1) * (y2 + x2)) % _ED_P
    c = (t1 * 2 * _ED_D * t2) % _ED_P
    d = (z1 * 2 * z2) % _ED_P
    e = (b - a) % _ED_P
    f = (d - c) % _ED_P
    g = (d + c) % _ED_P
    h = (b + a) % _ED_P
    return ((e * f) % _ED_P, (g * h) % _ED_P, (f * g) % _ED_P, (e * h) % _ED_P)


def _ed_mul(scalar, point):
    result = _ED_ZERO
    for bit in range(scalar.bit_length() - 1, -1, -1):
        result = _ed_add(result, result)
        if (scalar >> bit) & 1:
            result = _ed_add(result, point)
    return result


def _ed_encode(point):
    x, y, z, _ = point
    zi = pow(z, _ED_P - 2, _ED_P)
    xp = (x * zi) % _ED_P
    yp = (y * zi) % _ED_P
    return (yp | ((xp & 1) << 255)).to_bytes(32, "little")


def _ed_decode(raw):
    if not isinstance(raw, (bytes, bytearray)) or len(raw) != 32:
        return None
    unpacked = int.from_bytes(raw, "little")
    sign = (unpacked >> 255) & 1
    y = unpacked & ((1 << 255) - 1)
    x = _ed_recover_x(y, sign)
    if x is None:
        return None
    return (x, y, 1, (x * y) % _ED_P)


def _ed_expand_seed(seed):
    if isinstance(seed, str):
        seed = bytes.fromhex(seed.strip())
    if not isinstance(seed, (bytes, bytearray)) or len(seed) != 32:
        raise ValueError("Ed25519 密钥种子必须为 32 字节")
    digest = hashlib.sha512(bytes(seed)).digest()
    scalar = int.from_bytes(digest[:32], "little")
    scalar &= (1 << 254) - 8
    scalar |= 1 << 254
    return scalar, digest[32:]


def ed25519_public_key(seed):
    scalar, _ = _ed_expand_seed(seed)
    return _ed_encode(_ed_mul(scalar, _ED_BASE))


def ed25519_sign(seed, message):
    if isinstance(message, str):
        message = message.encode("utf-8")
    scalar, prefix = _ed_expand_seed(seed)
    pub = _ed_encode(_ed_mul(scalar, _ED_BASE))
    r = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % _ED_L
    r_bytes = _ed_encode(_ed_mul(r, _ED_BASE))
    k = int.from_bytes(hashlib.sha512(r_bytes + pub + message).digest(), "little") % _ED_L
    s = (r + k * scalar) % _ED_L
    return r_bytes + s.to_bytes(32, "little")


def ed25519_verify(public_key, message, signature):
    try:
        if isinstance(public_key, str):
            text = public_key.strip().lower()
            if len(text) != 64 or not _HEX_RE.match(text):
                return False
            public_key = bytes.fromhex(text)
        if isinstance(signature, str):
            text = signature.strip().lower()
            if len(text) != 128 or not _HEX_RE.match(text):
                return False
            signature = bytes.fromhex(text)
        if isinstance(message, str):
            message = message.encode("utf-8")
        if len(public_key) != 32 or len(signature) != 64:
            return False
        r_bytes, s_bytes = bytes(signature[:32]), bytes(signature[32:])
        s = int.from_bytes(s_bytes, "little")
        if s >= _ED_L:
            return False
        a_point = _ed_decode(public_key)
        r_point = _ed_decode(r_bytes)
        if a_point is None or r_point is None:
            return False
        k = int.from_bytes(hashlib.sha512(r_bytes + bytes(public_key) + message).digest(), "little") % _ED_L
        lhs = _ed_encode(_ed_mul(8 * s, _ED_BASE))
        rhs = _ed_encode(_ed_mul(8, _ed_add(r_point, _ed_mul(k, a_point))))
        return lhs == rhs
    except Exception:
        return False


# ---------- Version & Manifest Validation ----------


def normalize_version(version):
    if not isinstance(version, str):
        raise ValueError("版本号必须为字符串")
    cleaned = version.strip()
    if cleaned.startswith(("v", "V")):
        cleaned = cleaned[1:]
    parts = cleaned.split(".")
    if not 2 <= len(parts) <= 6 or any(not part.isascii() or not part.isdigit() for part in parts):
        raise ValueError(f"无效版本号格式：{version!r}")
    return ".".join(str(int(part)) for part in parts)


def parse_version(version):
    return tuple(int(part) for part in normalize_version(version).split("."))


def is_newer_version(candidate, current=APP_VERSION):
    return parse_version(candidate) > parse_version(current)


def canonical_manifest_payload(version, exe_sha256, exe_size):
    ver = normalize_version(version)
    digest = str(exe_sha256 or "").strip().lower()
    if not _SHA256_RE.match(digest):
        raise ValueError("无效的 SHA-256 摘要")
    if type(exe_size) is not int or isinstance(exe_size, bool) or not 1 <= exe_size <= MAX_EXE_BYTES:
        raise ValueError("无效的安装包大小")
    return f"{MANIFEST_DOMAIN}\n{ver}\n{digest}\n{exe_size}".encode("utf-8")


def build_signed_manifest(*, version, exe_url, exe_sha256, exe_size, signing_seed, notes="", published_at=""):
    ver = normalize_version(version)
    digest = str(exe_sha256).strip().lower()
    payload = canonical_manifest_payload(ver, digest, exe_size)
    sig = ed25519_sign(signing_seed, payload).hex()
    return {
        "schema": 1,
        "version": ver,
        "published_at": published_at or datetime.now(timezone.utc).isoformat(),
        "exe_url": str(exe_url).strip(),
        "exe_sha256": digest,
        "exe_size": exe_size,
        "signature": sig,
        "notes": str(notes or "").strip()[:2000],
    }


def validate_manifest(raw, *, public_key=None, allow_http=False):
    if not isinstance(raw, dict):
        raise ValueError("更新清单格式无效")
    key = RELEASE_PUBLIC_KEY if public_key is None else public_key
    if not key:
        raise ValueError("未配置发布公钥，已拒绝未经签名的更新")
    version = normalize_version(raw.get("version", ""))
    exe_url = str(raw.get("exe_url") or "").strip()
    parsed = urllib.parse.urlsplit(exe_url)
    allowed_schemes = ("https", "http") if allow_http else ("https",)
    if parsed.scheme not in allowed_schemes or not parsed.netloc:
        raise ValueError("更新下载地址必须使用 HTTPS")
    exe_sha256 = str(raw.get("exe_sha256") or "").strip().lower()
    exe_size = raw.get("exe_size")
    signature = str(raw.get("signature") or "").strip().lower()
    payload = canonical_manifest_payload(version, exe_sha256, exe_size)
    if not ed25519_verify(key, payload, signature):
        raise ValueError("更新包数字签名校验失败，已拒绝安装")
    return {
        "schema": 1,
        "version": version,
        "published_at": str(raw.get("published_at") or "").strip()[:64],
        "exe_url": exe_url,
        "exe_sha256": exe_sha256,
        "exe_size": exe_size,
        "signature": signature,
        "notes": str(raw.get("notes") or "").strip()[:2000],
    }


# ---------- Persistent Settings & State ----------


def updater_settings_path(host_root):
    return Path(host_root) / "state" / "updater-settings.json"


def updater_state_path(host_root):
    return Path(host_root) / "state" / "updater-state.json"


def load_updater_settings(host_root):
    try:
        saved = read_json(updater_settings_path(host_root), {})
    except (OSError, ValueError):
        saved = {}
    if not isinstance(saved, dict):
        saved = {}
    auto_update = saved.get("auto_update", True)
    if type(auto_update) is not bool:
        auto_update = True
    mirror = saved.get("mirror_prefix", "")
    if not isinstance(mirror, str):
        mirror = ""
    return {"auto_update": auto_update, "mirror_prefix": mirror.strip()}


def save_updater_settings(host_root, *, auto_update=None, mirror_prefix=None):
    def mutate(current):
        base = current if isinstance(current, dict) else {}
        next_auto = base.get("auto_update", True) if auto_update is None else bool(auto_update)
        next_mirror = base.get("mirror_prefix", "") if mirror_prefix is None else str(mirror_prefix).strip()
        if next_mirror:
            parsed = urllib.parse.urlsplit(next_mirror)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("镜像加速地址必须以 https:// 开头")
        return {"auto_update": bool(next_auto), "mirror_prefix": next_mirror}

    return update_json(updater_settings_path(host_root), mutate, {})


def load_updater_state(host_root):
    try:
        state = read_json(updater_state_path(host_root), {})
    except (OSError, ValueError):
        state = {}
    return state if isinstance(state, dict) else {}


def update_updater_state(host_root, fn):
    return update_json(
        updater_state_path(host_root),
        lambda current: fn(current if isinstance(current, dict) else {}),
        {},
    )


def apply_mirror_prefix(url, mirror_prefix=""):
    prefix = str(mirror_prefix or "").strip()
    if not prefix:
        return url
    parsed = urllib.parse.urlsplit(prefix)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("镜像加速地址必须使用 HTTPS")
    if url.startswith("https://github.com/"):
        return prefix.rstrip("/") + "/" + url
    return url


# ---------- Network Manifest Polling & Binary Staging ----------


def sha256_file(path):
    hasher = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(DOWNLOAD_CHUNK_BYTES)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def fetch_manifest(
    host_root,
    *,
    current_version=APP_VERSION,
    public_key=None,
    manifest_url=None,
    mirror_prefix="",
    opener=None,
    timeout=15,
    allow_http=False,
):
    """Fetch and cryptographically verify latest.json using ETag conditional GET."""
    host_root = Path(host_root)
    state = load_updater_state(host_root)
    base_url = manifest_url or os.environ.get("BILIOSHI_UPDATE_MANIFEST_URL") or DEFAULT_MANIFEST_URL
    target_url = apply_mirror_prefix(base_url, mirror_prefix)
    parsed_url = urllib.parse.urlsplit(target_url)
    if parsed_url.scheme not in (("https", "http") if allow_http else ("https",)) or not parsed_url.netloc:
        raise ValueError("更新清单地址必须使用 HTTPS")

    headers = {
        "Accept": "application/json",
        "User-Agent": f"BiliOshi/{current_version}",
    }
    etag = state.get("etag")
    cached_manifest = state.get("cached_manifest")
    if isinstance(etag, str) and etag and isinstance(cached_manifest, dict):
        headers["If-None-Match"] = etag

    req = urllib.request.Request(target_url, headers=headers, method="GET")
    open_fn = opener or urllib.request.urlopen
    now = time.time()
    try:
        with open_fn(req, timeout=timeout) as resp:
            body = resp.read(MAX_MANIFEST_BYTES + 1)
            if len(body) > MAX_MANIFEST_BYTES:
                raise ValueError("更新清单体积超出限制")
            resp_headers = getattr(resp, "headers", None) or {}
            new_etag = resp_headers.get("ETag", "") if hasattr(resp_headers, "get") else ""
        manifest = validate_manifest(
            json.loads(body.decode("utf-8")),
            public_key=public_key,
            allow_http=allow_http,
        )
        update_updater_state(
            host_root,
            lambda cur: {
                **cur,
                "etag": str(new_etag or ""),
                "cached_manifest": manifest,
                "last_checked_at": now,
                "last_error": "",
            },
        )
    except urllib.error.HTTPError as exc:
        try:
            if exc.code == 304 and isinstance(cached_manifest, dict):
                manifest = validate_manifest(
                    cached_manifest,
                    public_key=public_key,
                    allow_http=allow_http,
                )
                update_updater_state(
                    host_root,
                    lambda cur: {**cur, "last_checked_at": now, "last_error": ""},
                )
            else:
                raise
        finally:
            try:
                exc.close()
            except Exception:
                pass

    skipped = state.get("skipped_versions")
    skipped_map = skipped if isinstance(skipped, dict) else {}
    newer = is_newer_version(manifest["version"], current_version)
    return {
        "manifest": manifest,
        "has_update": bool(newer and manifest["version"] not in skipped_map),
        "skipped_reason": skipped_map.get(manifest["version"], "") if newer else "",
        "checked_at": now,
    }


def download_release_exe(
    host_root,
    manifest,
    *,
    public_key=None,
    mirror_prefix="",
    opener=None,
    cancel_event=None,
    timeout=30,
    allow_http=False,
):
    """Stream, size-bound, and SHA-256 verify the signed release executable."""
    verified = validate_manifest(manifest, public_key=public_key, allow_http=allow_http)
    updates_dir = Path(host_root) / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    final_path = updates_dir / f"BiliOshi-{verified['version']}.exe"
    if final_path.is_file():
        try:
            if (
                final_path.stat().st_size == verified["exe_size"]
                and sha256_file(final_path) == verified["exe_sha256"]
            ):
                prune_staged_updates(host_root, keep_versions={verified["version"]})
                return final_path
        except OSError:
            pass

    target_url = apply_mirror_prefix(verified["exe_url"], mirror_prefix)
    req = urllib.request.Request(
        target_url,
        headers={"Accept": "application/octet-stream", "User-Agent": f"BiliOshi/{APP_VERSION}"},
        method="GET",
    )
    part_path = updates_dir / f"BiliOshi-{verified['version']}.exe.{os.getpid()}.part"
    open_fn = opener or urllib.request.urlopen
    hasher = hashlib.sha256()
    total = 0
    try:
        with open_fn(req, timeout=timeout) as resp, part_path.open("wb") as out:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError("更新下载已取消")
                chunk = resp.read(DOWNLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                total += len(chunk)
                if total > verified["exe_size"]:
                    raise ValueError("下载体积超出签名清单声明大小")
                hasher.update(chunk)
                out.write(chunk)
        if total != verified["exe_size"]:
            raise ValueError("更新包下载不完整")
        if hasher.hexdigest() != verified["exe_sha256"]:
            raise ValueError("更新包哈希校验不匹配，已丢弃")
        os.replace(part_path, final_path)
    except BaseException:
        try:
            part_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    prune_staged_updates(host_root, keep_versions={verified["version"]})
    return final_path


def prune_staged_updates(host_root, *, keep_versions=(), current_version=None):
    """Remove obsolete or already-installed staged executables under updates/."""
    updates_dir = Path(host_root) / "updates"
    if not updates_dir.is_dir():
        return
    keep_names = {f"BiliOshi-{ver}.exe" for ver in keep_versions}
    for item in updates_dir.iterdir():
        if not item.is_file():
            continue
        if item.name in keep_names:
            if current_version is not None:
                match = re.match(r"^BiliOshi-(.+)\.exe$", item.name)
                if match:
                    try:
                        if not is_newer_version(match.group(1), current_version):
                            item.unlink(missing_ok=True)
                            continue
                    except ValueError:
                        pass
            continue
        try:
            item.unlink(missing_ok=True)
        except OSError:
            # A running --apply-update helper still holds its own image briefly.
            continue


def mark_skipped_version(host_root, version, reason):
    ver = normalize_version(version)
    return update_updater_state(
        host_root,
        lambda cur: {
            **cur,
            "skipped_versions": {
                **(cur.get("skipped_versions") if isinstance(cur.get("skipped_versions"), dict) else {}),
                ver: str(reason or "该版本自检未通过")[:240],
            },
        },
    )
