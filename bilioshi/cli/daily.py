"""CLI for main-site Daily EXP tasks (login + watch + share + optional coin)."""

import argparse
import json
import sys

from ..account_migration import ensure_account_store
from ..application import AppContext
from ..credentials import load_saved
from ..redaction import redact
from ..runtime import data_dir
from ..services.daily_exp import check_daily_status, run_daily_tasks


def _active_app_root():
    root = data_dir()
    store = ensure_account_store(root).store
    if store.active_id and store.has(store.active_id):
        return store.account_root(store.active_id)
    return root


def format_status(snapshot: dict) -> str:
    if not snapshot.get("ok"):
        return f"❌ {snapshot.get('error', '无法读取状态')}"
    u = snapshot["user"]
    l = snapshot["ledger"]
    exp_text = f"{u['current_exp']} (已满级)" if u.get("is_max_level") else f"{u['current_exp']}/{u['next_exp']}"
    lines = [
        f"📊 {u['name']} (Lv{u['level']})  经验：{exp_text}  硬币：{u['coins']}",
        "",
        f"  🔑 每日登录：{'✅ 已完成 (+5 经验)' if l['login'] else '⏳ 待更新'}",
        f"  ▶️  观看视频：{'✅ 已完成 (+5 经验)' if l['watch'] else '❌ 未完成'}",
        f"  🔗 分享视频：{'✅ 已完成 (+5 经验)' if l['share'] else '❌ 未完成'}",
        f"  🪙 视频投币：{l['coins_exp']}/50 经验 ({l['coins_count']}/5 枚)",
        "",
        f"📈 今日经验：{l['earned_exp']}/65 经验",
    ]
    days = snapshot.get("days_to_next_level")
    if u.get("is_max_level"):
        lines.append("🎉 已达到最高等级 Lv6")
    elif days is not None and days > 0:
        lines.append(f"🎯 按当前设置预计距离 Lv{u['level'] + 1} 约需 {days} 天")
    return "\n".join(lines)


def format_run_result(result: dict) -> str:
    if not result.get("ok") and "tasks" not in result:
        return f"❌ {result.get('error', '任务执行失败')}"
    u = result["user"]
    exp_text = f"{u['current_exp']} (已满级)" if u.get("is_max_level") else f"{u['current_exp']}/{u['next_exp']}"
    lines = [
        f"📊 B 站每日经验签到 — {u['name']} (Lv{u['level']})",
        f"   经验：{exp_text}  硬币余额：{u['coins']}",
        "",
    ]
    labels = {
        "login": "🔑 每日登录",
        "watch": "▶️  观看视频",
        "share": "🔗 分享视频",
        "coin": "🪙 视频投币",
    }
    for item in result.get("tasks", []):
        label = labels.get(item.get("task", ""), item.get("task", ""))
        if item.get("success"):
            if item.get("skipped"):
                lines.append(f"  ⏭️  {label}  {item.get('message', '')}")
            elif item.get("already_done"):
                lines.append(f"  ✅ {label}  ({item.get('message', '今日已完成')})")
            elif item.get("task") == "coin":
                lines.append(f"  ✅ {label}  已投 {item['count']}/{item['target']} 枚 (+{item['exp']} 经验)")
            else:
                video = f" ({item['video'][:24]})" if item.get("video") else ""
                exp = f" +{item['exp']} 经验" if item.get("exp") else ""
                lines.append(f"  ✅ {label}{exp}{video}")
        else:
            err = item.get("error") or item.get("message") or "执行失败"
            if item.get("partial"):
                lines.append(f"  ⚠️  {label}  部分完成 {item['count']}/{item['target']} 枚：{err}")
            else:
                lines.append(f"  ❌ {label}  {err}")

    lines.append("")
    lines.append(f"📒 今日经验：{result['confirmed_exp_today']}/65 经验")
    if result.get("pending_settlement"):
        lines.append(f"⏳ 本次新增 +{result['submitted_gain']} 经验，正在等待 B 站结算")
    if u.get("is_max_level"):
        lines.append("🎉 已达到最高等级 Lv6")
    elif result.get("days_to_next_level") is not None and result["days_to_next_level"] > 0:
        lines.append(f"🎯 按当前设置距离 Lv{u['level'] + 1} 预计还需约 {result['days_to_next_level']} 天")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="B 站每日经验签到（默认不消耗硬币）",
    )
    parser.add_argument("--status", action="store_true", help="仅查看今日经验与等级进度")
    parser.add_argument("--do-coin", action="store_true", help="显式启用投币任务（默认关闭以保护硬币）")
    parser.add_argument("--coin", type=int, default=None, help="目标投币枚数（1–5；传入 >0 时自动启用投币）")
    parser.add_argument("--popular-only", action="store_true", help="投币仅从热门视频抽取（默认优先关注主播）")
    parser.add_argument("--coin-with-like", action="store_true", help="投币时顺带点赞（默认关闭）")
    parser.add_argument("--json", action="store_true", help="输出脱敏后的 JSON 结果")
    args = parser.parse_args(argv)

    do_coin = bool(args.do_coin or (args.coin is not None and args.coin > 0))
    coin_target = max(0, min(5, args.coin if args.coin is not None else 5))
    if coin_target == 0:
        do_coin = False

    root = _active_app_root()
    app = AppContext(root)
    saved = load_saved([root / "credentials.json"])
    if not saved:
        msg = "尚未配置登录凭证，请先在桌面端扫码登录"
        if args.json:
            print(json.dumps({"ok": False, "error": msg, "error_kind": "auth"}, ensure_ascii=False, indent=2))
        else:
            print(f"❌ {msg}", file=sys.stderr)
        return 2

    from ..context import use_context
    from ..members import load_members

    with use_context(app.runtime):
        if args.status:
            res = check_daily_status(
                saved["SESSDATA"], saved["bili_jct"], do_coin=do_coin, coin_target=coin_target
            )
            if args.json:
                print(json.dumps(redact(res), ensure_ascii=False, indent=2))
            else:
                print(format_status(res))
            if not res.get("ok"):
                return 2 if res.get("error_kind") == "auth" else 1
            return 0

        res = run_daily_tasks(
            saved["SESSDATA"],
            saved["bili_jct"],
            do_coin=do_coin,
            coin_target=coin_target,
            prefer_medals=not args.popular_only,
            coin_with_like=args.coin_with_like,
            members=load_members(root),
        )

    if args.json:
        print(json.dumps(redact(res), ensure_ascii=False, indent=2))
    else:
        print(format_run_result(res))

    if not res.get("ok"):
        kind = res.get("error_kind")
        if kind == "auth":
            return 2
        if kind == "safety":
            return 3
        return 1
    return 0
