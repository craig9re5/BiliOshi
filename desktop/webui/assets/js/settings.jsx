/* Settings use the same vocabulary as the overview; changes apply through Python. */

const { useState, useEffect, useRef } = React;
const { Icon, relativeTime, absoluteTime, numberLabel } = window;

const Switch = ({ checked, onChange, label, disabled }) => (
  <button type="button" className="switch" role="switch" aria-checked={Boolean(checked)}
    aria-label={label} disabled={disabled} onClick={() => onChange(!checked)} />
);

const SettingRow = ({ name, desc, children }) => (
  <div className="setting"><div className="setting-text"><div className="setting-name">{name}</div>
    {desc && <div className="setting-desc">{desc}</div>}</div>{children}</div>
);

/* A compact trigger plus a themed menu. The native select rendered its own
   system popup, which did not follow the card surfaces or spacing. */
const Choice = ({ value, options, onChange, label, disabled }) => {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const menu = useRef(null);
  const selected = Math.max(0, options.findIndex((option) => option.value === value));

  useEffect(() => {
    if (!open) return undefined;
    const dismiss = (event) => {
      if (!root.current?.contains(event.target)) setOpen(false);
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
      {open && <div className="choice-menu" role="listbox" aria-label={label} ref={menu}>
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
      </div>}
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
  settings, onSetting, pendingSettings, theme = "system", onTheme, dayTheme = "white", onDayTheme,
  scope, onLogs, onHostLogs, onDiagnostics, version
}) => {
  const systemDark = useSystemDark();
  const disabled = (key) => pendingSettings.has(key);
  const runMode = settings.run_mode || "stable";
  const dayThemeName = (DAY_THEME_CHOICES.find((item) => item.key === dayTheme) || DAY_THEME_CHOICES[0]).name;
  return (<>
    <div className="settings" data-screen-label="设置"><div className="settings-inner">
      <section className="group card">
        <header className="group-head">每日任务</header>
        <SettingRow name="点亮粉丝牌" desc="牌子熄灭时发送弹幕重新点亮">
          <Switch label="点亮粉丝牌" checked={settings.auto_revive} disabled={disabled("auto_revive")}
            onChange={(value) => onSetting("auto_revive", value)} />
        </SettingRow>
        <SettingRow name="完成弹幕任务" desc="自动补齐每日弹幕亲密度任务">
          <Switch label="完成弹幕任务" checked={settings.auto_danmaku_intimacy} disabled={disabled("auto_danmaku_intimacy")}
            onChange={(value) => onSetting("auto_danmaku_intimacy", value)} />
        </SettingRow>
        <SettingRow name="直播点赞" desc="进入开播直播间后自动完成点赞">
          <Switch label="直播点赞" checked={settings.auto_like} disabled={disabled("auto_like")}
            onChange={(value) => onSetting("auto_like", value)} />
        </SettingRow>
      </section>
      <section className="group card">
        <header className="group-head">运行与启动</header>
        <SettingRow name="开播通知" desc="关注的主播开播时弹出系统提醒">
          <Switch label="开播通知" checked={settings.notify_on_live} disabled={disabled("notify_on_live")}
            onChange={(value) => onSetting("notify_on_live", value)} />
        </SettingRow>
        <SettingRow name="开机启动" desc="登录系统后在托盘静默运行">
          <Switch label="开机启动" checked={settings.autostart} disabled={disabled("autostart")}
            onChange={(value) => onSetting("autostart", value)} />
        </SettingRow>
        <SettingRow name="运行模式" desc="稳健模式推荐日常挂机；激进模式检测更频繁">
          <Choice label="运行模式" value={runMode} disabled={disabled("run_mode")}
            options={[{ value: "stable", label: "稳健" }, { value: "aggressive", label: "激进" }]}
            onChange={(value) => onSetting("run_mode", value)} />
        </SettingRow>
      </section>
      <section className="group card">
        <header className="group-head">日志与诊断反馈</header>
        <SettingRow name="运行日志" desc={scope ? "可分别查看当前账号挂机日志或主程序全局日志" : "打开日志文件所在目录，便于排障"}>
          <div className="btn-row">
            <button type="button" className="btn sm" onClick={onLogs}>
              <Icon name="folder" size={13} />{scope ? "账号日志" : "查看日志"}
            </button>
            {scope && onHostLogs && (
              <button type="button" className="btn sm" onClick={onHostLogs}>
                <Icon name="folder" size={13} />主程序日志
              </button>
            )}
          </div>
        </SettingRow>
        <SettingRow name="一键导出诊断包" desc="打包日志、近期报错与环境摘要，自动移除凭证并默认匿名化身份">
          <button type="button" className="btn sm primary" onClick={onDiagnostics}>
            <Icon name="download" size={13} />导出诊断包
          </button>
        </SettingRow>
        {version && (
          <SettingRow name="版本信息" desc="提交问题反馈时建议附带版本号与脱敏诊断包">
            <span className="version-pill">v{version}</span>
          </SettingRow>
        )}
      </section>
      <section className="group card">
        <header className="group-head">外观</header>
        <SettingRow name="界面主题"
          desc={theme === "system" ? `跟随系统，当前为${systemDark ? "深色 · 墨青暗" : `浅色 · ${dayThemeName}`}` : "自定义应用配色风格"}>
          <ThemeOptions value={theme} onChange={onTheme} systemDark={systemDark} dayThemeName={dayThemeName} />
        </SettingRow>
        {theme === "system" && (
          <SettingRow name="白天默认主题" desc="系统处于浅色外观时优先使用的配色">
            <ThemeOptions choices={DAY_THEME_CHOICES} value={dayTheme} onChange={onDayTheme}
              ariaLabel="白天默认主题" isDayPicker />
          </SettingRow>
        )}
      </section>
    </div></div>
  </>);
};

const AccountRow = ({ account, isActive, image, onView, onSwitch, onScan, onLogout, onRemove, onProtection, busy }) => {
  const state = window.accountStateLabel(account);
  const needsLogin = !account.signed_in || account.status === "needs_login";
  const protection = account.status === "blocked" || Boolean(account.safety?.blocked);
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
          {isActive && <span className="mini-tag live">当前使用</span>}
          {!isActive && !needsLogin && !protection && <span className={`mini-tag ${state.tone}`}>{state.label}</span>}
          {needsLogin && <span className="mini-tag warn">需要重新扫码</span>}
          {protection && <span className="mini-tag warn">需在平台处理</span>}
        </div>
        <div className="account-item-meta">UID {account.uid}</div>
        {issueText && <div className="account-item-sub warn">{issueText}</div>}
      </div>
      <div className="account-item-actions">
        {protection && (
          <button type="button" className="btn sm" onClick={() => onProtection(account.id)}>
            查看原因
          </button>
        )}
        {needsLogin && (
          <button type="button" className="btn sm primary" onClick={() => onScan(account.id)}>
            <Icon name="qr" size={12} />重新扫码
          </button>
        )}
        {!isActive && !needsLogin && !protection && (
          <button type="button" className="btn sm primary" onClick={() => onSwitch(account.id)} disabled={busy}>
            <Icon name="play" size={12} />切换账号
          </button>
        )}
        <button type="button" className="btn sm" onClick={() => onLogout(account.id)}
          disabled={busy} title={needsLogin ? "清除本机保存的失效登录凭证" : "退出此账号登录"}
          aria-label={`${needsLogin ? "清除" : "退出"} ${account.name} 的登录`}>
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

const AccountPage = ({ accounts, activeId, account, avatar, avatars = {}, onScan, onView, onSwitch,
  onLogout, onRemove, onProtection, onResumeSafety, onCheckSafety, safetyProbe, onCheck, busy, version }) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const checkingSafety = Boolean(safetyProbe?.loading);
  const locationParts = [hold.room_label, hold.operation_label].filter(Boolean);
  return (<>
    <div className="settings" data-screen-label="账号"><div className="settings-inner">
      <section className="group card">
        <header className="group-head group-head-action">
          <span className="group-head-title">B 站账号</span>
          <button type="button" className="btn primary sm" onClick={() => onScan("")} disabled={busy}>
            <Icon name="plus" size={13} />添加账号
          </button>
        </header>
        {accounts.length ? accounts.map((item) => <AccountRow key={item.id} account={item}
          isActive={item.id === activeId}
          image={item.id === activeId ? (avatar || avatars[item.id]) : avatars[item.id]}
          onView={onView} onSwitch={onSwitch} onScan={onScan} onLogout={onLogout} onRemove={onRemove} onProtection={onProtection}
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
                {hold.blocked && hold.code !== undefined && hold.code !== null && `（错误码 ${hold.code}）`}
              </strong>
              {hold.blocked && hold.reason && <span className="safety-reason">{hold.reason}</span>}
            </div>
            {hold.blocked && locationParts.length > 0 && (
              <small className="safety-time">触发位置：{locationParts.join(" · ")}</small>
            )}
            {cooldown && <small className="safety-time">最早自动恢复：{absoluteTime(hold.until)}</small>}
            {!cooldown && hold.blocked && hold.next_probe_at && (
              <small className="safety-time">下次自动复检：{absoluteTime(hold.next_probe_at)}</small>
            )}
            {hold.pace_multiplier > 1 && (
              <small className="safety-time">今日防风控降频保护：互动发送间隔已调整为 {hold.pace_multiplier}×</small>
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
                  <span>查看详情与排查</span>
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
