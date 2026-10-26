"""Explicit CLI for the same daily summary service used by the desktop."""

import argparse
import getpass
import json
from ..runtime import data_dir
from . import settings
from .service import DailyNotifications


def main():
    parser = argparse.ArgumentParser(description="BiliOshi 每日手机总结")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true")
    group.add_argument("--preview", action="store_true", help="只读查询，不发送")
    group.add_argument("--configure", action="store_true", help="交互输入专用消息 Token")
    group.add_argument("--test", action="store_true", help="明确发送一条合成测试消息")
    group.add_argument("--run", action="store_true", help="运行每日总结调度器")
    group.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    from . import AVAILABLE, UNAVAILABLE_REASON
    if not AVAILABLE and (args.configure or args.test or args.run or args.resume):
        print(UNAVAILABLE_REASON)
        return 1
    root = data_dir()
    service = DailyNotifications(root)
    try:
        if args.configure:
            config = settings.load(root)
            token = getpass.getpass("PushPlus 专用消息 Token（留空保留）：").strip() or None
            config["summary_at"] = input("每日发送时间 HH:MM（UTC+8，默认23:50）：").strip() or "23:50"
            config["enabled"] = True
            settings.save(root, config, token)
            print("已保存并启用；运行 BiliOshi 桌面或本命令 --run 后按时发送。")
        elif args.run:
            service.run()
        elif args.preview:
            print(json.dumps(service.preview(), ensure_ascii=False, indent=2))
        elif args.test:
            print(service.queue_test())
            # This is an explicit test; do not also generate a scheduled daily report.
            from .outbox import Outbox
            from . import transport
            from ..runtime import FileLock
            with FileLock(root / "locks/daily-notification.lock") as lease:
                if lease.acquired:
                    box = Outbox(root)
                    message = box.claim(service.clock(), kind="test")
                    if message:
                        box.finish(message, transport.send(settings.token(root), message), service.clock())
            print(json.dumps(service.status(), ensure_ascii=False, indent=2))
        elif args.resume:
            print(service.resume())
        else:
            print(json.dumps(service.status(), ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        service.stop()
    except Exception as exc:
        print(f"操作失败（{type(exc).__name__}），请检查本机配置。")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
