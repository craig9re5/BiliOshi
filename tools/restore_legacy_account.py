"""Restore one migrated account's credentials into the legacy install root.

This is an explicit rollback path. It never prints credentials and never
changes the account registry or the account root.
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bilioshi.accounts import AccountStore, UnknownAccount  # noqa: E402
from bilioshi.runtime import data_dir, read_json, save_login, write_json  # noqa: E402


def _backup(root, path):
    if not path.exists():
        return None
    folder = root / "state" / "backup"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    target = folder / f"pre-rollback-credentials-{stamp}.json"
    counter = 1
    while target.exists():
        target = folder / f"pre-rollback-credentials-{stamp}-{counter}.json"
        counter += 1
    target.write_bytes(path.read_bytes())
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description="把某个账号的登录凭证恢复到旧版单账号根目录")
    parser.add_argument("--account", required=True, help="账号 id，例如 uid-123")
    parser.add_argument("--root", default=None, help="安装数据目录；默认使用当前数据目录")
    parser.add_argument("--copy-members", action="store_true", help="同时恢复该账号的关注列表")
    parser.add_argument("--copy-settings", action="store_true", help="同时恢复账号任务设置")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else data_dir()
    store = AccountStore(root)
    try:
        account = store.get(args.account)
        sessdata, bili_jct = store.credentials(account["id"])
    except UnknownAccount as exc:
        print(f"无法恢复：{exc}", file=sys.stderr)
        return 2

    legacy = root / "credentials.json"
    try:
        backup = _backup(root, legacy)
    except OSError as exc:
        print(f"无法备份旧凭证：{type(exc).__name__}", file=sys.stderr)
        return 1
    save_login(sessdata, bili_jct, legacy)

    account_root = store.account_root(account["id"])
    if args.copy_members and (account_root / "members.json").exists():
        write_json(root / "members.json", read_json(account_root / "members.json", []))
    if args.copy_settings and (account_root / "settings.json").exists():
        current = read_json(root / "settings.json", {})
        if not isinstance(current, dict):
            current = {}
        account_settings = read_json(account_root / "settings.json", {})
        if not isinstance(account_settings, dict):
            account_settings = {}
        merged = {**current, **account_settings}
        merged["autostart"] = current.get("autostart", False)
        write_json(root / "settings.json", merged)

    print(
        f"已恢复 {account['name']}（{account['id']}）到旧版登录文件"
        + (f"；旧文件备份：{backup.name}" if backup else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
