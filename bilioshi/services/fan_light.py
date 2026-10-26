"""Offline fan-club lamp discovery, planning and settlement assessment.

This research prototype has no HTTP calls, credential handling, reservations or
send method. A preview is never authorization to execute a gift purchase.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
import re
from typing import Optional, Tuple

FAN_LIGHT_NAME = "粉丝团灯牌"
SNAPSHOT_TTL = 300
TASK_TIMEZONE = timezone(timedelta(hours=8))


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


@dataclass(frozen=True)
class FeedLightTask:
    current: int
    limit: int
    done: bool


def parse_feed_light_task(club):
    """Accept only an unambiguous feedLight task with consistent daily progress."""
    tasks = club.get("task_info") if isinstance(club, dict) else None
    if not isinstance(tasks, list):
        return None
    matches = [t for t in tasks if isinstance(t, dict) and t.get("jump_type") == "feedLight"]
    if len(matches) != 1:
        return None
    task = matches[0]
    subtitle = task.get("sub_title")
    ratios = re.findall(r"([0-9]+)\s*/\s*([0-9]+)", subtitle) if isinstance(subtitle, str) else []
    if (
        len(ratios) != 1
        or any(len(part) > 4 for part in ratios[0])
        or type(task.get("is_done")) is not bool
    ):
        return None
    current, limit = map(int, ratios[0])
    # More than one lamp per day needs new evidence and an explicit policy change.
    if limit != 1 or not 0 <= current <= limit or task["is_done"] != (current == limit):
        return None
    return FeedLightTask(current, limit, task["is_done"])


@dataclass(frozen=True)
class GiftOffer:
    gift_id: int
    name: str
    unit_price: int
    coin_type: str
    placements: Tuple[str, ...]


@dataclass(frozen=True)
class GiftDiscovery:
    offers: Tuple[GiftOffer, ...] = ()
    error: str = ""


def _panel_placements(data):
    """Read known room and tab placements; never treat the whole catalog as offered."""
    gifts = data.get("gift_data")
    if not isinstance(gifts, dict):
        raise ValueError
    room = gifts.get("room_gift_list", {})
    tabs = gifts.get("tab_list", [])
    if not isinstance(room, dict) or not isinstance(tabs, list):
        raise ValueError
    groups = []
    for name in ("gold_list", "silver_list"):
        rows = room.get(name, [])
        if not isinstance(rows, list):
            raise ValueError
        groups.append(("room_gift_list." + name, rows))
    for index, tab in enumerate(tabs):
        if not isinstance(tab, dict) or not isinstance(tab.get("list"), list):
            raise ValueError
        groups.append((f"tab_list[{index}].list", tab["list"]))
    return [(f"{path}[{i}]", row) for path, rows in groups for i, row in enumerate(rows)]


def discover_fan_light_offers(response):
    """Intersect exact-name catalog entries with currently advertised room placements."""
    try:
        if (
            not isinstance(response, dict)
            or type(response.get("code")) is not int
            or response["code"] != 0
        ):
            raise ValueError
        data = response["data"]
        catalog = data["gift_config"]["base_config"]["list"]
        if not isinstance(catalog, list):
            raise ValueError
        candidates = {}
        for item in catalog:
            if not isinstance(item, dict):
                raise ValueError
            if item.get("name") != FAN_LIGHT_NAME:
                continue
            gift_id, price, coin = item.get("id"), item.get("price"), item.get("coin_type")
            if not _integer(gift_id, 1) or not _integer(price) or coin not in ("gold", "silver"):
                raise ValueError
            signature = (price, coin)
            if gift_id in candidates and candidates[gift_id] != signature:
                raise ValueError
            candidates[gift_id] = signature
        places = {}
        for path, item in _panel_placements(data):
            if not isinstance(item, dict):
                raise ValueError
            gift_id = item.get("gift_id")
            if not _integer(gift_id, 1):
                raise ValueError
            if gift_id not in candidates:
                continue
            scene = item.get("gift_scene")
            if (
                "id" in item and (not _integer(item["id"], 1) or item["id"] != gift_id)
            ) or not isinstance(scene, dict):
                raise ValueError
            if (
                scene.get("scene") != "default_gift"
                or scene.get("pay_type") != "send_gift"
                or scene.get("hide_price") is not False
            ):
                raise ValueError
            places.setdefault(gift_id, []).append(path)
        offers = tuple(
            GiftOffer(gift_id, FAN_LIGHT_NAME, *candidates[gift_id], tuple(places[gift_id]))
            for gift_id in sorted(places)
        )
        return GiftDiscovery(offers)
    except (KeyError, TypeError, ValueError, AttributeError):
        return GiftDiscovery(error="礼物面板结构、标价或售卖场景无法确认")


@dataclass(frozen=True)
class PlanContext:
    """Caller-supplied provenance: fresh task, panel and live reads for this account/room.

    authenticated means a successful nav verification, not a UID parsed from a Cookie.
    The pure planner cannot independently establish this provenance.
    """

    room_id: int
    anchor_uid: int
    viewer_uid: int
    day: str
    checked_at: float
    authenticated: bool
    live: bool
    safety_blocked: bool = False


@dataclass(frozen=True)
class FanLightPolicy:
    enabled: bool = False
    allow_paid: bool = False
    rooms: Tuple[int, ...] = ()
    max_unit_price: int = 0
    daily_gold_limit: int = 0
    selected_gift_id: Optional[int] = None


@dataclass(frozen=True)
class GiftBudget:
    """Planning input only; spent + outstanding reservations count toward the limit.

    room_attempts includes failed attempts. account_pending includes unresolved
    purchases from previous days. These inputs do not implement a persistent ledger.
    """

    day: str
    spent_gold: int = 0
    reserved_gold: int = 0
    room_attempts: int = 0
    account_pending: bool = False


@dataclass(frozen=True)
class GiftPreview:
    room_id: int
    anchor_uid: int
    gift_id: int
    unit_price: int
    idempotency_key: str
    quantity: int = field(default=1, init=False)
    coin_type: str = field(default="gold", init=False)
    execution_allowed: bool = field(default=False, init=False)


@dataclass(frozen=True)
class PlanResult:
    status: str
    reason: str
    offers: Tuple[GiftOffer, ...] = ()
    preview: Optional[GiftPreview] = None


def _context_error(context, budget, now):
    if not all(_integer(v, 1) for v in (context.room_id, context.anchor_uid, context.viewer_uid)):
        return "房间或账号身份无效"
    if type(now) not in (int, float) or not math.isfinite(now):
        return "当前时间无效"
    if type(context.checked_at) not in (int, float) or not math.isfinite(context.checked_at):
        return "查询时间无效"
    if not 0 <= now - context.checked_at <= SNAPSHOT_TTL:
        return "查询快照过期或时间倒退，请重新只读查询"
    try:
        day = datetime.fromtimestamp(now, TASK_TIMEZONE).date().isoformat()
        observed_day = datetime.fromtimestamp(context.checked_at, TASK_TIMEZONE).date().isoformat()
    except (OSError, ValueError, OverflowError):
        return "查询时间超出有效范围"
    if context.day != day or observed_day != day or budget.day != day:
        return "日期不一致，请重新读取当日任务和预算"
    if context.authenticated is not True:
        return "账号身份尚未通过服务端认证"
    if type(context.safety_blocked) is not bool or context.safety_blocked:
        return "账号保护状态不允许规划投喂"
    if not all(
        _integer(v) for v in (budget.spent_gold, budget.reserved_gold, budget.room_attempts)
    ):
        return "预算账本数据无效"
    if type(budget.account_pending) is not bool or budget.account_pending:
        return "存在尚未核清的投喂结果，需先核对订单与消费"
    return ""


def plan_fan_light(club, panel, context, policy, budget, *, now):
    """Produce a fixed one-item preview, never a send request or a budget reservation."""
    if policy.enabled is not True:
        return PlanResult("disabled", "自动投喂默认关闭")
    error = _context_error(context, budget, now)
    if error:
        return PlanResult("blocked", error)
    task = parse_feed_light_task(club)
    if task is None:
        return PlanResult("unavailable", "无法确认每日投喂任务；不把查询失败当作 0/1")
    if task.done:
        return PlanResult("complete", "每日投喂任务已经完成")
    if context.live is not True:
        return PlanResult("blocked", "当前原型仅规划已确认在播房间")
    if (
        not isinstance(policy.rooms, (tuple, list))
        or not all(_integer(room, 1) for room in policy.rooms)
        or context.room_id not in policy.rooms
    ):
        return PlanResult("blocked", "房间未明确授权投喂")
    if budget.room_attempts:
        return PlanResult("already_attempted", "本账号今日已对该房间尝试投喂，请核对结果")
    discovery = discover_fan_light_offers(panel)
    if discovery.error:
        return PlanResult("unavailable", discovery.error)
    offers = discovery.offers
    if not offers:
        return PlanResult("unavailable", "面板没有可确认的粉丝团灯牌")
    if policy.selected_gift_id is None:
        return PlanResult("needs_selection", "需用正常投喂成功记录确认目标礼物 ID", offers)
    offer = next((g for g in offers if g.gift_id == policy.selected_gift_id), None)
    if not _integer(policy.selected_gift_id, 1) or offer is None:
        return PlanResult("unavailable", "指定礼物不在当前房间可确认的灯牌候选中", offers)
    if offer.coin_type != "gold" or offer.unit_price <= 0:
        return PlanResult("unsupported", "免费、银瓜子或背包灯牌的任务资格尚未验证", offers)
    if policy.allow_paid is not True:
        return PlanResult("needs_authorization", "当前灯牌涉及金瓜子消耗，付费投喂未授权", offers)
    if not _integer(policy.max_unit_price, 1) or not _integer(policy.daily_gold_limit, 1):
        return PlanResult("blocked", "必须设置有效的单价与账号每日预算上限", offers)
    if offer.unit_price > policy.max_unit_price:
        return PlanResult("over_budget", "当前单价超过授权上限", offers)
    if budget.spent_gold + budget.reserved_gold + offer.unit_price > policy.daily_gold_limit:
        return PlanResult("over_budget", "账号当日已消费及预留金额超过预算", offers)
    preview = GiftPreview(
        context.room_id,
        context.anchor_uid,
        offer.gift_id,
        offer.unit_price,
        f"uid-{context.viewer_uid}:{context.day}:{context.room_id}:feedLight",
    )
    return PlanResult(
        "preview_ready", "仅离线预览；执行接口、账本与任务资格验收尚未接入", offers, preview
    )


@dataclass(frozen=True)
class SettlementResult:
    status: str
    reason: str
    intimacy_delta: Optional[int] = None
    retry_allowed: bool = field(default=False, init=False)


def assess_fan_light_settlement(
    before, after, *, outcome, before_day, after_day, intimacy_before=None, intimacy_after=None
):
    """Separate request acceptance, task completion and contemporaneous intimacy growth.

    outcome is accepted / rejected / unknown from the HTTP boundary. No outcome
    authorizes automatic replay, and a concurrent gain is not gift attribution.
    """
    if outcome not in ("accepted", "rejected", "unknown"):
        return SettlementResult("unverifiable", "请求结果分类无效")
    if not before_day or before_day != after_day:
        return SettlementResult("unverifiable", "跨日数据不能核验同一次任务结算")
    start, end = parse_feed_light_task(before), parse_feed_light_task(after)
    if start is None:
        return SettlementResult("unverifiable", "缺少可靠的投喂前任务基线")
    if start.done:
        return SettlementResult("preexisting_complete", "任务在投喂前已完成，无法据此证明本次有效")
    if end is None:
        return SettlementResult("awaiting_confirmation", "无法读取有效的投喂后进度，需要只读核对")
    if not end.done:
        state = {"accepted": "awaiting_settlement", "rejected": "rejected", "unknown": "unknown"}[
            outcome
        ]
        return SettlementResult(state, "任务尚未确认完成；不自动补送")
    if outcome != "accepted":
        return SettlementResult(
            "task_complete_spend_unresolved", "任务已完成，但本次发送及消费仍需独立核对"
        )
    delta = None
    if _integer(intimacy_before) and _integer(intimacy_after) and intimacy_after >= intimacy_before:
        delta = intimacy_after - intimacy_before
    return SettlementResult(
        "task_confirmed", "任务已完成；同期亲密度差值不等于本次投喂独立收益", delta
    )
