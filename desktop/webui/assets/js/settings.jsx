/* Settings use the same vocabulary as the overview; changes apply through Python. */

const { useState, useEffect, useLayoutEffect, useRef } = React;
const { Icon, relativeTime, absoluteTime, numberLabel } = window;

const Switch = ({ checked, onChange, label, disabled }) => (
  <button type="button" className="switch" role="switch" aria-checked={Boolean(checked)}
    aria-label={label} disabled={disabled} onClick={() => onChange(!checked)} />
);

const SettingRow = ({ name, desc, className = "", children }) => (
  <div className={`setting${className ? ` ${className}` : ""}`}><div className="setting-text"><div className="setting-name">{name}</div>
    {desc && <div className="setting-desc">{desc}</div>}</div>{children}</div>
);

/* A compact trigger plus a themed menu. The native select rendered its own
   system popup, which did not follow the card surfaces or spacing. */
const Choice = ({ value, options, onChange, label, disabled }) => {
  const [open, setOpen] = useState(false);
  const [flipUp, setFlipUp] = useState(false);
  const [menuStyle, setMenuStyle] = useState(null);
  const root = useRef(null);
  const trigger = useRef(null);
  const menu = useRef(null);
  const selected = Math.max(0, options.findIndex((option) => option.value === value));

  useLayoutEffect(() => {
    if (!open || !trigger.current) return undefined;
    const updatePosition = () => {
      if (!trigger.current) return;
      const triggerRect = trigger.current.getBoundingClientRect();
      if (triggerRect.bottom < 0 || triggerRect.top > window.innerHeight) {
        setOpen(false);
        return;
      }
      const estimatedHeight = menu.current?.offsetHeight || (options.length * 29 + 10);
      const spaceBelow = window.innerHeight - triggerRect.bottom;
      const shouldFlip = spaceBelow < estimatedHeight + 14 && triggerRect.top > estimatedHeight + 14;
      setFlipUp(shouldFlip);
      const width = Math.max(triggerRect.width, 112);
      const left = Math.max(8, Math.min(triggerRect.left, window.innerWidth - width - 8));
      setMenuStyle(
        shouldFlip
          ? { position: "fixed", left, width, bottom: Math.max(8, window.innerHeight - triggerRect.top + 5), top: "auto" }
          : { position: "fixed", left, width, top: Math.min(window.innerHeight - 16, triggerRect.bottom + 5), bottom: "auto" }
      );
    };
    updatePosition();
    window.addEventListener("scroll", updatePosition, true);
    window.addEventListener("resize", updatePosition);
    return () => {
      window.removeEventListener("scroll", updatePosition, true);
      window.removeEventListener("resize", updatePosition);
    };
  }, [open, options.length]);

  useEffect(() => {
    if (!open) return undefined;
    const dismiss = (event) => {
      if (!root.current?.contains(event.target) && !menu.current?.contains(event.target)) {
        setOpen(false);
      }
    };
    const escape = (event) => {
      if (event.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    const focus = window.setTimeout(() => {
      menu.current?.querySelector('[aria-selected="true"]')?.focus();
    }, 0);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
      window.clearTimeout(focus);
    };
  }, [open]);

  const moveFocus = (event, index) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const nodes = Array.from(menu.current?.querySelectorAll(".choice-option") || []);
    if (!nodes.length) return;
    const next = event.key === "Home" ? 0 : event.key === "End" ? nodes.length - 1
      : (index + (event.key === "ArrowDown" ? 1 : -1) + nodes.length) % nodes.length;
    nodes[next]?.focus();
  };

  const menuNode = open && (
    <div
      className={`choice-menu${flipUp ? " flip-up" : ""}`}
      role="listbox"
      aria-label={label}
      ref={menu}
      style={menuStyle || { position: "fixed", visibility: "hidden" }}
    >
      {options.map((option, index) => (
        <button type="button" key={option.value} className="choice-option" role="option"
          data-value={option.value} aria-selected={option.value === value}
          onKeyDown={(event) => moveFocus(event, index)}
          onClick={() => {
            setOpen(false);
            if (option.value !== value) onChange(option.value);
            trigger.current?.focus();
          }}>
          <span>{option.label}</span>
          {option.value === value && <Icon name="check" size={12} />}
        </button>
      ))}
    </div>
  );

  return (
    <div className={`choice ${open ? "open" : ""}`} ref={root}>
      <button type="button" className="choice-button" ref={trigger} aria-haspopup="listbox"
        aria-expanded={open} aria-label={label} disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}>
        <span className="choice-label">{options[selected]?.label}</span>
        <Icon name="chevron" size={12} />
      </button>
      {menuNode && (typeof ReactDOM !== "undefined" && ReactDOM.createPortal
        ? ReactDOM.createPortal(menuNode, document.body)
        : menuNode)}
    </div>
  );
};

/* 暖杏灰（apricot）暂时灰度下线，置 enabled: true 即可重新开放选项。 */
const ALL_THEME_CHOICES = [
  { key: "system", name: "跟随系统", hint: "随系统深浅外观切换" },
  { key: "white", name: "纸白", hint: "中性纸面", day: true },
  { key: "paper", name: "暖纸白", hint: "温和纸感", day: true },
  { key: "mist", name: "雾青灰", hint: "清爽青灰", day: true },
  { key: "apricot", name: "暖杏灰", hint: "温暖柔和", day: true, enabled: false },
  { key: "dark", name: "墨青暗", hint: "夜间深色" }
];
const THEME_CHOICES = ALL_THEME_CHOICES.filter((item) => item.enabled !== false);
const DAY_THEME_CHOICES = THEME_CHOICES.filter((item) => item.day);
/* 运行模式切换（稳健 / 激进）暂时灰度下线，置 ENABLE_RUN_MODE_SWITCH = true 即可重新开放选项。 */
const ENABLE_RUN_MODE_SWITCH = false;

const useSystemDark = () => {
  const [dark, setDark] = useState(() =>
    typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event) => setDark(Boolean(event.matches));
    setDark(Boolean(media.matches));
    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", onChange);
      return () => media.removeEventListener("change", onChange);
    }
    media.addListener(onChange);
    return () => media.removeListener(onChange);
  }, []);
  return dark;
};

const ThemeOptions = ({
  choices = THEME_CHOICES, value, onChange, systemDark, dayThemeName,
  ariaLabel = "界面主题", isDayPicker = false
}) => (
  <div className="theme-options" role="group" aria-label={ariaLabel}>
    {choices.map((item) => {
      const active = item.key === value;
      const hint = item.key === "system"
        ? `当前${systemDark ? "深色 · 墨青暗" : `浅色 · ${dayThemeName}`}`
        : item.hint;
      const dataProps = isDayPicker ? { "data-day-theme": item.key } : { "data-theme": item.key };
      return <button type="button" key={item.key} className="theme-option" {...dataProps}
        aria-pressed={active} title={`${item.name} · ${hint}`}
        onClick={() => onChange(item.key)}>
        <span className={`theme-chip ${item.key}`} aria-hidden="true">
          {item.key === "system" && <Icon name="contrast" size={12} stroke={1.7} />}
        </span>
        <span className="theme-name">{item.name}</span>
        {active && <Icon name="check" size={11} />}
      </button>;
    })}
  </div>
);

const SettingsPage = ({
  settings, onSetting, onSettingsBatch, pendingSettings, theme = "system", onTheme, dayTheme = "white", onDayTheme,
  tab = "account", onTab, scope, scopeAvatar, onSetRunning, onOpenLogin, onOpenSafety,
  onLogs, onHostLogs, onDiagnostics, version, update, onCheckUpdate, onApplyUpdate, updateBusy, busy
}) => {
  const systemDark = useSystemDark();
  const disabled = (key) => pendingSettings.has(key);
  const runMode = settings.run_mode || "stable";
  const coinEnabled = Boolean(settings.do_coin);
  const coinTarget = coinEnabled ? Math.max(1, Math.min(5, Number(settings.coin_target ?? 5))) : 0;
  const dayThemeName = (DAY_THEME_CHOICES.find((item) => item.key === dayTheme) || DAY_THEME_CHOICES[0]).name;
  const activeTab = tab === "app" ? "app" : "account";
  const scopeState = scope && window.accountStateLabel ? window.accountStateLabel(scope) : null;
  const scopeNeedsLogin = Boolean(scope && (!scope.signed_in || scope.status === "needs_login"));
  const scopeBlocked = Boolean(scope && (scope.status === "blocked" || scope.safety?.blocked));
  const scopeRunning = Boolean(scope && (scope.engine_active || scope.running));
  const updateState = update?.status || "idle";
  const updateChecking = Boolean(updateBusy || ["checking", "downloading", "verifying", "applying"].includes(updateState));
  const updateDesc = updateState === "checking"
    ? "正在检查最新版本…"
    : updateState === "downloading"
      ? `正在下载新版本 v${update?.latest_version || ""}…`
      : updateState === "verifying"
        ? `正在校验新版本 v${update?.latest_version || ""}…`
        : updateState === "applying"
          ? "正在重启并安装更新…"
          : updateState === "ready"
            ? (update?.waiting_reason
              ? `新版本 v${update.ready_version} 已就绪 · ${update.waiting_reason}`
              : `新版本 v${update?.ready_version || ""} 已下载就绪`)
            : updateState === "update_available"
              ? `发现新版本 v${update?.latest_version || ""}`
              : updateState === "up_to_date"
                ? (update?.last_checked_at
                  ? `当前已是最新版本 · 上次检查 ${relativeTime(update.last_checked_at)}`
                  : "当前已是最新版本")
                : updateState === "error" && update?.error
                  ? update.error
                  : "检查新版本或自动保持最新";

  const changeAutoCoin = (nextCount) => {
    const count = Number(nextCount) || 0;
    if (typeof onSettingsBatch === "function") {
      if (count <= 0) onSettingsBatch({ do_coin: false });
      else onSettingsBatch({ do_coin: true, coin_target: count });
      return;
    }
    if (count <= 0) onSetting("do_coin", false);
    else {
      onSetting("do_coin", true);
      onSetting("coin_target", count);
    }
  };

  const selectTab = (next) => {
    if (typeof onTab === "function") onTab(next);
  };

  return (<>
    <div className="settings" data-screen-label="设置"><div className="settings-inner">
      <div className="settings-tabs-bar">
        <div className="settings-tabs" role="tablist" aria-label="设置作用域">
          <button type="button" role="tab" aria-selected={activeTab === "account"}
            className={`settings-tab ${activeTab === "account" ? "active" : ""}`}
            onClick={() => selectTab("account")}>
            <Icon name="user" size={13} />
            <span>账号设置</span>
          </button>
          <button type="button" role="tab" aria-selected={activeTab === "app"}
            className={`settings-tab ${activeTab === "app" ? "active" : ""}`}
            onClick={() => selectTab("app")}>
            <Icon name="sliders" size={13} />
            <span>应用设置</span>
          </button>
        </div>
        <span className="settings-scope-hint">
          {activeTab === "account"
            ? (scope?.name ? `以下配置仅对「${scope.name}」独立生效` : "以下配置按账号独立保存")
            : "以下配置对整个应用与本机全局生效"}
        </span>
      </div>

      {activeTab === "account" ? (
        !scope ? (
          <section className="group card">
            <div className="empty list-empty">
              <Icon name="user" size={24} />
              <strong>尚未添加 B 站账号</strong>
              <span>登录账号后可单独配置每日签到与直播应援偏好</span>
              {onOpenLogin && (
                <button type="button" className="btn primary sm" onClick={() => onOpenLogin("")} disabled={busy}>
                  <Icon name="qr" size={12} />扫码添加账号
                </button>
              )}
            </div>
          </section>
        ) : (
          <>
            <section className="card settings-account-bar">
              <window.AccountAvatar account={scope} size="sm" image={scopeAvatar} />
              <div className="settings-account-info">
                <strong>{scope.name}</strong>
                {scopeState && <span className={`mini-tag ${scopeState.tone}`}>{scopeState.label}</span>}
              </div>
              <div className="btn-row">
                {scopeNeedsLogin && onOpenLogin ? (
                  <button type="button" className="btn sm primary" onClick={() => onOpenLogin(scope.id)} disabled={busy}>
                    <Icon name="qr" size={12} />重新扫码
                  </button>
                ) : scopeBlocked && onOpenSafety ? (
                  <button type="button" className="btn sm" onClick={() => onOpenSafety(scope)} disabled={busy}>
                    查看原因
                  </button>
                ) : onSetRunning ? (
                  <button type="button" className={`btn sm ${scopeRunning ? "" : "primary"}`}
                    onClick={() => onSetRunning(scope.id, !scopeRunning)} disabled={busy}>
                    <Icon name={scopeRunning ? "pause" : "play"} size={12} />
                    {scopeRunning ? "停止挂机" : "开启挂机"}
                  </button>
                ) : null}
              </div>
            </section>
            <section className="group card">
              <header className="group-head">每日签到</header>
              <SettingRow name="自动完成日常经验" desc="每日自动领取登录、观看与分享经验">
                <Switch label="自动完成日常经验" checked={settings.auto_daily_exp !== false} disabled={disabled("auto_daily_exp")}
                  onChange={(value) => onSetting("auto_daily_exp", value)} />
              </SettingRow>
              <SettingRow name="每日自动投币" desc="默认关闭以保护硬币，开启后按每日上限自动补齐">
                <Choice label="每日自动投币" value={coinTarget} disabled={disabled("do_coin") || disabled("coin_target")}
                  options={[
                    { value: 0, label: "关闭" },
                    { value: 1, label: "1 枚" },
                    { value: 2, label: "2 枚" },
                    { value: 3, label: "3 枚" },
                    { value: 4, label: "4 枚" },
                    { value: 5, label: "5 枚" },
                  ]}
                  onChange={changeAutoCoin} />
              </SettingRow>
              {coinTarget > 0 && (
                <>
                  <SettingRow className="setting-sub" name="优先投给关注主播" desc="优先从当前关注列表和粉丝牌主播的投稿中挑选视频">
                    <Switch label="优先投给关注主播" checked={settings.prefer_medals !== false} disabled={disabled("prefer_medals")}
                      onChange={(value) => onSetting("prefer_medals", value)} />
                  </SettingRow>
                  <SettingRow className="setting-sub" name="投币时同时点赞" desc="每次投币时顺便为该视频点赞">
                    <Switch label="投币时同时点赞" checked={Boolean(settings.coin_with_like)} disabled={disabled("coin_with_like")}
                      onChange={(value) => onSetting("coin_with_like", value)} />
                  </SettingRow>
                </>
              )}
            </section>
            <section className="group card">
              <header className="group-head">直播应援</header>
              <SettingRow name="点亮粉丝牌" desc="仅在主播开播时发送弹幕重新点亮熄灭的牌子">
                <Switch label="点亮粉丝牌" checked={settings.auto_revive} disabled={disabled("auto_revive")}
                  onChange={(value) => onSetting("auto_revive", value)} />
              </SettingRow>
              <SettingRow name="完成弹幕任务" desc="仅在主播开播时自动补齐每日弹幕亲密度任务">
                <Switch label="完成弹幕任务" checked={settings.auto_danmaku_intimacy} disabled={disabled("auto_danmaku_intimacy")}
                  onChange={(value) => onSetting("auto_danmaku_intimacy", value)} />
              </SettingRow>
              <SettingRow name="发弹幕前佩戴粉丝牌" desc="开播执行弹幕任务前自动佩戴对应主播的粉丝牌">
                <Switch label="发弹幕前佩戴粉丝牌" checked={settings.auto_wear !== false} disabled={disabled("auto_wear")}
                  onChange={(value) => onSetting("auto_wear", value)} />
              </SettingRow>
              <SettingRow name="直播点赞" desc="进入开播直播间后自动完成点赞">
                <Switch label="直播点赞" checked={settings.auto_like} disabled={disabled("auto_like")}
                  onChange={(value) => onSetting("auto_like", value)} />
              </SettingRow>
            </section>
            <section className="group card">
              <header className="group-head">提醒与记录</header>
              <SettingRow name="开播通知" desc="该账号关注的主播开播时弹出桌面提醒">
                <Switch label="开播通知" checked={settings.notify_on_live} disabled={disabled("notify_on_live")}
                  onChange={(value) => onSetting("notify_on_live", value)} />
              </SettingRow>
              {ENABLE_RUN_MODE_SWITCH && (
                <SettingRow name="运行模式" desc="稳健模式推荐日常挂机；激进模式检测更频繁">
                  <Choice label="运行模式" value={runMode} disabled={disabled("run_mode")}
                    options={[{ value: "stable", label: "稳健" }, { value: "aggressive", label: "激进" }]}
                    onChange={(value) => onSetting("run_mode", value)} />
                </SettingRow>
              )}
              {onLogs && (
                <SettingRow name="此账号日志" desc="查看该账号独立的运行与任务记录目录">
                  <button type="button" className="btn sm" onClick={onLogs}>
                    <Icon name="folder" size={13} />打开目录
                  </button>
                </SettingRow>
              )}
            </section>
          </>
        )
      ) : (
        <>
          <section className="group card">
            <header className="group-head">外观</header>
            <SettingRow name="界面主题"
              desc={theme === "system" ? `跟随系统，当前为${systemDark ? "深色 · 墨青暗" : `浅色 · ${dayThemeName}`}` : "自定义应用配色风格"}>
              <ThemeOptions value={theme} onChange={onTheme} systemDark={systemDark} dayThemeName={dayThemeName} />
            </SettingRow>
            {theme === "system" && (
              <SettingRow className="setting-sub" name="白天默认主题" desc="系统处于浅色外观时优先使用的配色">
                <ThemeOptions choices={DAY_THEME_CHOICES} value={dayTheme} onChange={onDayTheme}
                  ariaLabel="白天默认主题" isDayPicker />
              </SettingRow>
            )}
          </section>
          <section className="group card">
            <header className="group-head">启动与更新</header>
            <SettingRow name="开机启动" desc="登录后在系统托盘静默运行">
              <Switch label="开机启动" checked={settings.autostart} disabled={disabled("autostart")}
                onChange={(value) => onSetting("autostart", value)} />
            </SettingRow>
            <SettingRow name="自动更新" desc="后台自动获取新版并在空闲时安装">
              <Switch label="自动更新" checked={settings.auto_update !== false} disabled={disabled("auto_update")}
                onChange={(value) => onSetting("auto_update", value)} />
            </SettingRow>
            {version && (
              <SettingRow name="当前版本" desc={updateDesc}>
                <div className="btn-row">
                  <span className="version-pill">v{version}</span>
                  {updateState === "ready" && update?.can_self_update && onApplyUpdate ? (
                    <button type="button" className="btn sm primary" disabled={Boolean(updateBusy || updateState === "applying")}
                      onClick={onApplyUpdate}>
                      <Icon name="download" size={13} />立即重启更新
                    </button>
                  ) : onCheckUpdate && (
                    <button type="button" className="btn sm" disabled={updateChecking} onClick={onCheckUpdate}>
                      <Icon name="refresh" size={13} />检查更新
                    </button>
                  )}
                </div>
              </SettingRow>
            )}
          </section>
          <details className="group card settings-dev">
            <summary className="group-head group-head-meta dev-summary">
              <span>开发者与诊断</span>
              <span className="dev-summary-right">
                <span className="dev-summary-hint">主程序日志 · 脱敏诊断包</span>
                <Icon name="chevron" size={14} />
              </span>
            </summary>
            <SettingRow name="主程序日志" desc="打开桌面宿主与守护进程日志目录，便于排障">
              <button type="button" className="btn sm" onClick={onHostLogs || onLogs}>
                <Icon name="folder" size={13} />打开目录
              </button>
            </SettingRow>
            <SettingRow name="一键导出诊断包" desc="打包日志、近期报错与环境摘要，自动移除登录凭证并默认匿名化">
              <button type="button" className="btn sm" onClick={onDiagnostics}>
                <Icon name="download" size={13} />导出诊断包
              </button>
            </SettingRow>
          </details>
        </>
      )}
    </div></div>
  </>);
};

const AccountRow = ({
  account, isActive, image, runningCount = 0,
  onView, onSwitch, onSetRunning, onSwitchExclusive, onScan, onLogout, onRemove, onProtection, busy
}) => {
  const state = window.accountStateLabel(account);
  const needsLogin = !account.signed_in || account.status === "needs_login";
  const protection = account.status === "blocked" || Boolean(account.safety?.blocked);
  const engineActive = Boolean(account.engine_active || account.running);
  const startLabel = runningCount > 0 ? "同时挂机" : "开启挂机";
  const issueText = protection
    ? (account.safety?.reason || "账号操作已暂停，需在平台处理")
    : needsLogin
      ? "登录已失效，请重新扫码"
      : null;

  return (
    <div className={`account-item ${isActive ? "current" : ""}`}>
      <window.AccountAvatar account={account} size="lg" image={image} />
      <div className="account-item-main">
        <div className="account-item-title">
          <strong>{account.name}</strong>
          {isActive && <span className="mini-tag">当前查看</span>}
          {!needsLogin && !protection && <span className={`mini-tag ${state.tone}`}>{state.label}</span>}
          {needsLogin && <span className="mini-tag warn">需要重新扫码</span>}
          {protection && <span className="mini-tag warn">需在平台处理</span>}
        </div>
        <div className="account-item-meta">
          UID {account.uid}{account.room_count > 0 ? ` · 关注 ${account.room_count} 位` : ""}
          {account.live_room_count > 0 ? ` · ${account.live_room_count} 房直播中` : ""}
        </div>
        {issueText && <div className="account-item-sub warn">{issueText}</div>}
      </div>
      <div className="account-item-actions">
        {protection && (
          <button type="button" className="btn sm" onClick={() => onProtection(account.id)}
            aria-label={`查看原因 ${account.name}`}>
            查看原因
          </button>
        )}
        {needsLogin && (
          <button type="button" className="btn sm primary" onClick={() => onScan(account.id)}
            aria-label={`重新扫码 ${account.name}`}>
            <Icon name="qr" size={12} />重新扫码
          </button>
        )}
        {!isActive && (
          <button type="button" className="btn sm" onClick={() => (onView ? onView(account.id) : onSwitch(account.id))} disabled={busy}
            title="只读查看此账号数据，不会改变其挂机状态" aria-label={`查看 ${account.name}`}>
            查看
          </button>
        )}
        {!needsLogin && !protection && engineActive && onSetRunning && (
          <button type="button" className="btn sm" onClick={() => onSetRunning(account.id, false)} disabled={busy}
            aria-label={`停止挂机 ${account.name}`}>
            停止挂机
          </button>
        )}
        {!needsLogin && !protection && !engineActive && onSetRunning && (
          <button type="button" className="btn sm primary" onClick={() => onSetRunning(account.id, true)} disabled={busy}
            aria-label={`${startLabel} ${account.name}`}>
            <Icon name="play" size={12} />{startLabel}
          </button>
        )}
        {!needsLogin && !protection && !engineActive && runningCount > 0 && onSwitchExclusive && (
          <button type="button" className="btn sm" onClick={() => onSwitchExclusive(account.id)} disabled={busy}
            title="停止其他账号，仅运行此账号" aria-label={`仅挂此号 ${account.name}`}>
            仅挂此号
          </button>
        )}
        <button type="button" className="btn sm" onClick={() => onLogout(account.id)}
          disabled={busy} title={needsLogin ? "清除本机保存的失效登录凭证" : "退出此账号登录"}
          aria-label={`${needsLogin ? "清除登录" : "退出登录"} ${account.name}`}>
          <Icon name="power" size={13} />
          <span>{needsLogin ? "清除登录" : "退出登录"}</span>
        </button>
        <button type="button" className="btn ghost sm danger-hover" onClick={() => onRemove(account.id)}
          disabled={busy} title="移除账号" aria-label={`移除 ${account.name}`}>
          <span>移除</span>
        </button>
      </div>
    </div>
  );
};

const AccountPage = ({ accounts, activeId, account, avatar, avatars = {}, maxConcurrent = 3, onScan, onView, onSwitch,
  onSetRunning, onSwitchExclusive, onLogout, onRemove, onProtection, onResumeSafety, onCheckSafety, safetyProbe, onCheck, busy, version }) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const checkingSafety = Boolean(safetyProbe?.loading);
  const locationParts = [hold.room_label, hold.operation_label].filter(Boolean);
  const runningCount = (accounts || []).filter((item) => item.running || item.engine_active).length;
  return (<>
    <div className="settings" data-screen-label="账号"><div className="settings-inner">
      <section className="group card">
        <header className="group-head group-head-action">
          <div className="btn-row">
            <span className="group-head-title">B 站账号</span>
            {accounts.length > 1 && (
              <span className="scope-tag">
                {runningCount > 1 ? `${runningCount} 号同时挂机中` : `最多支持 ${maxConcurrent} 号同时挂机`}
              </span>
            )}
          </div>
          <button type="button" className="btn primary sm" onClick={() => onScan("")} disabled={busy}>
            <Icon name="plus" size={13} />添加账号
          </button>
        </header>
        {accounts.length ? accounts.map((item) => <AccountRow key={item.id} account={item}
          isActive={item.id === activeId}
          runningCount={runningCount}
          image={item.id === activeId ? (avatar || avatars[item.id]) : avatars[item.id]}
          onView={onView} onSwitch={onSwitch} onSetRunning={onSetRunning} onSwitchExclusive={onSwitchExclusive}
          onScan={onScan} onLogout={onLogout} onRemove={onRemove} onProtection={onProtection}
          busy={busy} />)
          : <div className="empty list-empty"><Icon name="user" size={24} />
            <strong>尚未添加 B 站账号</strong>
            <button type="button" className="btn primary sm" onClick={() => onScan("")}>
              <Icon name="qr" size={12} />扫码添加账号</button></div>}
      </section>
      <section className="group card">
        <header className="group-head">账号安全</header>
        <div className="safety-row">
          <div className="safety-info">
            <div className="safety-status">
              <i className={`status-dot ${hold.blocked ? "warn" : "ok"}`} />
              <strong>
                {hold.blocked ? (hold.kind_label || "保护暂停中") : "状态正常"}
              </strong>
              {hold.blocked && hold.reason && <span className="safety-reason">{hold.reason}</span>}
            </div>
            {hold.blocked && locationParts.length > 0 && (
              <small className="safety-time">触发位置：{locationParts.join(" · ")}</small>
            )}
            {cooldown && <small className="safety-time">最早自动恢复：{absoluteTime(hold.until)}</small>}
            {!cooldown && hold.blocked && hold.next_probe_at && (
              <small className="safety-time">下次自动检测：{absoluteTime(hold.next_probe_at)}</small>
            )}
            {hold.pace_multiplier > 1 && (
              <small className="safety-time">今日保护降速中：互动间隔已放慢至 {hold.pace_multiplier}×</small>
            )}
          </div>
          <div className="safety-actions">
            {(!account.signed_in || needsLogin) && (
              <button type="button" className="btn sm primary" onClick={() => onScan()} disabled={busy}>
                <Icon name="qr" size={13} />
                <span>扫码登录</span>
              </button>
            )}
            {account.signed_in && !needsLogin && hold.blocked && (
              <>
                <button type="button" className="btn sm" onClick={() => onResumeSafety()} disabled={busy || checkingSafety}>
                  <Icon name="shield" size={13} />
                  <span>查看详情</span>
                </button>
                {!cooldown && onCheckSafety && (
                  <button type="button" className="btn sm primary" onClick={() => onCheckSafety(true)} disabled={busy || checkingSafety}>
                    <Icon name="refresh" size={13} />
                    <span>{checkingSafety ? "检测中…" : "检测并恢复"}</span>
                  </button>
                )}
              </>
            )}
            {account.signed_in && !needsLogin && !hold.blocked && (
              <button type="button" className="btn sm" onClick={() => onCheck()} disabled={busy}>
                <Icon name="refresh" size={13} />
                <span>立即检查</span>
              </button>
            )}
          </div>
        </div>
      </section>
      {version && <div className="page-foot-version">ビリ推し v{version}</div>}
    </div></div>
  </>);
};

Object.assign(window, { SettingsPage, AccountPage, AccountRow, Switch, SettingRow });
