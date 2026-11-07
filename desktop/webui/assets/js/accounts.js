/* BiliOshi JSX {"code_sha256":"d1f7154b717c68326d08f7959b1df6ce05a87062c94fef36cdf3771d2959482b","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"accounts.jsx","source_sha256":"9b95debc4ae06f7cb69018fcaaeabf26f30c8f376ab25cabf761f22b99e85db8"} */
(function () {
"use strict";
/* Account tabs and the account switcher.
   One account is displayed and active at a time; switching is instant. */

const {
  Icon,
  relativeTime,
  numberLabel
} = window;
const {
  useEffect,
  useRef
} = React;
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
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      key: account.id,
      id: `account-tab-${account.id}`,
      role: "tab",
      "aria-selected": selected,
      "aria-controls": "monitor-body",
      tabIndex: selected ? 0 : -1,
      className: `account-tab ${selected ? "active" : ""}`,
      title: state.label,
      onClick: () => onSelect(account.id),
      onKeyDown: event => move(event, index)
    }, /*#__PURE__*/React.createElement("span", {
      className: "tab-avatar",
      style: {
        background: accountColor(account.id)
      }
    }, accountInitial(account.name)), /*#__PURE__*/React.createElement("span", {
      className: "tab-name"
    }, account.name), /*#__PURE__*/React.createElement("i", {
      className: `tab-state ${state.tone}`,
      "aria-hidden": "true"
    }), /*#__PURE__*/React.createElement("span", {
      className: "tab-count"
    }, account.live_room_count || 0));
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
const AccountDashboard = () => null;
const AccountSwitcher = ({
  open,
  accounts,
  activeId,
  onSelect,
  onManage,
  onAdd,
  onClose
}) => {
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
    const keydown = event => {
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
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : index < 0 ? 0 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
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
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "switcher-scrim open",
    onClick: onClose
  }), /*#__PURE__*/React.createElement("div", {
    className: "switcher open",
    role: "menu",
    "aria-label": "\u8D26\u53F7\u5207\u6362\u5668",
    ref: menu
  }, /*#__PURE__*/React.createElement("div", {
    className: "switcher-head"
  }, /*#__PURE__*/React.createElement("strong", null, "\u5207\u6362\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", null, "\u5171 ", accounts.length, " \u4E2A\u8D26\u53F7")), accounts.map(account => {
    const state = accountStateLabel(account);
    const selected = activeId === account.id;
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      key: account.id,
      role: "menuitemradio",
      "aria-checked": selected,
      className: "switcher-item",
      onClick: () => onSelect(account.id)
    }, /*#__PURE__*/React.createElement(AccountAvatar, {
      account: account,
      size: "sm"
    }), /*#__PURE__*/React.createElement("span", {
      className: "switcher-item-main"
    }, /*#__PURE__*/React.createElement("strong", null, account.name), /*#__PURE__*/React.createElement("small", {
      className: state.tone === "warn" ? "warn" : ""
    }, selected ? "当前使用 · 挂机中" : state.label)), selected && /*#__PURE__*/React.createElement(Icon, {
      name: "check",
      size: 13
    }));
  }), !accounts.length && /*#__PURE__*/React.createElement("p", {
    className: "switcher-mode"
  }, "\u5C1A\u672A\u6DFB\u52A0\u8D26\u53F7\u3002"), /*#__PURE__*/React.createElement("div", {
    className: "switcher-foot"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    onClick: onManage
  }, "\u7BA1\u7406\u8D26\u53F7"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    onClick: onAdd
  }, "\u6DFB\u52A0\u8D26\u53F7"))));
};
Object.assign(window, {
  AccountTabs,
  AccountDashboard,
  AccountSwitcher,
  AccountAvatar,
  accountStateLabel,
  accountColor,
  accountInitial
});
})();
