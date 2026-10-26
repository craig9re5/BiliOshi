"""Offline regressions for wrong gifts, duplicate spending and false reward claims."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request

from bilioshi.services.fan_light import (
    FanLightPolicy,
    GiftBudget,
    PlanContext,
    assess_fan_light_settlement,
    discover_fan_light_offers,
    parse_feed_light_task,
    plan_fan_light,
)
from tools.fan_light_preview import main


DAY = "2026-01-02"
NOW = datetime(2026, 1, 2, 12, tzinfo=timezone(timedelta(hours=8))).timestamp()


def club(current=0, **changes):
    task = dict(
        jump_type="feedLight",
        title="投喂粉丝灯牌",
        sub_title=f"每日上限 {current}/1",
        is_done=current == 1,
    )
    task.update(changes)
    return {"is_lighted": True, "task_info": [task]}


def panel():
    def placement(gift_id):
        return {
            "gift_id": gift_id,
            "id": gift_id,
            "gift_scene": {"scene": "default_gift", "pay_type": "send_gift", "hide_price": False},
        }

    return {
        "code": 0,
        "data": {
            "gift_config": {
                "base_config": {
                    "list": [
                        {"id": 101, "name": "粉丝团灯牌", "price": 100, "coin_type": "gold"},
                        {"id": 102, "name": "粉丝团灯牌", "price": 100, "coin_type": "gold"},
                        {"id": 103, "name": "专属灯牌", "price": 5000, "coin_type": "gold"},
                        {"id": 104, "name": "粉丝团灯牌", "price": 100, "coin_type": "gold"},
                    ]
                }
            },
            "gift_data": {
                "room_gift_list": {"gold_list": [placement(101), placement(103)]},
                "tab_list": [{"list": [placement(102), placement(101)]}],
            },
        },
    }


class FanLightTaskTests(unittest.TestCase):
    def test_revival_is_not_a_feed_task(self):
        self.assertFalse(parse_feed_light_task(club()).done)
        value = club(jump_type="sendDanmu")
        self.assertIsNone(parse_feed_light_task(value))

    def test_missing_conflicting_or_duplicate_tasks_are_unavailable(self):
        invalid = [
            {},
            {"task_info": {}},
            club(2),
            club(is_done="false"),
            club(is_done=True),
            club(1, is_done=False),
            club(sub_title="0/2"),
            club(sub_title="0/1 1/1"),
            club(sub_title=None),
            club(sub_title="9" * 5000 + "/1"),
        ]
        value = club()
        value["task_info"] *= 2
        invalid.append(value)
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                self.assertIsNone(parse_feed_light_task(value))
        self.assertTrue(parse_feed_light_task(club(1)).done)


class FanLightDiscoveryTests(unittest.TestCase):
    def test_intersects_room_and_tab_offers_and_excludes_expensive_names(self):
        found = discover_fan_light_offers(panel())
        self.assertEqual(found.error, "")
        self.assertEqual([gift.gift_id for gift in found.offers], [101, 102])
        self.assertEqual(len(found.offers[0].placements), 2)

    def test_catalog_order_does_not_choose_a_duplicate_name(self):
        first = panel()
        second = panel()
        second["data"]["gift_config"]["base_config"]["list"].reverse()
        self.assertEqual(discover_fan_light_offers(first), discover_fan_light_offers(second))

    def test_missing_price_is_not_treated_as_free(self):
        for price in (None, "100", -1, True, 0.5):
            value = panel()
            value["data"]["gift_config"]["base_config"]["list"][0]["price"] = price
            self.assertTrue(discover_fan_light_offers(value).error)

    def test_conflicting_catalog_rows_block_discovery(self):
        value = panel()
        catalog = value["data"]["gift_config"]["base_config"]["list"]
        catalog.append({**catalog[0], "price": 200})
        self.assertTrue(discover_fan_light_offers(value).error)

    def test_invalid_response_or_offer_scene_does_not_enable_purchase(self):
        for key, bad in (("pay_type", "subscription"), ("hide_price", True), ("scene", None)):
            value = panel()
            value["data"]["gift_data"]["room_gift_list"]["gold_list"][0]["gift_scene"][key] = bad
            self.assertTrue(discover_fan_light_offers(value).error)
        for value in ({}, {"code": False}, {"code": 412}, {"code": 0, "data": None}):
            self.assertTrue(discover_fan_light_offers(value).error)


class FanLightPlanningTests(unittest.TestCase):
    def setUp(self):
        self.context = PlanContext(1001, 1002, 1003, DAY, NOW, True, True)
        self.policy = FanLightPolicy(True, True, (1001,), 100, 300, 101)
        self.budget = GiftBudget(DAY)

    def plan(self, *, context=None, policy=None, budget=None, task=None, gifts=None, now=NOW):
        return plan_fan_light(
            club() if task is None else task,
            panel() if gifts is None else gifts,
            context or self.context,
            policy or self.policy,
            budget or self.budget,
            now=now,
        )

    def test_defaults_never_enable_paid_gifts(self):
        self.assertEqual(self.plan(policy=FanLightPolicy()).status, "disabled")
        result = self.plan(policy=replace(self.policy, allow_paid=False))
        self.assertEqual(result.status, "needs_authorization")
        self.assertIsNone(result.preview)

    def test_name_is_insufficient_even_with_only_one_candidate(self):
        policy = replace(self.policy, selected_gift_id=None)
        self.assertEqual(self.plan(policy=policy).status, "needs_selection")
        value = panel()
        value["data"]["gift_data"]["tab_list"] = []
        self.assertEqual(self.plan(policy=policy, gifts=value).status, "needs_selection")

    def test_selected_gift_must_be_advertised_and_exact_name(self):
        for selected in (103, 104, 999, True):
            result = self.plan(policy=replace(self.policy, selected_gift_id=selected))
            self.assertEqual(result.status, "unavailable")
        self.assertEqual(
            self.plan(policy=replace(self.policy, selected_gift_id=102)).preview.gift_id, 102
        )

    def test_room_account_live_and_protection_checks(self):
        contexts = [
            replace(self.context, room_id=1004),
            replace(self.context, viewer_uid=True),
            replace(self.context, anchor_uid=0),
            replace(self.context, authenticated=False),
            replace(self.context, live=False),
            replace(self.context, safety_blocked=True),
        ]
        for context in contexts:
            self.assertEqual(self.plan(context=context).status, "blocked")
        self.assertEqual(self.plan(policy=replace(self.policy, rooms=None)).status, "blocked")

    def test_completed_task_skips_and_read_failure_is_not_zero_progress(self):
        self.assertEqual(self.plan(task=club(1)).status, "complete")
        self.assertEqual(self.plan(task={}).status, "unavailable")

    def test_stale_clock_reversal_nonfinite_and_cross_day_require_refresh(self):
        for stamp in (NOW - 301, NOW + 1, float("nan"), float("inf")):
            self.assertEqual(
                self.plan(context=replace(self.context, checked_at=stamp)).status, "blocked"
            )
        self.assertEqual(
            self.plan(context=replace(self.context, day="2026-01-01")).status, "blocked"
        )
        self.assertEqual(self.plan(budget=replace(self.budget, day="2026-01-01")).status, "blocked")
        self.assertEqual(
            self.plan(now=1e300, context=replace(self.context, checked_at=1e300)).status, "blocked"
        )
        midnight = datetime(2026, 1, 2, tzinfo=timezone(timedelta(hours=8))).timestamp()
        self.assertEqual(
            self.plan(
                now=midnight + 60, context=replace(self.context, checked_at=midnight - 1)
            ).status,
            "blocked",
        )

    def test_outstanding_reservations_and_price_increase_count_toward_budget(self):
        self.assertEqual(
            self.plan(budget=replace(self.budget, spent_gold=100, reserved_gold=101)).status,
            "over_budget",
        )
        result = self.plan(budget=replace(self.budget, spent_gold=100, reserved_gold=100))
        self.assertEqual(result.status, "preview_ready")
        self.assertEqual(
            self.plan(policy=replace(self.policy, max_unit_price=99)).status, "over_budget"
        )
        for budget in (
            replace(self.budget, spent_gold=-1),
            replace(self.budget, reserved_gold=True),
        ):
            self.assertEqual(self.plan(budget=budget).status, "blocked")

    def test_unknown_results_and_all_prior_attempts_prevent_replay(self):
        self.assertEqual(
            self.plan(budget=replace(self.budget, account_pending=True)).status, "blocked"
        )
        for count in (1, 2):
            self.assertEqual(
                self.plan(budget=replace(self.budget, room_attempts=count)).status,
                "already_attempted",
            )

    def test_zero_price_and_silver_are_not_claimed_as_eligible_free_lamps(self):
        for change in ({"price": 0}, {"coin_type": "silver"}):
            value = panel()
            value["data"]["gift_config"]["base_config"]["list"][0].update(change)
            self.assertEqual(self.plan(gifts=value).status, "unsupported")

    def test_preview_is_immutable_fixed_one_and_does_not_send_or_reserve(self):
        task, gifts = club(), panel()
        original = deepcopy((task, gifts))
        with patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")):
            result = self.plan(task=task, gifts=gifts)
        self.assertEqual((task, gifts), original)
        self.assertEqual(result.preview.quantity, 1)
        self.assertFalse(result.preview.execution_allowed)
        self.assertEqual(result.preview.idempotency_key, f"uid-1003:{DAY}:1001:feedLight")
        with self.assertRaises(FrozenInstanceError):
            result.preview.quantity = 10


class FanLightSettlementTests(unittest.TestCase):
    def assess(self, *, before=None, after=None, outcome="accepted", **kwargs):
        return assess_fan_light_settlement(
            club() if before is None else before,
            club(1) if after is None else after,
            outcome=outcome,
            before_day=kwargs.pop("before_day", DAY),
            after_day=kwargs.pop("after_day", DAY),
            **kwargs,
        )

    def test_api_success_does_not_prove_task_completion(self):
        result = self.assess(after=club())
        self.assertEqual(result.status, "awaiting_settlement")
        self.assertFalse(result.retry_allowed)

    def test_already_complete_baseline_cannot_prove_effect(self):
        self.assertEqual(self.assess(before=club(1)).status, "preexisting_complete")

    def test_task_completion_and_reward_observation_are_separate(self):
        result = self.assess(intimacy_before=20, intimacy_after=20)
        self.assertEqual(result.status, "task_confirmed")
        self.assertEqual(result.intimacy_delta, 0)
        self.assertEqual(self.assess(intimacy_before=20, intimacy_after=29).intimacy_delta, 9)
        self.assertIsNone(self.assess(intimacy_before=20, intimacy_after=19).intimacy_delta)

    def test_unknown_write_stays_unresolved_even_after_task_completes(self):
        result = self.assess(outcome="unknown")
        self.assertEqual(result.status, "task_complete_spend_unresolved")
        self.assertFalse(result.retry_allowed)
        self.assertEqual(self.assess(after=club(), outcome="unknown").status, "unknown")

    def test_missing_reads_cross_day_and_rejections_never_trigger_replay(self):
        self.assertEqual(self.assess(before={}).status, "unverifiable")
        self.assertEqual(self.assess(after={}).status, "awaiting_confirmation")
        self.assertEqual(self.assess(after_day="2026-01-03").status, "unverifiable")
        self.assertEqual(self.assess(outcome="rejected", after=club()).status, "rejected")
        self.assertEqual(self.assess(outcome="rejected").status, "task_complete_spend_unresolved")


class FanLightPreviewToolTests(unittest.TestCase):
    def test_demo_does_not_access_accounts_and_never_enables_execution(self):
        with (
            patch("builtins.print") as output,
            patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")),
        ):
            self.assertEqual(main(["--demo"]), 0)
        self.assertFalse(
            json.loads(output.call_args.args[0])["plan"]["preview"]["execution_allowed"]
        )

    def test_invalid_input_does_not_echo_private_fields(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "input.json"
            path.write_text(
                json.dumps({"private_field": "must-not-echo-this-value"}), encoding="utf-8"
            )
            with patch("builtins.print") as output:
                self.assertEqual(main(["--input", str(path)]), 2)
        self.assertNotIn("must-not-echo-this-value", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
