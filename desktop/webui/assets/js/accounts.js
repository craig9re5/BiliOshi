/* BiliOshi JSX {"code_sha256":"9c1f9bf11000429889549f129e11d774e95cc8bca1ceab775f3c5b834a81b95f","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"accounts.jsx","source_sha256":"e3dc2fa3914588f20bfb26ef61cee07b2a8143d7694180b6856afc20ac42a250"} */
(function () {
"use strict";
/* Account tabs, the aggregate dashboard and the account switcher.
   Tabs only change the viewed account; running changes stay explicit. */

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
  viewId,
  activeId,
  onView,
  onAdd
}) => {
  const items = [{
    id: "all",
    name: "全部账号",
    state: "muted",
    count: accounts.length
  }].concat(accounts.map(account => ({
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
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + items.length) % items.length;
    onView(items[next].id);
    window.requestAnimationFrame(() => {
      document.getElementById(`account-tab-${items[next].id}`)?.focus();
    });
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "account-tabs"
  }, /*#__PURE__*/React.createElement("div", {
    className: "account-tablist",
    role: "tablist",
    "aria-label": "\u8D26\u53F7"
  }, items.map((item, index) => {
    const selected = viewId === item.id;
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      key: item.id,
      id: `account-tab-${item.id}`,
      role: "tab",
      "aria-selected": selected,
      "aria-controls": "monitor-body",
      tabIndex: selected ? 0 : -1,
      className: `account-tab ${selected ? "active" : ""}`,
      title: item.status || "全部账号",
      onClick: () => onView(item.id),
      onKeyDown: event => move(event, index)
    }, item.id === "all" ? /*#__PURE__*/React.createElement("span", {
      className: "tab-avatar all"
    }, "\u5168") : /*#__PURE__*/React.createElement("span", {
      className: "tab-avatar",
      style: {
        background: accountColor(item.id)
      }
    }, accountInitial(item.name)), /*#__PURE__*/React.createElement("span", {
      className: "tab-name"
    }, item.name), item.id !== "all" && /*#__PURE__*/React.createElement("i", {
      className: `tab-state ${item.state}`,
      "aria-hidden": "true"
    }), /*#__PURE__*/React.createElement("span", {
      className: "tab-count"
    }, item.count || 0));
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
const AccountDashboard = ({
  accounts,
  globalPaused,
  onView,
  onSwitch,
  onCheckAll,
  onPauseAll,
  onResumeAll,
  onRelogin,
  onProtection,
  busy
}) => {
  const running = accounts.filter(account => account.running);
  const liveTotal = running.reduce((sum, account) => sum + (account.live_room_count || 0), 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "dashboard-scroll"
  }, globalPaused && /*#__PURE__*/React.createElement("div", {
    className: "banner neutral",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "pause",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, "\u6240\u6709\u8D26\u53F7\u5DF2\u6682\u505C\u6302\u673A\uFF08\u5168\u5C40\u6682\u505C\uFF09\u3002\u6062\u590D\u65F6\u53EA\u6062\u590D\u6682\u505C\u524D\u6B63\u5728\u8FD0\u884C\u7684\u8D26\u53F7\u3002"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onResumeAll,
    disabled: busy
  }, "\u6062\u590D\u5168\u90E8")), /*#__PURE__*/React.createElement("div", {
    className: "dashboard-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h2", null, "\u8D26\u53F7\u603B\u89C8"), /*#__PURE__*/React.createElement("p", null, globalPaused ? "全局暂停中" : running.length ? `${running.length} 个账号挂机中 · ${liveTotal} 个直播间直播中` : "当前没有账号在挂机")), /*#__PURE__*/React.createElement("div", {
    className: "dash-actions"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onCheckAll,
    disabled: busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 12
  }), "\u5168\u90E8\u68C0\u67E5"), globalPaused ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: onResumeAll,
    disabled: busy
  }, "\u6062\u590D\u5168\u90E8") : running.length ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onPauseAll,
    disabled: busy
  }, "\u5168\u90E8\u6682\u505C") : null)), accounts.length ? /*#__PURE__*/React.createElement("div", {
    className: "account-grid"
  }, accounts.map(account => {
    const state = accountStateLabel(account);
    const needsLogin = !account.signed_in || account.status === "needs_login";
    const protection = account.status === "blocked";
    return /*#__PURE__*/React.createElement("article", {
      key: account.id,
      className: `account-card ${account.running ? "running" : ""}`
    }, /*#__PURE__*/React.createElement("header", null, /*#__PURE__*/React.createElement(AccountAvatar, {
      account: account,
      size: "lg"
    }), /*#__PURE__*/React.createElement("div", {
      className: "account-card-title"
    }, /*#__PURE__*/React.createElement("strong", null, account.name), /*#__PURE__*/React.createElement("span", null, "UID ", account.uid, " \xB7 \u5173\u6CE8 ", account.room_count, " \u4F4D")), /*#__PURE__*/React.createElement("span", {
      className: `status-pill ${state.tone}`
    }, state.label)), /*#__PURE__*/React.createElement("div", {
      className: "account-stats"
    }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("strong", null, account.room_count), /*#__PURE__*/React.createElement("span", null, "\u5173\u6CE8")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("strong", null, account.live_room_count || 0), /*#__PURE__*/React.createElement("span", null, account.running ? "直播中" : "上次直播中")), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("strong", null, account.gain === null || account.gain === undefined ? "—" : "+" + numberLabel(account.gain)), /*#__PURE__*/React.createElement("span", null, "\u4ECA\u65E5\u4EB2\u5BC6\u5EA6"))), needsLogin && /*#__PURE__*/React.createElement("div", {
      className: "card-notice"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "alert",
      size: 13
    }), /*#__PURE__*/React.createElement("span", null, "\u767B\u5F55\u5DF2\u5931\u6548\uFF0C\u65E0\u6CD5\u5F00\u59CB\u6302\u673A"), /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "link-btn",
      onClick: () => onRelogin(account.id)
    }, "\u91CD\u65B0\u626B\u7801")), protection && /*#__PURE__*/React.createElement("div", {
      className: "card-notice"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "shield",
      size: 13
    }), /*#__PURE__*/React.createElement("span", null, "\u8D26\u53F7\u4FDD\u62A4\u6682\u505C\uFF0C\u91CD\u65B0\u626B\u7801\u4E0D\u4F1A\u89E3\u9664"), /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "link-btn",
      onClick: () => onProtection(account.id)
    }, "\u67E5\u770B\u539F\u56E0")), /*#__PURE__*/React.createElement("footer", null, /*#__PURE__*/React.createElement("span", null, "\u4E0A\u6B21\u68C0\u67E5 ", relativeTime(account.snapshot_at)), account.running ? /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "link-btn",
      onClick: () => onView(account.id)
    }, "\u6253\u5F00\u603B\u89C8 \u2192") : needsLogin ? /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "link-btn",
      onClick: () => onRelogin(account.id)
    }, "\u91CD\u65B0\u626B\u7801") : protection ? /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "link-btn",
      onClick: () => onProtection(account.id)
    }, "\u67E5\u770B\u539F\u56E0") : /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "link-btn",
      onClick: () => onSwitch(account.id)
    }, "\u5207\u6362\u5E76\u6302\u673A")));
  })) : /*#__PURE__*/React.createElement("div", {
    className: "empty list-empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "user",
    size: 24
  }), /*#__PURE__*/React.createElement("strong", null, "\u5C1A\u672A\u6DFB\u52A0 B \u7AD9\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", null, "\u626B\u7801\u6DFB\u52A0\u8D26\u53F7\u540E\uFF0C\u6BCF\u4E2A\u8D26\u53F7\u4F1A\u6709\u72EC\u7ACB\u7684\u5173\u6CE8\u5217\u8868\u548C\u76F4\u64AD\u603B\u89C8\u3002")));
};
const AccountSwitcher = ({
  open,
  accounts,
  viewId,
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
  const running = accounts.filter(account => account.running);
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
  }, /*#__PURE__*/React.createElement("strong", null, "\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", null, running.length ? `${running.length} 个挂机中` : "未挂机")), accounts.map(account => {
    const state = accountStateLabel(account);
    const selected = viewId === account.id;
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
    }, state.label, account.id === activeId ? " · 当前挂机" : "")), selected && /*#__PURE__*/React.createElement(Icon, {
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
