"""Validate Bilibili credentials without printing secret values."""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional, Tuple
from .credentials import cookie_path
from .runtime import read_json
from .session_headers import session_headers
from .http import request_json

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _load_local_cookies() -> Tuple[Optional[str], Optional[str]]:
    path = cookie_path()
    if not path.exists():
        return (None, None)
    try:
        data = read_json(path, {})
    except (OSError, json.JSONDecodeError):
        return (None, None)
    return (data.get("SESSDATA"), data.get("bili_jct"))


def _public_uid(value) -> int:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isascii() and value.isdigit() and int(value) > 0:
        return int(value)
    return 0


def parse_nav_profile(data: dict) -> dict:
    """Extract sanitized public identity, level, EXP and coin fields from /nav data."""
    name = data.get("uname") or "已登录账号"
    face = data.get("face")
    level_info = data.get("level_info") if isinstance(data.get("level_info"), dict) else {}
    level = int(level_info.get("current_level") or 0)
    current_exp = int(level_info.get("current_exp") or 0)
    raw_next = level_info.get("next_exp", 0)
    is_max_level = level >= 6 or (isinstance(raw_next, str) and raw_next == "--")
    try:
        next_exp = 0 if is_max_level else int(raw_next or 0)
    except (TypeError, ValueError):
        next_exp = 0
    try:
        coins = round(float(data.get("money") or 0), 1)
    except (TypeError, ValueError):
        coins = 0.0
    vip_label = ""
    if isinstance(data.get("vip_label"), dict):
        vip_label = str(data["vip_label"].get("text") or "")
    elif isinstance(data.get("vip"), dict):
        vip_label = str(((data["vip"].get("label")) or {}).get("text") or "")
    return {
        "name": name,
        "uid": _public_uid(data.get("mid")),
        "face": face if isinstance(face, str) else "",
        "level": level,
        "current_exp": current_exp,
        "next_exp": next_exp,
        "is_max_level": is_max_level,
        "coins": coins,
        "vip_label": vip_label,
    }


def check_daily_profile(sessdata: str, bili_jct: str) -> Tuple[bool, str, dict]:
    """Validate credentials and return identity plus account level/EXP/coins."""
    try:
        body = request_json(
            "https://api.bilibili.com/x/web-interface/nav",
            session_headers(sessdata, bili_jct),
            timeout=15,
            auth_probe=True,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return (False, f"登录状态检查失败: {type(exc).__name__}", {"error_kind": "network"})
    if body.get("error_kind") == "network":
        return (False, "网络连接异常，请稍后重试", {"error_kind": "network"})
    data = body.get("data") or {}
    if body.get("code") == 0 and data.get("isLogin") is True:
        profile = parse_nav_profile(data)
        return (True, profile["name"], profile)
    return (
        False,
        f"{body.get('code', '?')} {body.get('message', '账号未登录')}",
        {"error_kind": body.get("error_kind", "auth")},
    )


def check_login_profile(sessdata: str, bili_jct: str) -> Tuple[bool, str, dict]:
    """Validate credentials and keep only the public identity fields the UI needs."""
    try:
        body = request_json(
            "https://api.bilibili.com/x/web-interface/nav",
            session_headers(sessdata, bili_jct),
            timeout=15,
            auth_probe=True,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        return (False, f"认证接口请求失败: {type(exc).__name__}", {})
    if body.get("error_kind") == "network":
        return (False, "认证接口请求失败: network", {})
    data = body.get("data") or {}
    if body.get("code") == 0 and data.get("isLogin") is True:
        name = data.get("uname") or "已登录账号"
        face = data.get("face")
        return (True, name, {
            "name": name,
            "uid": _public_uid(data.get("mid")),
            "face": face if isinstance(face, str) else "",
        })
    return (False, f"{body.get('code', '?')} {body.get('message', '账号未登录')}", {})


def check_login(sessdata: str, bili_jct: str) -> Tuple[bool, str]:
    valid, message, _profile = check_login_profile(sessdata, bili_jct)
    return (valid, message)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 B 站 Cookie 登录态")
    parser.add_argument("--sessdata")
    parser.add_argument("--bili-jct")
    args = parser.parse_args()
    local_sessdata, local_bili_jct = _load_local_cookies()
    sessdata = args.sessdata or os.environ.get("SESSDATA") or local_sessdata
    bili_jct = args.bili_jct or os.environ.get("BILI_JCT") or local_bili_jct
    if not sessdata or not bili_jct:
        print("❌ 缺少 SESSDATA 或 BILI_JCT。", file=sys.stderr)
        return 1
    valid, message = check_login(sessdata, bili_jct)
    if not valid:
        print(
            f"❌ B 站登录态无效（{message}）。请在本机运行 setup_local_cookie.py 更新 Cookie。",
            file=sys.stderr,
        )
        return 1
    print(f"✅ B 站登录态有效：{message}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
