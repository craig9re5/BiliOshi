/* Settings use the same vocabulary as the overview; changes apply through Python. */

const { useState, useEffect, useRef } = React;
const { Icon, relativeTime, absoluteTime } = window;

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

const SettingsPage = ({ settings, onSetting, pendingSettings }) => {
  const disabled = (key) => pendingSettings.has(key);
  const runMode = settings.run_mode || "stable";
  return (<>
    <div className="settings" data-screen-label="挂机设置"><div className="settings-inner">
      <section className="group card">
        <header className="group-head">每日任务<small>开播后，按 B 站的任务进度自动完成</small></header>
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
      </section>
      <p className="settings-note">运行模式保存后立即生效。当天的已完成进度与发送额度会保留。</p>
    </div></div>
  </>);
};

const AccountPage = ({ account, avatar, onScan, onLogout, onResumeSafety, onCheck, busy, version }) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const action = !account.signed_in || needsLogin ? onScan : cooldown ? null : hold.blocked ? onResumeSafety : onCheck;
  const actionLabel = !account.signed_in || needsLogin ? "扫码登录" : cooldown ? "等待自动恢复" : hold.blocked ? "确认并恢复" : "检查状态";
  return (<>
    <div className="settings" data-screen-label="账号"><div className="settings-inner">
      <section className="group card">
        <header className="group-head">B 站账号</header>
        <div className="setting">
          <span className="account-avatar">{avatar ? <img src={avatar} alt="" /> : Array.from(account.name || "?")[0]}</span>
          <div className="setting-text">
            <div className="account-name">{account.name || (account.signed_in ? "登录状态待确认" : "尚未登录")}</div>
            <div className="account-meta" title={absoluteTime(account.checked_at)}>
              {account.signed_in ? account.confirmed ? `${relativeTime(account.checked_at)}验证` : "检查状态以验证登录" : "扫码后开始自动挂机与每日任务"}
            </div>
          </div>
          <div className="account-actions">
            <button type="button" className="btn primary" onClick={onScan} disabled={busy}><Icon name="qr" size={13} />
              {account.signed_in ? "切换账号" : "扫码登录"}</button>
            {account.signed_in && <button type="button" className="btn sm" onClick={onLogout} disabled={busy}>退出登录</button>}
          </div>
        </div>
      </section>
      <section className="group card">
        <header className="group-head">账号保护</header>
        <SettingRow name={hold.blocked ? "操作已暂停" : account.signed_in ? "未触发保护" : "等待登录"}
          desc={hold.blocked ? hold.reason || "账号出现异常，已暂停互动操作" : "遇到账号异常或请求结果不确定时，自动暂停互动"}>
          <button type="button" className="btn sm" onClick={action || undefined} disabled={!action || busy}>
            <Icon name={needsLogin ? "qr" : "shield"} size={13} />{actionLabel}
          </button>
        </SettingRow>
        {cooldown && <p className="settings-note inside">最早恢复时间：{absoluteTime(hold.until)}。冷却结束后会自动检查。</p>}
      </section>
      <p className="settings-note">ビリ推し {version || ""} · 关闭窗口后继续在托盘运行</p>
    </div></div>
  </>);
};

Object.assign(window, { SettingsPage, AccountPage, Switch, SettingRow });
