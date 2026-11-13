"""BiliOshi desktop entry point. Worker modes reuse the existing protocol."""

import argparse
import logging
import os
from pathlib import Path
import platform
import sys

from desktop.storage import data_dir, initialize, send_command
from bilioshi.members import MEMBERS
from bilioshi.runtime import APP_VERSION
from bilioshi import logging_setup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=int)
    parser.add_argument("--supervisor", action="store_true", help="独立守护桌面进程")
    parser.add_argument("--start", action="store_true", help="守护进程记录启动意图")
    parser.add_argument("--supervised", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--probe")
    parser.add_argument("--skip-actions", action="store_true")
    parser.add_argument("--watch-only", action="store_true")
    parser.add_argument("--command", choices=["pause", "resume", "check", "show", "exit"])
    parser.add_argument("--show", action="store_true")
    parser.add_argument("--tk", action="store_true", help="使用兼容的 Tk 桌面界面")
    parser.add_argument("--login", action="store_true", help="打开 B 站扫码登录")
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--export-diagnostic", action="store_true", help="生成一键脱敏诊断包 (.zip)")
    parser.add_argument("--no-anonymize", action="store_true", help="导出诊断包时保留原始账号/主播 ID（仅调试使用）")
    parser.add_argument("--web-diagnostic", type=Path, metavar="REPORT", help="用隔离数据验收 WebView2 窗口")
    parser.add_argument("--diagnostic-screenshot", type=Path, metavar="PNG")
    parser.add_argument("--protect-credentials", action="store_true")
    parser.add_argument("--legacy-credentials")
    parser.add_argument("--log-level", choices=sorted(logging_setup.LEVELS), metavar="LEVEL",
                        help="日志详细程度，默认 INFO，也可用 BILIOSHI_LOG_LEVEL 设置")
    args = parser.parse_args()
    if args.web_diagnostic:
        from desktop.webui.diagnostics import run

        return run(args.web_diagnostic, args.diagnostic_screenshot)
    try:
        root = data_dir()
        initialize(root, MEMBERS)
    except Exception as exc:
        if not (args.command or args.worker or args.probe or args.supervisor):
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None, f"初始化数据目录失败（{type(exc).__name__}）：{exc}", "BiliOshi", 0x10
            )
        else:
            sys.stderr.write(f"Failed to initialize data directory: {exc}\n")
        return 1
    if args.protect_credentials:
        from bilioshi.runtime import protect_credentials, write_json

        write_json(
            root / "credential-migration.json", protect_credentials(root, args.legacy_credentials)
        )
        return 0
    if args.export_diagnostic:
        import json as _json
        from bilioshi.diagnostics_bundle import export_diagnostic_bundle

        result = export_diagnostic_bundle(
            root,
            anonymize=not args.no_anonymize,
            include_state=True,
            ui_mode="cli",
        )
        print(_json.dumps({k: v for k, v in result.items() if k not in ("summary_markdown", "recent_errors")},
                          ensure_ascii=False, indent=2))
        return 0
    if args.command:
        from desktop.windows import Mutex, instance_name

        if args.command == "exit":
            from desktop.supervisor import request_stop

            request_stop(root)
        active = Mutex(instance_name(root))
        if active.acquired:
            active.close()
            return 0 if args.command == "exit" else 2
        send_command(root, args.command)
        active.close()
        return 0
    # No-console executables have no usable standard streams, even with redirection.
    role = "supervisor" if args.supervisor else "probe" if args.probe else "worker" if args.worker else "desktop"
    logging_setup.setup(root, role, args.worker, level=args.log_level)
    logging.info(
        "Startup version=%s os=%s python=%s frozen=%s tk_flag=%s mode=%s root=%s cwd=%s credentials_present=%s",
        APP_VERSION,
        platform.platform(),
        platform.python_version(),
        bool(getattr(sys, "frozen", False)),
        bool(args.tk),
        role,
        root,
        os.getcwd(),
        (root / "credentials.json").exists(),
    )
    if args.supervisor:
        try:
            from desktop.supervisor import run

            return run(root, start=args.start)
        except Exception:
            logging.exception("Supervisor failed")
            return 1
    if args.probe:
        try:
            from desktop.worker import probe

            return probe(root, Path(args.probe))
        except Exception:
            logging.exception("Probe failed")
            return 1
    if args.worker:
        try:
            from desktop.worker import watch

            return watch(root, args.worker, args.skip_actions, watch_only=args.watch_only)
        except Exception:
            logging.exception("Worker failed room=%s", args.worker)
            return 1
    if args.diagnostic:
        from desktop.ui import icon_image
        from desktop.storage import write_json, load_config
        from desktop.windows import Job
        import tkinter as tk
        import qrcode
        from qrcode.image.pil import PilImage

        qr = qrcode.make("https://www.bilibili.com/", image_factory=PilImage)

        config, members = load_config(root)
        window = tk.Tk()
        window.withdraw()
        window.update()
        window.destroy()
        job = Job()
        job.close()
        from desktop.webui.window import available as web_available
        web_assets = Path(__file__).resolve().parent / "desktop" / "webui" / "assets"
        frontend_ready = all((web_assets / name).is_file() for name in (
            "index.html", "style.css", "vendor/react.js", "vendor/react-dom.js",
            "js/app.js", "js/bridge.js", "js/overview.js", "js/settings.js", "js/dialogs.js",
            "js/accounts.js", "js/growth.js", "js/theme.js",
        ))
        write_json(
            root / "diagnostic.json",
            {
                "ok": frontend_ready,
                "version": APP_VERSION,
                "frozen": bool(getattr(sys, "frozen", False)),
                "members": len(members),
                "icon": icon_image().size,
                "qr": qr.size,
                "desktop": {"renderer": "webview2" if web_available() else "tk",
                            "web_assets": frontend_ready},
                "daily_notifications": {"available": False},
            },
        )
        return 0
    from desktop.windows import Mutex, instance_name

    mutex = Mutex(instance_name(root))
    if not mutex.acquired:
        send_command(root, "login" if args.login else "show")
        mutex.close()
        return 0
    try:
        from desktop.supervisor import ensure_supervisor, register_desktop

        if register_desktop(root, tk=args.tk, supervised=args.supervised) is None:
            return 0
        ensure_supervisor(root)
        from desktop.host import AccountHost
        from bilioshi.account_migration import ensure_account_store

        migration = ensure_account_store(root)
        if migration.legacy_mode:
            logging.warning("Running in legacy single-account mode: %s", migration.reason)
        host = AccountHost(root, migration.store)
        # First run opens the login screen; later launches stay in the tray so an
        # update never steals focus from whatever the user is doing.
        signed_in = bool(migration.store.accounts()) and any(
            migration.store.has_credentials(row["id"]) for row in migration.store.accounts()
        )
        show = args.show or args.login or not signed_in
        from desktop.webui.window import available as web_available

        if not args.tk and web_available():
            from desktop.webui.window import WebHost

            ui = WebHost(host, show=show)
            ui.run(show=show, login=args.login)
        else:
            from desktop.ui import TrayUI

            # The compatibility Tk layer shows only the current account.
            host.start()
            engine = host.active_engine()
            if engine is None:
                from desktop.engine import Engine

                engine = Engine(root)
                engine.start()
            ui = TrayUI(engine, show=show, commands_root=root)
            if args.login:
                ui.root.after_idle(lambda: ui.open_settings(focus_auth=True, scan=True))
            try:
                ui.run()
            finally:
                host.close()
    except Exception:
        logging.exception("Desktop startup failed")
        import ctypes

        ctypes.windll.user32.MessageBoxW(
            None, f"启动失败，请查看 {root / 'logs' / 'errors.log'}", "BiliOshi", 0x10
        )
        return 1
    finally:
        mutex.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
