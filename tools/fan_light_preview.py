"""Offline lamp planning from local JSON or a synthetic demo; never connects to an API."""

import argparse
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilioshi.services.fan_light import (  # noqa: E402
    FanLightPolicy,
    GiftBudget,
    PlanContext,
    discover_fan_light_offers,
    plan_fan_light,
)


def demo():
    now = time.time()
    day = datetime.fromtimestamp(now, timezone(timedelta(hours=8))).date().isoformat()
    return {
        "context": dict(
            room_id=1001,
            anchor_uid=1002,
            viewer_uid=1003,
            day=day,
            checked_at=now,
            authenticated=True,
            live=True,
        ),
        "policy": dict(
            enabled=True,
            allow_paid=True,
            rooms=[1001],
            max_unit_price=100,
            daily_gold_limit=200,
            selected_gift_id=101,
        ),
        "budget": {"day": day},
        "club": {
            "task_info": [{"jump_type": "feedLight", "sub_title": "每日上限 0/1", "is_done": False}]
        },
        "panel": {
            "code": 0,
            "data": {
                "gift_config": {
                    "base_config": {
                        "list": [
                            {"id": 101, "name": "粉丝团灯牌", "price": 100, "coin_type": "gold"},
                            {"id": 102, "name": "粉丝团灯牌", "price": 100, "coin_type": "gold"},
                        ]
                    }
                },
                "gift_data": {
                    "room_gift_list": {
                        "gold_list": [
                            {
                                "gift_id": gift_id,
                                "id": gift_id,
                                "gift_scene": {
                                    "scene": "default_gift",
                                    "pay_type": "send_gift",
                                    "hide_price": False,
                                },
                            }
                            for gift_id in (101, 102)
                        ]
                    }
                },
            },
        },
    }


def evaluate(value, now):
    context = PlanContext(**value["context"])
    policy = FanLightPolicy(**value.get("policy", {}))
    budget = GiftBudget(**value["budget"])
    discovery = discover_fan_light_offers(value["panel"])
    result = plan_fan_light(value["club"], value["panel"], context, policy, budget, now=now)
    return {"discovery": asdict(discovery), "plan": asdict(result)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--input", type=Path, help="Local sanitized JSON, see docs/FAN_LIGHT_RESEARCH.md"
    )
    source.add_argument("--demo", action="store_true", help="Use synthetic room, account and gifts")
    args = parser.parse_args(argv)
    try:
        value = demo() if args.demo else json.loads(args.input.read_text(encoding="utf-8-sig"))
        result = evaluate(value, time.time())
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        # Never echo supplied JSON or exception text: the file might contain a session.
        print(json.dumps({"error": "输入格式无效或文件无法读取"}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
