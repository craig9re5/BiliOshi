"""One paginated medal query, shared by watch, synchronization and check-in."""

from types import SimpleNamespace

from ..http import get_json, require_data
from ..session_headers import session_headers


def _default_gateway():
    return SimpleNamespace(_get_json=get_json, _make_headers=session_headers)


def entries(sessdata, bili_jct, gateway=None):
    gw = gateway if gateway is not None else _default_gateway()
    page = 1
    seen = set()
    while page <= 100:
        url = f"https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/panel?page={page}&page_size=50"
        response = gw._get_json(url, gw._make_headers(sessdata, bili_jct))
        data = require_data(response, "获取粉丝牌")
        for item in (data.get("special_list") or []) + (data.get("list") or []):
            medal = item.get("medal", item)
            identity = medal.get("medal_id") or medal.get("target_id")
            if identity and identity not in seen:
                seen.add(identity)
                yield item
        if page >= int(data.get("page_info", {}).get("total_page", 1)):
            return
        page += 1
    raise RuntimeError("粉丝牌分页超过上限，无法确认完整列表")


def all_user_medals(sessdata, bili_jct):
    """Fetch normalized user fan-medal rows without depending on heartbeat."""
    results = []
    for item in entries(sessdata, bili_jct):
        medal = item.get("medal", {})
        room = item.get("room_info", {})
        anchor = item.get("anchor_info", {})
        uid = medal.get("target_id") or item.get("target_id", 0)
        room_id = room.get("room_id", 0)
        name = anchor.get("nick_name") or item.get("uname", "")
        if uid and room_id and name:
            results.append(
                {
                    "uid": uid,
                    "room": room_id,
                    "name": name,
                    "medal_name": medal.get("medal_name", ""),
                    "level": medal.get("level", 0),
                    "is_lighted": medal.get("is_lighted", 0),
                }
            )
    return results
