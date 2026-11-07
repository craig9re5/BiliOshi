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

const THEME_CHOICES = [
  { key: "white", name: "纸白", hint: "中性纸面" },
  { key: "paper", name: "暖纸白", hint: "温和纸感" },
  { key: "mist", name: "雾青灰", hint: "清爽青灰" },
  { key: "apricot", name: "暖杏灰", hint: "温暖柔和" }
];

const ThemeOptions = ({ value, onChange }) => (
  <div className="theme-options" role="group" aria-label="界面主题">
    {THEME_CHOICES.map((theme) => {
      const active = theme.key === value;
      return <button type="button" key={theme.key} className="theme-option" data-theme={theme.key}
        aria-pressed={active} title={`${theme.name} · ${theme.hint}`}
        onClick={() => onChange(theme.key)}>
        <span className={`theme-chip ${theme.key}`} aria-hidden="true" />
        <span className="theme-name">{theme.name}</span>
        {active && <Icon name="check" size={11} />}
      </button>;
    })}
  </div>
);

const SettingsPage = ({ settings, onSetting, pendingSettings, theme = "white", onTheme, onLogs }) => {
  const disabled = (key) => pendingSettings.has(key);
  const runMode = settings.run_mode || "stable";
  return (<>
    <div className="settings" data-screen-label="设置"><div className="settings-inner">
      <section className="group card">
        <header className="group-head">每日任务</header>
        <SettingRow name="点亮粉丝牌" desc="粉丝牌熄灭时发送弹幕，点亮后停止">
          <Switch label="点亮粉丝牌" checked={settings.auto_revive} disabled={disabled("auto_revive")}
            onChange={(value) => onSetting("auto_revive", value)} />
        </SettingRow>
        <SettingRow name="完成弹幕任务" desc="只补齐剩余弹幕，完成后停止">
          <Switch label="完成弹幕任务" checked={settings.auto_danmaku_intimacy} disabled={disabled("auto_danmaku_intimacy")}
            onChange={(value) => onSetting("auto_danmaku_intimacy", value)} />
        </SettingRow>
        <SettingRow name="直播点赞" desc="自动点赞并检查任务进度，默认关闭">
          <Switch label="直播点赞" checked={settings.auto_like} disabled={disabled("auto_like")}
            onChange={(value) => onSetting("auto_like", value)} />
        </SettingRow>
      </section>
      <section className="group card">
        <header className="group-head">运行与启动</header>
        <SettingRow name="开播通知" desc="关注的主播开播时，通过系统通知提醒">
          <Switch label="开播通知" checked={settings.notify_on_live} disabled={disabled("notify_on_live")}
            onChange={(value) => onSetting("notify_on_live", value)} />
        </SettingRow>
        <SettingRow name="开机启动" desc="登录 Windows 后在托盘运行，不打开主窗口">
          <Switch label="开机启动" checked={settings.autostart} disabled={disabled("autostart")}
            onChange={(value) => onSetting("autostart", value)} />
        </SettingRow>
        <SettingRow name="运行模式" desc="稳健：5 分钟查开播、60 秒续点赞；激进：1 分钟查开播、20 秒续点赞">
          <Choice label="运行模式" value={runMode} disabled={disabled("run_mode")}
            options={[{ value: "stable", label: "稳健" }, { value: "aggressive", label: "激进" }]}
            onChange={(value) => onSetting("run_mode", value)} />
        </SettingRow>
        <SettingRow name="运行日志" desc="在文件资源管理器中打开当前账号的日志目录，排查异常或查看运行记录">
          <button type="button" className="btn sm" onClick={onLogs}>
            <Icon name="folder" size={13} />查看日志
          </button>
        </SettingRow>
      </section>
      <section className="group card">
        <header className="group-head">外观</header>
        <SettingRow name="界面主题" desc="选择界面表面颜色，切换后立即生效并记住选择（全应用，不随账号切换）">
          <ThemeOptions value={theme} onChange={onTheme} />
        </SettingRow>
      </section>
      <p className="settings-note">运行模式保存后立即生效。当天的已完成进度与发送额度会保留。任务开关与运行模式按账号独立保存。</p>
    </div></div>
  </>);
};

const AccountRow = ({ account, isActive, image, onView, onSwitch, onScan, onLogout, onRemove, onProtection, busy }) => {
  const state = window.accountStateLabel(account);
  const needsLogin = !account.signed_in || account.status === "needs_login";
  const protection = account.status === "blocked";
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
        <button type="button" className="btn ghost sm" onClick={() => onLogout(account.id)}
          disabled={busy || needsLogin} title="退出此账号登录" aria-label={`退出 ${account.name} 的登录`}>
          <Icon name="power" size={13} />
          <span>退出登录</span>
        </button>
        <button type="button" className="btn ghost sm danger" onClick={() => onRemove(account.id)}
          disabled={busy} title="移除账号" aria-label={`移除 ${account.name}`}>
          <span>移除</span>
        </button>
      </div>
    </div>
  );
};

const AccountPage = ({ accounts, activeId, account, avatar, onScan, onView, onSwitch,
  onLogout, onRemove, onProtection, onResumeSafety, onCheck, busy, version }) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const action = !account.signed_in || needsLogin ? onScan : cooldown ? null : hold.blocked ? onResumeSafety : onCheck;
  const actionLabel = !account.signed_in || needsLogin ? "扫码登录" : cooldown ? "等待自动恢复" : hold.blocked ? "确认并恢复" : "检查状态";
  return (<>
    <div className="settings" data-screen-label="账号"><div className="settings-inner">
      {hold.blocked && (
        <section className="group card card-warn">
          <header className="group-head">账号异常保护</header>
          <div className="account-alert-body">
            <div className="account-alert-icon">
              <Icon name="shield" size={18} />
            </div>
            <div className="account-alert-main">
              <strong>操作已暂停</strong>
              <p>{hold.reason || "账号出现异常，已暂停互动操作"}</p>
              {cooldown && <small>最早恢复时间：{absoluteTime(hold.until)}</small>}
            </div>
            {action && (
              <button type="button" className="btn sm primary" onClick={() => action?.()} disabled={busy}>
                <Icon name={needsLogin ? "qr" : "shield"} size={13} />{actionLabel}
              </button>
            )}
          </div>
        </section>
      )}
      <section className="group card">
        <header className="group-head group-head-action">
          <span className="group-head-title">B 站账号</span>
          <button type="button" className="btn primary sm" onClick={() => onScan("")} disabled={busy}>
            <Icon name="plus" size={13} />添加账号
          </button>
        </header>
        {accounts.length ? accounts.map((item) => <AccountRow key={item.id} account={item}
          isActive={item.id === activeId}
          image={item.id === activeId ? avatar : undefined}
          onView={onView} onSwitch={onSwitch} onScan={onScan} onLogout={onLogout} onRemove={onRemove} onProtection={onProtection}
          busy={busy} />)
          : <div className="empty list-empty"><Icon name="user" size={28} />
            <strong>尚未添加 B 站账号</strong>
            <button type="button" className="btn primary sm" onClick={() => onScan("")}>
              <Icon name="qr" size={12} />扫码添加账号</button></div>}
      </section>
    </div></div>
  </>);
};

Object.assign(window, { SettingsPage, AccountPage, AccountRow, Switch, SettingRow });
