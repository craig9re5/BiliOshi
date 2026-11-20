"""Persistent account safety holds and shared per-room budgets at the IO boundary."""

import time
import json
import threading
from urllib.parse import urlsplit, parse_qs
from .runtime import (
    data_dir,
    file_stat_signature,
    read_json,
    write_json,
    update_json,
    FileLock,
    session_fingerprint,
    task_day,
    append_event,
)

_DEFAULT_READ_JSON = read_json
_READ_CACHE = {}
_READ_CACHE_LOCK = threading.Lock()


def _read_cached_json(path, default=None):
    """Read immutable snapshots from safety state with stat-keyed caching."""
    if read_json is not _DEFAULT_READ_JSON:
        return read_json(path, default)
    sig = file_stat_signature(path)
    key = str(path)
    if sig is None:
        with _READ_CACHE_LOCK:
            _READ_CACHE.pop(key, None)
        return default
    with _READ_CACHE_LOCK:
        cached = _READ_CACHE.get(key)
        if cached is not None and cached[0] == sig:
            return cached[1]
    value = read_json(path, default)
    new_sig = file_stat_signature(path)
    if new_sig is not None and isinstance(value, dict):
        with _READ_CACHE_LOCK:
            if len(_READ_CACHE) >= 128:
                _READ_CACHE.clear()
            _READ_CACHE[key] = (new_sig, value)
    return value
from .policies import COIN_DAILY_ATTEMPT_LIMIT, DANMAKU_SESSION_ATTEMPT_LIMIT, LIVE_LIKE_BATCHES
from .redaction import redact

RATE_COOLDOWN = 300
EDGE_LIMIT_COOLDOWN = 180
NETWORK_COOLDOWN = 60
ROOM_CAPABILITY_COOLDOWN = 43200
PROBATION_SECONDS = {
    "review": 300,
    "uncertain": 90,
}
INTERACTION_OPS = ("danmaku", "like", "wear", "coin", "share", "watch")
PROBATION_CLEAR_OPS = ("danmaku", "like")
INTERACTION_SCOPED_KINDS = ("rate", "uncertain", "edge_limit")
ACCOUNT_BAN_WORDS = ("封禁", "封号", "冻结", "注销")
AUTO_PROBE_DELAYS = {
    "uncertain": (60, 180, 300),
    "review": (900, 1800, 3600),
}
AUTO_RECOVER_DAILY_LIMIT = {
    "uncertain": 5,
    "review": 3,
}
KIND_LABELS = {
    "review": "安全验证 / 风控拦截",
    "permission": "权限或禁言限制",
    "rate": "请求频率限制",
    "edge_limit": "短时访问限制",
    "uncertain": "操作结果待核验",
    "auth": "登录凭证失效",
    "credentials": "本机凭证异常",
    "network": "网络连续异常",
}
OPERATION_LABELS = {
    "danmaku": "发送弹幕",
    "like": "直播点赞",
    "wear": "佩戴粉丝牌",
    "room_entry": "进入直播间",
    "heartbeat": "观看状态同步",
    "coin": "视频投币",
    "share": "视频分享",
    "watch": "视频观看",
    "other": "账号操作",
}
HEARTBEAT_PATHS = {
    "/xlive/data-interface/v1/x25Kn/E",
    "/xlive/data-interface/v1/x25Kn/X",
}
ROOM_ENTRY_PATHS = {"/xlive/web-room/v1/index/roomEntryAction"}
READ_POST_PATHS = {"/room/v1/Room/get_status_info_by_uids"}


def _infer_scope(kind, operation=None, scope=None):
    if scope in ("account", "interaction"):
        return scope
    op_kind = (operation or {}).get("kind") if isinstance(operation, dict) else ""
    if kind in INTERACTION_SCOPED_KINDS and op_kind in INTERACTION_OPS:
        return "interaction"
    return "account"


def is_interaction_only(hold):
    return bool(isinstance(hold, dict) and hold.get("blocked") and hold.get("scope") == "interaction")


def is_watch_operation(op, *, mutation=True):
    if not mutation:
        return True
    if not isinstance(op, dict):
        return False
    return op.get("kind") == "heartbeat" or op.get("path") in ROOM_ENTRY_PATHS


def blocks_watch(hold):
    return bool(
        isinstance(hold, dict)
        and hold.get("blocked")
        and hold.get("scope", "account") != "interaction"
    )


def _next_probe_delay(kind, auto_attempts, auto_recovered_today):
    delays = AUTO_PROBE_DELAYS.get(kind)
    limit = AUTO_RECOVER_DAILY_LIMIT.get(kind, 0)
    if not delays or auto_attempts >= len(delays) or auto_recovered_today >= limit:
        return None
    index = min(auto_attempts + auto_recovered_today, len(delays) - 1)
    return delays[index]


def describe_hold(hold, members=None):
    """Build user-facing context and self-check steps for an active safety hold."""
    if not hold or hold.get("blocked") is False or not (hold.get("blocked") or hold.get("kind")):
        return {}
    kind = hold.get("kind") or "review"
    op = hold.get("operation") or {}
    op_kind = op.get("kind") or ""
    room_raw = str(op.get("room") or "").strip()
    room_id = int(room_raw) if room_raw.isdigit() and int(room_raw) > 0 else None
    room_name = ""
    if room_id and members:
        matched = next((m for m in members if m.get("room") == room_id), None)
        if matched:
            room_name = str(matched.get("name") or "")
    room_desc = f"「{room_name}」（房间 {room_id}）" if room_name and room_id else (f"房间 {room_id}" if room_id else "")
    op_label = OPERATION_LABELS.get(op_kind, "账号请求" if op else "")
    scope = hold.get("scope") or _infer_scope(kind, op)
    interaction_only = scope == "interaction"

    if kind == "review":
        steps = [
            f"打开{room_desc or '任意已关注的 B 站直播间'}，确认网页端登录正常且能正常加载直播画面。",
            "在直播间尝试手动发送 1 条弹幕或点赞，观察是否弹出滑块/安全验证并完成验证。",
            "若近期切换过网络环境或同时挂机多个直播间，建议等待 15 分钟冷却后再点下方「检测并自动恢复」。",
        ]
        action_url = f"https://live.bilibili.com/{room_id}" if room_id else "https://live.bilibili.com/"
        action_label = "打开触发直播间" if room_id else "打开 B 站直播"
    elif kind == "permission":
        steps = [
            f"打开{room_desc or '对应 B 站直播间'}，检查当前账号是否被房管禁言、未满足发言等级或仅允许粉丝发言。",
            "前往 B 站账号安全中心确认账号未处于受限/封禁状态。",
            "若只是单个直播间被禁言，建议在设置中关闭自动弹幕或暂时移除该主播，再点击「确认已处理并恢复」。",
        ]
        action_url = f"https://live.bilibili.com/{room_id}" if room_id else "https://account.bilibili.com/account/home"
        action_label = "打开触发直播间" if room_id else "打开账号中心"
    elif kind in ("rate", "edge_limit"):
        steps = [
            (
                "当前互动触发了短时访问限制，已仅暂停自动弹幕与点赞，各直播间挂机看播正常继续。"
                if interaction_only
                else "当前操作触发了平台短时访问限制，通常无需在 B 站做额外操作。"
            ),
            "等待下方倒计时结束后，程序会自动恢复正常任务。",
            "如频繁出现限制，可适当减少同时开启自动弹幕与点赞的房间或账号数量。",
        ]
        action_url = "https://live.bilibili.com/"
        action_label = "打开 B 站直播"
    elif kind == "uncertain":
        steps = [
            (
                f"刚才在{room_desc or '直播间'}执行「{op_label or '互动操作'}」时遇到网络超时或服务端异常，"
                + ("已仅暂停重复发送互动，看播正常继续。" if interaction_only else "为避免重复执行已暂时停机。")
            ),
            "可打开直播间或粉丝团任务面板，确认今日任务进度是否已实际到账。",
            "程序会在约 1 分钟后自动检测状态并进入试探恢复；也可直接点击下方「检测并自动恢复」。",
        ]
        action_url = f"https://live.bilibili.com/{room_id}" if room_id else "https://live.bilibili.com/"
        action_label = "打开触发直播间" if room_id else "打开 B 站直播"
    elif kind in ("auth", "credentials"):
        steps = [
            "当前 B 站登录状态已失效或需要重新授权。",
            "请直接点击下方「重新扫码登录」，使用哔哩哔哩手机客户端扫码即可恢复。",
        ]
        action_url = "https://live.bilibili.com/"
        action_label = "打开 B 站直播"
    else:
        steps = [
            "检测到连续网络请求失败，程序已进入短暂冷却以保护账号。",
            "请确认本机网络连接畅通，冷却结束后将自动恢复。",
        ]
        action_url = "https://live.bilibili.com/"
        action_label = "打开 B 站直播"

    return {
        "kind_label": KIND_LABELS.get(kind, "账号保护暂停"),
        "scope": scope,
        "scope_label": (
            "仅暂停弹幕/点赞互动 · 挂机看播正常继续"
            if interaction_only
            else "全账号暂停（含挂机看播与日常操作）"
        ),
        "operation_label": op_label,
        "room_id": room_id,
        "room_name": room_name,
        "room_label": room_desc,
        "action_url": action_url,
        "action_label": action_label,
        "steps": steps,
        "can_probe": kind in ("review", "permission", "uncertain", "rate", "edge_limit", "network"),
        "can_auto_recover": kind in AUTO_PROBE_DELAYS,
    }


def _root(root=None):
    return root if root is not None else data_dir()


def identity(sessdata, root=None):
    root = _root(root)
    fingerprint = session_fingerprint(sessdata)
    return _read_cached_json(root / "state/account-bindings.json", {}).get(fingerprint, fingerprint)


def _path(key, root=None):
    return _root(root) / "state" / "safety" / f"{key}.json"


def status(sessdata, root=None):
    if not sessdata:
        return {"blocked": False}
    value = _read_cached_json(_path(identity(sessdata, root), root), {})
    hold = value.get("hold") or {}
    if hold.get("until") and time.time() >= hold["until"]:
        return {"blocked": False}
    return {"blocked": bool(hold), **hold}


def blocked_response(hold):
    return {
        "code": hold.get("code", -1),
        "message": hold.get("reason", "账号保护暂停"),
        "error_kind": "safety",
        "safety": hold,
        "success": False,
    }


def _is_safety_entry(entry):
    if not isinstance(entry, dict):
        return False
    return bool(
        entry.get("error_kind") == "safety"
        or (isinstance(entry.get("safety"), dict) and entry["safety"].get("blocked"))
    )


def format_task_errors(result, *, separator="；", skip_kinds=(), suppress_safety=False):
    """Collect unique non-empty error messages from a task check result."""
    if not isinstance(result, dict) or result.get("dismissed"):
        return ""
    skip = set(skip_kinds or ())
    safety_info = result.get("safety") if isinstance(result.get("safety"), dict) else {}
    safety_reason = str(safety_info.get("reason") or "").strip()

    def _entry_text(entry, allow_top_safety=False):
        if not isinstance(entry, dict):
            return ""
        text = str(entry.get("error") or "").strip()
        if not text:
            return ""
        if suppress_safety and (
            _is_safety_entry(entry)
            or (allow_top_safety and _is_safety_entry(result))
            or (safety_reason and text == safety_reason)
            or text.startswith("操作结果未知")
        ):
            return ""
        return text

    seen = []
    skipped_texts = {
        _entry_text(result.get(key), allow_top_safety=False)
        for key in skip
        if key in ("danmaku", "like")
    } - {""}
    top_text = _entry_text(result, allow_top_safety=True)
    candidates = [] if top_text in skipped_texts else [top_text]
    for key in ("danmaku", "like"):
        if key not in skip:
            candidates.append(_entry_text(result.get(key), allow_top_safety=False))
    for text in candidates:
        if text and text not in seen:
            seen.append(text)
    return separator.join(seen)


def bind_account(sessdata, uid, root=None):
    """Only a successful authenticated nav response can establish a UID binding."""
    key = f"uid-{int(uid)}"
    fingerprint = session_fingerprint(sessdata)
    root = _root(root)
    path = root / "state/account-bindings.json"
    with FileLock(str(path) + ".guard", timeout=5) as lock:
        if not lock.acquired:
            raise TimeoutError("账号身份写入超时")
        values = read_json(path, {})
        if values.get(fingerprint) != key:
            _migrate_session_state(root, fingerprint, key)
            values[fingerprint] = key
            write_json(path, values)
    # Authentication resolves only an expired-login hold, never a risk/permission hold.
    update_json(
        _path(key, root),
        lambda v: {**v, "hold": {}} if (v.get("hold") or {}).get("kind") == "auth" else v,
        {},
    )
    return key


def _migrate_session_state(root, old, new):
    source = _path(old, root)
    if source.exists():
        previous = read_json(source, {})

        def merge_safety(current):
            for name, count in previous.get("counts", {}).items():
                current.setdefault("counts", {})[name] = (
                    current.get("counts", {}).get(name, 0) + count
                )
            if previous.get("hold"):
                current["hold"] = previous["hold"]
            return current

        update_json(_path(new, root), merge_safety, {})
        source.unlink()
    # Upgrade existing daily runner files once, preserving attempts across QR replacement.
    folder = root / "state/tasks"
    for source in folder.glob(f"{old}-*.json"):
        previous = read_json(source, {})
        room = previous.get("room")
        if not isinstance(room, int):
            continue
        destination = folder / f"{new}-{room}.json"
        with FileLock(root / "locks" / f"tasks-{new}-{room}.lock", timeout=5) as lease:
            if not lease.acquired:
                raise TimeoutError("任务预算迁移等待超时")
            current = read_json(destination, {})
            if current.get("day") == previous.get("day"):
                for field in ("attempted", "like_attempted"):
                    current[field] = current.get(field, 0) + previous.get(field, 0)
            elif current.get("day", "") < previous.get("day", ""):
                current = previous
            current["account_key"] = new
            write_json(destination, current)

            def carry_budget(value):
                counts = value.setdefault("counts", {})
                prefix = f"{current.get('day')}:{room}:"
                for kind, amount in (
                    ("danmaku", current.get("attempted", 0)),
                    ("like", current.get("like_attempted", 0) * LIVE_LIKE_BATCHES),
                ):
                    counts[prefix + kind] = max(counts.get(prefix + kind, 0), amount)
                return value

            update_json(_path(new, root), carry_budget, {})
            source.unlink()


def classify(response):
    code = response.get("code")
    message = str(response.get("message", ""))
    if response.get("error_kind") == "network":
        return "network", "网络连续失败，暂缓请求", NETWORK_COOLDOWN
    if code in (401, -101, -111) or "未登录" in message or "登录失效" in message:
        return "auth", "登录已失效，请重新扫码登录", None
    if code in (429, -509) or any(
        word in message
        for word in (
            "过于频繁",
            "发言频繁",
            "请求频繁",
            "频率过高",
            "频率限制",
            "请求过快",
            "发言过快",
            "msg in 1s",
        )
    ):
        return "rate", "触发操作频率限制，账号操作已冷却", RATE_COOLDOWN
    if code in (403, -403) or any(
        word in message
        for word in ("禁言", "权限不足", "封禁", "黑名单", "等级不足", "仅粉丝")
    ):
        return "permission", "收到权限或禁言限制，请先在平台确认账号状态", None
    if (
        response.get("error_kind") == "http"
        and code == 412
        and response.get("bili_code") not in (-352, -412)
        and not any(word in message for word in ("验证码", "安全验证", "风控"))
    ):
        return "edge_limit", "触发平台短时访问限制，已进入短暂冷却", EDGE_LIMIT_COOLDOWN
    if code in (412, -412, -352) or any(word in message for word in ("验证码", "安全验证", "风控")):
        return "review", "收到验证或异常拒绝，请在平台检查后手动恢复", None
    return None


def probation_until(sessdata, root=None):
    """Return active post-recovery trial window expiry timestamp, or 0.0."""
    if not sessdata:
        return 0.0
    value = _read_cached_json(_path(identity(sessdata, root), root), {})
    until = float(value.get("probation_until") or 0.0)
    return until if until > time.time() else 0.0


def _clear_probation(sessdata, op=None, root=None):
    if probation_until(sessdata, root) <= 0:
        return
    cleared = [False]

    def change(current):
        if float(current.get("probation_until") or 0.0) > time.time():
            current["probation_until"] = 0
            cleared[0] = True
        return current

    update_json(_path(identity(sessdata, root), root), change, {})
    if cleared[0]:
        append_event(
            _root(root) / "logs/activity.jsonl",
            {"type": "safety_probation_passed", "operation": op or {}},
        )


def pace_multiplier(sessdata, root=None):
    """Slow down same-day write cadence after recent rate/review triggers or during probation."""
    if not sessdata:
        return 1.0
    if probation_until(sessdata, root) > 0:
        return 3.0
    value = _read_cached_json(_path(identity(sessdata, root), root), {})
    hits = int((value.get("counts") or {}).get(f"{task_day()}:risk_hits", 0) or 0)
    if hits >= 2:
        return 3.0
    if hits == 1:
        return 2.0
    return 1.0


def _prune_room_blocks(blocks, now, today):
    return {
        k: v
        for k, v in (blocks or {}).items()
        if isinstance(v, dict) and v.get("day") == today and (not v.get("until") or now < v["until"])
    }


def block_room_capability(
    sessdata,
    room,
    op_kind,
    reason,
    *,
    code=-1,
    seconds=ROOM_CAPABILITY_COOLDOWN,
    raw_message="",
    root=None,
):
    """Pause one interaction capability in a single room without stopping account watching."""
    now = time.time()
    today = task_day()
    room_str = str(room or "").strip()
    if not room_str or not op_kind:
        return {}
    clean_raw = redact(str(raw_message or "")).strip()[:160]
    key = f"{room_str}:{op_kind}"
    entry = {
        "room": room_str,
        "kind": op_kind,
        "kind_label": OPERATION_LABELS.get(op_kind, op_kind),
        "code": code,
        "reason": reason,
        "raw_message": clean_raw,
        "since": now,
        "until": now + seconds if seconds else None,
        "day": today,
    }
    added = []

    def change(current):
        blocks = _prune_room_blocks(current.get("room_blocks"), now, today)
        if key not in blocks:
            added.append(entry)
        else:
            entry["since"] = blocks[key].get("since", now)
        blocks[key] = entry
        current["room_blocks"] = blocks
        return current

    result = update_json(_path(identity(sessdata, root), root), change, {}).get("room_blocks") or {}
    if added:
        append_event(
            _root(root) / "logs/activity.jsonl",
            {
                "type": "room_capability_blocked",
                "room": room_str,
                "capability": op_kind,
                "code": code,
                "until": entry["until"],
            },
        )
    return result.get(key, {})


def room_blocks(sessdata, root=None):
    if not sessdata:
        return {}
    value = _read_cached_json(_path(identity(sessdata, root), root), {})
    return _prune_room_blocks(value.get("room_blocks"), time.time(), task_day())


def room_capability_blocked(sessdata, room, op_kind, root=None):
    room_str = str(room or "").strip()
    if not room_str or not op_kind:
        return {}
    return room_blocks(sessdata, root).get(f"{room_str}:{op_kind}", {})


def clear_room_block(sessdata, room, op_kind=None, root=None):
    room_str = str(room or "").strip()
    if not sessdata or not room_str:
        return False
    removed = []

    def change(current):
        blocks = dict(current.get("room_blocks") or {})
        targets = [f"{room_str}:{op_kind}"] if op_kind else [k for k in blocks if k.startswith(f"{room_str}:")]
        for k in targets:
            if k in blocks:
                removed.append(blocks.pop(k))
        current["room_blocks"] = blocks
        return current

    update_json(_path(identity(sessdata, root), root), change, {})
    if removed:
        append_event(
            _root(root) / "logs/activity.jsonl",
            {"type": "room_capability_cleared", "room": room_str, "capability": op_kind or "all"},
        )
    return bool(removed)


def record_danmaku_shield(sessdata, room, marker, *, threshold=3, seconds=3600, root=None):
    """Track consecutive silent danmaku shields (code=0, msg=f/k) and isolate room after threshold."""
    if not sessdata or not room:
        return {}
    room_str = str(room).strip()
    today = task_day()
    streak_key = f"{today}:{room_str}:shield_streak"
    hit_threshold = [False]

    def change(current):
        counts = {
            name: n
            for name, n in (current.get("counts") or {}).items()
            if name.startswith(today + ":")
        }
        streak = int(counts.get(streak_key, 0) or 0) + 1
        counts[streak_key] = streak
        current["counts"] = counts
        if streak >= threshold:
            hit_threshold[0] = True
        return current

    update_json(_path(identity(sessdata, root), root), change, {})
    if hit_threshold[0]:
        return block_room_capability(
            sessdata,
            room_str,
            "danmaku",
            "该直播间连续触发弹幕静默屏蔽，已暂停本房自动弹幕，不影响看播与其他主播",
            code=0,
            seconds=seconds,
            raw_message=f"code=0 msg={marker}",
            root=root,
        )
    return {}


def reset_danmaku_shield(sessdata, room, *, root=None):
    """Clear a room's silent-shield streak once a danmaku is cleanly accepted."""
    if not sessdata or not room:
        return
    room_str = str(room).strip()
    streak_key = f"{task_day()}:{room_str}:shield_streak"
    value = _read_cached_json(_path(identity(sessdata, root), root), {})
    if not (value.get("counts") or {}).get(streak_key):
        return

    def change(current):
        counts = dict(current.get("counts") or {})
        counts.pop(streak_key, None)
        current["counts"] = counts
        return current

    update_json(_path(identity(sessdata, root), root), change, {})


def hold_account(
    sessdata,
    kind,
    reason,
    *,
    code=-1,
    seconds=None,
    operation=None,
    raw_message="",
    scope=None,
    root=None,
):
    now = time.time()
    clean_raw = redact(str(raw_message or "")).strip()[:160]
    today = task_day()
    target_scope = _infer_scope(kind, operation, scope)
    changed = []

    def change(current):
        previous = current.get("hold") or {}
        if previous.get("until") and now >= previous["until"]:
            previous = {}
        permanent = previous and not previous.get("until")
        same_active = (
            bool(previous)
            and previous.get("kind") == kind
            and previous.get("code") == code
            and previous.get("scope", "account") == target_scope
            and not previous.get("until")
        )
        if same_active:
            return current
        escalates = (
            not permanent
            or (previous.get("scope") == "interaction" and target_scope == "account")
            or kind in ("auth", "credentials", "review", "permission")
        )
        if escalates:
            counts = {
                name: n
                for name, n in (current.get("counts") or {}).items()
                if name.startswith(today + ":")
            }
            if kind in ("rate", "review", "edge_limit"):
                counts[f"{today}:risk_hits"] = int(counts.get(f"{today}:risk_hits", 0) or 0) + 1
                current["counts"] = counts
            recovered_today = int(counts.get(f"{today}:auto_recover:{kind}", 0) or 0)
            probe_delay = None if seconds else _next_probe_delay(kind, 0, recovered_today)
            hold = {
                "kind": kind,
                "scope": target_scope,
                "reason": reason,
                "code": code,
                "since": now,
                "until": now + seconds if seconds else None,
                "operation": operation or {},
                "raw_message": clean_raw,
                "auto_attempts": 0,
                "max_auto_attempts": len(AUTO_PROBE_DELAYS.get(kind, ())),
                "auto_recover_remaining": (
                    max(0, AUTO_RECOVER_DAILY_LIMIT[kind] - recovered_today)
                    if kind in AUTO_RECOVER_DAILY_LIMIT
                    else 0
                ),
                "next_probe_at": now + probe_delay if probe_delay else None,
                "last_probe": None,
            }
            current["hold"] = hold
            changed.append(hold)
        return current

    result = update_json(_path(identity(sessdata, root), root), change, {}).get("hold") or {}
    if changed:
        hold = changed[0]
        append_event(
            _root(root) / "logs/activity.jsonl",
            {
                "type": "safety_hold",
                "kind": kind,
                "scope": hold["scope"],
                "code": code,
                "until": hold["until"],
                "next_probe_at": hold.get("next_probe_at"),
                "operation": hold["operation"],
            },
        )
    return result


def operation(url, data, method):
    parsed = urlsplit(url)
    params = parse_qs(parsed.query)
    if isinstance(data, dict):
        params.update({str(key): [str(value)] for key, value in data.items()})
    elif isinstance(data, bytes):
        body = data.decode("utf-8", errors="replace")
        try:
            payload = json.loads(body)
        except ValueError:
            payload = None
        if isinstance(payload, dict):
            params.update({key: [str(value)] for key, value in payload.items()})
        else:
            params.update(parse_qs(body))
    room = next((params[name][0] for name in ("roomid", "room_id") if params.get(name)), "")
    if parsed.path == "/msg/send":
        kind = "danmaku"
    elif parsed.path.endswith("/likeReportV3"):
        kind = "like"
    elif parsed.path in HEARTBEAT_PATHS:
        kind = "heartbeat"
    elif parsed.path in ROOM_ENTRY_PATHS:
        kind = "room_entry"
    elif parsed.path == "/xlive/web-room/v1/fansMedal/wear":
        kind = "wear"
    elif parsed.path == "/x/web-interface/coin/add":
        kind = "coin"
    elif parsed.path == "/x/web-interface/share/add":
        kind = "share"
    elif parsed.path == "/x/click-interface/web/heartbeat":
        kind = "watch"
    else:
        kind = "other"
    return {"path": parsed.path, "room": room, "kind": kind, "method": method}


def reserve(sessdata, op):
    """Reserve before IO so uncertain outcomes and process crashes consume budget."""
    key = identity(sessdata)
    if not key.startswith("uid-"):
        return blocked_response({"reason": "无法认证账号身份，本次跳过操作", "kind": "auth"})
    hold = status(sessdata)
    if hold["blocked"] and not (is_interaction_only(hold) and is_watch_operation(op, mutation=True)):
        return blocked_response(hold)
    if op["kind"] not in ("danmaku", "like", "coin"):
        return None
    if op["kind"] in ("danmaku", "like") and op.get("room"):
        room_hold = room_capability_blocked(sessdata, op["room"], op["kind"])
        if room_hold:
            return blocked_response({**room_hold, "kind": "room_permission"})
    scope_key = "main" if op["kind"] == "coin" else op.get("room", "")
    counter = f"{task_day()}:{scope_key}:{op['kind']}"
    if op["kind"] == "danmaku":
        limit = DANMAKU_SESSION_ATTEMPT_LIMIT
    elif op["kind"] == "like":
        limit = LIVE_LIKE_BATCHES * 3
    else:
        limit = COIN_DAILY_ATTEMPT_LIMIT
    allowed = [False]

    def change(current):
        counts = {
            name: n
            for name, n in current.get("counts", {}).items()
            if name.startswith(task_day() + ":")
        }
        count = counts.get(counter, 0)
        if count < limit and not status(sessdata)["blocked"]:
            counts[counter] = count + 1
            allowed[0] = True
        current["counts"] = counts
        return current

    update_json(_path(key), change, {})
    if not allowed[0]:
        reason = "今日投币请求次数已达上限" if op["kind"] == "coin" else "今日该房间操作尝试已达上限"
        return blocked_response({"kind": "budget", "reason": reason})
    return None


def observe(sessdata, url, response, *, mutation=False, op=None):
    path = urlsplit(url).path
    data = response.get("data") or {}
    if path == "/x/web-interface/nav" and response.get("code") == 0:
        if isinstance(data, dict) and data.get("isLogin") is True:
            uid = data.get("mid")
            if str(uid).isdigit() and int(uid) > 0:
                bind_account(sessdata, uid)
        elif isinstance(data, dict) and data.get("isLogin") is False:
            hold_account(sessdata, "auth", "登录已失效，请重新扫码登录", code=-101)
        return
    decision = classify(response)
    if mutation and (
        response.get("error_kind") in ("network", "data")
        or (
            response.get("error_kind") == "http"
            and (response.get("code", 0) >= 500 or response.get("code") == 408)
        )
    ):
        raw_msg = response.get("message", "")
        if path in HEARTBEAT_PATHS:
            # Keep a single IO attempt. After cooldown, workers establish a new E chain;
            # replaying an X payload could reuse stale sequence/timestamp state.
            hold_account(
                sessdata, "network", "看播连接异常，冷却后自动重连",
                code=response.get("code"), seconds=NETWORK_COOLDOWN, operation=op,
                raw_message=raw_msg,
            )
        elif path in ROOM_ENTRY_PATHS:
            # Room entry is an idempotent presence ping; a single transport failure
            # only aborts this room's startup and must not freeze other rooms.
            return
        else:
            op_info = op or operation(url, None, "POST")
            uncertain_msg = (
                "操作结果未知，已停止重复发送；看播连接正常继续，请核对服务端进度"
                if op_info.get("kind") in INTERACTION_OPS
                else "操作结果未知，已停止重复发送；请核对服务端进度"
            )
            hold_account(
                sessdata, "uncertain", uncertain_msg,
                code=response.get("code", -1), operation=op_info,
                raw_message=raw_msg,
            )
    elif decision:
        kind, reason, delay = decision
        op_info = op or operation(url, None, "POST" if mutation else "GET")
        raw_msg = str(response.get("message", ""))
        if (
            kind == "permission"
            and op_info.get("room")
            and op_info.get("kind") in ("danmaku", "like")
            and not any(word in raw_msg for word in ACCOUNT_BAN_WORDS)
        ):
            block_room_capability(
                sessdata,
                op_info["room"],
                op_info["kind"],
                "该直播间互动权限受限（禁言或发言限制），已仅暂停此房操作，不影响看播与其他主播",
                code=response.get("code", -1),
                raw_message=raw_msg,
            )
            return
        if kind == "rate" and op_info.get("kind") in INTERACTION_OPS:
            reason = "收到频率限制，互动操作已冷却（看播正常继续）"
        elif kind == "edge_limit" and op_info.get("kind") in INTERACTION_OPS:
            reason = "触发平台短时访问限制，互动操作已冷却（看播正常继续）"
        if kind in ("rate", "edge_limit") and response.get("retry_after"):
            delay = max(delay, response["retry_after"])
        hold_account(sessdata, kind, reason, code=response.get("code"), seconds=delay,
                     operation=op_info, raw_message=raw_msg)
    elif mutation and response.get("code") == 0:
        op_info = op or operation(url, None, "POST")
        if op_info.get("kind") in PROBATION_CLEAR_OPS:
            shield_marker = str(response.get("msg") or response.get("message") or "").strip().lower()
            if shield_marker not in {"f", "k", "fire", "max limit"}:
                _clear_probation(sessdata, op_info)


def record_probe(sessdata, checks, *, passed, summary="", auto=False, root=None):
    """Record a read-only diagnostic check and schedule the next auto-probe if failed."""
    now = time.time()
    today = task_day()
    probe = {
        "at": now,
        "passed": bool(passed),
        "auto": bool(auto),
        "summary": redact(str(summary or "")).strip()[:200],
        "checks": list(checks or []),
    }

    def change(current):
        hold = dict(current.get("hold") or {})
        if not hold or (hold.get("until") and now >= hold["until"]):
            return current
        hold["last_probe"] = probe
        if auto and not passed and not hold.get("until"):
            kind = hold.get("kind") or ""
            attempts = int(hold.get("auto_attempts") or 0) + 1
            counts = current.get("counts") or {}
            recovered_today = int(counts.get(f"{today}:auto_recover:{kind}", 0) or 0)
            delay = _next_probe_delay(kind, attempts, recovered_today)
            hold["auto_attempts"] = attempts
            hold["next_probe_at"] = now + delay if delay else None
        current["hold"] = hold
        return current

    return update_json(_path(identity(sessdata, root), root), change, {}).get("hold") or {}


def auto_resume(sessdata, checks, *, summary="", root=None):
    """Clear an eligible hold after read-only probes confirm normal API responses."""
    hold = status(sessdata, root)
    if not hold.get("blocked"):
        return True, "账号当前没有保护暂停"
    kind = hold.get("kind")
    if kind not in AUTO_PROBE_DELAYS or hold.get("until"):
        return False, "当前暂停类型不支持自动解除"
    today = task_day()
    cleared = []

    def change(current):
        current_hold = current.get("hold") or {}
        if not current_hold or current_hold.get("kind") not in AUTO_PROBE_DELAYS or current_hold.get("until"):
            return current
        counts = {
            name: n
            for name, n in (current.get("counts") or {}).items()
            if name.startswith(today + ":")
        }
        key = f"{today}:auto_recover:{current_hold['kind']}"
        if counts.get(key, 0) >= AUTO_RECOVER_DAILY_LIMIT[current_hold["kind"]]:
            current_hold = dict(current_hold, next_probe_at=None, auto_recover_remaining=0)
            current["hold"] = current_hold
            return current
        counts[key] = counts.get(key, 0) + 1
        current["counts"] = counts
        probation_secs = PROBATION_SECONDS.get(current_hold["kind"], 0)
        if probation_secs > 0:
            current["probation_until"] = time.time() + probation_secs
        current["hold"] = {}
        cleared.append(current_hold)
        return current

    update_json(_path(identity(sessdata, root), root), change, {})
    if not cleared:
        return False, "今日自动恢复次数已达上限，请手动检查后确认恢复"
    append_event(
        _root(root) / "logs/activity.jsonl",
        {
            "type": "safety_auto_resumed",
            "kind": kind,
            "code": hold.get("code"),
            "operation": hold.get("operation", {}),
            "probation_seconds": PROBATION_SECONDS.get(kind, 0),
            "summary": redact(str(summary or ""))[:200],
            "checks": list(checks or []),
        },
    )
    return True, "状态检测通过，保护暂停已自动解除；进入低速试探观察期，当天额度保留"


def resume(sessdata, *, confirmed=False, root=None):
    """Explicit local acknowledgement; auth expiry can only be cleared by authentication."""
    hold = status(sessdata, root)
    if hold.get("kind") == "auth" and hold["blocked"]:
        return False, "请先重新扫码登录"
    if hold["blocked"] and hold.get("until"):
        return False, "冷却期间不提前恢复，请等待冷却结束"
    if hold["blocked"] and not confirmed:
        return False, "请先在平台处理异常或核对任务结果，再确认恢复"
    update_json(
        _path(identity(sessdata, root), root),
        lambda v: {**v, "hold": {}, "probation_until": 0},
        {},
    )
    if hold["blocked"]:
        append_event(_root(root) / "logs/activity.jsonl",
                     {"type": "safety_resumed", "kind": hold.get("kind"),
                      "operation": hold.get("operation", {})})
    return True, "账号保护暂停已解除；当天预算保留"
