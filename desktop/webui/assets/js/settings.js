/* BiliOshi JSX {"code_sha256":"51e9982b48b492d6fac984a27e46164b71e9fd789930f21ba2d4c9ca19aed89e","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"settings.jsx","source_sha256":"8836eff41f7e0bbff984bcd54818eb17c34b934f005dba34f792c1e95ae46fec"} */
(function () {
"use strict";
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Settings use the same vocabulary as the overview; changes apply through Python. */

const {
  useState,
  useEffect,
  useLayoutEffect,
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
  className = "",
  children
}) => /*#__PURE__*/React.createElement("div", {
  className: `setting${className ? ` ${className}` : ""}`
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
  const [flipUp, setFlipUp] = useState(false);
  const root = useRef(null);
  const trigger = useRef(null);
  const menu = useRef(null);
  const selected = Math.max(0, options.findIndex(option => option.value === value));
  useLayoutEffect(() => {
    if (!open || !trigger.current || !menu.current) return;
    const triggerRect = trigger.current.getBoundingClientRect();
    const menuHeight = menu.current.offsetHeight || 72;
    const spaceBelow = window.innerHeight - triggerRect.bottom;
    setFlipUp(spaceBelow < menuHeight + 14 && triggerRect.top > menuHeight + 14);
  }, [open]);
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
    className: `choice-menu${flipUp ? " flip-up" : ""}`,
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

/* 暖杏灰（apricot）暂时灰度下线，置 enabled: true 即可重新开放选项。 */
const ALL_THEME_CHOICES = [{
  key: "system",
  name: "跟随系统",
  hint: "随系统深浅外观切换"
}, {
  key: "white",
  name: "纸白",
  hint: "中性纸面",
  day: true
}, {
  key: "paper",
  name: "暖纸白",
  hint: "温和纸感",
  day: true
}, {
  key: "mist",
  name: "雾青灰",
  hint: "清爽青灰",
  day: true
}, {
  key: "apricot",
  name: "暖杏灰",
  hint: "温暖柔和",
  day: true,
  enabled: false
}, {
  key: "dark",
  name: "墨青暗",
  hint: "夜间深色"
}];
const THEME_CHOICES = ALL_THEME_CHOICES.filter(item => item.enabled !== false);
const DAY_THEME_CHOICES = THEME_CHOICES.filter(item => item.day);
/* 运行模式切换（稳健 / 激进）暂时灰度下线，置 ENABLE_RUN_MODE_SWITCH = true 即可重新开放选项。 */
const ENABLE_RUN_MODE_SWITCH = false;
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
  choices = THEME_CHOICES,
  value,
  onChange,
  systemDark,
  dayThemeName,
  ariaLabel = "界面主题",
  isDayPicker = false
}) => /*#__PURE__*/React.createElement("div", {
  className: "theme-options",
  role: "group",
  "aria-label": ariaLabel
}, choices.map(item => {
  const active = item.key === value;
  const hint = item.key === "system" ? `当前${systemDark ? "深色 · 墨青暗" : `浅色 · ${dayThemeName}`}` : item.hint;
  const dataProps = isDayPicker ? {
    "data-day-theme": item.key
  } : {
    "data-theme": item.key
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    key: item.key,
    className: "theme-option"
  }, dataProps, {
    "aria-pressed": active,
    title: `${item.name} · ${hint}`,
    onClick: () => onChange(item.key)
  }), /*#__PURE__*/React.createElement("span", {
    className: `theme-chip ${item.key}`,
    "aria-hidden": "true"
  }, item.key === "system" && /*#__PURE__*/React.createElement(Icon, {
    name: "contrast",
    size: 12,
    stroke: 1.7
  })), /*#__PURE__*/React.createElement("span", {
    className: "theme-name"
  }, item.name), active && /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 11
  }));
}));
const SettingsPage = ({
  settings,
  onSetting,
  onSettingsBatch,
  pendingSettings,
  theme = "system",
  onTheme,
  dayTheme = "white",
  onDayTheme,
  scope,
  onLogs,
  onHostLogs,
  onDiagnostics,
  version,
  update,
  onCheckUpdate,
  onApplyUpdate,
  updateBusy
}) => {
  const systemDark = useSystemDark();
  const disabled = key => pendingSettings.has(key);
  const runMode = settings.run_mode || "stable";
  const coinEnabled = Boolean(settings.do_coin);
  const coinTarget = coinEnabled ? Math.max(1, Math.min(5, Number(settings.coin_target ?? 5))) : 0;
  const dayThemeName = (DAY_THEME_CHOICES.find(item => item.key === dayTheme) || DAY_THEME_CHOICES[0]).name;
  const accountScopeLabel = scope?.name ? `当前账号 · ${scope.name}` : "当前账号生效";
  const updateState = update?.status || "idle";
  const updateChecking = Boolean(updateBusy || ["checking", "downloading", "verifying", "applying"].includes(updateState));
  const updateDesc = updateState === "checking" ? "正在检查最新版本…" : updateState === "downloading" ? `正在下载新版本 v${update?.latest_version || ""}…` : updateState === "verifying" ? `正在校验新版本 v${update?.latest_version || ""}…` : updateState === "applying" ? "正在重启并安装更新…" : updateState === "ready" ? update?.waiting_reason ? `新版本 v${update.ready_version} 已就绪 · ${update.waiting_reason}` : `新版本 v${update?.ready_version || ""} 已下载就绪` : updateState === "update_available" ? `发现新版本 v${update?.latest_version || ""}` : updateState === "up_to_date" ? update?.last_checked_at ? `当前已是最新版本 · 上次检查 ${relativeTime(update.last_checked_at)}` : "当前已是最新版本" : updateState === "error" && update?.error ? update.error : "检查新版本或自动保持最新";
  const changeAutoCoin = nextCount => {
    const count = Number(nextCount) || 0;
    if (typeof onSettingsBatch === "function") {
      if (count <= 0) onSettingsBatch({
        do_coin: false
      });else onSettingsBatch({
        do_coin: true,
        coin_target: count
      });
      return;
    }
    if (count <= 0) onSetting("do_coin", false);else {
      onSetting("do_coin", true);
      onSetting("coin_target", count);
    }
  };
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u8BBE\u7F6E"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head group-head-meta"
  }, /*#__PURE__*/React.createElement("span", null, "\u6BCF\u65E5\u7B7E\u5230"), /*#__PURE__*/React.createElement("span", {
    className: "scope-tag"
  }, accountScopeLabel)), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u81EA\u52A8\u5B8C\u6210\u65E5\u5E38\u7ECF\u9A8C",
    desc: "\u6BCF\u65E5\u81EA\u52A8\u9886\u53D6\u767B\u5F55\u3001\u89C2\u770B\u4E0E\u5206\u4EAB\u7ECF\u9A8C"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u81EA\u52A8\u5B8C\u6210\u65E5\u5E38\u7ECF\u9A8C",
    checked: settings.auto_daily_exp !== false,
    disabled: disabled("auto_daily_exp"),
    onChange: value => onSetting("auto_daily_exp", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u6BCF\u65E5\u81EA\u52A8\u6295\u5E01",
    desc: "\u9ED8\u8BA4\u5173\u95ED\u4EE5\u4FDD\u62A4\u786C\u5E01\uFF0C\u5F00\u542F\u540E\u6309\u6BCF\u65E5\u4E0A\u9650\u81EA\u52A8\u8865\u9F50"
  }, /*#__PURE__*/React.createElement(Choice, {
    label: "\u6BCF\u65E5\u81EA\u52A8\u6295\u5E01",
    value: coinTarget,
    disabled: disabled("do_coin") || disabled("coin_target"),
    options: [{
      value: 0,
      label: "关闭"
    }, {
      value: 1,
      label: "1 枚"
    }, {
      value: 2,
      label: "2 枚"
    }, {
      value: 3,
      label: "3 枚"
    }, {
      value: 4,
      label: "4 枚"
    }, {
      value: 5,
      label: "5 枚"
    }],
    onChange: changeAutoCoin
  })), coinTarget > 0 && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(SettingRow, {
    className: "setting-sub",
    name: "\u4F18\u5148\u6295\u7ED9\u5173\u6CE8\u4E3B\u64AD",
    desc: "\u4F18\u5148\u4ECE\u5F53\u524D\u5173\u6CE8\u5217\u8868\u548C\u7C89\u4E1D\u724C\u4E3B\u64AD\u7684\u6295\u7A3F\u4E2D\u6311\u9009\u89C6\u9891"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u4F18\u5148\u6295\u7ED9\u5173\u6CE8\u4E3B\u64AD",
    checked: settings.prefer_medals !== false,
    disabled: disabled("prefer_medals"),
    onChange: value => onSetting("prefer_medals", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    className: "setting-sub",
    name: "\u6295\u5E01\u65F6\u540C\u65F6\u70B9\u8D5E",
    desc: "\u6BCF\u6B21\u6295\u5E01\u65F6\u987A\u4FBF\u4E3A\u8BE5\u89C6\u9891\u70B9\u8D5E"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u6295\u5E01\u65F6\u540C\u65F6\u70B9\u8D5E",
    checked: Boolean(settings.coin_with_like),
    disabled: disabled("coin_with_like"),
    onChange: value => onSetting("coin_with_like", value)
  })))), /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head group-head-meta"
  }, /*#__PURE__*/React.createElement("span", null, "\u76F4\u64AD\u5E94\u63F4"), /*#__PURE__*/React.createElement("span", {
    className: "scope-tag"
  }, accountScopeLabel)), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    desc: "\u4EC5\u5728\u4E3B\u64AD\u5F00\u64AD\u65F6\u53D1\u9001\u5F39\u5E55\u91CD\u65B0\u70B9\u4EAE\u7184\u706D\u7684\u724C\u5B50"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u70B9\u4EAE\u7C89\u4E1D\u724C",
    checked: settings.auto_revive,
    disabled: disabled("auto_revive"),
    onChange: value => onSetting("auto_revive", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    desc: "\u4EC5\u5728\u4E3B\u64AD\u5F00\u64AD\u65F6\u81EA\u52A8\u8865\u9F50\u6BCF\u65E5\u5F39\u5E55\u4EB2\u5BC6\u5EA6\u4EFB\u52A1"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5B8C\u6210\u5F39\u5E55\u4EFB\u52A1",
    checked: settings.auto_danmaku_intimacy,
    disabled: disabled("auto_danmaku_intimacy"),
    onChange: value => onSetting("auto_danmaku_intimacy", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u53D1\u5F39\u5E55\u524D\u4F69\u6234\u7C89\u4E1D\u724C",
    desc: "\u5F00\u64AD\u6267\u884C\u5F39\u5E55\u4EFB\u52A1\u524D\u81EA\u52A8\u4F69\u6234\u5BF9\u5E94\u4E3B\u64AD\u7684\u7C89\u4E1D\u724C"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u53D1\u5F39\u5E55\u524D\u4F69\u6234\u7C89\u4E1D\u724C",
    checked: settings.auto_wear !== false,
    disabled: disabled("auto_wear"),
    onChange: value => onSetting("auto_wear", value)
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
    desc: "\u5F53\u524D\u8D26\u53F7\u5173\u6CE8\u7684\u4E3B\u64AD\u5F00\u64AD\u65F6\u5F39\u51FA\u684C\u9762\u63D0\u9192"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u64AD\u901A\u77E5",
    checked: settings.notify_on_live,
    disabled: disabled("notify_on_live"),
    onChange: value => onSetting("notify_on_live", value)
  })), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F00\u673A\u542F\u52A8",
    desc: "\u672C\u673A\u5168\u5C40\u751F\u6548\uFF0C\u767B\u5F55\u540E\u5728\u6258\u76D8\u9759\u9ED8\u8FD0\u884C"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u5F00\u673A\u542F\u52A8",
    checked: settings.autostart,
    disabled: disabled("autostart"),
    onChange: value => onSetting("autostart", value)
  })), ENABLE_RUN_MODE_SWITCH && /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u8FD0\u884C\u6A21\u5F0F",
    desc: "\u7A33\u5065\u6A21\u5F0F\u63A8\u8350\u65E5\u5E38\u6302\u673A\uFF1B\u6FC0\u8FDB\u6A21\u5F0F\u68C0\u6D4B\u66F4\u9891\u7E41\uFF08\u6309\u8D26\u53F7\u72EC\u7ACB\u4FDD\u5B58\uFF09"
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
    className: "group-head group-head-meta"
  }, /*#__PURE__*/React.createElement("span", null, "\u5916\u89C2"), /*#__PURE__*/React.createElement("span", {
    className: "scope-tag"
  }, "\u672C\u673A\u5168\u5C40")), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u754C\u9762\u4E3B\u9898",
    desc: theme === "system" ? `跟随系统，当前为${systemDark ? "深色 · 墨青暗" : `浅色 · ${dayThemeName}`}` : "自定义应用配色风格"
  }, /*#__PURE__*/React.createElement(ThemeOptions, {
    value: theme,
    onChange: onTheme,
    systemDark: systemDark,
    dayThemeName: dayThemeName
  })), theme === "system" && /*#__PURE__*/React.createElement(SettingRow, {
    className: "setting-sub",
    name: "\u767D\u5929\u9ED8\u8BA4\u4E3B\u9898",
    desc: "\u7CFB\u7EDF\u5904\u4E8E\u6D45\u8272\u5916\u89C2\u65F6\u4F18\u5148\u4F7F\u7528\u7684\u914D\u8272"
  }, /*#__PURE__*/React.createElement(ThemeOptions, {
    choices: DAY_THEME_CHOICES,
    value: dayTheme,
    onChange: onDayTheme,
    ariaLabel: "\u767D\u5929\u9ED8\u8BA4\u4E3B\u9898",
    isDayPicker: true
  }))), /*#__PURE__*/React.createElement("details", {
    className: "group card settings-dev"
  }, /*#__PURE__*/React.createElement("summary", {
    className: "group-head group-head-meta dev-summary"
  }, /*#__PURE__*/React.createElement("span", null, "\u5F00\u53D1\u8005\u4E0E\u8BCA\u65AD"), /*#__PURE__*/React.createElement("span", {
    className: "dev-summary-right"
  }, /*#__PURE__*/React.createElement("span", {
    className: "dev-summary-hint"
  }, "\u65E5\u5FD7 \xB7 \u8BCA\u65AD\u5305 \xB7 \u7248\u672C\u66F4\u65B0"), /*#__PURE__*/React.createElement(Icon, {
    name: "chevron",
    size: 14
  }))), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u8FD0\u884C\u65E5\u5FD7",
    desc: scope ? "可分别查看当前账号日志或主程序全局日志" : "打开日志文件所在目录，便于排障"
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
    desc: "\u6253\u5305\u65E5\u5FD7\u3001\u8FD1\u671F\u62A5\u9519\u4E0E\u73AF\u5883\u6458\u8981\uFF0C\u81EA\u52A8\u79FB\u9664\u767B\u5F55\u51ED\u8BC1\u5E76\u9ED8\u8BA4\u533F\u540D\u5316"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onDiagnostics
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), "\u5BFC\u51FA\u8BCA\u65AD\u5305")), /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u81EA\u52A8\u66F4\u65B0",
    desc: "\u540E\u53F0\u81EA\u52A8\u83B7\u53D6\u65B0\u7248\u5E76\u5728\u7A7A\u95F2\u65F6\u5B89\u88C5\uFF08\u5168\u5C40\u751F\u6548\uFF09"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "\u81EA\u52A8\u66F4\u65B0",
    checked: settings.auto_update !== false,
    disabled: disabled("auto_update"),
    onChange: value => onSetting("auto_update", value)
  })), version && /*#__PURE__*/React.createElement(SettingRow, {
    name: "\u5F53\u524D\u7248\u672C",
    desc: updateDesc
  }, /*#__PURE__*/React.createElement("div", {
    className: "btn-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "version-pill"
  }, "v", version), updateState === "ready" && update?.can_self_update && onApplyUpdate ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    disabled: Boolean(updateBusy || updateState === "applying"),
    onClick: onApplyUpdate
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), "\u7ACB\u5373\u91CD\u542F\u66F4\u65B0") : onCheckUpdate && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    disabled: updateChecking,
    onClick: onCheckUpdate
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), "\u68C0\u67E5\u66F4\u65B0")))))));
};
const AccountRow = ({
  account,
  isActive,
  image,
  runningCount = 0,
  onSwitch,
  onSetRunning,
  onSwitchExclusive,
  onScan,
  onLogout,
  onRemove,
  onProtection,
  busy
}) => {
  const state = window.accountStateLabel(account);
  const needsLogin = !account.signed_in || account.status === "needs_login";
  const protection = account.status === "blocked" || Boolean(account.safety?.blocked);
  const engineActive = Boolean(account.engine_active || account.running);
  const startLabel = runningCount > 0 ? "同时挂机" : "开启挂机";
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
    className: "mini-tag"
  }, "\u5F53\u524D\u67E5\u770B"), !needsLogin && !protection && /*#__PURE__*/React.createElement("span", {
    className: `mini-tag ${state.tone}`
  }, state.label), needsLogin && /*#__PURE__*/React.createElement("span", {
    className: "mini-tag warn"
  }, "\u9700\u8981\u91CD\u65B0\u626B\u7801"), protection && /*#__PURE__*/React.createElement("span", {
    className: "mini-tag warn"
  }, "\u9700\u5728\u5E73\u53F0\u5904\u7406")), /*#__PURE__*/React.createElement("div", {
    className: "account-item-meta"
  }, "UID ", account.uid, account.room_count > 0 ? ` · 关注 ${account.room_count} 位` : "", account.live_room_count > 0 ? ` · ${account.live_room_count} 房直播中` : ""), issueText && /*#__PURE__*/React.createElement("div", {
    className: "account-item-sub warn"
  }, issueText)), /*#__PURE__*/React.createElement("div", {
    className: "account-item-actions"
  }, protection && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onProtection(account.id),
    "aria-label": `查看原因 ${account.name}`
  }, "\u67E5\u770B\u539F\u56E0"), needsLogin && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: () => onScan(account.id),
    "aria-label": `重新扫码 ${account.name}`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "qr",
    size: 12
  }), "\u91CD\u65B0\u626B\u7801"), !needsLogin && !protection && engineActive && !isActive && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: () => onSwitch(account.id),
    disabled: busy,
    "aria-label": `查看 ${account.name}`
  }, "\u67E5\u770B"), !needsLogin && !protection && engineActive && onSetRunning && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onSetRunning(account.id, false),
    disabled: busy,
    "aria-label": `停止挂机 ${account.name}`
  }, "\u505C\u6B62\u6302\u673A"), !needsLogin && !protection && !engineActive && onSetRunning && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: () => onSetRunning(account.id, true),
    disabled: busy,
    "aria-label": `${startLabel} ${account.name}`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 12
  }), startLabel), !needsLogin && !protection && !engineActive && runningCount > 0 && onSwitchExclusive && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onSwitchExclusive(account.id),
    disabled: busy,
    title: "\u505C\u6B62\u5176\u4ED6\u8D26\u53F7\uFF0C\u4EC5\u8FD0\u884C\u6B64\u8D26\u53F7",
    "aria-label": `仅挂此号 ${account.name}`
  }, "\u4EC5\u6302\u6B64\u53F7"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onLogout(account.id),
    disabled: busy,
    title: needsLogin ? "清除本机保存的失效登录凭证" : "退出此账号登录",
    "aria-label": `${needsLogin ? "清除登录" : "退出登录"} ${account.name}`
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
  maxConcurrent = 3,
  onScan,
  onView,
  onSwitch,
  onSetRunning,
  onSwitchExclusive,
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
  const runningCount = (accounts || []).filter(item => item.running || item.engine_active).length;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "settings",
    "data-screen-label": "\u8D26\u53F7"
  }, /*#__PURE__*/React.createElement("div", {
    className: "settings-inner"
  }, /*#__PURE__*/React.createElement("section", {
    className: "group card"
  }, /*#__PURE__*/React.createElement("header", {
    className: "group-head group-head-action"
  }, /*#__PURE__*/React.createElement("div", {
    className: "btn-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "group-head-title"
  }, "B \u7AD9\u8D26\u53F7"), accounts.length > 1 && /*#__PURE__*/React.createElement("span", {
    className: "scope-tag"
  }, runningCount > 1 ? `${runningCount} 号同时挂机中` : `最多支持 ${maxConcurrent} 号同时挂机`)), /*#__PURE__*/React.createElement("button", {
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
    runningCount: runningCount,
    image: item.id === activeId ? avatar || avatars[item.id] : avatars[item.id],
    onView: onView,
    onSwitch: onSwitch,
    onSetRunning: onSetRunning,
    onSwitchExclusive: onSwitchExclusive,
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
  }), /*#__PURE__*/React.createElement("strong", null, hold.blocked ? hold.kind_label || "保护暂停中" : "状态正常"), hold.blocked && hold.reason && /*#__PURE__*/React.createElement("span", {
    className: "safety-reason"
  }, hold.reason)), hold.blocked && locationParts.length > 0 && /*#__PURE__*/React.createElement("small", {
    className: "safety-time"
  }, "\u89E6\u53D1\u4F4D\u7F6E\uFF1A", locationParts.join(" · ")), cooldown && /*#__PURE__*/React.createElement("small", {
    className: "safety-time"
  }, "\u6700\u65E9\u81EA\u52A8\u6062\u590D\uFF1A", absoluteTime(hold.until)), !cooldown && hold.blocked && hold.next_probe_at && /*#__PURE__*/React.createElement("small", {
    className: "safety-time"
  }, "\u4E0B\u6B21\u81EA\u52A8\u68C0\u6D4B\uFF1A", absoluteTime(hold.next_probe_at)), hold.pace_multiplier > 1 && /*#__PURE__*/React.createElement("small", {
    className: "safety-time"
  }, "\u4ECA\u65E5\u4FDD\u62A4\u964D\u901F\u4E2D\uFF1A\u4E92\u52A8\u95F4\u9694\u5DF2\u653E\u6162\u81F3 ", hold.pace_multiplier, "\xD7")), /*#__PURE__*/React.createElement("div", {
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
  }), /*#__PURE__*/React.createElement("span", null, "\u67E5\u770B\u8BE6\u60C5")), !cooldown && onCheckSafety && /*#__PURE__*/React.createElement("button", {
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
