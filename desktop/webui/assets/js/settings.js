/* BiliOshi JSX {"code_sha256":"7b74bcf7a996259d19dfbb2583c537942a3c62a39a58c3b9a8dcdd9110049c24","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"settings.jsx","source_sha256":"a6427d936e1311faad794d79bad4c64160f15b3825b2caedcb09cac7b86aa04b"} */
(function () {
"use strict";
/* Settings use the same vocabulary as the overview; changes apply through Python. */

const {
  useState,
  useEffect,
  useRef
} = React;
const {
  Icon,
  relativeTime,
  absoluteTime,
  numberLabel
} = window;
const Switch = ({
  checked,
  onChange,
  label,
  disabled
}) => /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "switch",
  role: "switch",
  "aria-checked": Boolean(checked),
  "aria-label": label,
  disabled: disabled,
  onClick: () => onChange(!checked)
});
const SettingRow = ({
  name,
  desc,
  children
}) => /*#__PURE__*/React.createElement("div", {
  className: "setting"
}, /*#__PURE__*/React.createElement("div", {
  className: "setting-text"
}, /*#__PURE__*/React.createElement("div", {
  className: "setting-name"
}, name), desc && /*#__PURE__*/React.createElement("div", {
  className: "setting-desc"
}, desc)), children);

/* A compact trigger plus a themed menu. The native select rendered its own
   system popup, which did not follow the card surfaces or spacing. */
const Choice = ({
  value,
  options,
  onChange,
  label,
  disabled
}) => {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const menu = useRef(null);
  const selected = Math.max(0, options.findIndex(option => option.value === value));
  useEffect(() => {
    if (!open) return undefined;
    const dismiss = event => {
      if (!root.current?.contains(event.target)) setOpen(false);
    };
    const escape = event => {
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
    const next = event.key === "Home" ? 0 : event.key === "End" ? nodes.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + nodes.length) % nodes.length;
    nodes[next]?.focus();
  };
  return /*#__PURE__*/React.createElement("div", {
    className: `choice ${open ? "open" : ""}`,
    ref: root
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "choice-button",
    ref: trigger,
    "aria-haspopup": "listbox",
    "aria-expanded": open,
    "aria-label": label,
    disabled: disabled,
    onClick: () => setOpen(current => !current),
    onKeyDown: event => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        setOpen(true);
      }
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "choice-label"
  }, options[selected]?.label), /*#__PURE__*/React.createElement(Icon, {
    name: "chevron",
    size: 12
  })), open && /*#__PURE__*/React.createElement("div", {
    className: "choice-menu",
    role: "listbox",
    "aria-label": label,
    ref: menu
  }, options.map((option, index) => /*#__PURE__*/React.createElement("button", {
    type: "button",
    key: option.value,
    className: "choice-option",
    role: "option",
    "data-value": option.value,
    "aria-selected": option.value === value,
    onKeyDown: event => moveFocus(event, index),
    onClick: () => {
      setOpen(false);
      if (option.value !== value) onChange(option.value);
      trigger.current?.focus();
    }
  }, /*#__PURE__*/React.createElement("span", null, option.label), option.value === value && /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 12
  })))));
};
const THEME_CHOICES = [{
  key: "white",
  name: "纸白",
  hint: "中性纸面"
}, {
  key: "paper",
  name: "暖纸白",
  hint: "温和纸感"
}, {
  key: "mist",
  name: "雾青灰",
  hint: "清爽青灰"
}, {
  key: "apricot",
  name: "暖杏灰",
  hint: "温暖柔和"
}];
const ThemeOptions = ({
  value,
  onChange
}) => /*#__PURE__*/React.createElement("div", {
  className: "theme-options",
  role: "group",
  "aria-label": "\u754C\u9762\u4E3B\u9898"
}, THEME_CHOICES.map(theme => {
  const active = theme.key === value;
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    key: theme.key,
    className: "theme-option",
    "data-theme": theme.key,
    "aria-pressed": active,
    title: `${theme.name} · ${theme.hint}`,
    onClick: () => onChange(theme.key)
  }, /*#__PURE__*/React.createElement("span", {
    className: `theme-chip ${theme.key}`,
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("span", {
    className: "theme-name"
  }, theme.name), active && /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 11
  }));
}));
const SettingsPage = ({
  settings,
  onSetting,
  pendingSettings,
  theme = "white",
  onTheme,
  scope,
  scopeAll,
  onLogs
}) => {
  const disabled = key => pendingSettings.has(key);
  const runMode = settings.run_mode || "stable";
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u8BBE\u7F6E"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("div", {
    className: "scope-bar"
  }, /*#__PURE__*/React.createElement("span", {
    className: "scope-label"
  }, "\u5F53\u524D\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", {
    className: "scope-chip"
  }, scope ? /*#__PURE__*/React.createElement(window.AccountAvatar, {
    account: scope,
    size: "sm"
  }) : null, scope ? scope.name : "未登录"), /*#__PURE__*/React.createElement("span", {
    className: "scope-note"
  }, "\u4EFB\u52A1\u5F00\u5173\u4E0E\u8FD0\u884C\u6A21\u5F0F\u6309\u8D26\u53F7\u72EC\u7ACB\u4FDD\u5B58\uFF1B\u754C\u9762\u4E3B\u9898\u4E0E\u5F00\u673A\u542F\u52A8\u5168\u5E94\u7528\u751F\u6548")), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u6BCF\u65E5\u4EFB\u52A1", /*#__PURE__*/React.createElement("small", null, "\u5F00\u64AD\u540E\uFF0C\u6309 B \u7AD9\u7684\u4EFB\u52A1\u8FDB\u5EA6\u81EA\u52A8\u5B8C\u6210")), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    desc: "\u7C89\u4E1D\u724C\u7184\u706D\u65F6\u53D1\u9001\u5F39\u5E55\uFF0C\u70B9\u4EAE\u540E\u505C\u6B62"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    checked: settings.auto_revive,
    disabled: disabled("auto_revive"),
    onChange: value => onSetting("auto_revive", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    desc: "\u53EA\u8865\u9F50\u5269\u4F59\u5F39\u5E55\uFF0C\u5B8C\u6210\u540E\u505C\u6B62"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    checked: settings.auto_danmaku_intimacy,
    disabled: disabled("auto_danmaku_intimacy"),
    onChange: value => onSetting("auto_danmaku_intimacy", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u76F4\u64AD\u70B9\u8D5E",
    desc: "\u81EA\u52A8\u70B9\u8D5E\u5E76\u68C0\u67E5\u4EFB\u52A1\u8FDB\u5EA6\uFF0C\u9ED8\u8BA4\u5173\u95ED"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u76F4\u64AD\u70B9\u8D5E",
    checked: settings.auto_like,
    disabled: disabled("auto_like"),
    onChange: value => onSetting("auto_like", value)
  }))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u8FD0\u884C\u4E0E\u542F\u52A8"), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F00\u64AD\u901A\u77E5",
    desc: "\u5173\u6CE8\u7684\u4E3B\u64AD\u5F00\u64AD\u65F6\uFF0C\u901A\u8FC7\u7CFB\u7EDF\u901A\u77E5\u63D0\u9192"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u64AD\u901A\u77E5",
    checked: settings.notify_on_live,
    disabled: disabled("notify_on_live"),
    onChange: value => onSetting("notify_on_live", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F00\u673A\u542F\u52A8",
    desc: "\u767B\u5F55 Windows \u540E\u5728\u6258\u76D8\u8FD0\u884C\uFF0C\u4E0D\u6253\u5F00\u4E3B\u7A97\u53E3"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u673A\u542F\u52A8",
    checked: settings.autostart,
    disabled: disabled("autostart"),
    onChange: value => onSetting("autostart", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u8FD0\u884C\u6A21\u5F0F",
    desc: "\u7A33\u5065\uFF1A5 \u5206\u949F\u67E5\u5F00\u64AD\u300160 \u79D2\u7EED\u70B9\u8D5E\uFF1B\u6FC0\u8FDB\uFF1A1 \u5206\u949F\u67E5\u5F00\u64AD\u300120 \u79D2\u7EED\u70B9\u8D5E"
  }, /*#__PURE__*/React.createElement(Choice, {
    label: "\u8FD0\u884C\u6A21\u5F0F",
    value: runMode,
    disabled: disabled("run_mode"),
    options: [{
      value: "stable",
      label: "稳健"
    }, {
      value: "aggressive",
      label: "激进"
    }],
    onChange: value => onSetting("run_mode", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u8FD0\u884C\u65E5\u5FD7",
    desc: "\u5728\u6587\u4EF6\u8D44\u6E90\u7BA1\u7406\u5668\u4E2D\u6253\u5F00\u5F53\u524D\u8D26\u53F7\u7684\u65E5\u5FD7\u76EE\u5F55\uFF0C\u6392\u67E5\u5F02\u5E38\u6216\u67E5\u770B\u8FD0\u884C\u8BB0\u5F55"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onLogs
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "folder",
    size: 13
  }), "\u67E5\u770B\u65E5\u5FD7"))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u5916\u89C2"), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u754C\u9762\u4E3B\u9898",
    desc: "\u9009\u62E9\u754C\u9762\u8868\u9762\u989C\u8272\uFF0C\u5207\u6362\u540E\u7ACB\u5373\u751F\u6548\u5E76\u8BB0\u4F4F\u9009\u62E9\uFF08\u5168\u5E94\u7528\uFF0C\u4E0D\u968F\u8D26\u53F7\u5207\u6362\uFF09"
  }, /*#__PURE__*/React.createElement(ThemeOptions, {
    value: theme,
    onChange: onTheme
  }))), /*#__PURE__*/React.createElement("p", {
    className: "settings-note"
  }, "\u8FD0\u884C\u6A21\u5F0F\u4FDD\u5B58\u540E\u7ACB\u5373\u751F\u6548\u3002\u5F53\u5929\u7684\u5DF2\u5B8C\u6210\u8FDB\u5EA6\u4E0E\u53D1\u9001\u989D\u5EA6\u4F1A\u4FDD\u7559\u3002\u4EFB\u52A1\u5F00\u5173\u4E0E\u8FD0\u884C\u6A21\u5F0F\u6309\u8D26\u53F7\u72EC\u7ACB\u4FDD\u5B58\u3002"))));
};
const AccountRow = ({
  account,
  isActive,
  image,
  onView,
  onSwitch,
  onScan,
  onLogout,
  onRemove,
  onProtection,
  busy
}) => {
  const state = window.accountStateLabel(account);
  const needsLogin = !account.signed_in || account.status === "needs_login";
  const protection = account.status === "blocked";
  let action = null;
  if (protection) {
    action = /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn sm",
      onClick: () => onProtection(account.id)
    }, "\u67E5\u770B\u539F\u56E0");
  } else if (needsLogin) {
    action = /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn sm primary",
      onClick: () => onScan(account.id)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "qr",
      size: 12
    }), "\u91CD\u65B0\u626B\u7801");
  } else if (isActive) {
    action = /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn sm",
      onClick: () => onView(account.id)
    }, "\u67E5\u770B\u603B\u89C8");
  } else {
    action = /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn sm primary",
      onClick: () => onSwitch(account.id)
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "play",
      size: 12
    }), "\u5207\u6362\u8D26\u53F7");
  }
  const note = protection ? account.safety?.reason || "账号操作已暂停，重新扫码不会解除" : needsLogin ? "登录已失效，其他账号不受影响" : isActive ? account.paused ? "已暂停挂机，关注与今日额度已保留" : "当前使用中 · 上次检查 " + relativeTime(account.snapshot_at) : "点击切换账号后即可使用此账号挂机";
  return /*#__PURE__*/React.createElement("div", {
    className: `account-item ${isActive ? "current" : ""}`
  }, /*#__PURE__*/React.createElement(window.AccountAvatar, {
    account: account,
    size: "lg",
    image: image
  }), /*#__PURE__*/React.createElement("div", {
    className: "account-item-main"
  }, /*#__PURE__*/React.createElement("div", {
    className: "account-item-title"
  }, /*#__PURE__*/React.createElement("strong", null, account.name), isActive && /*#__PURE__*/React.createElement("span", {
    className: "mini-tag live"
  }, "\u5F53\u524D\u4F7F\u7528"), !isActive && !needsLogin && !protection && /*#__PURE__*/React.createElement("span", {
    className: `mini-tag ${state.tone}`
  }, state.label), needsLogin && /*#__PURE__*/React.createElement("span", {
    className: "mini-tag warn"
  }, "\u9700\u8981\u91CD\u65B0\u626B\u7801"), protection && /*#__PURE__*/React.createElement("span", {
    className: "mini-tag warn"
  }, "\u9700\u5728\u5E73\u53F0\u5904\u7406")), /*#__PURE__*/React.createElement("div", {
    className: "account-item-meta"
  }, "UID ", account.uid, " \xB7 \u5173\u6CE8 ", account.room_count, " \xB7 ", account.live_room_count || 0, " \u4E2A\u76F4\u64AD \xB7 \u4ECA\u65E5 ", account.gain === null || account.gain === undefined ? "—" : "+" + numberLabel(account.gain)), /*#__PURE__*/React.createElement("div", {
    className: `account-item-sub ${needsLogin || protection ? "warn" : ""}`
  }, note)), /*#__PURE__*/React.createElement("div", {
    className: "account-item-actions"
  }, action, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm icon-only",
    onClick: () => onLogout(account.id),
    disabled: busy || needsLogin,
    title: "\u9000\u51FA\u6B64\u8D26\u53F7\u767B\u5F55",
    "aria-label": `退出 ${account.name} 的登录`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "power",
    size: 13
  })), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm icon-only",
    onClick: () => onRemove(account.id),
    disabled: busy,
    title: "\u79FB\u9664\u8D26\u53F7",
    "aria-label": `移除 ${account.name}`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "more",
    size: 15
  }))));
};
const AccountPage = ({
  accounts,
  activeId,
  account,
  avatar,
  onScan,
  onView,
  onSwitch,
  onLogout,
  onRemove,
  onProtection,
  onResumeSafety,
  onCheck,
  busy,
  version
}) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const action = !account.signed_in || needsLogin ? onScan : cooldown ? null : hold.blocked ? onResumeSafety : onCheck;
  const actionLabel = !account.signed_in || needsLogin ? "扫码登录" : cooldown ? "等待自动恢复" : hold.blocked ? "确认并恢复" : "检查状态";
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u8D26\u53F7"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head with-action"
  }, /*#__PURE__*/React.createElement("div", null, "B \u7AD9\u8D26\u53F7", /*#__PURE__*/React.createElement("small", null, "\u6BCF\u4E2A\u8D26\u53F7\u72EC\u7ACB\u4FDD\u5B58\u767B\u5F55\u51ED\u8BC1\u3001\u5173\u6CE8\u5217\u8868\u548C\u4EFB\u52A1\u8FDB\u5EA6")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary sm",
    onClick: () => onScan(""),
    disabled: busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 13
  }), "\u6DFB\u52A0\u8D26\u53F7")), accounts.length ? accounts.map(item => /*#__PURE__*/React.createElement(AccountRow, {
    key: item.id,
    account: item,
    isActive: item.id === activeId,
    image: item.id === activeId ? avatar : undefined,
    onView: onView,
    onSwitch: onSwitch,
    onScan: onScan,
    onLogout: onLogout,
    onRemove: onRemove,
    onProtection: onProtection,
    busy: busy
  })) : /*#__PURE__*/React.createElement("div", {
    className: "empty list-empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "user",
    size: 24
  }), /*#__PURE__*/React.createElement("strong", null, "\u5C1A\u672A\u6DFB\u52A0 B \u7AD9\u8D26\u53F7"), /*#__PURE__*/React.createElement("span", null, "\u626B\u7801\u6DFB\u52A0\u8D26\u53F7\u540E\uFF0C\u53EF\u4EE5\u5728\u8FD9\u91CC\u7BA1\u7406\u767B\u5F55\u72B6\u6001\u4E0E\u6302\u673A\u7B56\u7565\u3002"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary sm",
    onClick: () => onScan("")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "qr",
    size: 12
  }), "\u626B\u7801\u6DFB\u52A0\u8D26\u53F7"))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u8D26\u53F7\u4FDD\u62A4"), /*#__PURE__*/React.createElement(SettingRow, {
    name: hold.blocked ? "操作已暂停" : account.signed_in ? "未触发保护" : "等待登录",
    desc: hold.blocked ? hold.reason || "账号出现异常，已暂停互动操作" : "遇到账号异常或请求结果不确定时，自动暂停互动"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => action?.(),
    disabled: !action || busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: needsLogin ? "qr" : "shield",
    size: 13
  }), actionLabel)), cooldown && /*#__PURE__*/React.createElement("p", {
    className: "settings-note inside"
  }, "\u6700\u65E9\u6062\u590D\u65F6\u95F4\uFF1A", absoluteTime(hold.until), "\u3002\u51B7\u5374\u7ED3\u675F\u540E\u4F1A\u81EA\u52A8\u68C0\u67E5\u3002")), /*#__PURE__*/React.createElement("p", {
    className: "settings-note"
  }, "\u30D3\u30EA\u63A8\u3057 ", version || "", " \xB7 \u5173\u95ED\u7A97\u53E3\u540E\u7EE7\u7EED\u5728\u6258\u76D8\u8FD0\u884C \xB7 \u5207\u6362\u8D26\u53F7\u65E0\u9700\u91CD\u65B0\u626B\u7801"))));
};
Object.assign(window, {
  SettingsPage,
  AccountPage,
  AccountRow,
  Switch,
  SettingRow
});
})();
