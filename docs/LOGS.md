# 日志与排查

所有日志都在本机数据目录的 `logs` 下：已有安装在 `%LOCALAPPDATA%\LiveSupport\logs`，全新安装为 `%LOCALAPPDATA%\BiliOshi\logs`。桌面版左侧「查看日志」会直接打开这个目录。

## 文件分工

| 文件 | 写入内容 | 轮转 | 保留 |
| --- | --- | --- | --- |
| `desktop.log` | 主界面进程的标准输出、标准错误与 INFO 及以上日志 | 每次启动超过 2 MB 时改名为 `desktop.previous.log` | 30 天 |
| `supervisor.log` | 守护进程（`--supervisor`）的同类输出 | 同上 | 30 天 |
| `room-<房间号>.log` | 单个直播间的看播进程输出：心跳、弹幕、点赞、任务进度 | 同上 | 30 天 |
| `probe.log` | 直播状态检查子进程的输出 | 同上 | 30 天 |
| `errors.log` | 所有进程的 WARNING 与 ERROR | 1 MB，保留 2 个备份 | — |
| `activity.jsonl` | 结构化事件：`check`、`watch_start/end`、任务、安全保护等，供日报统计 | 达到 8 MB 时归档为 `activity-YYYYMMDD-HHMMSS.jsonl` | 归档保留 30 天 |

每个角色只写自己的文本日志，`errors.log` 只收警告和错误，因此排查问题先看 `errors.log`，再对照相应角色的日志。

## 级别与开关

默认级别为 `INFO`。需要更细的调用过程时：

```powershell
BiliOshi.exe --log-level DEBUG
```

也可设置环境变量 `BILIOSHI_LOG_LEVEL=DEBUG`。级别只影响当前进程及其子进程，恢复默认不写即可。

## 脱敏

日志写入前统一经过 `SafeFormatter` / `SafeStream`：`SESSDATA`、`bili_jct`、Cookie、Authorization、二维码 key、pushplus token 等字段和已登记的密钥值都会替换为 `[REDACTED]`，异常消息与跨行输出同样处理。日志中不会出现可直接使用的登录凭证。

## 归档与汇总

活动日志归档后，日报会自动读取当前文件及归档分段：

```powershell
python scripts/daily_summary.py --hours 24
```

归档分段按修改时间跳过超出统计窗口的文件；显式指定 `--log-file <路径>` 时只读该文件。启动时还会清理 30 天前的房间日志、归档分段和 `.previous.log`，目录大小因此有上限。

## 手工排查顺序

1. `errors.log`：最近的异常与账号保护触发。
2. 对应角色日志：`desktop.log` 看监控循环，`room-<房间号>.log` 看心跳与任务。
3. `activity.jsonl`：按 `type` 过滤结构化事件，例如 `check`、`watch_end`、`safety_hold`。

日志留在本机，不会上传；其中包含主播名、直播间号与账号昵称。发送给他人前请自行检查。
