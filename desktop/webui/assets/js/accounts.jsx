/* Account tabs, the aggregate dashboard and the account switcher.
   Tabs only change the viewed account; running changes stay explicit. */

const { Icon, relativeTime, numberLabel } = window;
const { useEffect, useRef } = React;

const ACCOUNT_COLORS = ["#3d7a6c", "#6a5f8f", "#8a7b62", "#7a6270", "#4f6f8a", "#7d6a4f"];

function accountColor(id) {
  let hash = 0;
  for (const letter of String(id || "")) hash = (hash * 31 + letter.charCodeAt(0)) % 997;
  return ACCOUNT_COLORS[hash % ACCOUNT_COLORS.length];
}

function accountInitial(name) {
  return Array.from(String(name || "?").trim())[0] || "?";
}

/* One state per account, so an account keeps its own status wording. */
function accountStateLabel(account) {
  if (!account) return { label: "未运行", tone: "muted" };
  if (account.status === "blocked") return { label: "保护暂停", tone: "warn" };
  if (!account.signed_in || account.status === "needs_login") return { label: "登录失效", tone: "warn" };
  if (account.global_paused) return { label: "全局暂停", tone: "muted" };
  if (account.running) return { label: "挂机中", tone: "live" };
  if (account.paused) return { label: "已暂停", tone: "muted" };
  return { label: "未运行", tone: "muted" };
}

const AccountAvatar = ({ account, size = "sm", image }) => {
  if (!account) return <span className={`avatar ${size}`} style={{ background: "var(--accent-soft)", color: "var(--accent)" }}>全</span>;
  return <span className={`avatar ${size}`} style={{ background: accountColor(account.id) }}
    aria-hidden="true">{image ? <img src={image} alt="" /> : accountInitial(account.name)}</span>;
};

const AccountTabs = ({ accounts, viewId, activeId, onView, onAdd }) => {
  const items = [{ id: "all", name: "全部账号", state: "muted", count: accounts.length }]
    .concat(accounts.map((account) => ({
      id: account.id,
      name: account.name,
      state: accountStateLabel(account).tone,
      count: account.live_room_count,
      running: account.running,
      status: accountStateLabel(account).label
    })));
  const move = (event, index) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + items.length) % items.length;
    onView(items[next].id);
    window.requestAnimationFrame(() => {
      document.getElementById(`account-tab-${items[next].id}`)?.focus();
    });
  };
  return (
    <div className="account-tabs">
      <div className="account-tablist" role="tablist" aria-label="账号">
        {items.map((item, index) => {
          const selected = viewId === item.id;
          return <button type="button" key={item.id} id={`account-tab-${item.id}`} role="tab"
            aria-selected={selected} aria-controls="monitor-body" tabIndex={selected ? 0 : -1}
            className={`account-tab ${selected ? "active" : ""}`} title={item.status || "全部账号"}
            onClick={() => onView(item.id)} onKeyDown={(event) => move(event, index)}>
            {item.id === "all" ? <span className="tab-avatar all">全</span>
              : <span className="tab-avatar" style={{ background: accountColor(item.id) }}>{accountInitial(item.name)}</span>}
            <span className="tab-name">{item.name}</span>
            {item.id !== "all" && <i className={`tab-state ${item.state}`} aria-hidden="true" />}
            <span className="tab-count">{item.count || 0}</span>
          </button>;
        })}
        <button type="button" className="account-tab add" onClick={onAdd} title="添加账号" aria-label="添加账号">
          <Icon name="plus" size={15} />
        </button>
      </div>
    </div>
  );
};

const AccountDashboard = ({ accounts, globalPaused, onView, onSwitch, onCheckAll, onPauseAll, onResumeAll,
  onRelogin, onProtection, busy }) => {
  const running = accounts.filter((account) => account.running);
  const liveTotal = running.reduce((sum, account) => sum + (account.live_room_count || 0), 0);
  return (
    <div className="dashboard-scroll">
      {globalPaused && <div className="banner neutral" role="status">
        <Icon name="pause" size={14} />
        <span>所有账号已暂停挂机（全局暂停）。恢复时只恢复暂停前正在运行的账号。</span>
        <button type="button" className="btn sm" onClick={onResumeAll} disabled={busy}>恢复全部</button>
      </div>}
      <div className="dashboard-head">
        <div>
          <h2>账号总览</h2>
          <p>{globalPaused ? "全局暂停中" : running.length
            ? `${running.length} 个账号挂机中 · ${liveTotal} 个直播间直播中`
            : "当前没有账号在挂机"}</p>
        </div>
        <div className="dash-actions">
          <button type="button" className="btn sm" onClick={onCheckAll} disabled={busy}>
            <Icon name="refresh" size={12} />全部检查</button>
          {globalPaused
            ? <button type="button" className="btn sm primary" onClick={onResumeAll} disabled={busy}>恢复全部</button>
            : running.length
              ? <button type="button" className="btn sm" onClick={onPauseAll} disabled={busy}>全部暂停</button>
              : null}
        </div>
      </div>
      {accounts.length ? <div className="account-grid">
        {accounts.map((account) => {
          const state = accountStateLabel(account);
          const needsLogin = !account.signed_in || account.status === "needs_login";
          const protection = account.status === "blocked";
          return <article key={account.id} className={`account-card ${account.running ? "running" : ""}`}>
            <header>
              <AccountAvatar account={account} size="lg" />
              <div className="account-card-title">
                <strong>{account.name}</strong>
                <span>UID {account.uid} · 关注 {account.room_count} 位</span>
              </div>
              <span className={`status-pill ${state.tone}`}>{state.label}</span>
            </header>
            <div className="account-stats">
              <div><strong>{account.room_count}</strong><span>关注</span></div>
              <div><strong>{account.live_room_count || 0}</strong><span>{account.running ? "直播中" : "上次直播中"}</span></div>
              <div><strong>{account.gain === null || account.gain === undefined ? "—" : "+" + numberLabel(account.gain)}</strong>
                <span>今日亲密度</span></div>
            </div>
            {needsLogin && <div className="card-notice">
              <Icon name="alert" size={13} />
              <span>登录已失效，无法开始挂机</span>
              <button type="button" className="link-btn" onClick={() => onRelogin(account.id)}>重新扫码</button>
            </div>}
            {protection && <div className="card-notice">
              <Icon name="shield" size={13} />
              <span>账号保护暂停，重新扫码不会解除</span>
              <button type="button" className="link-btn" onClick={() => onProtection(account.id)}>查看原因</button>
            </div>}
            <footer>
              <span>上次检查 {relativeTime(account.snapshot_at)}</span>
              {account.running
                ? <button type="button" className="link-btn" onClick={() => onView(account.id)}>打开总览 →</button>
                : needsLogin
                  ? <button type="button" className="link-btn" onClick={() => onRelogin(account.id)}>重新扫码</button>
                  : protection
                    ? <button type="button" className="link-btn" onClick={() => onProtection(account.id)}>查看原因</button>
                    : <button type="button" className="link-btn" onClick={() => onSwitch(account.id)}>切换并挂机</button>}
            </footer>
          </article>;
        })}
      </div> : <div className="empty list-empty">
        <Icon name="user" size={24} />
        <strong>尚未添加 B 站账号</strong>
        <span>扫码添加账号后，每个账号会有独立的关注列表和直播总览。</span>
      </div>}
    </div>
  );
};

const AccountSwitcher = ({ open, accounts, viewId, activeId, onSelect, onManage, onAdd, onClose }) => {
  const menu = useRef(null);
  const trigger = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    if (!open) return undefined;
    trigger.current = document.activeElement;
    const focusTimer = window.setTimeout(() => {
      const selected = menu.current?.querySelector('[aria-checked="true"]');
      (selected || menu.current?.querySelector("button"))?.focus();
    }, 0);
    const keydown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const items = Array.from(menu.current?.querySelectorAll("button") || []);
      if (!items.length) return;
      const index = items.indexOf(document.activeElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
        : index < 0 ? 0
          : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      items[next].focus();
    };
    document.addEventListener("keydown", keydown);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", keydown);
      trigger.current?.focus?.();
    };
  }, [open]);

  if (!open) return null;
  const running = accounts.filter((account) => account.running);
  return (
    <>
      <div className="switcher-scrim open" onClick={onClose} />
      <div className="switcher open" role="menu" aria-label="账号切换器" ref={menu}>
        <div className="switcher-head">
          <strong>账号</strong>
          <span>{running.length ? `${running.length} 个挂机中` : "未挂机"}</span>
        </div>
        {accounts.map((account) => {
          const state = accountStateLabel(account);
          const selected = viewId === account.id;
          return <button type="button" key={account.id} role="menuitemradio" aria-checked={selected}
            className="switcher-item" onClick={() => onSelect(account.id)}>
            <AccountAvatar account={account} size="sm" />
            <span className="switcher-item-main">
              <strong>{account.name}</strong>
              <small className={state.tone === "warn" ? "warn" : ""}>
                {state.label}{account.id === activeId ? " · 当前挂机" : ""}
              </small>
            </span>
            {selected && <Icon name="check" size={13} />}
          </button>;
        })}
        {!accounts.length && <p className="switcher-mode">尚未添加账号。</p>}
        <div className="switcher-foot">
          <button type="button" role="menuitem" onClick={onManage}>管理账号</button>
          <button type="button" role="menuitem" onClick={onAdd}>添加账号</button>
        </div>
      </div>
    </>
  );
};

Object.assign(window, { AccountTabs, AccountDashboard, AccountSwitcher, AccountAvatar, accountStateLabel, accountColor, accountInitial });
