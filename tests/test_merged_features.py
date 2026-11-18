"""Contract tests for merged BiliCheckin capabilities inside BiliOshi."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from bilioshi import safety
from bilioshi.account_migration import import_bilicheckin_data
from bilioshi.accounts import AccountStore
from bilioshi.application import AppContext
from bilioshi.check_auth import check_daily_profile, check_login_profile, parse_nav_profile
from bilioshi.cli import daily as daily_cli
from bilioshi.context import RuntimeContext, use_context
from bilioshi.launch import watch_arguments
from bilioshi.runtime import read_json, write_json
from bilioshi.services import daily_exp, lookup
from desktop.engine import Engine
from desktop.storage import initialize, load_config
from desktop.webui.api import Api

SESSION = "synthetic-merged-session"
CSRF = "synthetic-merged-csrf"


class DailyProfileTests(unittest.TestCase):
    def test_parse_nav_profile_extracts_level_exp_and_lv6_cap(self):
        lv5 = parse_nav_profile(
            {
                "uname": "测试玩家",
                "mid": 10086,
                "face": "https://i0.hdslb.com/bfs/face/test.jpg",
                "money": 42.5,
                "level_info": {"current_level": 5, "current_exp": 12000, "next_exp": 28800},
                "vip_label": {"text": "大会员"},
            }
        )
        self.assertEqual(lv5["level"], 5)
        self.assertEqual(lv5["current_exp"], 12000)
        self.assertEqual(lv5["next_exp"], 28800)
        self.assertFalse(lv5["is_max_level"])
        self.assertEqual(lv5["coins"], 42.5)
        self.assertEqual(lv5["vip_label"], "大会员")

        lv6 = parse_nav_profile(
            {
                "uname": "满级玩家",
                "mid": 10087,
                "level_info": {"current_level": 6, "current_exp": 35000, "next_exp": "--"},
            }
        )
        self.assertTrue(lv6["is_max_level"])
        self.assertEqual(lv6["next_exp"], 0)

    def test_login_profile_contract_stays_minimal_while_daily_profile_is_rich(self):
        body = {
            "code": 0,
            "data": {
                "isLogin": True,
                "uname": "用户A",
                "mid": 88,
                "face": "https://example.invalid/a.jpg",
                "money": 15,
                "level_info": {"current_level": 4, "current_exp": 4500, "next_exp": 10800},
            },
        }
        with patch("bilioshi.check_auth.request_json", return_value=body):
            ok1, _, base = check_login_profile(SESSION, CSRF)
            ok2, _, rich = check_daily_profile(SESSION, CSRF)
        self.assertTrue(ok1 and ok2)
        self.assertEqual(set(base.keys()), {"name", "uid", "face"})
        self.assertEqual(rich["coins"], 15.0)
        self.assertEqual(rich["level"], 4)


class DailyExpServiceTests(unittest.TestCase):
    def test_run_daily_fails_closed_when_ledger_unreadable(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with use_context(RuntimeContext(root)):
                safety.bind_account(SESSION, 123, root=root)
                with patch(
                    "bilioshi.services.daily_exp.check_daily_profile",
                    return_value=(True, "测试", {"uid": 123, "name": "测试", "level": 4, "coins": 20.0}),
                ), patch(
                    "bilioshi.services.daily_exp.query_reward_ledger",
                    return_value={"ok": False, "code": -1, "error": "网络超时", "error_kind": "network"},
                ), patch("bilioshi.services.daily_exp.post_form") as post:
                    res = daily_exp.run_daily_tasks(SESSION, CSRF, do_coin=True, coin_target=5)
                self.assertFalse(res["ok"])
                post.assert_not_called()

    def test_run_daily_executes_watch_share_and_oshi_coin_and_persists_state(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with use_context(RuntimeContext(root)):
                safety.bind_account(SESSION, 123, root=root)
                ledgers = iter(
                    [
                        {"ok": True, "login": True, "watch": False, "share": False, "coins_exp": 0, "coins_count": 0, "earned_exp": 5},
                        {"ok": True, "login": True, "watch": True, "share": True, "coins_exp": 20, "coins_count": 2, "earned_exp": 35},
                    ]
                )
                with patch(
                    "bilioshi.services.daily_exp.check_daily_profile",
                    return_value=(
                        True,
                        "测试",
                        {"uid": 123, "name": "测试", "level": 4, "current_exp": 4500, "next_exp": 10800, "is_max_level": False, "coins": 10.0},
                    ),
                ), patch("bilioshi.services.daily_exp.query_reward_ledger", side_effect=lambda *_: next(ledgers)), \
                     patch(
                         "bilioshi.services.daily_exp.collect_candidate_videos",
                         return_value=[
                             {"aid": 11, "bvid": "BV1", "cid": 101, "title": "视频1", "duration": 90, "source": "oshi"},
                             {"aid": 22, "bvid": "BV2", "cid": 202, "title": "视频2", "duration": 120, "source": "popular"},
                         ],
                     ), \
                     patch("bilioshi.services.daily_exp.post_form", return_value={"code": 0}) as post:
                    res = daily_exp.run_daily_tasks(
                        SESSION, CSRF, do_coin=True, coin_target=2, coin_with_like=True, sleep_fn=lambda *_: None
                    )
                self.assertTrue(res["ok"])
                self.assertEqual(res["confirmed_exp_today"], 35)
                self.assertEqual(post.call_count, 4)  # watch + share + 2 coins
                saved = read_json(root / "state" / "daily-exp.json")
                self.assertEqual(saved["ledger"]["coins_count"], 2)

    def test_coin_daily_budget_reservation_and_rate_classification(self):
        with tempfile.TemporaryDirectory() as folder, use_context(RuntimeContext(Path(folder))):
            root = Path(folder)
            safety.bind_account(SESSION, 123, root=root)
            self.assertEqual(safety.classify({"code": -509, "message": "msg in 1s"})[0], "rate")
            op = safety.operation("https://api.bilibili.com/x/web-interface/coin/add", {"aid": "1"}, "POST")
            self.assertEqual(op["kind"], "coin")
            for _ in range(8):
                self.assertIsNone(safety.reserve(SESSION, op))
            blocked = safety.reserve(SESSION, op)
            self.assertIsNotNone(blocked)
            self.assertEqual(blocked["safety"]["kind"], "budget")

    def test_daily_cli_status_and_run_text_formatting(self):
        out = daily_cli.format_run_result(
            {
                "ok": True,
                "user": {"name": "主播粉", "level": 5, "current_exp": 12000, "next_exp": 28800, "is_max_level": False, "coins": 8},
                "tasks": [
                    {"task": "login", "success": True, "already_done": True, "exp": 0, "message": "今日已登录"},
                    {"task": "watch", "success": True, "submitted": True, "exp": 5, "video": "晚安回放"},
                ],
                "confirmed_exp_today": 10,
                "submitted_gain": 5,
                "pending_settlement": False,
                "days_to_next_level": 10,
            }
        )
        self.assertIn("主播粉", out)
        self.assertIn("10/65", out)


class LookupResolverTests(unittest.TestCase):
    def test_four_stage_resolution_covers_short_url_uid_medal_and_multi_search(self):
        def fake_get(url, headers):
            if "Room/get_info?room_id=777" in url:
                return {"code": 0, "data": {"room_id": 22625025, "short_id": 777, "uid": 672328094, "title": "开播", "live_status": 1}}
            if "Master/info?uid=672328094" in url:
                return {"code": 0, "data": {"room_id": 22625025, "medal_name": "嘉心糖", "info": {"uname": "嘉然今天吃什么"}}}
            if "Room/get_info?room_id=99999" in url:
                return {"code": 1, "message": "not found"}
            if "Master/info?uid=99999" in url:
                return {"code": 0, "data": {"room_id": 0, "info": {"uname": "无房间用户"}}}
            if "wbi/search/type" in url:
                return {
                    "code": 0,
                    "data": {
                        "result": [
                            {"mid": 11, "uname": "<em>星瞳</em>Official", "fans": 500000, "room_id": 21672023},
                            {"mid": 22, "uname": "普通用户", "fans": 120, "room_id": 0},
                        ]
                    },
                }
            return {"code": -1, "message": "unexpected"}

        with patch("bilioshi.services.lookup.get_json", side_effect=fake_get), \
             patch("bilioshi.services.lookup._public_cookies", return_value="buvid3=test"), \
             patch("bilioshi.services.lookup.get_mixin_key", return_value="a" * 32), \
             patch(
                 "bilioshi.services.lookup.request_json",
                 return_value={"code": 0, "data": {"11": {"room_id": 21672023, "title": "歌回", "live_status": 1}}},
             ):
            live_url = lookup.resolve_anchor("https://live.bilibili.com/777")
            self.assertEqual(live_url["type"], "found")
            self.assertEqual(live_url["data"]["room"], 22625025)

            no_room = lookup.resolve_anchor("https://space.bilibili.com/99999")
            self.assertEqual(no_room["type"], "error")
            self.assertEqual(no_room["error_kind"], "no_room")

            multi = lookup.resolve_anchor("星瞳")
            self.assertEqual(multi["type"], "multiple")
            self.assertEqual(multi["data"][0]["room"], 21672023)
            self.assertEqual(multi["data"][0]["live_status"], "直播中")
            self.assertIsNone(multi["data"][1]["room"])

        with patch(
            "bilioshi.services.lookup.all_user_medals",
            return_value=[{"uid": 42, "room": 4200, "name": "牌主", "medal_name": "专属牌", "level": 9}],
        ), patch(
            "bilioshi.services.lookup.resolve_room_meta",
            return_value={"ok": True, "room": 4200, "uid": 42, "name": "牌主", "medal_name": "专属牌", "title": "聊天", "live_status": 0},
        ):
            medal_hit = lookup.resolve_anchor("专属牌", SESSION, CSRF)
            self.assertEqual(medal_hit["type"], "found")
            self.assertEqual(medal_hit["data"]["uid"], 42)


class DesktopMergeIntegrationTests(unittest.TestCase):
    def test_settings_engine_and_api_daily_and_candidate_endpoints(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            initialize(root, [{"room": 7, "uid": 9, "name": "测试主播"}])
            cfg, _ = load_config(root)
            self.assertTrue(cfg["auto_daily_exp"])
            self.assertTrue(cfg["auto_wear"])
            self.assertFalse(cfg["do_coin"])
            self.assertEqual(cfg["coin_target"], 5)

            self.assertIn("--no-wear", watch_arguments({"name": "测试主播"}, {"auto_wear": False}))
            self.assertEqual(
                watch_arguments({"name": "测试主播"}, {"auto_revive": True, "auto_danmaku_intimacy": True, "auto_wear": True}),
                ["--until-offline", "--members", "测试主播"],
            )

            engine = Engine(root, job=Mock())
            ui = Mock()
            api = Api(engine, ui)

            saved = api.save_settings({"auto_daily_exp": False, "do_coin": True, "coin_target": 3, "auto_wear": False})
            self.assertTrue(saved["ok"])
            self.assertEqual(api.snapshot()["settings"]["coin_target"], 3)
            self.assertFalse(api.save_settings({"coin_target": 9})["ok"])

            with patch.object(
                engine.application,
                "run_daily",
                return_value={
                    "ok": True,
                    "day": "2026-11-19",
                    "updated": 1000.0,
                    "user": {"name": "账号甲", "uid": 1, "level": 5, "current_exp": 100, "next_exp": 200, "is_max_level": False, "coins": 5.0},
                    "ledger": {"ok": True, "login": True, "watch": True, "share": True, "coins_exp": 30, "coins_count": 3, "earned_exp": 45},
                    "tasks": [],
                    "submitted_gain": 10,
                },
            ):
                daily_res = api.run_daily()
            self.assertTrue(daily_res["ok"])
            snap = api.snapshot()
            self.assertEqual(snap["daily"]["ledger"]["earned_exp"], 45)
            self.assertEqual(snap["profile"]["level"], 5)

            with patch.object(
                engine.application,
                "resolve_candidates",
                return_value={
                    "type": "multiple",
                    "data": [{"uid": 55, "name": "候选主播", "room": 5500, "room_id": 5500, "fans": "1.2万", "live_status": "未开播"}],
                },
            ):
                resolved = api.resolve_member("候选")
            self.assertTrue(resolved["ok"])
            self.assertEqual(len(resolved["candidates"]), 1)

            added = api.add_member({"uid": 55, "room": 5500, "name": "候选主播"})
            self.assertTrue(added["ok"])
            rooms = {m["room"] for m in read_json(root / "members.json")}
            self.assertEqual(rooms, {7, 5500})

    def test_bilicheckin_migration_imports_non_destructively_once(self):
        with tempfile.TemporaryDirectory() as src_dir, tempfile.TemporaryDirectory() as dst_dir:
            src = Path(src_dir)
            dst = Path(dst_dir)
            src_store = AccountStore(src)
            src_store.upsert(999, "迁移账号")
            acc_root = src_store.ensure_root("uid-999", 999)
            write_json(acc_root / "members.json", [{"name": "收藏主播", "room": 8080, "uid": 1080}])
            write_json(acc_root / "settings.json", {"do_coin": True, "coin_target": 2})
            write_json(acc_root / "credentials.json", {"SESSDATA": "synthetic-bilicheckin", "bili_jct": "synthetic-jct"})
            # Rewrite with bilicheckin envelope marker on non-Windows or plaintext compat check
            if os.name == "nt":
                from bilioshi.secret_store import seal

                sealed = seal({"SESSDATA": "synthetic-bilicheckin", "bili_jct": "synthetic-jct"})
                sealed["format"] = "bilicheckin-protected-credentials"
                (acc_root / "credentials.json").write_text(json.dumps(sealed), encoding="utf-8")

            dst_store = AccountStore(dst)
            dst_store.save(dst_store._empty())
            count = import_bilicheckin_data(dst, dst_store, source_root=src)
            self.assertEqual(count, 1)
            self.assertTrue(dst_store.has("uid-999"))
            self.assertTrue(dst_store.has_credentials("uid-999"))
            self.assertEqual(read_json(dst_store.account_root("uid-999") / "settings.json")["coin_target"], 2)
            # Source untouched & marker prevents re-running
            self.assertTrue((acc_root / "credentials.json").is_file())
            self.assertEqual(import_bilicheckin_data(dst, dst_store, source_root=src), 0)


if __name__ == "__main__":
    unittest.main()
