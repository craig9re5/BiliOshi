"""Bilibili WBI query parameter signing (authenticated and public sessions)."""

import hashlib
import threading
import time
from typing import Dict, Optional, Tuple
import urllib.parse

from .http import get_json
from .session_headers import DEFAULT_UA, session_headers

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
]
_CACHE_TTL = 1800.0
_CACHE: Dict[str, Tuple[float, str]] = {}
_LOCK = threading.Lock()


def extract_mixin_key(wbi_img: dict) -> str:
    """Derive the 32-character WBI mixin key from nav response image URLs."""
    img_url = str(wbi_img.get("img_url") or "")
    sub_url = str(wbi_img.get("sub_url") or "")
    img_key = img_url.rsplit("/", 1)[-1].split(".")[0]
    sub_key = sub_url.rsplit("/", 1)[-1].split(".")[0]
    orig = img_key + sub_key
    if len(orig) < 64:
        raise ValueError("签名密钥长度不足")
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


def get_mixin_key(sessdata: str = "", bili_jct: str = "", *, public_cookies: str = "") -> Optional[str]:
    """Fetch and cache the current WBI mixin key for an authenticated or public session."""
    cache_key = sessdata[:16] if sessdata else "public"
    now = time.monotonic()
    with _LOCK:
        cached = _CACHE.get(cache_key)
        if cached and now - cached[0] < _CACHE_TTL:
            return cached[1]
    if sessdata and bili_jct:
        headers = session_headers(sessdata, bili_jct)
    else:
        headers = {"User-Agent": DEFAULT_UA, "Referer": "https://www.bilibili.com/"}
        if public_cookies:
            headers["Cookie"] = public_cookies
    resp = get_json("https://api.bilibili.com/x/web-interface/nav", headers)
    wbi_img = ((resp or {}).get("data") or {}).get("wbi_img")
    if not isinstance(wbi_img, dict):
        return None
    try:
        key = extract_mixin_key(wbi_img)
    except ValueError:
        return None
    with _LOCK:
        if len(_CACHE) >= 16:
            _CACHE.clear()
        _CACHE[cache_key] = (now, key)
    return key


def sign_wbi(params: dict, mixin_key: str) -> dict:
    """Return a copy of query parameters signed with `wts` and `w_rid`."""
    signed = dict(params)
    signed["wts"] = int(time.time())
    signed.pop("w_rid", None)
    filtered = {
        k: "".join(c for c in str(v) if c not in "!'()*")
        for k, v in signed.items()
    }
    query = urllib.parse.urlencode(sorted(filtered.items()))
    signed["w_rid"] = hashlib.md5((query + mixin_key).encode("utf-8")).hexdigest()
    return signed
