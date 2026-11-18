# BiliOshi（ビリ推し）

可配置的 B 站直播应援工具，提供 **Windows 托盘桌面端**与 **Python 命令行（CLI）**。桌面自动挂机、手动补齐与命令行脚本共用同一套业务服务、每日预算与账号异常保护策略。

> 本项目为独立维护基线（早期源自 [XiaoYiWeio/asoul-support](https://github.com/XiaoYiWeio/asoul-support)，保留原始作者署名与 MIT 许可，详见 [NOTICE.md](NOTICE.md)）。BiliOshi 与哔哩哔哩官方无隶属关系。

## 功能与边界

| 模块 | 实现机制与行为边界 |
| --- | --- |
| 开播检测与观看心跳 | 支持稳健（5 分钟）/ 激进（1 分钟）巡检档位；采用 X25Kn `E/X` 链式签名并遵循服务端心跳间隔，定期核验看播任务进度，停滞时提醒并在限次内自动重建心跳链 |
| 粉丝牌点亮与弹幕任务 | 点亮粉丝牌与每日弹幕亲密度独立开关；先读服务端任务缺额再发送，跨进程共享发送间隔（10 秒 / 6 秒）与每日预算（每 UID / 房间 / 日最多 35 次），跨日自动重新核验 |
| 直播点赞 | 默认关闭；复用扫码登录保存的账号与设备会话，使用 WBI 签名分批上报并延迟复查任务进度，接口返回 `code=0` 不单独视为记账成功 |
| 视频与动态互动（CLI） | 按月份或最近天数分页拉取并校验完整性；视频默认仅点赞（`--coin` 投币、`--fav` 收藏需显式开启），动态按日期筛选点赞，查询异常或分页不完整直接返回失败 |
| Windows 托盘工作台 | 默认使用 WebView2 + React 本地离线界面（缺失运行时自动回退 Tk 兼容界面）；支持房号 / 短号 / UID / 链接添加主播、同步粉丝牌、检索筛选、批量管理、单任务补做、开播提醒、开机守护自启与深浅色主题 |
| 多账号管理 | 逐账号隔离保存加密凭证、关注列表、任务策略、尝试额度与运行日志；支持切换查看各账号快照，或免扫码切换当前挂机账号（同一时间仅运行一个挂机账号） |
| 粉丝牌成长记录 | 按账号与 UTC+8 自然日记录关注主播今日及近 7 日亲密度涨幅（保留 90 天）；严格区分有效 `0`、尚未同步与未记录，缺失样本不补 `0` |
| 异常保护与脱敏诊断 | 遇到频控自动冷却，触发验证拦截、禁言或写请求结果未知时立即停止写操作并保留当日预算，需核对后确认恢复；日志全程脱敏，支持一键导出匿名化诊断压缩包 |

每日任务进度以 B 站服务端返回值为准；接口请求成功不保证亲密度实时结算，项目不承诺固定收益，也不提供绕过平台风控、伪造设备标识或多账号并发刷量能力。

## Windows 桌面端

### 环境要求

- **操作系统**：Windows 10 / 11。
- **界面运行时**：默认使用 Microsoft Edge WebView2 Runtime；未安装时自动回退至内置 Tk 兼容界面，也可通过 `--tk` 手动指定。前端资源随程序离线打包，不依赖外部 CDN；源码已包含预编译前端产物，直接运行无需安装 Node.js。

### 安装与启动

**方式一：运行或安装打包版（无需安装 Python）**

解压发行包后可直接双击 `BiliOshi.exe` 运行，或通过安装脚本部署到 `%LOCALAPPDATA%\Programs\BiliOshi` 并注册系统登录守护自启任务：

```powershell
powershell -ExecutionPolicy Bypass -File .\Install-Desktop.ps1 -Activate
```

**方式二：从源码运行（需 CPython 3.11+）**

```powershell
git clone https://github.com/craig9re5/BiliOshi.git
cd BiliOshi
python -m pip install -r requirements-desktop.txt
python tray_app.py --show
```

### 快速上手

1. **扫码登录**：进入左侧「账号」页点击「添加账号」，使用 B 站 App 扫码并在手机端确认，无需浏览器插件或手动复制 Cookie。
2. **添加监控主播**：在「直播总览」点击「添加主播」（支持输入房间号、短号、UID 或直播间链接解析）或「同步粉丝牌」批量导入；新增账号的关注列表默认为空。
3. **调整策略与外观**：在「设置」中按账号开关点亮粉丝牌、弹幕任务、直播点赞、开播通知与运行模式（稳健 / 激进），或切换本机界面主题（跟随系统及白天默认主题、纸白、暖纸白、雾青灰、墨青暗）。关闭窗口后程序继续常驻系统托盘；完全退出请使用侧栏底部或托盘菜单中的「退出」。

### 常用启动参数

以下参数同时适用于 `BiliOshi.exe` 与 `python tray_app.py`：

```powershell
python tray_app.py --show                  # 启动或唤起主窗口
python tray_app.py --tk --show             # 使用 Tk 兼容界面启动
python tray_app.py --login                 # 直接打开 B 站扫码登录
python tray_app.py --command pause         # 控制运行中实例：pause | resume | check | show | exit
python tray_app.py --export-diagnostic     # 离线导出脱敏且默认匿名化的诊断包 (.zip)
python tray_app.py --log-level DEBUG       # 临时以 DEBUG 级别输出日志（或设 BILIOSHI_LOG_LEVEL=DEBUG）
```

工作台交互、单房间重连、看播停滞核验与独立守护机制详见 [DESKTOP.md](DESKTOP.md)。

## Python 命令行

核心模块仅依赖 Python 标准库，支持 **Python 3.9+**。首次运行可执行 `setup_local_cookie.py` 录入并验证登录凭证（终端输入不回显）；如需在命令行启用直播点赞，可再运行 `setup_live_like_cookie.py` 保存匹配的请求上下文。

```powershell
# 录入并检查登录凭证
python setup_local_cookie.py
python scripts/check_auth.py

# 开播检测、持续观看心跳与单轮直播点赞（可通过 --mode stable|aggressive 指定档位）
python scripts/heartbeat.py --check-only
python scripts/heartbeat.py --until-offline
python scripts/heartbeat.py --likes-only

# 粉丝牌点亮与弹幕签到（--count 为本轮尝试上限，仍按任务缺额发送并受每日预算约束）
python scripts/checkin.py --live-only

# 视频与动态互动（视频默认仅点赞，投币 --coin 与收藏 --fav 需显式指定）
python scripts/videos.py --days 7
python scripts/videos.py --days 7 --coin --fav
python scripts/dynamics.py --days 7

# 查看近 24 小时运行汇总与本机账号保护状态
python scripts/daily_summary.py --hours 24
python scripts/heartbeat.py --safety-status
```

可选将核心包安装到当前 Python 环境，直接使用命令行入口（旧版 `asoul-*` 命令仍作为兼容别名保留）：

```powershell
python -m pip install .
bilioshi-heartbeat --help
```

安装后可使用 `bilioshi-heartbeat`、`bilioshi-checkin`、`bilioshi-videos`、`bilioshi-dynamics`、`bilioshi-summary`。所有命令均支持 `--help` 查看详细参数，以及 `--json` 输出结构化结果。

## 数据存储与凭证安全

- **本机数据目录**：默认位于 `%LOCALAPPDATA%\BiliOshi`（Windows，兼容已有 `%LOCALAPPDATA%\LiveSupport` 安装目录）或 `~/.config/bilioshi`（Linux / macOS，遵循 `XDG_CONFIG_HOME`），可通过环境变量 `BILIOSHI_APP_DATA` 覆盖，不写入源码目录。
- **安装根与账号根分离**：桌面端在主数据目录下维护 `state/accounts.json` 注册表、守护进程状态与主日志，各账号的凭证、关注列表、策略与状态独立存放在 `accounts/uid-<mid>/`；命令行工具默认读写主数据目录下的配置与 `credentials.json`。
- **加密凭据存储**：Windows 使用当前用户范围的 DPAPI（`UI_FORBIDDEN`）加密保存凭证；macOS / Linux 保存登录态需安装 `python -m pip install "bilioshi[secure-store]"` 并启用系统 Keychain 或 Secret Service。无可用安全存储时直接拒绝落盘，不回退到明文。
- **零前端凭证与自动脱敏**：WebView2 渲染层只接收 Python 桥接发布的公开快照与本机二维码图像，不接触 Cookie、扫码密钥，也不直接访问 B 站接口；日志输出与诊断包导出均自动脱敏。

## 开发与构建

```powershell
# 运行离线契约与回归测试（禁止真实网络访问）
python tools/offline_test.py

# 校验模块分层与依赖方向（核心层 bilioshi 不导入 desktop 或 scripts）
python tools/check_architecture.py

# 扫描工作区文件与本地待发布提交中的敏感字段、个人路径及违规产物
python tools/scan_public.py

# 修改 desktop/webui/assets/js/*.jsx 后重编译前端资源（需 Node.js 22+；--check 无需 Node）
python tools/build_webui.py
python tools/build_webui.py --check

# Windows 桌面端界面测试（Tk 冒烟测试 / WebView2 隔离合成数据自检）
python tools/desktop_smoke.py
python tray_app.py --web-diagnostic build/webui-native-check.json

# 打包 Windows 单文件桌面程序（输出 dist/onefile/BiliOshi.exe 与 build-info.json）
powershell -ExecutionPolicy Bypass -File .\build_desktop.ps1 -Mode onefile
```

主分支推送自动运行离线 CI；仓库中的账号操作工作流（`.github/workflows/daily.yml`）仅支持手动触发，需在自有仓库配置相应 Secrets。完整发版校验流程见 [docs/RELEASING.md](docs/RELEASING.md)。

## 文档索引

- **桌面端与功能说明**：[桌面端详细指南](DESKTOP.md) · [扫码登录](docs/QR_LOGIN.md) · [多账号管理](docs/MULTI_ACCOUNT.md) · [粉丝牌成长记录](docs/GROWTH.md) · [运行模式与桌面守护](docs/OPERATING_MODES.md) · [直播点赞实现与验收](docs/LIVE_LIKES.md) · [日志与诊断排查](docs/LOGS.md)
- **架构、安全与工程规范**：[架构与调用关系](ARCHITECTURE.md) · [Web 桌面开发](docs/WEB_UI.md) · [账号异常保护与凭证存储](docs/ACCOUNT_SAFETY.md) · [安全与漏洞报告](SECURITY.md) · [贡献指南](CONTRIBUTING.md) · [品牌与视觉规范](docs/BRAND.md)
- **历史与演进记录**：[重构审计与计划](docs/REFACTOR_PLAN.md) · [重构结果与验证](docs/REFACTOR_RESULTS.md) · [变更日志](CHANGELOG.md)

## 许可证

代码采用 [MIT License](LICENSE) 发布。项目来源与归属说明见 [NOTICE.md](NOTICE.md)，桌面端打包依赖许可证清单见 [THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md)。
