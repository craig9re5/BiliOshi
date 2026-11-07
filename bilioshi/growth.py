"""Per-account daily fan-medal growth history.

The only writer is ``Engine._apply_probe`` after a successful probe. Each
sample is the server's ``today_intimacy`` for one room; the day's value is the
maximum observed value, because the server counter rises during the day and
resets at 00:00 UTC+8. A missing room/day is "not recorded"; a valid 0 is a
recorded value.

This module never performs network IO. It is deliberately independent from
``desktop`` so the same rules can be tested offline and reused by a CLI.
"""

from __future__ import annotations

import logging
import math
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from .runtime import read_json, update_json

SCHEMA_VERSION = 1
RETENTION_DAYS = 90
MAX_VALUE = 10_000_000
DAY_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHINA_TZ = timezone(timedelta(hours=8))


def growth_path(root) -> Path:
    return Path(root) / "state" / "growth.json"


def _is_int(value, minimum=0, maximum=MAX_VALUE):
    return type(value) is int and minimum <= value <= maximum


def _is_time(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _iso_day(value):
    if not _is_time(value):
        return ""
    try:
        return datetime.fromtimestamp(value, CHINA_TZ).date().isoformat()
    except (OSError, ValueError, OverflowError):
        return ""


def _today(now=None):
    return _iso_day(time.time() if now is None else now)


def _empty(account_id=""):
    return {
        "version": SCHEMA_VERSION,
        "account_id": account_id or "",
        "updated": 0.0,
        "days": {},
    }


def _day_cutoff(today):
    try:
        bound = date.fromisoformat(today) - timedelta(days=RETENTION_DAYS - 1)
    except ValueError:
        return ""
    return bound.isoformat()


def _prune(days, today):
    cutoff = _day_cutoff(today)
    if not cutoff:
        return
    for key in [key for key in days if key < cutoff]:
        days.pop(key, None)


def _validate(data, account_id=""):
    """Return an error message for a structurally unusable history file."""
    if not isinstance(data, dict):
        return "成长记录结构无效"
    if data.get("version") != SCHEMA_VERSION:
        return "成长记录版本无法识别"
    stored = data.get("account_id")
    if stored is not None and not isinstance(stored, str):
        return "成长记录账号字段无效"
    if stored and account_id and stored != account_id:
        return "成长记录属于其他账号"
    days = data.get("days")
    if not isinstance(days, dict):
        return "成长记录日期结构无效"
    for day, entry in days.items():
        if not isinstance(day, str) or not DAY_PATTERN.match(day):
            return "成长记录日期格式无效"
        if not isinstance(entry, dict):
            return "成长记录日期内容无效"
        rooms = entry.get("rooms")
        if not isinstance(rooms, dict):
            return "成长记录房间结构无效"
        for room, cell in rooms.items():
            if not isinstance(room, str) or not room.isdigit():
                return "成长记录房间号无效"
            if not isinstance(cell, dict):
                return "成长记录房间内容无效"
            if not _is_int(cell.get("max")):
                return "成长记录数值无效"
            for key in ("samples",):
                if key in cell and not _is_int(cell[key], 0, 100_000_000):
                    return "成长记录采样计数无效"
            for key in ("first_at", "last_at"):
                if key in cell and not _is_time(cell[key]):
                    return "成长记录时间无效"
            if "last_value" in cell and not _is_int(cell["last_value"]):
                return "成长记录数值无效"
        for key in ("samples",):
            if key in entry and not _is_int(entry[key], 0, 100_000_000):
                return "成长记录采样计数无效"
        for key in ("first_at", "last_at"):
            if key in entry and not _is_time(entry[key]):
                return "成长记录时间无效"
    return ""


def _metadata(member, medal):
    name = member.get("name") if isinstance(member, dict) else ""
    uid = member.get("uid") if isinstance(member, dict) else None
    medal_name = medal.get("medal_name") if isinstance(medal, dict) else ""
    level = medal.get("level") if isinstance(medal, dict) else None
    limit = medal.get("day_limit") if isinstance(medal, dict) else None
    lighted = medal.get("is_lighted") if isinstance(medal, dict) else None
    value = {}
    if _is_int(uid, 1, 10**18):
        value["uid"] = uid
    if isinstance(name, str) and name.strip():
        value["name"] = name
    if isinstance(medal_name, str) and medal_name.strip():
        value["medal_name"] = medal_name
    if _is_int(level, 0, 1000):
        value["level"] = level
    if _is_int(limit, 0, MAX_VALUE):
        value["day_limit"] = limit
    if _is_int(lighted, 0, 1):
        value["is_lighted"] = lighted
    return value


def _updates(members, medals):
    """Map room -> value and metadata from one successful probe."""
    if not isinstance(members, (list, tuple)) or not isinstance(medals, dict):
        return {}
    updates = {}
    seen_uids = set()
    for member in members:
        if not isinstance(member, dict):
            continue
        uid, room = member.get("uid"), member.get("room")
        if not _is_int(uid, 1, 10**18) or not _is_int(room, 1, 10**18):
            continue
        if uid in seen_uids:
            continue
        seen_uids.add(uid)
        medal = medals.get(uid)
        if medal is None:
            medal = medals.get(str(uid))
        if not isinstance(medal, dict):
            continue
        value = medal.get("today_intimacy")
        if not _is_int(value, 0, MAX_VALUE):
            continue
        meta = _metadata(member, medal)
        updates[str(room)] = (value, meta)
    return updates


def _merge(days, day, updates, observed_at):
    """Merge one probe into ``days``; return whether any room was applied."""
    created = day not in days
    entry = days.get(day)
    if not isinstance(entry, dict):
        entry = {"rooms": {}}
        days[day] = entry
    rooms = entry.get("rooms")
    if not isinstance(rooms, dict):
        raise ValueError("成长记录日期内容无效")
    applied = False
    for room, (value, meta) in updates.items():
        # Reject a sample earlier than this room's newest recorded day. This
        # prevents a clock rollback from rewriting history; a probe that
        # started before midnight is still allowed if it is the newest day.
        newest = ""
        for key, item in days.items():
            if isinstance(item, dict) and isinstance(item.get("rooms"), dict):
                if room in item["rooms"] and key > newest:
                    newest = key
        if newest and day < newest:
            continue
        cell = rooms.get(room)
        if not isinstance(cell, dict):
            cell = {}
            rooms[room] = cell
        old_max = cell.get("max")
        if old_max is not None and not _is_int(old_max):
            raise ValueError("成长记录数值无效")
        samples = cell.get("samples", 0)
        if not _is_int(samples, 0, 100_000_000):
            raise ValueError("成长记录采样计数无效")
        first_at = cell.get("first_at")
        if not _is_time(first_at):
            first_at = observed_at
        last_at = cell.get("last_at")
        if not _is_time(last_at):
            last_at = observed_at
        cell.update(meta)
        cell["max"] = value if old_max is None else max(old_max, value)
        cell["samples"] = samples + 1
        cell["first_at"] = min(first_at, observed_at)
        cell["last_at"] = max(last_at, observed_at)
        cell["last_value"] = value
        applied = True
    if not applied:
        if created:
            days.pop(day, None)
        return False
    samples = entry.get("samples", 0)
    if not _is_int(samples, 0, 100_000_000):
        samples = 0
    first_at = entry.get("first_at")
    if not _is_time(first_at):
        first_at = observed_at
    last_at = entry.get("last_at")
    if not _is_time(last_at):
        last_at = observed_at
    entry["samples"] = samples + 1
    entry["first_at"] = min(first_at, observed_at)
    entry["last_at"] = max(last_at, observed_at)
    return True


def record_samples(root, account_id, members, medals, observed_at, *, now=None):
    """Merge one successful probe into the account's history.

    Returns True when the file was written. Any IO, clock or schema problem is
    logged and skipped; this function never raises into the engine tick.
    """
    day = _iso_day(observed_at)
    today = _today(now)
    if not day or not today or day > today:
        return False
    updates = _updates(members, medals)
    if not updates:
        return False
    path = growth_path(root)
    applied = False

    def change(data):
        nonlocal applied
        error = _validate(data, account_id)
        if error:
            raise ValueError(error)
        days = data.setdefault("days", {})
        if not isinstance(days, dict):
            raise ValueError("成长记录日期结构无效")
        if not _merge(days, day, updates, observed_at):
            return data
        _prune(days, today)
        data["version"] = SCHEMA_VERSION
        data["account_id"] = account_id or data.get("account_id", "")
        data["updated"] = observed_at
        applied = True
        return data

    try:
        update_json(path, change, _empty(account_id))
        return applied
    except (OSError, ValueError, TypeError, TimeoutError) as exc:
        logging.warning("Cannot record fan-medal growth; history left unchanged: %s", exc)
        return False


def _member_rows(members):
    """Current rooms in member order, skipping invalid or duplicate rooms."""
    rows, seen = [], set()
    for member in members if isinstance(members, (list, tuple)) else ():
        if not isinstance(member, dict):
            continue
        room, uid = member.get("room"), member.get("uid")
        if not _is_int(room, 1, 10**18) or not _is_int(uid, 1, 10**18):
            continue
        if room in seen:
            continue
        seen.add(room)
        name = member.get("name") if isinstance(member.get("name"), str) else ""
        rows.append({
            "room": room, "uid": uid, "name": name, "tracked": True,
            "medal_name": "", "level": 0,
        })
    return rows


def load_history(root, account_id="", days=7, *, members=None, now=None):
    """Return the public growth payload for one account and window.

    ``members`` is the account's current members list; current rooms always get
    a row even when they have no samples. Historical rooms are appended after
    them. Cells are aligned with ``days`` and never turn a missing value into 0.
    """
    if type(days) is not int or isinstance(days, bool) or not 1 <= days <= RETENTION_DAYS:
        raise ValueError(f"days 必须是 1 到 {RETENTION_DAYS} 之间的整数")
    today = _today(now)
    if not today:
        return {
            "schema": 1, "available": False, "error": "当前时间无效",
            "today": "", "days": [], "rooms": [], "coverage": {},
            "account_id": account_id or "", "generated_at": time.time(),
        }
    try:
        start = date.fromisoformat(today) - timedelta(days=days - 1)
    except ValueError:
        start = date.fromisoformat(today)
    day_list = [(start + timedelta(days=offset)).isoformat() for offset in range(days)]
    try:
        raw = read_json(growth_path(root), None)
    except FileNotFoundError:
        raw = None
    except (OSError, ValueError, TypeError):
        return {
            "schema": 1, "available": False,
            "error": "成长记录无法读取，历史数据未改动",
            "today": today, "days": day_list, "rooms": [], "coverage": {},
            "account_id": account_id or "", "generated_at": time.time(),
        }
    if raw is None:
        data = _empty(account_id)
        error = ""
    else:
        error = _validate(raw, account_id)
        data = raw if not error else None
    if error:
        return {
            "schema": 1, "available": False, "error": error,
            "today": today, "days": day_list, "rooms": [], "coverage": {},
            "account_id": account_id or "", "generated_at": time.time(),
        }

    rows = _member_rows(members)
    by_room = {row["room"]: row for row in rows}
    days = data.get("days", {}) if isinstance(data, dict) else {}
    for day in day_list:
        entry = days.get(day) if isinstance(days, dict) else None
        rooms = entry.get("rooms", {}) if isinstance(entry, dict) else {}
        if not isinstance(rooms, dict):
            continue
        for key, cell in rooms.items():
            if not isinstance(cell, dict) or not isinstance(key, str) or not key.isdigit():
                continue
            room = int(key)
            row = by_room.get(room)
            if row is None:
                row = {
                    "room": room, "uid": cell.get("uid", 0), "name": "",
                    "tracked": False, "medal_name": "", "level": 0,
                }
                rows.append(row)
                by_room[room] = row
            # Newer days win for a historical row's metadata. A current room
            # keeps its current member name; only its medal metadata updates.
            for field in ("name", "medal_name", "level"):
                value = cell.get(field)
                if field == "name" and row["tracked"]:
                    continue
                if field == "level":
                    if _is_int(value, 0, 1000):
                        row[field] = value
                elif isinstance(value, str) and value.strip():
                    row[field] = value

    current_rooms = [row for row in rows if row["tracked"]]
    recordable = len(current_rooms)
    coverage = {}
    for day in day_list:
        entry = days.get(day) if isinstance(days, dict) else None
        rooms = entry.get("rooms", {}) if isinstance(entry, dict) else {}
        recorded = 0
        first_at = last_at = None
        for row in current_rooms:
            cell = rooms.get(str(row["room"])) if isinstance(rooms, dict) else None
            if isinstance(cell, dict) and _is_int(cell.get("max")):
                recorded += 1
                if _is_time(cell.get("first_at")):
                    first_at = cell["first_at"] if first_at is None else min(first_at, cell["first_at"])
                if _is_time(cell.get("last_at")):
                    last_at = cell["last_at"] if last_at is None else max(last_at, cell["last_at"])
        if first_at is None and isinstance(entry, dict) and _is_time(entry.get("first_at")):
            first_at = entry["first_at"]
        if last_at is None and isinstance(entry, dict) and _is_time(entry.get("last_at")):
            last_at = entry["last_at"]
        partial = day == today
        if last_at is not None and not partial:
            try:
                day_end = datetime.fromisoformat(day + "T23:55:00").replace(tzinfo=CHINA_TZ)
                partial = last_at < day_end.timestamp()
            except ValueError:
                partial = False
        coverage[day] = {
            "samples": entry.get("samples", 0) if isinstance(entry, dict) and _is_int(entry.get("samples"), 0) else 0,
            "first_at": first_at,
            "last_at": last_at,
            "rooms_recorded": recorded,
            "rooms_recordable": recordable,
            "partial": partial,
        }

    result_rooms = []
    for row in rows:
        cells = []
        recorded_days = 0
        recorded_total = 0
        for day in day_list:
            entry = days.get(day) if isinstance(days, dict) else None
            rooms = entry.get("rooms", {}) if isinstance(entry, dict) else {}
            cell = rooms.get(str(row["room"])) if isinstance(rooms, dict) else None
            if isinstance(cell, dict) and _is_int(cell.get("max")):
                value = cell["max"]
                recorded_days += 1
                recorded_total += value
                cells.append({
                    "day": day, "recorded": True, "value": value,
                    "samples": cell.get("samples", 0) if _is_int(cell.get("samples"), 0) else 0,
                    "last_at": cell.get("last_at") if _is_time(cell.get("last_at")) else None,
                })
            else:
                cells.append({"day": day, "recorded": False, "value": None, "samples": 0, "last_at": None})
        result_rooms.append({
            **row,
            "recorded_days": recorded_days,
            "recorded_total": recorded_total,
            "cells": cells,
        })

    return {
        "schema": 1,
        "available": True,
        "error": "",
        "today": today,
        "days": day_list,
        "rooms": result_rooms,
        "coverage": coverage,
        "account_id": account_id or (data.get("account_id", "") if isinstance(data, dict) else ""),
        "generated_at": time.time(),
    }
