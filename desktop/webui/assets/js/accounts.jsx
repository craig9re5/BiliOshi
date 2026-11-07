/* Account tabs and the account switcher.
   One account is displayed and active at a time; switching is instant. */

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

const AccountTabs = ({ accounts, activeId, onSelect, onAdd }) => {
  if (!accounts || !accounts.length) return null;
  const move = (event, index) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? accounts.length - 1
      : (index + (event.key === "ArrowRight" ? 1 : -1) + accounts.length) % accounts.length;
    onSelect(accounts[next].id);
    window.requestAnimationFrame(() => {
      document.getElementById(`account-tab-${accounts[next].id}`)?.focus();
    });
  };
  return (
    <div className="account-tabs">
      <div className="account-tablist" role="tablist" aria-label="账号列表">
        {accounts.map((account, index) => {
          const selected = activeId === account.id;
          const state = accountStateLabel(account);
          return <button type="button" key={account.id} id={`account-tab-${account.id}`} role="tab"
            aria-selected={selected} aria-controls="monitor-body" tabIndex={selected ? 0 : -1}
            className={`account-tab ${selected ? "active" : ""}`} title={state.label}
            onClick={() => onSelect(account.id)} onKeyDown={(event) => move(event, index)}>
            <span className="tab-avatar" style={{ background: accountColor(account.id) }}>{accountInitial(account.name)}</span>
            <span className="tab-name">{account.name}</span>
            <i className={`tab-state ${state.tone}`} aria-hidden="true" />
            <span className="tab-count">{account.live_room_count || 0}</span>
          </button>;
        })}
        <button type="button" className="account-tab add" onClick={onAdd} title="添加账号" aria-label="添加账号">
          <Icon name="plus" size={15} />
        </button>
      </div>
    </div>
  );
};

const AccountDashboard = () => null;

const AccountSwitcher = ({ open, accounts, activeId, onSelect, onManage, onAdd, onClose }) => {
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
  return (
    <>
      <div className="switcher-scrim open" onClick={onClose} />
      <div className="switcher open" role="menu" aria-label="账号切换器" ref={menu}>
        <div className="switcher-head">
          <strong>切换账号</strong>
          <span>共 {accounts.length} 个账号</span>
        </div>
        {accounts.map((account) => {
          const state = accountStateLabel(account);
          const selected = activeId === account.id;
          return <button type="button" key={account.id} role="menuitemradio" aria-checked={selected}
            className="switcher-item" onClick={() => onSelect(account.id)}>
            <AccountAvatar account={account} size="sm" />
            <span className="switcher-item-main">
              <strong>{account.name}</strong>
              <small className={state.tone === "warn" ? "warn" : ""}>
                {selected ? "当前使用 · 挂机中" : state.label}
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
