"""Main-site Daily EXP service (up to 65 EXP/day), backed by the server reward progress."""

import logging
import random
import time
from typing import Callable, Dict, List, Optional
import urllib.parse

from ..api.medals import all_user_medals as get_all_user_medals
from ..check_auth import check_daily_profile
from ..context import runtime_path
from ..http import get_json, post_form
from .. import safety
from ..runtime import FileLock, append_event, data_dir, task_day, write_json
from ..session_headers import session_headers
from ..wbi import get_mixin_key, sign_wbi

REWARD_URL = "https://api.bilibili.com/x/member/web/exp/reward"
POPULAR_URL = "https://api.bilibili.com/x/web-interface/popular?ps=30&pn=1"
HEARTBEAT_URL = "https://api.bilibili.com/x/click-interface/web/heartbeat"
SHARE_URL = "https://api.bilibili.com/x/web-interface/share/add"
COIN_URL = "https://api.bilibili.com/x/web-interface/coin/add"
PAGELIST_URL = "https://api.bilibili.com/x/player/pagelist"
ARCHIVE_COINS_URL = "https://api.bilibili.com/x/web-interface/archive/coins"


def _root():
    return runtime_path("_LOG_DIR", data_dir() / "logs").parent


def _parse_coins_exp(raw) -> int:
    if isinstance(raw, bool):
        return 50 if raw else 0
    if isinstance(raw, (int, float)):
        return max(0, min(50, int(raw)))
    return 0


def query_reward_ledger(sessdata: str, bili_jct: str) -> dict:
    """Read today's daily EXP status from Bilibili. Never fabricate 0/False on failure."""
    headers = session_headers(sessdata, bili_jct, "https://account.bilibili.com/")
    resp = get_json(REWARD_URL, headers)
    if not resp or resp.get("code") != 0 or not isinstance(resp.get("data"), dict):
        code = (resp or {}).get("code", -1)
        msg = str((resp or {}).get("message") or "无法读取今日进度")
        return {
            "ok": False,
            "code": code,
            "error": msg,
            "error_kind": (resp or {}).get("error_kind", "api"),
        }
    data = resp["data"]
    login_done = bool(data.get("login", False))
    watch_done = bool(data.get("watch", data.get("watch_av", False)))
    share_done = bool(data.get("share", data.get("share_av", False)))
    coins_exp = _parse_coins_exp(data.get("coins", data.get("coins_av", 0)))
    earned_exp = (
        (5 if login_done else 0)
        + (5 if watch_done else 0)
        + (5 if share_done else 0)
        + coins_exp
    )
    return {
        "ok": True,
        "login": login_done,
        "watch": watch_done,
        "share": share_done,
        "coins_exp": coins_exp,
        "coins_count": coins_exp // 10,
        "earned_exp": earned_exp,
    }


def _parse_duration_seconds(raw) -> int:
    if isinstance(raw, int) and not isinstance(raw, bool) and raw > 0:
        return raw
    if isinstance(raw, str) and ":" in raw:
        parts = raw.strip().split(":")
        try:
            nums = [int(p) for p in parts]
            total = 0
            for n in nums:
                total = total * 60 + n
            return max(30, total)
        except ValueError:
            return 90
    return 90


def _fetch_member_videos(uid: int, sessdata: str, bili_jct: str, limit: int = 6) -> List[dict]:
    mixin_key = get_mixin_key(sessdata, bili_jct)
    if not mixin_key:
        return []
    params = sign_wbi(
        {"mid": str(uid), "ps": str(max(1, min(30, limit))), "pn": "1", "order": "pubdate", "tid": "0"},
        mixin_key,
    )
    url = f"https://api.bilibili.com/x/space/wbi/arc/search?{urllib.parse.urlencode(params)}"
    resp = get_json(url, session_headers(sessdata, bili_jct, f"https://space.bilibili.com/{uid}/video"))
    if not resp or resp.get("code") != 0:
        return []
    vlist = (((resp.get("data") or {}).get("list") or {}).get("vlist")) or []
    videos: List[dict] = []
    for item in vlist:
        if not isinstance(item, dict) or not item.get("aid"):
            continue
        videos.append(
            {
                "aid": int(item["aid"]),
                "bvid": str(item.get("bvid") or ""),
                "cid": int(item.get("cid") or 0),
                "title": str(item.get("title") or ""),
                "duration": _parse_duration_seconds(item.get("length", 90)),
                "source": "oshi",
                "author": str(item.get("author") or ""),
            }
        )
    return videos


def _is_uncoined(aid: int, sessdata: str, bili_jct: str) -> bool:
    url = f"{ARCHIVE_COINS_URL}?aid={aid}"
    resp = get_json(url, session_headers(sessdata, bili_jct))
    if not resp or resp.get("code") != 0 or not isinstance(resp.get("data"), dict):
        return False
    return int(resp["data"].get("multiply") or 0) == 0


def _fetch_popular_videos(sessdata: str, bili_jct: str) -> List[dict]:
    resp = get_json(POPULAR_URL, session_headers(sessdata, bili_jct))
    if not resp or resp.get("code") != 0:
        return []
    items = ((resp.get("data") or {}).get("list")) or []
    videos: List[dict] = []
    for v in items:
        if not isinstance(v, dict) or not v.get("aid"):
            continue
        owner = v.get("owner") if isinstance(v.get("owner"), dict) else {}
        videos.append(
            {
                "aid": int(v["aid"]),
                "bvid": str(v.get("bvid") or ""),
                "cid": int(v.get("cid") or 0),
                "title": str(v.get("title") or ""),
                "duration": _parse_duration_seconds(v.get("duration", 90)),
                "source": "popular",
                "author": str(owner.get("name") or ""),
            }
        )
    random.shuffle(videos)
    return videos


def collect_candidate_videos(
    sessdata: str,
    bili_jct: str,
    *,
    prefer_medals: bool = True,
    for_coin: bool = False,
    members: Optional[List[dict]] = None,
    needed: int = 5,
) -> List[dict]:
    """Build a deduplicated candidate list: followed/medal streamers first, popular fallback."""
    seen_aids = set()
    chosen: List[dict] = []

    if prefer_medals and for_coin:
        streamer_uids: List[int] = []
        for m in members or []:
            if isinstance(m, dict) and isinstance(m.get("uid"), int) and m["uid"] > 0:
                if m["uid"] not in streamer_uids:
                    streamer_uids.append(m["uid"])
        if len(streamer_uids) < 5:
            try:
                for medal in get_all_user_medals(sessdata, bili_jct):
                    if medal["uid"] not in streamer_uids:
                        streamer_uids.append(medal["uid"])
                    if len(streamer_uids) >= 6:
                        break
            except Exception as exc:
                logging.info("Skipping medal video lookup: %s", type(exc).__name__)

        for uid in streamer_uids[:6]:
            for v in _fetch_member_videos(uid, sessdata, bili_jct, limit=5):
                if v["aid"] in seen_aids:
                    continue
                if _is_uncoined(v["aid"], sessdata, bili_jct):
                    seen_aids.add(v["aid"])
                    chosen.append(v)
                    if len(chosen) >= needed + 2:
                        return chosen

    for v in _fetch_popular_videos(sessdata, bili_jct):
        if v["aid"] not in seen_aids:
            seen_aids.add(v["aid"])
            chosen.append(v)
    return chosen


def _ensure_cid(video: dict, sessdata: str, bili_jct: str) -> int:
    if video.get("cid") and int(video["cid"]) > 0:
        return int(video["cid"])
    resp = get_json(f"{PAGELIST_URL}?aid={video['aid']}", session_headers(sessdata, bili_jct))
    pages = (resp or {}).get("data")
    if resp and resp.get("code") == 0 and isinstance(pages, list) and pages:
        cid = int((pages[0] or {}).get("cid") or 0)
        video["cid"] = cid
        return cid
    return 0


def do_watch_video(video: dict, uid: int, sessdata: str, bili_jct: str) -> dict:
    cid = _ensure_cid(video, sessdata, bili_jct)
    if cid <= 0:
        return {"task": "watch", "success": False, "exp": 0, "error": "无法读取视频信息"}
    duration = max(20, int(video.get("duration") or 90))
    played = random.randint(15, min(duration, 180))
    now = int(time.time())
    bvid = str(video.get("bvid") or "")
    form = {
        "aid": str(video["aid"]),
        "cid": str(cid),
        "bvid": bvid,
        "mid": str(uid),
        "csrf": bili_jct,
        "played_time": str(played),
        "real_played_time": str(played),
        "realtime": str(duration),
        "start_ts": str(now - played),
        "type": "3",
        "dt": "2",
        "play_type": "1",
    }
    referer = f"https://www.bilibili.com/video/{bvid}" if bvid else "https://www.bilibili.com/"
    resp = post_form(HEARTBEAT_URL, form, session_headers(sessdata, bili_jct, referer))
    if resp and resp.get("code") == 0:
        return {
            "task": "watch",
            "success": True,
            "submitted": True,
            "exp": 5,
            "video": video["title"],
            "bvid": bvid,
        }
    return {
        "task": "watch",
        "success": False,
        "exp": 0,
        "error": str((resp or {}).get("message") or "观看任务未完成"),
        "error_kind": (resp or {}).get("error_kind", "api"),
    }


def do_share_video(video: dict, sessdata: str, bili_jct: str) -> dict:
    bvid = str(video.get("bvid") or "")
    form = {
        "aid": str(video["aid"]),
        "bvid": bvid,
        "csrf": bili_jct,
    }
    referer = f"https://www.bilibili.com/video/{bvid}" if bvid else "https://www.bilibili.com/"
    resp = post_form(SHARE_URL, form, session_headers(sessdata, bili_jct, referer))
    if resp and resp.get("code") == 0:
        return {
            "task": "share",
            "success": True,
            "submitted": True,
            "exp": 5,
            "video": video["title"],
            "bvid": bvid,
        }
    if resp and resp.get("code") == 71000:
        return {
            "task": "share",
            "success": True,
            "already_done": True,
            "exp": 0,
            "message": "今日已完成",
        }
    return {
        "task": "share",
        "success": False,
        "exp": 0,
        "error": str((resp or {}).get("message") or "分享任务未完成"),
        "error_kind": (resp or {}).get("error_kind", "api"),
    }


def do_coin_videos(
    candidates: List[dict],
    needed_coins: int,
    available_coins: float,
    sessdata: str,
    bili_jct: str,
    *,
    select_like: bool = False,
    root=None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Coin distinct videos up to needed_coins, respecting coin balance and safety holds."""
    usable_balance = int(max(0.0, available_coins))
    if usable_balance < 1:
        return {
            "task": "coin",
            "success": False,
            "exp": 0,
            "count": 0,
            "target": needed_coins,
            "error": "硬币余额不足 1 枚，已跳过投币",
            "error_kind": "balance",
            "details": [],
        }
    target = min(needed_coins, usable_balance)
    details: List[dict] = []
    coined = 0

    for video in candidates:
        if coined >= target or safety.status(sessdata, root)["blocked"]:
            break
        bvid = str(video.get("bvid") or "")
        referer = f"https://www.bilibili.com/video/{bvid}" if bvid else "https://www.bilibili.com/"
        form = {
            "aid": str(video["aid"]),
            "bvid": bvid,
            "multiply": "1",
            "select_like": "1" if select_like else "0",
            "csrf": bili_jct,
        }
        resp = post_form(COIN_URL, form, session_headers(sessdata, bili_jct, referer))
        code = (resp or {}).get("code", -1)
        if code == 0:
            coined += 1
            details.append(
                {
                    "success": True,
                    "aid": video["aid"],
                    "bvid": bvid,
                    "video": video["title"],
                    "author": video.get("author", ""),
                    "source": video.get("source", "popular"),
                }
            )
            if coined < target:
                sleep_fn(random.uniform(1.2, 2.5))
        elif code == 34005:
            continue
        else:
            err_msg = str((resp or {}).get("message") or "投币失败")
            details.append({"success": False, "video": video["title"], "error": err_msg, "code": code})
            if code in (-104, -101, -111, -352, -412, 412, 429, -509) or safety.status(sessdata, root)["blocked"]:
                break

    return {
        "task": "coin",
        "success": coined >= target,
        "partial": 0 < coined < target,
        "submitted": coined > 0,
        "exp": coined * 10,
        "count": coined,
        "target": target,
        "requested": needed_coins,
        "details": details,
        "error": (
            None
            if coined >= target
            else (
                details[-1].get("error")
                if details and not details[-1].get("success")
                else f"仅完成 {coined}/{target} 枚投币"
            )
        ),
    }


def estimate_days_to_next_level(
    user: dict,
    earned_today_exp: int,
    *,
    do_coin: bool = False,
    coin_target: int = 5,
) -> Optional[int]:
    if user.get("is_max_level") or not user.get("next_exp"):
        return None
    daily_cap = 15 + (min(5, max(0, coin_target)) * 10 if do_coin else 0)
    if daily_cap <= 0:
        return None
    remaining_today_potential = max(0, daily_cap - earned_today_exp)
    exp_gap = max(0, int(user["next_exp"]) - int(user.get("current_exp") or 0) - remaining_today_potential)
    if exp_gap <= 0:
        return 0
    return (exp_gap + daily_cap - 1) // daily_cap


def check_daily_status(
    sessdata: str,
    bili_jct: str,
    *,
    do_coin: bool = False,
    coin_target: int = 5,
) -> dict:
    valid, msg, user = check_daily_profile(sessdata, bili_jct)
    if not valid:
        return {"ok": False, "error": f"登录验证失败：{msg}", "error_kind": user.get("error_kind", "auth")}
    ledger = query_reward_ledger(sessdata, bili_jct)
    if not ledger["ok"]:
        return {
            "ok": False,
            "user": user,
            "error": f"无法读取今日进度：{ledger['error']}",
            "error_kind": ledger.get("error_kind", "api"),
        }
    days_left = estimate_days_to_next_level(
        user, ledger["earned_exp"], do_coin=do_coin, coin_target=coin_target
    )
    snapshot = {
        "ok": True,
        "day": task_day(),
        "updated": time.time(),
        "user": user,
        "ledger": ledger,
        "days_to_next_level": days_left,
    }
    write_json(_root() / "state" / "daily-exp.json", snapshot)
    return snapshot


def _execute_coin_step(
    candidates,
    coins_done_count,
    coin_target,
    effective_do_coin,
    user,
    sessdata,
    bili_jct,
    *,
    root,
    coin_with_like,
    sleep_fn,
):
    if not effective_do_coin:
        return (
            {
                "task": "coin",
                "success": True,
                "skipped": True,
                "exp": 0,
                "count": coins_done_count,
                "target": 5,
                "message": "未开启自动投币",
            },
            user,
        )
    remaining_coins = max(0, coin_target - coins_done_count)
    if remaining_coins == 0:
        return (
            {
                "task": "coin",
                "success": True,
                "already_done": True,
                "exp": 0,
                "count": coins_done_count,
                "target": coin_target,
                "message": "今日投币已完成",
            },
            user,
        )
    if safety.status(sessdata, root)["blocked"]:
        return ({"task": "coin", "success": False, "exp": 0, "error": "触发账号保护暂停，已中止"}, user)
    if not candidates:
        return ({"task": "coin", "success": False, "exp": 0, "error": "无法获取可投币视频"}, user)
    res_c = do_coin_videos(
        candidates,
        remaining_coins,
        user["coins"],
        sessdata,
        bili_jct,
        select_like=coin_with_like,
        root=root,
        sleep_fn=sleep_fn,
    )
    if res_c.get("count", 0) > 0:
        user = {**user, "coins": max(0.0, user["coins"] - res_c["count"])}
    return (res_c, user)


def run_daily_tasks(
    sessdata: str,
    bili_jct: str,
    *,
    do_coin: bool = False,
    coin_target: int = 5,
    prefer_medals: bool = True,
    coin_with_like: bool = False,
    only_task: Optional[str] = None,
    members: Optional[List[dict]] = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> dict:
    """Execute daily EXP tasks using the server progress as source of truth."""
    root = _root()
    hold = safety.status(sessdata, root)
    if hold["blocked"]:
        return {"ok": False, "error": hold["reason"], "error_kind": "safety", "safety": hold}

    with FileLock(root / "locks" / "daily-exp.lock", timeout=10) as lock:
        if not lock.acquired:
            return {"ok": False, "error": "今日签到任务正在执行中，请稍候", "error_kind": "busy"}

        valid, msg, user = check_daily_profile(sessdata, bili_jct)
        if not valid:
            return {"ok": False, "error": f"登录验证失败：{msg}", "error_kind": user.get("error_kind", "auth")}

        ledger_before = query_reward_ledger(sessdata, bili_jct)
        if not ledger_before["ok"]:
            return {
                "ok": False,
                "user": user,
                "error": f"无法读取今日进度（{ledger_before['error']}），已暂缓执行",
                "error_kind": ledger_before.get("error_kind", "api"),
            }

        coin_target = max(0, min(5, int(coin_target)))
        tasks_out: List[dict] = []
        want = {only_task} if only_task in {"watch", "share", "coin"} else {"login", "watch", "share", "coin"}

        if "login" in want:
            tasks_out.append({
                "task": "login", "success": True, "already_done": ledger_before["login"],
                "exp": 0 if ledger_before["login"] else 5,
                "message": "今日已登录" if ledger_before["login"] else "登录已激活",
            })

        need_watch = "watch" in want and not ledger_before["watch"]
        need_share = "share" in want and not ledger_before["share"]
        effective_do_coin = (do_coin or only_task == "coin") and "coin" in want
        remaining_coins = max(0, coin_target - ledger_before["coins_count"]) if effective_do_coin else 0

        candidates = (
            collect_candidate_videos(
                sessdata, bili_jct, prefer_medals=prefer_medals,
                for_coin=remaining_coins > 0, members=members, needed=max(2, remaining_coins),
            )
            if (need_watch or need_share or remaining_coins > 0)
            else []
        )

        if "watch" in want:
            if ledger_before["watch"]:
                tasks_out.append({"task": "watch", "success": True, "already_done": True, "exp": 0, "message": "今日已完成"})
            elif not candidates:
                tasks_out.append({"task": "watch", "success": False, "exp": 0, "error": "无法获取可用视频"})
            else:
                tasks_out.append(do_watch_video(candidates[0], user["uid"], sessdata, bili_jct))
                if need_share or remaining_coins > 0:
                    sleep_fn(random.uniform(1.0, 1.8))

        if "share" in want:
            if ledger_before["share"]:
                tasks_out.append({"task": "share", "success": True, "already_done": True, "exp": 0, "message": "今日已完成"})
            elif safety.status(sessdata, root)["blocked"]:
                tasks_out.append({"task": "share", "success": False, "exp": 0, "error": "触发账号保护暂停，已中止"})
            elif not candidates:
                tasks_out.append({"task": "share", "success": False, "exp": 0, "error": "无法获取可用视频"})
            else:
                share_video = candidates[1] if len(candidates) > 1 else candidates[0]
                tasks_out.append(do_share_video(share_video, sessdata, bili_jct))
                if remaining_coins > 0:
                    sleep_fn(random.uniform(1.0, 1.8))

        if "coin" in want:
            coin_res, user = _execute_coin_step(
                candidates, ledger_before["coins_count"], coin_target, effective_do_coin,
                user, sessdata, bili_jct, root=root, coin_with_like=coin_with_like, sleep_fn=sleep_fn,
            )
            tasks_out.append(coin_res)

        ledger_after = query_reward_ledger(sessdata, bili_jct)
        effective_ledger = ledger_after if ledger_after["ok"] else ledger_before
        confirmed_gain = max(0, effective_ledger["earned_exp"] - ledger_before["earned_exp"])
        submitted_gain = sum(int(t.get("exp") or 0) for t in tasks_out if t.get("submitted") or t.get("task") == "login")
        pending_settlement = submitted_gain > confirmed_gain
        days_left = estimate_days_to_next_level(
            user, max(effective_ledger["earned_exp"], ledger_before["earned_exp"] + submitted_gain),
            do_coin=effective_do_coin, coin_target=coin_target if effective_do_coin else 0,
        )
        all_ok = all(t.get("success") for t in tasks_out)
        output = {
            "ok": all_ok, "day": task_day(), "updated": time.time(), "user": user, "tasks": tasks_out,
            "ledger_before": ledger_before, "ledger_after": effective_ledger, "ledger": effective_ledger,
            "confirmed_exp_today": effective_ledger["earned_exp"], "confirmed_gain": confirmed_gain,
            "submitted_gain": submitted_gain, "pending_settlement": pending_settlement,
            "days_to_next_level": days_left, "safety": safety.status(sessdata, root),
        }
        write_json(root / "state" / "daily-exp.json", output)
        append_event(
            root / "logs" / "activity.jsonl",
            {
                "type": "daily_exp_run", "day": output["day"], "ok": all_ok,
                "confirmed_exp_today": output["confirmed_exp_today"],
                "submitted_gain": submitted_gain, "pending_settlement": pending_settlement,
            },
        )
        return output
