/* BiliOshi JSX {"code_sha256":"2bc214e8194c9c929d09d8354bea5697e6d1c2334006e681129850ee5ae2c389","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"settings.jsx","source_sha256":"17881edd1f2deb1449839aa3f7cb2d9278dd306ba87e538de5ac4ce1a160956b"} */
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
  key: "system",
  name: "跟随系统",
  hint: "随系统深浅外观切换"
}, {
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
}, {
  key: "dark",
  name: "墨青暗",
  hint: "夜间深色"
}];
const useSystemDark = () => {
  const [dark, setDark] = useState(() => typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = event => setDark(Boolean(event.matches));
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
  value,
  onChange,
  systemDark
}) => /*#__PURE__*/React.createElement("div", {
  className: "theme-options",
  role: "group",
  "aria-label": "\u754C\u9762\u4E3B\u9898"
}, THEME_CHOICES.map(theme => {
  const active = theme.key === value;
  const hint = theme.key === "system" ? `当前${systemDark ? "深色" : "浅色"}` : theme.hint;
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    key: theme.key,
    className: "theme-option",
    "data-theme": theme.key,
    "aria-pressed": active,
    title: `${theme.name} · ${hint}`,
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
  theme = "system",
  onTheme,
  scope,
  onLogs,
  onHostLogs,
  onDiagnostics,
  version
}) => {
  const systemDark = useSystemDark();
  const disabled = key => pendingSettings.has(key);
  const runMode = settings.run_mode || "stable";
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u8BBE\u7F6E"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u6BCF\u65E5\u4EFB\u52A1"), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    desc: "\u724C\u5B50\u7184\u706D\u65F6\u53D1\u9001\u5F39\u5E55\u91CD\u65B0\u70B9\u4EAE"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    checked: settings.auto_revive,
    disabled: disabled("auto_revive"),
    onChange: value => onSetting("auto_revive", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    desc: "\u81EA\u52A8\u8865\u9F50\u6BCF\u65E5\u5F39\u5E55\u4EB2\u5BC6\u5EA6\u4EFB\u52A1"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    checked: settings.auto_danmaku_intimacy,
    disabled: disabled("auto_danmaku_intimacy"),
    onChange: value => onSetting("auto_danmaku_intimacy", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u76F4\u64AD\u70B9\u8D5E",
    desc: "\u8FDB\u5165\u5F00\u64AD\u76F4\u64AD\u95F4\u540E\u81EA\u52A8\u5B8C\u6210\u70B9\u8D5E"
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
    desc: "\u5173\u6CE8\u7684\u4E3B\u64AD\u5F00\u64AD\u65F6\u5F39\u51FA\u7CFB\u7EDF\u63D0\u9192"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u64AD\u901A\u77E5",
    checked: settings.notify_on_live,
    disabled: disabled("notify_on_live"),
    onChange: value => onSetting("notify_on_live", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F00\u673A\u542F\u52A8",
    desc: "\u767B\u5F55\u7CFB\u7EDF\u540E\u5728\u6258\u76D8\u9759\u9ED8\u8FD0\u884C"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u673A\u542F\u52A8",
    checked: settings.autostart,
    disabled: disabled("autostart"),
    onChange: value => onSetting("autostart", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u8FD0\u884C\u6A21\u5F0F",
    desc: "\u7A33\u5065\u6A21\u5F0F\u63A8\u8350\u65E5\u5E38\u6302\u673A\uFF1B\u6FC0\u8FDB\u6A21\u5F0F\u68C0\u6D4B\u66F4\u9891\u7E41"
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
  }))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u65E5\u5FD7\u4E0E\u8BCA\u65AD\u53CD\u9988"), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u8FD0\u884C\u65E5\u5FD7",
    desc: scope ? "可分别查看当前账号挂机日志或主程序全局日志" : "打开日志文件所在目录，便于排障"
  }, /*#__PURE__*/React.createElement("div", {
    className: "btn-row"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onLogs
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "folder",
    size: 13
  }), scope ? "账号日志" : "查看日志"), scope && onHostLogs && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onHostLogs
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "folder",
    size: 13
  }), "\u4E3B\u7A0B\u5E8F\u65E5\u5FD7"))), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u4E00\u952E\u5BFC\u51FA\u8BCA\u65AD\u5305",
    desc: "\u6253\u5305\u65E5\u5FD7\u3001\u8FD1\u671F\u62A5\u9519\u4E0E\u73AF\u5883\u6458\u8981\uFF0C\u81EA\u52A8\u79FB\u9664\u51ED\u8BC1\u5E76\u9ED8\u8BA4\u533F\u540D\u5316\u8EAB\u4EFD"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: onDiagnostics
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), "\u5BFC\u51FA\u8BCA\u65AD\u5305")), version && /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u7248\u672C\u4FE1\u606F",
    desc: "\u63D0\u4EA4\u95EE\u9898\u53CD\u9988\u65F6\u5EFA\u8BAE\u9644\u5E26\u7248\u672C\u53F7\u4E0E\u8131\u654F\u8BCA\u65AD\u5305"
  }, /*#__PURE__*/React.createElement("span", {
    className: "version-pill"
  }, "v", version))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head"
  }, "\u5916\u89C2"), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u754C\u9762\u4E3B\u9898",
    desc: theme === "system" ? `跟随系统，当前为${systemDark ? "深色" : "浅色"}外观` : "自定义应用配色风格"
  }, /*#__PURE__*/React.createElement(ThemeOptions, {
    value: theme,
    onChange: onTheme,
    systemDark: systemDark
  }))))));
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
  const protection = account.status === "blocked" || Boolean(account.safety?.blocked);
  const issueText = protection ? account.safety?.reason || "账号操作已暂停，需在平台处理" : needsLogin ? "登录已失效，请重新扫码" : null;
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
  }, "UID ", account.uid), issueText && /*#__PURE__*/React.createElement("div", {
    className: "account-item-sub warn"
  }, issueText)), /*#__PURE__*/React.createElement("div", {
    className: "account-item-actions"
  }, protection && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onProtection(account.id)
  }, "\u67E5\u770B\u539F\u56E0"), needsLogin && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: () => onScan(account.id)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "qr",
    size: 12
  }), "\u91CD\u65B0\u626B\u7801"), !isActive && !needsLogin && !protection && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: () => onSwitch(account.id),
    disabled: busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 12
  }), "\u5207\u6362\u8D26\u53F7"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onLogout(account.id),
    disabled: busy,
    title: needsLogin ? "清除本机保存的失效登录凭证" : "退出此账号登录",
    "aria-label": `${needsLogin ? "清除" : "退出"} ${account.name} 的登录`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "power",
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, needsLogin ? "清除登录" : "退出登录")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm danger-hover",
    onClick: () => onRemove(account.id),
    disabled: busy,
    title: "\u79FB\u9664\u8D26\u53F7",
    "aria-label": `移除 ${account.name}`
  }, /*#__PURE__*/React.createElement("span", null, "\u79FB\u9664"))));
};
const AccountPage = ({
  accounts,
  activeId,
  account,
  avatar,
  avatars = {},
  onScan,
  onView,
  onSwitch,
  onLogout,
  onRemove,
  onProtection,
  onResumeSafety,
  onCheckSafety,
  safetyProbe,
  onCheck,
  busy,
  version
}) => {
  const hold = account.safety || {};
  const cooldown = hold.blocked && hold.until > Date.now() / 1000;
  const needsLogin = hold.kind === "auth" || hold.kind === "credentials";
  const checkingSafety = Boolean(safetyProbe?.loading);
  const locationParts = [hold.room_label, hold.operation_label].filter(Boolean);
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u8D26\u53F7"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head group-head-action"
  }, /*#__PURE__*/React.createElement("span", {
    className: "group-head-title"
  }, "B \u7AD9\u8D26\u53F7"), /*#__PURE__*/React.createElement("button", {
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
    image: item.id === activeId ? avatar || avatars[item.id] : avatars[item.id],
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
  }), /*#__PURE__*/React.createElement("strong", null, "\u5C1A\u672A\u6DFB\u52A0 B \u7AD9\u8D26\u53F7"), /*#__PURE__*/React.createElement("button", {
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
  }, "\u8D26\u53F7\u5B89\u5168"), /*#__PURE__*/React.createElement("div", {
    className: "safety-row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "safety-info"
  }, /*#__PURE__*/React.createElement("div", {
    className: "safety-status"
  }, /*#__PURE__*/React.createElement("i", {
    className: `status-dot ${hold.blocked ? "warn" : "ok"}`
  }), /*#__PURE__*/React.createElement("strong", null, hold.blocked ? hold.kind_label || "保护暂停中" : "状态正常", hold.blocked && hold.code !== undefined && hold.code !== null && `（错误码 ${hold.code}）`), hold.blocked && hold.reason && /*#__PURE__*/React.createElement("span", {
    className: "safety-reason"
  }, hold.reason)), hold.blocked && locationParts.length > 0 && /*#__PURE__*/React.createElement("small", {
    className: "safety-time"
  }, "\u89E6\u53D1\u4F4D\u7F6E\uFF1A", locationParts.join(" · ")), cooldown && /*#__PURE__*/React.createElement("small", {
    className: "safety-time"
  }, "\u6700\u65E9\u81EA\u52A8\u6062\u590D\uFF1A", absoluteTime(hold.until)), !cooldown && hold.blocked && hold.next_probe_at && /*#__PURE__*/React.createElement("small", {
    className: "safety-time"
  }, "\u4E0B\u6B21\u81EA\u52A8\u590D\u68C0\uFF1A", absoluteTime(hold.next_probe_at))), /*#__PURE__*/React.createElement("div", {
    className: "safety-actions"
  }, (!account.signed_in || needsLogin) && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: () => onScan(),
    disabled: busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "qr",
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, "\u626B\u7801\u767B\u5F55")), account.signed_in && !needsLogin && hold.blocked && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onResumeSafety(),
    disabled: busy || checkingSafety
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "shield",
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, "\u67E5\u770B\u8BE6\u60C5\u4E0E\u6392\u67E5")), !cooldown && onCheckSafety && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: () => onCheckSafety(true),
    disabled: busy || checkingSafety
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, checkingSafety ? "检测中…" : "检测并恢复"))), account.signed_in && !needsLogin && !hold.blocked && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onCheck(),
    disabled: busy
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, "\u7ACB\u5373\u68C0\u67E5"))))), version && /*#__PURE__*/React.createElement("div", {
    className: "page-foot-version"
  }, "\u30D3\u30EA\u63A8\u3057 v", version))));
};
Object.assign(window, {
  SettingsPage,
  AccountPage,
  AccountRow,
  Switch,
  SettingRow
});
})();
