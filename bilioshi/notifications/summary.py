"""Compose a dated, verified snapshot, never a sum of heartbeat task results."""

from datetime import datetime, timedelta, timezone
import re
import time
from ..application import AppContext
from ..members import load_members
from ..redaction import redact
from ..safety import identity

ZONE = timezone(timedelta(hours=8))


def local_time(now):
    return datetime.fromtimestamp(now, ZONE)


def clean(value, limit=32):
    return re.sub(r"[\x00-\x1f\x7f|｜]", " ", str(redact(value))).strip()[:limit]


def task_label(task):
    title = str(task.get("title", ""))
    kind = task.get("jump_type")
    if kind == "watchLive" or "观看" in title or "看播" in title:
        name = "看播"
    elif "弹幕" in title:
        name = "弹幕"
    elif "点赞" in title:
        name = "点赞"
    elif "灯牌" in title:
        name = "灯牌"
    else:
        return None
    progress = re.search(r"(\d+)\s*/\s*(\d+)", str(task.get("sub_title", "")))
    if task.get("is_done") is True:
        return name + "完成"
    if progress and 0 <= int(progress[1]) <= int(progress[2]) and int(progress[2]) > 0:
        return name + progress[0].replace(" ", "")
    return name + "待核验"


def compose(members, result, now, *, anonymous=False):
    """Missing daily counters stay unknown even if task rows say complete."""
    day = local_time(now).date().isoformat()
    observed = result.get("observed", 0)
    fresh = (isinstance(observed, (int, float)) and 0 <= now - observed <= 13 * 60
             and local_time(observed).date().isoformat() == day)
    medals = result.get("medals", {}) if fresh and not result.get("error") else {}
    tasks = result.get("tasks", {}) if fresh and not result.get("error") else {}
    statuses = result.get("statuses", {}) if fresh and not result.get("error") else {}
    medals = medals if isinstance(medals, dict) else {}
    tasks = tasks if isinstance(tasks, dict) else {}
    statuses = statuses if isinstance(statuses, dict) else {}
    total, verified, lines = 0, 0, []
    seen = set()
    for member in members:
        uid = str(member["uid"])
        if uid in seen:
            continue
        seen.add(uid)
        label = f"主播{len(seen)}" if anonymous else clean(member["name"])
        medal = medals.get(uid, medals.get(member["uid"], {}))
        gain = medal.get("today_intimacy") if isinstance(medal, dict) else None
        valid = type(gain) is int and gain >= 0
        if valid:
            total += gain
            verified += 1
        entry = tasks.get(str(member["room"]), {})
        task_fresh = (isinstance(entry, dict) and entry.get("day") == day
                      and type(entry.get("updated")) in (int, float)
                      and 0 <= now - entry["updated"] <= 13 * 60)
        rows = entry.get("tasks", []) if task_fresh else []
        rows = rows if isinstance(rows, list) else []
        labels = [task_label(task) for task in rows if isinstance(task, dict)]
        progress = "、".join(dict.fromkeys(label for label in labels if label)) or "任务待核验"
        status = statuses.get(str(member["room"]), statuses.get(member["room"], {}))
        running = "（仍在播）" if isinstance(status, dict) and status.get("live_status") == 1 else ""
        lines.append(f"{label}：今日{'+' + str(gain) if valid else '待核验'}；{progress}{running}")
    count = len(seen)
    heading = f"{day[5:]}日报｜已核验+{total}｜{verified}/{count}房"
    if verified == 0 and count:
        heading = f"{day[5:]}日报｜收益待核验｜0/{count}房"
    elif verified < count:
        heading += " 待核验"
    content = [f"BiliOshi 每日总结 · {day}", f"截至 {local_time(now):%H:%M}（UTC+8）",
               f"当天亲密度已核验合计：+{total}；已核验 {verified}/{count} 个房间。", *lines,
               "每日计数包含手动或其他来源收益，不代表本软件独占收益。任务完成不等于收益到账。"]
    if result.get("error"):
        content.insert(3, "本次只读查询未成功，收益无法核验；请在本机检查登录、网络或账号保护状态。")
    body = "\n".join(content)
    if len(body) > 1200:
        suffix = "\n更多房间请在本机查看。每日计数并非本软件独占收益；任务完成不等于收益到账。"
        body = body[:1200 - len(suffix)] + suffix
    return {"day": day, "title": heading, "content": body,
            "verified": verified, "rooms": count, "total": total}


def collect(root, *, application=None, clock=time.time):
    """One read-only full probe; discard results across login/day changes."""
    app = application or AppContext(root)
    members = load_members(root)
    sessdata, _ = app.credentials()
    key = identity(sessdata, root)
    before = clock()
    result = app.probe(members)
    now = clock()
    current, _ = app.credentials()
    if current != sessdata or identity(current, root) != key:
        raise ValueError("查询期间账号发生变化，请重新预览")
    if local_time(before).date() != local_time(now).date():
        raise ValueError("查询跨过午夜，请在新日期重新预览")
    # The full probe timestamps completion; medal counters were read earlier.
    # A conservative start timestamp prevents a slow task query from refreshing them.
    result = {**result, "observed": before}
    return members, result, now, key
