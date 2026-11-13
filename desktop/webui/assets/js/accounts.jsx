/* Account tabs. One account is displayed and active at a time; switching is
   instant, so a tab click also has to say what will happen. */

const { Icon } = window;

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

const AccountTabs = ({ accounts, activeId, avatars = {}, onSelect, onAdd }) => {
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
          const image = avatars[account.id];
          const live = account.live_room_count || 0;
          const liveText = live ? ` · ${live} 个开播` : "";
          const actionText = selected ? "当前使用" : "点击切换";
          return <button type="button" key={account.id} id={`account-tab-${account.id}`} role="tab"
            aria-selected={selected} aria-controls="monitor-body" tabIndex={selected ? 0 : -1}
            className={`account-tab ${selected ? "active" : ""}`}
            title={`${account.name} · ${state.label}${liveText}（${actionText}）`}
            aria-label={`${account.name} · ${state.label}${liveText}`}
            onClick={() => onSelect(account.id)} onKeyDown={(event) => move(event, index)}>
            <span className="tab-avatar" style={{ background: accountColor(account.id) }} aria-hidden="true">
              {image ? <img src={image} alt="" /> : accountInitial(account.name)}
            </span>
            <span className="tab-name">{account.name}</span>
            <i className={`tab-state ${state.tone}`} aria-hidden="true" />
            {live > 0 && <span className="tab-count" title="直播中的直播间数">{live}</span>}
          </button>;
        })}
        <button type="button" className="account-tab add" onClick={onAdd} title="添加账号" aria-label="添加账号">
          <Icon name="plus" size={15} />
        </button>
      </div>
    </div>
  );
};

Object.assign(window, { AccountTabs, AccountAvatar, accountStateLabel, accountColor, accountInitial });
