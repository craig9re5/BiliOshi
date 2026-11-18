"""Four-stage streamer and live room resolver.

1. URL parsing (live.bilibili.com/<id> converted to real room_id; space.bilibili.com/<uid>)
2. Pure numbers: Room/get_info first (real room_id or short_id), then Master/info (UID)
3. Authenticated local fans medal match (zero risk, instant match for followed oshi)
4. WBI-signed /x/web-interface/wbi/search/type with thread-local public buvid3 fallback

Network/risk failures preserve error_kind and are never reported as missing rooms.
"""

import re
from typing import Dict, List, Optional
import urllib.parse

from ..api.medals import all_user_medals
from ..context import CURRENT
from ..http import get_json, request_json
from ..public_session import PublicSession
from ..session_headers import DEFAULT_UA, session_headers
from ..wbi import get_mixin_key, sign_wbi

ROOM_INFO_URL = "https://api.live.bilibili.com/room/v1/Room/get_info"
MASTER_INFO_URL = "https://api.live.bilibili.com/live_user/v1/Master/info"
BATCH_STATUS_URL = "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids"
WBI_SEARCH_URL = "https://api.bilibili.com/x/web-interface/wbi/search/type"
SUGGEST_URL = "https://s.search.bilibili.com/main/suggest"


def _live_headers(sessdata: str = "", bili_jct: str = "", referer: str = "https://live.bilibili.com/") -> dict:
    if sessdata and bili_jct:
        return {**session_headers(sessdata, bili_jct, referer), "Origin": "https://live.bilibili.com"}
    return {"User-Agent": DEFAULT_UA, "Referer": referer}


def _human_fans(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(max(0, n))


def _live_status_label(status_code) -> str:
    if status_code == 1:
        return "直播中"
    if status_code == 2:
        return "轮播中"
    if status_code == 0:
        return "未开播"
    return "待更新"


def resolve_room_meta(room_id_or_short: int, sessdata: str = "", bili_jct: str = "") -> dict:
    """Resolve short or real room_id via Room/get_info and fetch streamer name/medal."""
    headers = _live_headers(sessdata, bili_jct)
    resp = get_json(f"{ROOM_INFO_URL}?room_id={int(room_id_or_short)}", headers)
    if not resp or resp.get("code") != 0 or not isinstance(resp.get("data"), dict):
        return {
            "ok": False,
            "code": (resp or {}).get("code", -1),
            "error": str((resp or {}).get("message") or f"无法查询房间 {room_id_or_short}"),
            "error_kind": (resp or {}).get("error_kind", "api"),
        }
    data = resp["data"]
    real_room = int(data.get("room_id") or 0)
    uid = int(data.get("uid") or 0)
    if real_room <= 0 or uid <= 0:
        return {"ok": False, "code": -1, "error": f"房间 {room_id_or_short} 不存在", "error_kind": "not_found"}

    uname = ""
    medal_name = ""
    master = get_json(f"{MASTER_INFO_URL}?uid={uid}", headers)
    if master and master.get("code") == 0 and isinstance(master.get("data"), dict):
        info = master["data"].get("info") or {}
        uname = str(info.get("uname") or "").strip()
        medal_name = str(master["data"].get("medal_name") or "").strip()

    return {
        "ok": True,
        "room": real_room,
        "short_id": int(data.get("short_id") or 0),
        "uid": uid,
        "name": uname or f"主播_{uid}",
        "medal_name": medal_name,
        "title": str(data.get("title") or ""),
        "area_name": str(data.get("area_name") or ""),
        "live_status": int(data.get("live_status") or 0),
    }


def _lookup_uid(uid: int, sessdata: str = "", bili_jct: str = "") -> dict:
    headers = (
        session_headers(sessdata, bili_jct)
        if sessdata and bili_jct
        else {"User-Agent": DEFAULT_UA, "Referer": "https://www.bilibili.com/"}
    )
    resp = get_json(f"{MASTER_INFO_URL}?uid={uid}", headers)
    if not resp or resp.get("code") != 0 or not isinstance(resp.get("data"), dict):
        if resp and resp.get("error_kind") in ("network", "http", "rate", "edge_limit", "review", "safety"):
            return {
                "type": "error",
                "error_kind": resp["error_kind"],
                "message": f"查询 UID {uid} 失败：{resp.get('message', '请求异常')}",
            }
        return {
            "type": "error",
            "error_kind": (resp or {}).get("error_kind", "api"),
            "message": f"无法查询 UID {uid}：{(resp or {}).get('message', '未知错误')}",
        }
    data = resp["data"]
    room_id = int(data.get("room_id") or 0)
    info = data.get("info") or {}
    uname = str(info.get("uname") or "").strip()
    medal_name = str(data.get("medal_name") or "").strip()
    if room_id <= 0:
        return {
            "type": "error",
            "error_kind": "no_room",
            "message": f"用户 {uname or uid} 尚未开通直播间",
        }
    meta = resolve_room_meta(room_id, sessdata, bili_jct)
    if meta["ok"]:
        return {
            "type": "found",
            "data": {
                "uid": uid,
                "name": uname or meta["name"],
                "room_id": meta["room"],
                "room": meta["room"],
                "medal_name": medal_name or meta["medal_name"],
                "url": f"https://live.bilibili.com/{meta['room']}",
                "title": meta["title"],
                "live_status_code": meta["live_status"],
                "live_status": _live_status_label(meta["live_status"]),
            },
        }
    return {
        "type": "found",
        "data": {
            "uid": uid,
            "name": uname or f"主播_{uid}",
            "room_id": room_id,
            "room": room_id,
            "medal_name": medal_name,
            "url": f"https://live.bilibili.com/{room_id}",
            "title": "",
            "live_status_code": None,
            "live_status": "待更新",
        },
    }


def _public_cookies() -> str:
    ctx = CURRENT.get()
    if ctx is not None and hasattr(ctx, "public_sessions"):
        session = ctx.public_sessions.current()
    else:
        session = PublicSession()
    return session.cookies(DEFAULT_UA)


def _search_users_wbi(keyword: str, sessdata: str = "", bili_jct: str = "", limit: int = 6) -> dict:
    pub_cookie = "" if (sessdata and bili_jct) else _public_cookies()
    mixin_key = get_mixin_key(sessdata, bili_jct, public_cookies=pub_cookie)
    if mixin_key:
        params = sign_wbi(
            {"search_type": "bili_user", "keyword": keyword, "page": "1"},
            mixin_key,
        )
        url = f"{WBI_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        if sessdata and bili_jct:
            headers = session_headers(sessdata, bili_jct, "https://search.bilibili.com/")
        else:
            headers = {"User-Agent": DEFAULT_UA, "Referer": "https://search.bilibili.com/"}
            if pub_cookie:
                headers["Cookie"] = pub_cookie
        resp = get_json(url, headers)
        if resp and resp.get("code") == 0 and isinstance(resp.get("data"), dict):
            raw_list = resp["data"].get("result") or []
            users: List[dict] = []
            for item in raw_list[:limit]:
                if not isinstance(item, dict) or not item.get("mid"):
                    continue
                clean_name = re.sub(r"<[^>]+>", "", str(item.get("uname") or "")).strip()
                fans = int(item.get("fans") or 0)
                room_id = int(item.get("room_id") or 0)
                users.append(
                    {
                        "uid": int(item["mid"]),
                        "name": clean_name,
                        "fans": fans,
                        "fans_display": _human_fans(fans),
                        "room_id": room_id,
                    }
                )
            return {"ok": True, "users": users}
        if resp and resp.get("error_kind") in ("network", "rate", "review", "safety"):
            return {
                "ok": False,
                "error_kind": resp["error_kind"],
                "error": str(resp.get("message") or "搜索服务暂不可用"),
            }

    encoded = urllib.parse.quote(keyword)
    sug_resp = get_json(
        f"{SUGGEST_URL}?term={encoded}&main_ver=v1&highlight=",
        {"User-Agent": DEFAULT_UA, "Referer": "https://www.bilibili.com/"},
    )
    if sug_resp and sug_resp.get("error_kind") == "network":
        return {"ok": False, "error_kind": "network", "error": "网络连接失败，无法搜索主播"}
    tags = (((sug_resp or {}).get("result") or {}).get("tag")) if isinstance(sug_resp, dict) else None
    users = []
    for tag in (tags or [])[:limit]:
        if isinstance(tag, dict) and tag.get("value") and tag.get("ref"):
            users.append(
                {
                    "uid": int(tag["ref"]),
                    "name": str(tag["value"]).strip(),
                    "fans": 0,
                    "fans_display": "未知",
                    "room_id": 0,
                }
            )
    return {"ok": True, "users": users}


def _enrich_rooms_by_uids(users: List[dict], sessdata: str = "", bili_jct: str = "") -> Dict[int, dict]:
    uids = [u["uid"] for u in users if u.get("uid")]
    if not uids:
        return {}
    headers = (
        {**session_headers(sessdata, bili_jct), "Content-Type": "application/x-www-form-urlencoded"}
        if sessdata and bili_jct
        else {
            "User-Agent": DEFAULT_UA,
            "Referer": "https://live.bilibili.com/",
            "Content-Type": "application/x-www-form-urlencoded",
        }
    )
    data = urllib.parse.urlencode([("uids[]", u) for u in uids]).encode("utf-8")
    resp = request_json(BATCH_STATUS_URL, headers, data=data)
    if not resp or resp.get("code") != 0 or not isinstance(resp.get("data"), dict):
        return {"_error_kind": (resp or {}).get("error_kind", "api")}
    out: Dict[int, dict] = {}
    for uid_str, info in resp["data"].items():
        if str(uid_str).isdigit() and isinstance(info, dict):
            room_id = int(info.get("room_id") or 0)
            if room_id > 0:
                out[int(uid_str)] = {
                    "room_id": room_id,
                    "title": str(info.get("title") or ""),
                    "live_status_code": int(info.get("live_status") or 0),
                    "live_status": _live_status_label(int(info.get("live_status") or 0)),
                }
    return out


def _found_payload(uid, name, room_id, medal_name="", title="", live_status_code=None):
    return {
        "type": "found",
        "data": {
            "uid": uid,
            "name": name,
            "room_id": room_id,
            "room": room_id,
            "medal_name": medal_name,
            "url": f"https://live.bilibili.com/{room_id}",
            "title": title,
            "live_status_code": live_status_code,
            "live_status": _live_status_label(live_status_code) if live_status_code is not None else "待更新",
        },
    }


def _match_local_medal(text: str, sessdata: str, bili_jct: str) -> Optional[dict]:
    if not (sessdata and bili_jct):
        return None
    kw_lower = text.lower()
    try:
        medals = all_user_medals(sessdata, bili_jct)
    except Exception:
        return None
    exact = [m for m in medals if m["name"].lower() == kw_lower or m["medal_name"].lower() == kw_lower]
    if len(exact) != 1:
        return None
    hit = exact[0]
    meta = resolve_room_meta(hit["room"], sessdata, bili_jct)
    room_id = meta["room"] if meta["ok"] else hit["room"]
    return _found_payload(
        hit["uid"],
        hit["name"],
        room_id,
        medal_name=hit["medal_name"],
        title=meta["title"] if meta["ok"] else "",
        live_status_code=meta["live_status"] if meta["ok"] else None,
    )


def _format_candidate_row(u: dict, room_map: Dict[int, dict], batch_failed: bool) -> dict:
    rinfo = room_map.get(u["uid"]) if not batch_failed else None
    fallback_room = u.get("room_id") or 0
    if rinfo:
        return {
            "uid": u["uid"], "name": u["name"], "fans": u["fans_display"],
            "has_live": True, "room_id": rinfo["room_id"], "room": rinfo["room_id"],
            "url": f"https://live.bilibili.com/{rinfo['room_id']}",
            "title": rinfo["title"], "live_status": rinfo["live_status"],
        }
    if batch_failed and fallback_room <= 0:
        return {
            "uid": u["uid"], "name": u["name"], "fans": u["fans_display"],
            "has_live": None, "room_id": None, "room": None,
            "url": None, "live_status": "待更新",
        }
    if fallback_room > 0:
        return {
            "uid": u["uid"], "name": u["name"], "fans": u["fans_display"],
            "has_live": True, "room_id": fallback_room, "room": fallback_room,
            "url": f"https://live.bilibili.com/{fallback_room}", "live_status": "待更新",
        }
    return {
        "uid": u["uid"], "name": u["name"], "fans": u["fans_display"],
        "has_live": False, "room_id": None, "room": None,
        "url": None, "live_status": "无直播间",
    }


def resolve_anchor(query: str, sessdata: str = "", bili_jct: str = "", *, limit: int = 5) -> dict:
    """Resolve URL, room_id, short_id, UID, medal name or streamer name."""
    text = str(query or "").strip()
    if not text:
        return {"type": "error", "error_kind": "input", "message": "请输入直播间号、UID、主播昵称或链接"}

    if "live.bilibili.com" in text:
        m = re.search(r"live\.bilibili\.com/(?:blanc/|h5/)?(\d+)", text)
        if not m:
            return {"type": "error", "error_kind": "input", "message": f"无法从链接解析房间号：{text}"}
        meta = resolve_room_meta(int(m.group(1)), sessdata, bili_jct)
        if not meta["ok"]:
            return {"type": "error", "error_kind": meta.get("error_kind", "api"), "message": meta["error"]}
        return _found_payload(meta["uid"], meta["name"], meta["room"], meta["medal_name"], meta["title"], meta["live_status"])

    if "space.bilibili.com" in text:
        m = re.search(r"space\.bilibili\.com/(\d+)", text)
        if not m:
            return {"type": "error", "error_kind": "input", "message": f"无法从链接解析 UID：{text}"}
        return _lookup_uid(int(m.group(1)), sessdata, bili_jct)

    if text.isascii() and text.isdigit():
        num = int(text)
        if num <= 0:
            return {"type": "error", "error_kind": "input", "message": "编号必须是大于 0 的整数"}
        meta = resolve_room_meta(num, sessdata, bili_jct)
        if meta["ok"]:
            return _found_payload(meta["uid"], meta["name"], meta["room"], meta["medal_name"], meta["title"], meta["live_status"])
        if meta.get("error_kind") in ("network", "rate", "review", "safety"):
            return {"type": "error", "error_kind": meta["error_kind"], "message": meta["error"]}
        return _lookup_uid(num, sessdata, bili_jct)

    medal_hit = _match_local_medal(text, sessdata, bili_jct)
    if medal_hit is not None:
        return medal_hit

    searched = _search_users_wbi(text, sessdata, bili_jct, limit=limit)
    if not searched["ok"]:
        return {"type": "error", "error_kind": searched.get("error_kind", "api"), "message": f"搜索失败：{searched['error']}"}
    users = searched["users"]
    if not users:
        return {"type": "error", "error_kind": "not_found", "message": f"没有找到匹配「{text}」的主播"}
    if len(users) == 1:
        return _lookup_uid(users[0]["uid"], sessdata, bili_jct)

    room_map = _enrich_rooms_by_uids(users, sessdata, bili_jct)
    batch_failed = "_error_kind" in room_map
    return {"type": "multiple", "data": [_format_candidate_row(u, room_map, batch_failed) for u in users]}


def resolve_single(query: str, sessdata: str = "", bili_jct: str = "") -> Optional[Dict]:
    """Resolve one exact live-room member dict for legacy single-result callers."""
    res = resolve_anchor(query, sessdata, bili_jct)
    if res.get("type") == "found" and isinstance(res.get("data"), dict):
        data = res["data"]
        return {
            "uid": int(data["uid"]),
            "room": int(data["room"]),
            "name": str(data["name"]),
            "medal_name": str(data.get("medal_name") or ""),
        }
    if res.get("type") == "multiple":
        items = [item for item in (res.get("data") or []) if item.get("room")]
        if len(items) == 1:
            hit = items[0]
            return {
                "uid": int(hit["uid"]),
                "room": int(hit["room"]),
                "name": str(hit["name"]),
                "medal_name": "",
            }
    return None
