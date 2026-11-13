/* BiliOshi JSX {"code_sha256":"d40e9ce69ccbedc762e4598e29022e0765cc6f80803e6f0de327fc741398c703","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"accounts.jsx","source_sha256":"0acfa6aebd569aecfde73770303ba97e810cd74435a33ae3ff26d140e005a458"} */
(function () {
"use strict";
/* Account tabs. One account is displayed and active at a time; switching is
   instant, so a tab click also has to say what will happen. */

const {
  Icon
} = window;
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
  if (!account) return {
    label: "未运行",
    tone: "muted"
  };
  if (account.status === "blocked") return {
    label: "保护暂停",
    tone: "warn"
  };
  if (!account.signed_in || account.status === "needs_login") return {
    label: "登录失效",
    tone: "warn"
  };
  if (account.global_paused) return {
    label: "全局暂停",
    tone: "muted"
  };
  if (account.running) return {
    label: "挂机中",
    tone: "live"
  };
  if (account.paused) return {
    label: "已暂停",
    tone: "muted"
  };
  return {
    label: "未运行",
    tone: "muted"
  };
}
const AccountAvatar = ({
  account,
  size = "sm",
  image
}) => {
  if (!account) return /*#__PURE__*/React.createElement("span", {
    className: `avatar ${size}`,
    style: {
      background: "var(--accent-soft)",
      color: "var(--accent)"
    }
  }, "\u5168");
  return /*#__PURE__*/React.createElement("span", {
    className: `avatar ${size}`,
    style: {
      background: accountColor(account.id)
    },
    "aria-hidden": "true"
  }, image ? /*#__PURE__*/React.createElement("img", {
    src: image,
    alt: ""
  }) : accountInitial(account.name));
};
const AccountTabs = ({
  accounts,
  activeId,
  avatars = {},
  onSelect,
  onAdd
}) => {
  if (!accounts || !accounts.length) return null;
  const move = (event, index) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? accounts.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + accounts.length) % accounts.length;
    onSelect(accounts[next].id);
    window.requestAnimationFrame(() => {
      document.getElementById(`account-tab-${accounts[next].id}`)?.focus();
    });
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "account-tabs"
  }, /*#__PURE__*/React.createElement("div", {
    className: "account-tablist",
    role: "tablist",
    "aria-label": "\u8D26\u53F7\u5217\u8868"
  }, accounts.map((account, index) => {
    const selected = activeId === account.id;
    const state = accountStateLabel(account);
    const image = avatars[account.id];
    const live = account.live_room_count || 0;
    const liveText = live ? ` · ${live} 个开播` : "";
    const actionText = selected ? "当前使用" : "点击切换";
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      key: account.id,
      id: `account-tab-${account.id}`,
      role: "tab",
      "aria-selected": selected,
      "aria-controls": "monitor-body",
      tabIndex: selected ? 0 : -1,
      className: `account-tab ${selected ? "active" : ""}`,
      title: `${account.name} · ${state.label}${liveText}（${actionText}）`,
      "aria-label": `${account.name} · ${state.label}${liveText}`,
      onClick: () => onSelect(account.id),
      onKeyDown: event => move(event, index)
    }, /*#__PURE__*/React.createElement("span", {
      className: "tab-avatar",
      style: {
        background: accountColor(account.id)
      },
      "aria-hidden": "true"
    }, image ? /*#__PURE__*/React.createElement("img", {
      src: image,
      alt: ""
    }) : accountInitial(account.name)), /*#__PURE__*/React.createElement("span", {
      className: "tab-name"
    }, account.name), /*#__PURE__*/React.createElement("i", {
      className: `tab-state ${state.tone}`,
      "aria-hidden": "true"
    }), live > 0 && /*#__PURE__*/React.createElement("span", {
      className: "tab-count",
      title: "\u76F4\u64AD\u4E2D\u7684\u76F4\u64AD\u95F4\u6570"
    }, live));
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "account-tab add",
    onClick: onAdd,
    title: "\u6DFB\u52A0\u8D26\u53F7",
    "aria-label": "\u6DFB\u52A0\u8D26\u53F7"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 15
  }))));
};
Object.assign(window, {
  AccountTabs,
  AccountAvatar,
  accountStateLabel,
  accountColor,
  accountInitial
});
})();
