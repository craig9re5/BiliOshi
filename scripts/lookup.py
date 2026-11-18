"""CLI entry point for resolving streamer UID, room ID, or search candidates."""

import argparse
import json
import sys
from pathlib import Path

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bilioshi.account_migration import ensure_account_store
from bilioshi.credentials import load_saved
from bilioshi.redaction import redact
from bilioshi.runtime import data_dir
from bilioshi.services.lookup import resolve_anchor


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="查找 B 站主播直播间信息")
    parser.add_argument("query", help="房间号、短号、UID、昵称或链接")
    parser.add_argument("--limit", type=int, default=5, help="最多返回的候选人数")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)

    root = data_dir()
    store = ensure_account_store(root).store
    acc_root = store.account_root(store.active_id) if store.active_id and store.has(store.active_id) else root
    saved = load_saved([acc_root / "credentials.json"]) or {}
    res = resolve_anchor(
        args.query,
        saved.get("SESSDATA", ""),
        saved.get("bili_jct", ""),
        limit=max(1, min(15, args.limit)),
    )
    if args.json:
        print(json.dumps(redact(res), ensure_ascii=False, indent=2))
        return 0 if res.get("type") != "error" else 1
    if res.get("type") == "found":
        d = res["data"]
        medal = f"  粉丝牌：{d['medal_name']}" if d.get("medal_name") else ""
        print(f"✅ {d['name']}  房间 {d['room']}  UID {d['uid']}  [{d.get('live_status', '待更新')}]{medal}")
        return 0
    if res.get("type") == "multiple":
        print(f"🔎 找到 {len(res['data'])} 位候选主播：")
        for item in res["data"]:
            room_txt = f"房间 {item['room']}" if item.get("room") else item.get("live_status", "无直播间")
            print(f"  - {item['name']}  UID {item['uid']}  {room_txt}  粉丝 {item.get('fans', '未知')}")
        return 0
    print(f"❌ {res.get('message', '未找到主播')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    from bilioshi.entrypoints import run_cli

    raise SystemExit(run_cli(main))
