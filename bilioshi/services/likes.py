import re
import time
import urllib.parse
from typing import Optional, Dict
from ..policies import *
from .. import safety
from ..danmaku_pacing import send_paced
from ..runtime import data_dir
from ..operating_mode import current_profile
from ..task_window import TaskDeferred, check_window, wait


def get_live_like_progress(
    room_id: int, anchor_uid: int, headers: dict, bili_jct: str, *, _gateway
) -> Dict:
    """Read the like task's current rounds and required likes per round."""
    params = {
        "csrf": bili_jct,
        "platform": "pc",
        "room_id": str(room_id),
        "scene": "club",
        "target_id": str(anchor_uid),
        "web_location": "444.260",
    }
    url = (
        "https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/GetActivatedMedalInfo?"
        + urllib.parse.urlencode(params)
    )
    response = _gateway._get_json(url, headers)
    if not response or response.get("code") != 0:
        code = response.get("code") if response else None
        return {"error": f"无法读取点赞任务进度（接口代码：{code}）",
                **{key: response[key] for key in ("code", "error_kind", "retry_after")
                   if response and key in response}}
    data = response.get("data") or {}
    if not isinstance(data, dict):
        return {"error": "粉丝团任务数据格式异常"}
    tasks = data.get("task_info") or []
    if not isinstance(tasks, list):
        return {"error": "粉丝团任务列表格式异常"}
    task = next(
        (item for item in tasks if isinstance(item, dict) and item.get("jump_type") == "like"), None
    )
    if not task:
        return {"error": "粉丝团信息中没有点赞任务"}
    progress = re.search("(\\d+)\\s*/\\s*(\\d+)", task.get("sub_title") or "")
    count = re.search("\\d+", task.get("title") or "")
    if not progress:
        return {"error": "无法解析点赞任务进度"}
    current, limit = map(int, progress.groups())
    if limit < 1 or current > limit:
        return {"error": "点赞任务进度异常"}
    per_round = int(count.group()) if count else _gateway.LIVE_LIKE_BATCH_SIZE
    if per_round < 1:
        return {"error": "点赞任务次数异常"}
    return {
        "current": current,
        "limit": limit,
        "per_round": per_round,
        "done": bool(task.get("is_done")),
    }


def report_live_likes(
    room_id: int,
    anchor_uid: int,
    viewer_uid: int,
    sessdata: str,
    bili_jct: str,
    count: int = LIVE_LIKE_BATCH_SIZE,
    headers: Optional[dict] = None,
    *,
    _gateway,
) -> Dict:
    """Report a small batch of live-room likes; this does not like a video."""
    if (
        isinstance(count, bool)
        or not isinstance(count, int)
        or not 1 <= count <= LIVE_LIKE_BATCH_SIZE
    ):
        return {"success": False, "code": None, "message": "点赞批次次数必须为 1–30"}
    params = {
        "click_time": str(count),
        "room_id": str(room_id),
        "uid": str(viewer_uid),
        "anchor_id": str(anchor_uid),
        "web_location": "444.8",
        "csrf": bili_jct,
    }
    headers = headers or _gateway._live_like_headers(room_id, viewer_uid, sessdata, bili_jct)
    if not headers:
        return {"success": False, "code": None,
                "message": "缺少匹配当前账号的登录会话；请在桌面重新扫码登录"}

    def send():
        # Sign after queueing so a wait never ages the request's WBI timestamp.
        check_window()
        try:
            signed = _gateway._sign_wbi(params, _gateway.get_mixin_key(sessdata, bili_jct))
        except TaskDeferred:
            raise
        except Exception:
            return {"code": None, "message": "无法生成 WBI 签名", "error_kind": "signing"}
        check_window()
        url = ("https://api.live.bilibili.com/xlive/app-ucenter/v1/like_info_v3/like/likeReportV3?"
               + urllib.parse.urlencode(signed))
        started = time.monotonic()
        resp = _gateway._post_empty_json(url, headers) or {}
        _gateway._log({"type": "live_like_batch", "room_id": room_id, "count": count,
                       "elapsed_seconds": round(time.monotonic() - started, 3),
                       **{key: resp[key] for key in ("code", "error_kind", "retry_after") if key in resp}})
        return resp

    try:
        resp = send_paced(send,
                          lock_path=data_dir() / "locks" / f"like-send-{safety.identity(sessdata)}.lock",
                          min_interval=current_profile().like_send_seconds)
    except TimeoutError:
        raise TaskDeferred("点赞队列繁忙，等待下次检查")
    return {"success": resp.get("code") == 0,
            "code": resp.get("code"), "message": resp.get("message", "请求失败"),
            **{key: resp[key] for key in ("error_kind", "retry_after", "safety") if key in resp}}


def like_live_room(
    room_id: int,
    anchor_uid: int,
    sessdata: str,
    bili_jct: str,
    batches: int = LIVE_LIKE_BATCHES,
    *,
    pending_current=None,
    checkpoint=None,
    _gateway,
) -> Dict:
    """Report remaining rounds; reconcile an accepted batch before another send."""
    state = {"reported": 0, "pending_current": pending_current}
    try:
        result = _like_live_room(room_id, anchor_uid, sessdata, bili_jct, batches,
                                 state, checkpoint, _gateway)
    except TaskDeferred:
        result = {"success": False, "done": False, "deferred": True,
                  "error": "本轮任务时间不足，等待下次检查"}
    return {**state, **result}


def _like_live_room(room_id, anchor_uid, sessdata, bili_jct, batches, state, checkpoint, gateway):
    check_window()
    viewer_uid = gateway.get_viewer_uid(sessdata, bili_jct)
    if viewer_uid is None:
        return {"success": False, "error": "无法获取当前账号 UID"}
    headers = gateway._live_like_headers(room_id, viewer_uid, sessdata, bili_jct)
    if not headers:
        return {"success": False, "error": "缺少匹配当前账号的登录会话；请在桌面重新扫码登录"}
    check_window()
    progress = gateway.get_live_like_progress(room_id, anchor_uid, headers, bili_jct)
    if "error" in progress:
        return {"success": False, **progress}
    start = progress["current"]
    state["progress"] = f"{start}/{progress['limit']}"
    done = progress["done"] or start >= progress["limit"]
    pending = state["pending_current"]
    if pending is not None and not done and start <= pending:
        return {"success": False, "done": False, "needs_confirmation": True,
                "error": "上一批点赞尚未确认到账，本次只核验进度"}
    state["pending_current"] = None
    if done:
        return {"success": True, "done": True}
    target = min(progress["limit"], start + batches)
    for i in range(batches):
        if progress["done"] or progress["current"] >= target:
            break
        if i:
            wait(gateway.LIVE_LIKE_DELAY)
        check_window()
        previous = progress["current"]
        if checkpoint is not None:
            checkpoint(previous)
        try:
            result = gateway.report_live_likes(
                room_id, anchor_uid, viewer_uid, sessdata, bili_jct,
                count=progress["per_round"], headers=headers,
            )
        except TaskDeferred:
            # No request started; the checkpoint is cleared on normal return.
            raise
        # Until proven rejected or credited, a submitted batch must not be replayed.
        state["pending_current"] = previous
        if not result["success"]:
            hold = safety.status(sessdata)
            if hold.get("kind") == "uncertain":
                wait(gateway.LIVE_LIKE_PROGRESS_DELAY)
                observed = gateway.get_live_like_progress(room_id, anchor_uid, headers, bili_jct)
                return {"success": False, "needs_confirmation": True, "safety": hold,
                        "error": hold["reason"],
                        "progress": (f"{observed['current']}/{observed['limit']}"
                                     if "error" not in observed else "查询失败")}
            state["pending_current"] = None
            return {"success": False, "error": f"[{result['code']}] {result['message']}",
                    **{key: result[key] for key in ("code", "error_kind", "retry_after") if key in result}}
        state["reported"] += progress["per_round"]
        for delay in (gateway.LIVE_LIKE_PROGRESS_DELAY, gateway.LIVE_LIKE_PROGRESS_RETRY_DELAY):
            wait(delay)
            progress = gateway.get_live_like_progress(room_id, anchor_uid, headers, bili_jct)
            if "error" in progress:
                return {"success": False, **progress}
            state["progress"] = f"{progress['current']}/{progress['limit']}"
            gateway._log({"type": "live_like_progress", "room_id": room_id,
                          "before": previous, "after": progress["current"], "limit": progress["limit"]})
            if progress["current"] > previous or progress["done"]:
                state["pending_current"] = None
                break
        else:
            return {"success": False, "needs_confirmation": True,
                    "error": "点赞接口返回成功，但粉丝团任务进度未增加"}
    return {"success": True, "done": progress["done"] or progress["current"] >= progress["limit"]}
