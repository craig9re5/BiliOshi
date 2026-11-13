# 日志与排查

本机日志分布在**主程序数据根**与**各账号独立数据根**：

- 主程序日志：`%LOCALAPPDATA%\BiliOshi\logs`（旧安装为 `%LOCALAPPDATA%\LiveSupport\logs`），保存 `desktop.log`、`supervisor.log` 与主程序 `errors.log`。
- 各账号日志：`<数据根>\accounts\uid-<mid>\logs`，独立保存该账号的 `probe.log`、`room-<房间号>.log`、`activity.jsonl` 与账号 `errors.log`（旧版兼容单账号模式保存在主目录 `logs\` 下）。

Web 桌面端在「设置 → 日志与诊断反馈」提供「账号日志」「主程序日志」和「导出诊断包」入口；系统托盘菜单同样提供「查看日志」与「导出诊断包」。

## 文件分工

| 文件 | 所在目录 | 写入内容 | 轮转 | 保留 |
| --- | --- | --- | --- | --- |
| `desktop.log` | 主数据根 | 主界面进程与前端错误转发（`WebUI frontend error`）的 INFO 及以上日志 | 每次启动超过 2 MB 时改名为 `desktop.previous.log` | 30 天 |
| `supervisor.log` | 主数据根 | 守护进程（`--supervisor`）的同类输出 | 同上 | 30 天 |
| `room-<房间号>.log` | 账号根（或单账号主根） | 单个直播间的看播进程输出：心跳、弹幕、点赞、任务进度（自动补全时间戳与上下文） | 同上 | 30 天 |
| `probe.log` | 账号根（或单账号主根） | 直播状态与任务检查子进程的输出 | 同上 | 30 天 |
| `errors.log` | 主根与各账号根 | 各进程 WARNING 与 ERROR（跨进程文件锁轮转，避免多进程冲突） | 1 MB，保留 2 个备份 | — |
| `activity.jsonl` | 账号根（或单账号主根） | 结构化事件：`check`、`watch_start/end`、任务、安全保护等，供日报统计 | 达到 8 MB 时归档为 `activity-YYYYMMDD-HHMMSS.jsonl` | 归档保留 30 天 |

日志行格式包含 `[pid=<进程ID> role=<角色> room=<房间号> uid-<mid> <模块>:<行号>]` 上下文，并收集未捕获异常，便于跨进程对照时间线定位根因。

## 级别与开关

默认级别为 `INFO`。需要更细的调用过程时：

```powershell
BiliOshi.exe --log-level DEBUG
```

也可设置环境变量 `BILIOSHI_LOG_LEVEL=DEBUG`。级别只影响当前进程及其子进程，恢复默认不写即可。

## 脱敏与一键诊断包

日志写入前统一经过 `SafeFormatter` / `SafeStream`：`SESSDATA`、`bili_jct`、`LIVE_BUVID`、`buvid*`、Cookie、Authorization、二维码 key、pushplus token、`w_rid` 等字段及其 URL 编码/已登记值都会替换为 `[REDACTED]`。

需要向开发者反馈问题时，可使用**一键导出脱敏诊断包**（导出到 `<主数据根>\exports\bilioshi-diagnostic-YYYYMMDD-HHMMSS.zip`，自动保留最新 10 份）：

- 图形界面：「设置 → 日志与诊断反馈 → 导出诊断包」，支持预览最近报错、复制 Markdown 问题摘要以及一键打开导出文件夹；系统托盘「导出诊断包」可在页面异常时直接生成并打开目录。
- 命令行：`BiliOshi.exe --export-diagnostic` 或 `python tray_app.py --export-diagnostic`（默认匿名化 UID/昵称/主播名/房间号；仅供本机调试时可加 `--no-anonymize`）。

诊断包包含：`environment.json`、`summary.md`、`recent_errors.txt`、`manifest.json`，以及主程序与各账号截取并脱敏后的日志文件（可选含非敏感 `settings.json`、`members.json`、`status.json`、`activity.jsonl` 尾部）。导出流程会强制跳过 `credentials.json`、`pushplus.credentials.json`、`notifications.sqlite3` 等凭证数据库，并将系统用户名路径替换为 `%USERPROFILE%` / `~`。

## 归档与汇总

活动日志归档后，日报会自动读取当前文件及归档分段：

```powershell
python scripts/daily_summary.py --hours 24
```

归档分段按修改时间跳过超出统计窗口的文件；显式指定 `--log-file <路径>` 时只读该文件。启动时还会清理 30 天前的房间日志、归档分段和 `.previous.log`，目录大小因此有上限。

## 手工排查顺序

1. 先查看对应根目录或导出包中的 `errors.log` / `recent_errors.txt`：定位最近的异常、HTTP 错误与账号保护触发。
2. 对照角色日志：`desktop.log` 看监控循环与前端错误，`accounts/uid-<mid>/logs/room-<房间号>.log` 看心跳与任务。
3. `activity.jsonl`：按 `type` 过滤结构化事件，例如 `check`、`watch_end`、`safety_hold`。

原始日志留在本机，不会自动上传；对外分享时请优先使用「导出脱敏诊断包」（开启身份匿名化）。
