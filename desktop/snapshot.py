from desktop.health import number, heartbeat_timeout
from datetime import datetime, timezone, timedelta
import os
import time
from bilioshi.runtime import APP_VERSION, task_day
from bilioshi.safety import blocks_watch, describe_hold, format_task_errors
from bilioshi.services.watch_progress import CHECK_INTERVAL, parse_watch_task


def project_snapshot(engine, states, now):
    import datetime

    rows = []
    for member in engine.members:
        rows.append(project_row(engine, member, states[member["room"]], now))
    safety_state = dict(getattr(engine, "safety", None) or {"blocked": False})
    if safety_state.get("blocked"):
        safety_state.update(describe_hold(safety_state, engine.members))
    return {
        "paused": engine.paused,
        "safety": safety_state,
        "checking": engine.probe is not None or (
            bool(getattr(engine, "force_probe", False))
            and not getattr(engine, "suspended", False)
            and not blocks_watch(safety_state)
        ),
        "error": engine.error,
        "account": engine.account,
        "rows": rows,
        "account_confirmed": bool(
            engine.account
            and engine.account_checked_at
            and (
                now - engine.account_checked_at
                <= max(180, engine.config.get("check_minutes", 30) * 60 + 180)
            )
        ),
        "account_checked_at": engine.account_checked_at,
        "medals": engine.medals,
        "tasks": engine.tasks,
        "daily": dict(getattr(engine, "daily", {}) or {}),
        "daily_running": bool(getattr(engine, "daily_running", False)),
        "profile": dict(getattr(engine, "profile", {}) or {}),
        "today": task_day(),
        "last_check": engine.last_check,
        "next_check": engine.next_check,
        "pid": os.getpid(),
        "updated": time.time(),
        "running": True,
        "stale": False,
        "version": APP_VERSION,
    }


def watch_warning_signature(watch, warning, *, expired=False):
    """Identify the active watch warning episode so dismissing one stays scoped."""
    if not warning:
        return None
    watch = watch if isinstance(watch, dict) else {}
    checked = number(watch.get("checked_at"))
    signature = {
        "day": task_day(),
        "status": "expired" if expired else str(watch.get("status") or ""),
        "warning_since": number(watch.get("warning_since")),
        "warning": str(warning),
    }
    if expired:
        signature["checked_at"] = checked
    return signature


def _completed_task_kinds(state, task_entry, tasks_stale):
    """Identify failed task branches superseded by a newer verified server probe."""
    if tasks_stale or not isinstance(task_entry, dict) or task_entry.get("day") != task_day():
        return set()
    recorded_at = number(state.get("task_updated"))
    if recorded_at <= 0 or number(task_entry.get("updated")) <= recorded_at:
        return set()
    task_result = state.get("task_result") or {}
    tasks = task_entry.get("tasks") or []
    completed = set()
    for capability, jump_type in (("danmaku", "sendDanmu"), ("like", "like")):
        branch = task_result.get(capability)
        if not (isinstance(branch, dict) and branch.get("error")):
            continue
        task = next((t for t in tasks if isinstance(t, dict) and t.get("jump_type") == jump_type), None)
        if not (task and task.get("is_done")):
            continue
        if capability == "danmaku" and task_entry.get("is_lighted") is False:
            continue
        completed.add(capability)
    return completed


def _row_task_error(state, room_blocks, safety_blocked, *, task_entry=None, tasks_stale=True):
    """Format an active day's task failure while suppressing covered blocks."""
    task_result = state.get("task_result") or {}
    blocked_caps = {
        item.get("kind")
        for item in room_blocks
        if (task_result.get(item.get("kind") or "") or {}).get("room_blocked")
    }
    completed_caps = _completed_task_kinds(state, task_entry, tasks_stale)
    if (
        task_result.get("day") == task_day()
        and not task_result.get("success")
        and not task_result.get("dismissed")
    ):
        return format_task_errors(
            task_result,
            skip_kinds=blocked_caps | completed_caps,
            suppress_safety=not safety_blocked,
        )
    return ""


def _resolve_row_phase(
    engine,
    state,
    *,
    active,
    heartbeat_stale,
    query_error,
    status_stale,
    observed,
    live_status,
):
    """Choose the primary status label for a projected room row."""
    if heartbeat_stale:
        return "心跳已过期，等待恢复"
    if active:
        return state.get("phase", "正在连接")
    if engine.paused:
        return "已暂停"
    if query_error:
        return "查询失败"
    if status_stale and observed:
        return "状态已过期"
    if state.get("phase") == "运行失败":
        return "等待重试"
    if live_status == 1:
        return "直播中，等待检查"
    if live_status in (0, 2):
        return "未开播"
    return "等待检查"


def _row_connection_state(
    engine,
    state,
    recovery,
    *,
    active,
    heartbeat_stale,
    live_status,
    safety_blocked,
    recovering,
    now,
):
    """Compute heartbeat health, warning banner, and manual reconnect eligibility."""
    heartbeat_healthy = bool(
        active
        and state.get("last_heartbeat")
        and not heartbeat_stale
        and not safety_blocked
        and not engine.paused
    )
    connection_warning = ""
    if heartbeat_stale and not engine.paused and not safety_blocked:
        connection_warning = "长时间没有成功心跳，看播收益可能中断。可点击下方“重连此直播间”恢复连接。"
        if state.get("task_started"):
            connection_warning += " 当前任务仍在执行，重连会停止该任务并只恢复看播。"
    elif recovery.get("state") == "failed" and not engine.paused and not safety_blocked:
        connection_warning = recovery.get("message", "重连失败，请稍后再试。")
    reconnect_allowed = bool(
        (active or live_status == 1 or connection_warning)
        and not engine.paused
        and not safety_blocked
        and not recovering
        and now >= recovery.get("cooldown_until", 0)
    )
    return heartbeat_healthy, connection_warning, reconnect_allowed


def _row_intimacy_gain(engine, medal, medals_stale):
    """Return today's intimacy gain only when both medal and timestamp are fresh."""
    today_value = medal.get("today_intimacy")
    checked = engine.account_checked_at
    medal_day = (
        datetime.fromtimestamp(checked, timezone(timedelta(hours=8))).date().isoformat()
        if checked
        else ""
    )
    if (
        not medals_stale
        and medal_day == task_day()
        and isinstance(today_value, int)
        and not isinstance(today_value, bool)
        and today_value >= 0
    ):
        return today_value
    return None


def project_row(engine, member, state, now):
    room = member["room"]
    uid = member.get("uid")
    room_str = str(room)
    medal = engine.medals.get(uid) or engine.medals.get(str(uid)) or {}
    task_entry = engine.tasks.get(room_str, {})
    live_info = engine.statuses.get(room_str, {})
    ttl = max(180, engine.config.get("check_minutes", 30) * 60 + 180)
    observed = engine.status_times.get(room_str, 0)
    status_stale = not observed or now - observed > ttl
    query_error = engine.status_errors.get(room_str, "")
    live_status = live_info.get("live_status") if not status_stale and (not query_error) else None
    tasks_stale = (
        status_stale
        or bool(query_error)
        or task_entry.get("day") != task_day()
        or (now - task_entry.get("updated", 0) > ttl)
        or bool(engine.task_errors.get(room_str))
    )
    live_time_val = live_info.get("live_time")
    live_duration = elapsed_label(live_status, live_time_val, now)
    safety = getattr(engine, "safety", {})
    safety_blocked = blocks_watch(safety)
    room_blocks = [
        item
        for item in (getattr(engine, "room_blocks", None) or {}).values()
        if isinstance(item, dict) and str(item.get("room")) == room_str
    ]
    active = room in engine.workers and engine.workers[room].poll() is None
    wake_grace = 0 < now - getattr(engine, "resumed_from_sleep_at", 0) < 90
    heartbeat_stale = active and not wake_grace and now - number(
        state.get("last_heartbeat"), number(state.get("started"), now)
    ) > heartbeat_timeout(state)
    phase = _resolve_row_phase(
        engine,
        state,
        active=active,
        heartbeat_stale=heartbeat_stale,
        query_error=query_error,
        status_stale=status_stale,
        observed=observed,
        live_status=live_status,
    )
    recovery = getattr(engine, "manual_reconnects", {}).get(room, {})
    recovering = recovery.get("state") == "checking"
    if recovering and not safety_blocked and not engine.paused:
        phase = "重连中，正在确认直播"
    heartbeat_healthy, connection_warning, reconnect_allowed = _row_connection_state(
        engine,
        state,
        recovery,
        active=active,
        heartbeat_stale=heartbeat_stale,
        live_status=live_status,
        safety_blocked=safety_blocked,
        recovering=recovering,
        now=now,
    )
    watch, watch_warning, watch_note, task_entry, tasks_stale = watch_observation(
        state,
        task_entry,
        active,
        tasks_stale,
        now,
        manual_checked_at=getattr(engine, "manual_check_at", 0),
    )
    if safety_blocked or engine.paused or heartbeat_stale:
        watch_warning = ""
        watch_note = ""
    elif active and state.get("watch_only") and not watch_note:
        watch_note = "手动重连后当前连接处于仅看播模式，如需补做互动任务可点击下方“补齐今日任务”。"
    task_error = _row_task_error(
        state,
        room_blocks,
        safety_blocked,
        task_entry=task_entry,
        tasks_stale=tasks_stale,
    )
    if state.get("state_error"):
        phase = "状态记录异常"
        task_error = state["state_error"]
    if safety_blocked:
        phase = "账号保护暂停"
        task_error = safety.get("reason", "需要处理账号异常")
    gain = _row_intimacy_gain(engine, medal, tasks_stale)
    reconnect_message = recovery.get("message", "")
    if recovery.get("state") == "offline" and live_status == 1:
        reconnect_message = ""
    elif recovery.get("state") == "starting" and heartbeat_healthy:
        settled_at = number(recovery.get("settled_at"), now)
        reconnect_message = "重连成功，已收到服务端心跳。" if now - settled_at <= 15 else ""
    return {
        **member,
        "phase": phase,
        "room_blocks": room_blocks,
        "active": active,
        "status_stale": status_stale,
        "status_error": query_error,
        "status_updated": observed,
        "heartbeat_stale": heartbeat_stale,
        "heartbeat_healthy": heartbeat_healthy,
        "connection_warning": connection_warning,
        "reconnect_allowed": reconnect_allowed,
        "reconnect_cooldown_until": recovery.get("cooldown_until", 0),
        "reconnecting": recovering or (recovery.get("state") == "starting" and not heartbeat_healthy and active),
        "reconnect_message": reconnect_message,
        "tasks_stale": tasks_stale,
        "session_id": state.get("session_id"),
        "task_error": task_error,
        "watch_warning": watch_warning,
        "watch_note": watch_note,
        "watch_progress": watch,
        "started": state.get("started"),
        "beats": state.get("beats", 0),
        "last_heartbeat": state.get("last_heartbeat"),
        "error": state.get("error", "") if active else "",
        "title": live_info.get("title", ""),
        "area_name": live_info.get("area_name", ""),
        "live_status": live_status,
        "live_time": live_time_val or "",
        "live_duration": live_duration,
        "medal_name": medal.get("medal_name", ""),
        "medal_level": medal.get("level", 0),
        "is_lighted": medal.get("is_lighted", 0),
        "today_intimacy": medal.get("today_intimacy", 0),
        "intimacy_gain": gain,
        "avatar_url": live_info.get("face", ""),
        "day_limit": medal.get("day_limit", 0),
        "tasks": [] if tasks_stale else task_entry.get("tasks", []),
        "intimacy": task_entry.get("intimacy", 0),
        "next_intimacy": task_entry.get("next_intimacy", 0),
        "task_light_days": task_entry.get("task_light_days", 0),
    }


def watch_observation(state, task_entry, active, tasks_stale, now, *, manual_checked_at=0):
    """Project verified task rows without making an old medal counter look fresh."""
    watch = state.get("watch_progress", {}) if active else {}
    if watch.get("day") != task_day():
        return {}, "", "", task_entry, tasks_stale
    note = ""
    minutes = int(watch.get("unchanged_minutes") or 0)
    if watch.get("rotation") and minutes >= 30:
        # The account is being credited elsewhere, so this room is simply queued.
        note = ("收益轮转中：多个直播间同时挂机时，账号收益按房间依次结算，"
                f"本房间已等待约 {minutes} 分钟，心跳正常。")
    warning = ""
    expired = False
    ttl = CHECK_INTERVAL * 2 + 180
    checked_at = number(watch.get("checked_at"))
    fresh_probe = (
        not tasks_stale
        and task_entry.get("day") == task_day()
        and number(task_entry.get("updated")) > checked_at
        and parse_watch_task({"task_info": task_entry.get("tasks", [])}) is not None
    )
    if 0 <= now - checked_at <= ttl:
        warning = watch.get("warning", "")
        if (number(watch.get("verified_at")) >= task_entry.get("updated", 0)
                and 0 <= now - number(watch.get("verified_at")) <= ttl
                and isinstance(watch.get("tasks"), list)):
            task_entry = {
                **task_entry,
                **{
                    key: watch[key]
                    for key in (
                        "tasks",
                        "intimacy",
                        "next_intimacy",
                        "is_lighted",
                        "reach_free_intimacy_limit",
                        "free_intimacy",
                    )
                    if key in watch
                },
                "updated": max(number(task_entry.get("updated")), number(watch.get("verified_at"))),
            }
            tasks_stale = False
    elif watch.get("status") != "complete":
        manual_fresh = (
            fresh_probe
            and manual_checked_at > checked_at
            and 0 <= now - number(manual_checked_at) <= ttl
            and number(task_entry.get("updated")) >= number(manual_checked_at)
        )
        if not manual_fresh:
            warning = "看播进度核验已过期，无法确认亲密度是否到账，请点击立即检查。"
            expired = True
    if fresh_probe and warning and not expired:
        status = watch.get("status")
        if status == "unavailable":
            warning = ""
        elif status == "limited":
            limit_cleared = (
                "reach_free_intimacy_limit" in task_entry
                and not task_entry["reach_free_intimacy_limit"]
            )
            lighted_after = (
                watch.get("is_lighted") is False
                and task_entry.get("is_lighted") is True
            )
            if limit_cleared or lighted_after:
                warning = ""
    progress = parse_watch_task({"task_info": task_entry.get("tasks", [])})
    if (not tasks_stale and progress and (progress.get("done")
            or progress.get("current", -1) > (watch.get("progress") or {}).get("current", -1))):
        warning = ""
        expired = False
    dismissed = state.get("watch_warning_dismissed")
    if warning and isinstance(dismissed, dict) and dismissed == watch_warning_signature(
        watch, warning, expired=expired
    ):
        warning = ""
    return watch, warning, note, task_entry, tasks_stale


def current_watch_warning_signature(engine, member, state, now):
    """Compute the dismissible signature for the active room's watch warning."""
    row = project_row(engine, member, state, now)
    warning = row.get("watch_warning", "")
    if not warning:
        return None
    watch = row.get("watch_progress") or state.get("watch_progress") or {}
    ttl = CHECK_INTERVAL * 2 + 180
    expired = not (0 <= now - number(watch.get("checked_at")) <= ttl)
    return watch_warning_signature(watch, warning, expired=expired)


def elapsed_label(live_status, live_time_val, now):
    import datetime

    live_duration = ""
    if live_status == 1 and live_time_val and (live_time_val != "0000-00-00 00:00:00"):
        try:
            if isinstance(live_time_val, (int, float)) and live_time_val > 0:
                t = float(live_time_val)
            else:
                t = time.mktime(
                    datetime.datetime.strptime(str(live_time_val), "%Y-%m-%d %H:%M:%S").timetuple()
                )
            diff = max(0, int(now - t))
            live_duration = (
                f"已播 {diff / 3600:.1f}h" if diff >= 3600 else f"已播 {max(1, diff // 60)}m"
            )
        except Exception:
            pass
    return live_duration
