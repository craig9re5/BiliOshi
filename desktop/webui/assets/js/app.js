/* BiliOshi JSX {"code_sha256":"44c65375c04ffa703fe24d4d0f67a8e8944b9ff9929b833979637d9f41c7c2ab","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"app.jsx","source_sha256":"8990b01e7c95cedf052342e2fc4e17f8b212f0fe98019aececdacf464fe0383d"} */
(function () {
"use strict";
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* One state owner. Python snapshots remain authoritative after every action. */

const {
  useState,
  useEffect,
  useRef,
  useCallback
} = React;
const {
  Icon,
  Pulse,
  call,
  bridgeReady,
  toRoom
} = window;
const DEFAULT_SETTINGS = {
  auto_revive: true,
  auto_danmaku_intimacy: true,
  auto_like: false,
  notify_on_live: true,
  run_mode: "stable",
  check_minutes: 5,
  autostart: false
};
const THEME_KEYS = ["system", "white", "paper", "mist", "dark"];
const DAY_THEME_KEYS = ["white", "paper", "mist"];
const normalizeThemeKey = (value, allowed, fallback) => {
  const mapped = value === "apricot" ? "paper" : value;
  return allowed.includes(mapped) ? mapped : fallback;
};
const applyDocumentTheme = value => {
  const theme = normalizeThemeKey(value, THEME_KEYS, "system");
  document.documentElement.dataset.theme = theme;
  const meta = document.querySelector('meta[name="color-scheme"]');
  if (meta) {
    meta.content = theme === "dark" ? "dark" : theme === "system" ? "light dark" : "light";
  }
  return theme;
};
const applyDocumentDayTheme = value => {
  const dayTheme = normalizeThemeKey(value, DAY_THEME_KEYS, "white");
  document.documentElement.dataset.dayTheme = dayTheme;
  return dayTheme;
};
const EMPTY_SNAPSHOT = {
  rows: [],
  paused: false,
  checking: false,
  error: "",
  account: "",
  safety: {},
  settings: DEFAULT_SETTINGS,
  accountInfo: {
    signed_in: false,
    name: "",
    confirmed: false,
    safety: {}
  }
};
const Sidebar = ({
  page,
  onPage,
  account,
  avatar,
  onQuit,
  brandHidden,
  collapsed,
  inert
}) => /*#__PURE__*/React.createElement("aside", {
  className: "side",
  inert: inert ? "" : undefined
}, !brandHidden && /*#__PURE__*/React.createElement("div", {
  className: "brand"
}, /*#__PURE__*/React.createElement("div", {
  className: "logo"
}, /*#__PURE__*/React.createElement(Pulse, {
  size: 18
})), /*#__PURE__*/React.createElement("div", {
  className: "brand-text"
}, /*#__PURE__*/React.createElement("span", {
  className: "brand-name"
}, "\u30D3\u30EA\u63A8\u3057"))), /*#__PURE__*/React.createElement("nav", {
  className: "nav",
  "aria-label": "\u4E3B\u5BFC\u822A"
}, [["monitor", "monitor", "直播总览"], ["growth", "trend", "成长记录"], ["automation", "sliders", "设置"], ["account", "user", "账号"]].map(([key, icon, text]) => /*#__PURE__*/React.createElement("button", {
  type: "button",
  key: key,
  className: "nav-item",
  "aria-current": page === key ? "page" : undefined,
  "aria-label": text,
  title: text,
  onClick: () => onPage(key)
}, /*#__PURE__*/React.createElement(Icon, {
  name: icon
}), /*#__PURE__*/React.createElement("span", null, text)))), /*#__PURE__*/React.createElement("div", {
  className: "nav-spacer"
}), /*#__PURE__*/React.createElement("nav", {
  className: "nav nav-bottom",
  "aria-label": "\u5E94\u7528\u64CD\u4F5C"
}, /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "nav-item",
  onClick: onQuit,
  "aria-label": "\u9000\u51FA\u5E94\u7528",
  title: "\u9000\u51FA\u5E94\u7528"
}, /*#__PURE__*/React.createElement(Icon, {
  name: "power"
}), /*#__PURE__*/React.createElement("span", null, "\u9000\u51FA\u5E94\u7528"))), /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "sidebar-account",
  onClick: () => onPage("account"),
  title: "\u8D26\u53F7\u7BA1\u7406",
  "aria-label": "\u8D26\u53F7\u7BA1\u7406"
}, /*#__PURE__*/React.createElement("span", {
  className: "sidebar-avatar"
}, avatar ? /*#__PURE__*/React.createElement("img", {
  src: avatar,
  alt: ""
}) : Array.from(account.name || "?")[0]), /*#__PURE__*/React.createElement("span", {
  className: "sidebar-account-text"
}, /*#__PURE__*/React.createElement("strong", null, account.name || (account.signed_in ? "等待验证" : "尚未登录")))));
const pageTitles = {
  monitor: "直播总览",
  growth: "成长记录",
  automation: "设置",
  account: "账号"
};
const WindowButtons = () => {
  const [maximized, setMaximized] = useState(false);
  // The real state lives in the native window: resizing it by double click,
  // snap or keyboard also has to flip the icon, so read it back after any
  // change and listen for the WM_SIZE event pushed by the host.
  const sync = async () => {
    try {
      const state = await call("window", "state");
      setMaximized(Boolean(state?.maximized));
    } catch {}
  };
  useEffect(() => {
    sync();
    const onState = event => {
      if (event?.type === "window_state") setMaximized(Boolean(event.payload?.maximized));
    };
    window.__onWindowState = onState;
    return () => {
      if (window.__onWindowState === onState) delete window.__onWindowState;
    };
  }, []);
  const act = async action => {
    try {
      await call("window", action);
    } catch {} finally {
      if (action !== "close") sync();
    }
  };
  useEffect(() => {
    document.documentElement.dataset.maximized = maximized ? "true" : "false";
  }, [maximized]);
  return /*#__PURE__*/React.createElement("div", {
    className: "win-buttons",
    "aria-label": "\u7A97\u53E3\u63A7\u5236"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "win-btn",
    "aria-label": "\u6700\u5C0F\u5316",
    title: "\u6700\u5C0F\u5316",
    onClick: () => act("minimize")
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 12 12",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M2.5 6h7",
    stroke: "currentColor",
    strokeWidth: "1.2",
    strokeLinecap: "round"
  }))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "win-btn",
    "aria-label": maximized ? "还原" : "最大化",
    title: maximized ? "还原" : "最大化",
    onClick: () => act("maximize")
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 12 12",
    "aria-hidden": "true"
  }, maximized ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("rect", {
    x: "2.4",
    y: "4",
    width: "5.4",
    height: "5.4",
    rx: "1.1",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M4.4 4V3a.6.6 0 0 1 .6-.6h4a.6.6 0 0 1 .6.6v4a.6.6 0 0 1-.6.6h-1",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.2"
  })) : /*#__PURE__*/React.createElement("rect", {
    x: "2.6",
    y: "2.6",
    width: "6.8",
    height: "6.8",
    rx: "1.2",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "1.2"
  }))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "win-btn close",
    "aria-label": "\u5173\u95ED",
    title: "\u5173\u95ED\u5230\u6258\u76D8",
    onClick: () => act("close")
  }, /*#__PURE__*/React.createElement("svg", {
    width: "12",
    height: "12",
    viewBox: "0 0 12 12",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("path", {
    d: "M3 3l6 6M9 3l-6 6",
    stroke: "currentColor",
    strokeWidth: "1.2",
    strokeLinecap: "round"
  }))));
};

/* Collapse the sidebar to icons, and reopen it, mirroring the desktop app's
   left-hand panel control. */
const SidebarToggle = ({
  collapsed,
  onToggle
}) => /*#__PURE__*/React.createElement("div", {
  className: "side-toggle"
}, /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "side-btn",
  "aria-label": collapsed ? "展开侧栏" : "收起侧栏",
  title: collapsed ? "展开侧栏" : "收起侧栏",
  "aria-pressed": collapsed,
  onClick: onToggle
}, /*#__PURE__*/React.createElement("svg", {
  width: "16",
  height: "16",
  viewBox: "0 0 16 16",
  "aria-hidden": "true"
}, /*#__PURE__*/React.createElement("rect", {
  x: "1.8",
  y: "2.8",
  width: "12.4",
  height: "10.4",
  rx: "2",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "1.3"
}), /*#__PURE__*/React.createElement("path", {
  d: "M6.2 3.2v9.6",
  stroke: "currentColor",
  strokeWidth: "1.3"
}), collapsed && /*#__PURE__*/React.createElement("path", {
  d: "M9 6.4l1.8 1.6L9 9.6",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "1.3",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}))));
function App() {
  const [page, setPage] = useState("monitor");
  const [theme, setTheme] = useState(() => normalizeThemeKey(document.documentElement.dataset.theme, THEME_KEYS, "system"));
  const [dayTheme, setDayTheme] = useState(() => normalizeThemeKey(document.documentElement.dataset.dayTheme, DAY_THEME_KEYS, "white"));
  const chooseTheme = useCallback(value => {
    if (!THEME_KEYS.includes(value)) return;
    setTheme(applyDocumentTheme(value));
    try {
      if (value === "system") window.localStorage.removeItem("bilioshi.theme");else window.localStorage.setItem("bilioshi.theme", value);
    } catch {}
  }, []);
  const chooseDayTheme = useCallback(value => {
    if (!DAY_THEME_KEYS.includes(value)) return;
    setDayTheme(applyDocumentDayTheme(value));
    try {
      if (value === "white") window.localStorage.removeItem("bilioshi.dayTheme");else window.localStorage.setItem("bilioshi.dayTheme", value);
    } catch {}
  }, []);
  useEffect(() => {
    const onStorage = event => {
      if (event.key === "bilioshi.theme") {
        setTheme(applyDocumentTheme(event.newValue || "system"));
      } else if (event.key === "bilioshi.dayTheme") {
        setDayTheme(applyDocumentDayTheme(event.newValue || "white"));
      }
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return window.localStorage.getItem("bilioshi.sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  const toggleSidebar = useCallback(() => {
    setCollapsed(value => {
      const next = !value;
      try {
        window.localStorage.setItem("bilioshi.sidebar", next ? "collapsed" : "open");
      } catch {}
      return next;
    });
  }, []);
  const [snap, setSnap] = useState(EMPTY_SNAPSHOT);
  const [selectedId, setSelectedId] = useState(null);
  const [connected, setConnected] = useState(false);
  const [controlBusy, setControlBusy] = useState(false);
  const [busyRoom, setBusyRoom] = useState(null);
  const [pendingSettings, setPendingSettings] = useState(new Set());
  const [dialog, setDialog] = useState(null);
  const [dialogBusy, setDialogBusy] = useState(false);
  const [safetyProbe, setSafetyProbe] = useState({
    loading: false,
    result: null
  });
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [medals, setMedals] = useState({
    data: [],
    loading: false,
    error: ""
  });
  const [medalSelection, setMedalSelection] = useState(new Set());
  const [diagPreview, setDiagPreview] = useState(null);
  const [diagLoading, setDiagLoading] = useState(false);
  const [diagAnonymize, setDiagAnonymize] = useState(true);
  const [diagIncludeState, setDiagIncludeState] = useState(true);
  const [diagExporting, setDiagExporting] = useState(false);
  const [diagExported, setDiagExported] = useState(null);
  const [diagStatus, setDiagStatus] = useState("");
  const [qr, setQr] = useState(null);
  const [menu, setMenu] = useState(null);
  const [images, setImages] = useState({});
  const [accountAvatar, setAccountAvatar] = useState("");
  const [accountAvatars, setAccountAvatars] = useState({});
  const [avatarVersion, setAvatarVersion] = useState(0);
  const [toasts, setToasts] = useState([]);
  const latest = useRef(EMPTY_SNAPSHOT);
  const titleRef = useRef(null);
  // Moving focus to the page title lets keyboard and screen-reader users hear
  // where a nav click landed instead of staying on the old nav button.
  const firstPage = useRef(true);
  useEffect(() => {
    if (firstPage.current) {
      firstPage.current = false;
      return;
    }
    titleRef.current?.focus({
      preventScroll: true
    });
  }, [page]);
  const selectionInitialized = useRef(false);
  const alive = useRef(true);
  const handlers = useRef({});
  const roomPending = useRef(new Set());
  const settingsQueue = useRef(Promise.resolve());
  const settingOverrides = useRef({});
  const searchGeneration = useRef(0);
  const dialogGeneration = useRef(0);
  const qrRequest = useRef(0);
  const qrOpen = useRef(false);
  const avatarPending = useRef(new Set());
  const avatarRetry = useRef({});
  const avatarAccountPending = useRef(new Set());
  const avatarAccountRetry = useRef({});
  const toastTimers = useRef(new Set());
  const userSelected = useRef(null);
  const toast = useCallback((text, tone = "info") => {
    if (!text || !alive.current) return;
    const id = Date.now() + Math.random();
    setToasts(items => [...items.slice(-2), {
      id,
      text,
      tone
    }]);
    const timer = window.setTimeout(() => {
      toastTimers.current.delete(timer);
      if (alive.current) setToasts(items => items.filter(item => item.id !== id));
    }, 4800);
    toastTimers.current.add(timer);
  }, []);
  const receiveSnapshot = useCallback(data => {
    if (!data || !alive.current) return;
    latest.current = {
      ...EMPTY_SNAPSHOT,
      ...data,
      settings: {
        ...DEFAULT_SETTINGS,
        ...data.settings
      },
      accountInfo: {
        ...EMPTY_SNAPSHOT.accountInfo,
        ...data.accountInfo,
        safety: data.safety || data.accountInfo?.safety || {}
      }
    };
    setSnap({
      ...latest.current,
      settings: {
        ...latest.current.settings,
        ...settingOverrides.current
      }
    });
    setConnected(true);
  }, []);
  const refresh = async () => {
    try {
      receiveSnapshot(await call("snapshot"));
    } catch {
      toast("无法更新状态，稍后重试", "error");
    }
  };
  useEffect(() => {
    alive.current = true;
    window.LS = {
      onSnapshot: receiveSnapshot,
      onEvent: event => {
        if (!event || !alive.current) return;
        const payload = event.payload || {};
        if (event.type === "window_state") {
          if (typeof window.__onWindowState === "function") window.__onWindowState(event);
          return;
        }
        if (event.type === "qr_state") {
          if (!qrOpen.current) return;
          if (payload.state === "confirmed") {
            setAccountAvatar("");
            setAccountAvatars({});
            avatarAccountRetry.current = {};
            setAvatarVersion(value => value + 1);
          }
          setQr(current => {
            if (!current || current.generation !== payload.generation) return current;
            return {
              ...current,
              ...payload
            };
          });
        } else if (event.type === "open_login") handlers.current.openQr?.();else if (event.type === "show_page" || event.type === "navigate") {
          if (["monitor", "growth", "automation", "account"].includes(payload.page)) setPage(payload.page);
        } else if (event.type === "add_member") handlers.current.openAdd?.();else if (event.type === "sync_medals") handlers.current.openMedals?.();else if (event.type === "open_diagnostic") handlers.current.openDiagnostics?.();else if (event.type === "toast") toast(payload.message, payload.tone);else if (event.type === "settings_changed") handlers.current.refresh?.();
      }
    };
    window.__reportClientError = msg => call("report_client_error", [[msg]]).catch(() => {});
    bridgeReady().then(async ready => {
      if (!alive.current) return;
      if (!ready) {
        toast("无法连接后台，重启应用后重试", "error");
        return;
      }
      if (Array.isArray(window.__errs) && window.__errs.length) {
        const queued = window.__errs.splice(0, window.__errs.length);
        call("report_client_error", [queued]).catch(() => {});
      }
      try {
        await call("ready");
        receiveSnapshot(await call("snapshot"));
      } catch {
        toast("无法读取运行状态，重启应用后重试", "error");
      }
    });
    return () => {
      alive.current = false;
      if (window.LS?.onSnapshot === receiveSnapshot) delete window.LS;
      delete window.__reportClientError;
      toastTimers.current.forEach(timer => window.clearTimeout(timer));
    };
  }, [receiveSnapshot, toast]);
  const accounts = snap.accounts || [];
  const activeId = snap.active_account_id || "";
  const viewId = activeId;
  const isAllView = false;
  const viewed = snap;
  useEffect(() => {
    const rows = viewed.rows || [];
    if (!selectionInitialized.current && rows.length) {
      selectionInitialized.current = true;
      setSelectedId(rows[0].room);
    } else if (selectedId !== null && !rows.some(row => row.room === selectedId)) setSelectedId(null);
  }, [viewed.rows, selectedId]);
  const fetchAvatar = useCallback(uid => {
    if (!uid || images[uid] || avatarPending.current.has(uid)) return;
    if (Date.now() < (avatarRetry.current[uid] || 0)) return;
    avatarPending.current.add(uid);
    call("avatar", uid, "", activeId).then(result => {
      avatarPending.current.delete(uid);
      if (result?.ok && result.data_uri && alive.current) {
        delete avatarRetry.current[uid];
        setImages(items => ({
          ...items,
          [uid]: result.data_uri
        }));
      } else {
        avatarRetry.current[uid] = Date.now() + 60000;
      }
    }).catch(() => {
      avatarPending.current.delete(uid);
      avatarRetry.current[uid] = Date.now() + 60000;
    });
  }, [images, activeId]);
  useEffect(() => {
    if (!connected || !viewed.accountInfo?.signed_in) return;
    for (const row of viewed.rows || []) {
      fetchAvatar(row.uid);
    }
  }, [viewed.rows, connected, fetchAvatar]);
  const rooms = (viewed.rows || []).map(row => toRoom(row, viewed));
  const selected = rooms.find(room => room.room === selectedId);
  const account = viewed.accountInfo || EMPTY_SNAPSHOT.accountInfo;
  const closing = Boolean(snap.closing);

  // The account avatar is resolved by Python from the signed-in profile; a
  // failure keeps the letter placeholder and retries once a minute for network
  // hiccups. A confirmed QR login bumps avatarVersion so a new account reloads.
  useEffect(() => {
    if (!connected || !account.signed_in) {
      setAccountAvatar("");
      return;
    }
    let live = true;
    let retry = 0;
    const load = () => {
      call("account_avatar", activeId).then(result => {
        if (!live) return;
        if (result?.ok && result.data_uri) {
          setAccountAvatar(result.data_uri);
          if (activeId) {
            setAccountAvatars(items => items[activeId] === result.data_uri ? items : {
              ...items,
              [activeId]: result.data_uri
            });
          }
        } else if (result?.error) retry = window.setTimeout(load, 60000);
      }).catch(() => {
        if (live) retry = window.setTimeout(load, 60000);
      });
    };
    load();
    return () => {
      live = false;
      window.clearTimeout(retry);
    };
  }, [connected, account.signed_in, account.name, avatarVersion, activeId]);
  const accountKeys = accounts.map(item => `${item.id}:${item.signed_in ? 1 : 0}`).join(",");
  useEffect(() => {
    if (!connected || !accounts.length) return;
    let live = true;
    for (const item of accounts) {
      if (!item.signed_in || !item.id || accountAvatars[item.id] || avatarAccountPending.current.has(item.id)) continue;
      if (Date.now() < (avatarAccountRetry.current[item.id] || 0)) continue;
      avatarAccountPending.current.add(item.id);
      call("account_avatar", item.id).then(result => {
        avatarAccountPending.current.delete(item.id);
        if (!live || !alive.current) return;
        if (result?.ok && result.data_uri) {
          delete avatarAccountRetry.current[item.id];
          setAccountAvatars(items => items[item.id] === result.data_uri ? items : {
            ...items,
            [item.id]: result.data_uri
          });
        } else {
          avatarAccountRetry.current[item.id] = Date.now() + 60000;
        }
      }).catch(() => {
        avatarAccountPending.current.delete(item.id);
        avatarAccountRetry.current[item.id] = Date.now() + 60000;
      });
    }
    return () => {
      live = false;
    };
  }, [connected, accountKeys, accountAvatars, avatarVersion]);
  const invoke = async (method, args = [], success = "") => {
    try {
      const result = await call(method, ...args);
      if (result?.ok === false) {
        toast(result.error || result.message || "操作未完成，稍后重试", "warn");
        return result;
      }
      if (result?.warning) toast(result.warning, "warn");else if (result?.message || success) toast(result.message || success);
      return result || {
        ok: true
      };
    } catch {
      toast("无法完成操作，稍后重试", "error");
      return {
        ok: false
      };
    }
  };
  const control = async (method, args = [], success = "") => {
    if (controlBusy || closing) return;
    setControlBusy(true);
    try {
      await invoke(method, args, success);
      await refresh();
    } finally {
      if (alive.current) setControlBusy(false);
    }
  };
  const roomAction = async (kind, roomId) => {
    if (roomPending.current.has(roomId) || closing) return;
    roomPending.current.add(roomId);
    setBusyRoom(roomId);
    try {
      await invoke({
        redo: "redo",
        reconnect: "reconnect",
        wear: "wear_medal"
      }[kind], [roomId]);
      await refresh();
    } finally {
      roomPending.current.delete(roomId);
      if (alive.current) setBusyRoom(roomPending.current.values().next().value ?? null);
    }
  };
  const setSetting = (key, value) => {
    settingOverrides.current[key] = value;
    setPendingSettings(current => new Set(current).add(key));
    setSnap(current => ({
      ...current,
      settings: {
        ...current.settings,
        [key]: value
      }
    }));
    settingsQueue.current = settingsQueue.current.catch(() => {}).then(async () => {
      try {
        await invoke("save_settings", [{
          [key]: value
        }, activeId]);
        delete settingOverrides.current[key];
        await refresh();
      } finally {
        if (alive.current) setPendingSettings(current => {
          const next = new Set(current);
          next.delete(key);
          return next;
        });
      }
    });
  };
  const closeQr = () => {
    qrOpen.current = false;
    qrRequest.current += 1;
    setQr(null);
    call("qr_cancel").catch(() => {});
  };
  const openQr = async (accountId = "") => {
    qrOpen.current = true;
    const request = ++qrRequest.current;
    setMenu(null);
    setPage("account");
    setQr({
      state: "starting",
      account_id: accountId
    });
    try {
      const result = await call("qr_start", accountId || "");
      if (!alive.current || !qrOpen.current || request !== qrRequest.current) return;
      setQr(result?.ok ? {
        ...result,
        state: "waiting"
      } : {
        state: "error",
        account_id: accountId,
        message: result?.error || "无法生成二维码，稍后重试"
      });
    } catch {
      if (qrOpen.current && request === qrRequest.current) {
        setQr({
          state: "error",
          account_id: accountId,
          message: "无法连接登录服务，稍后重试"
        });
      }
    }
  };
  const closeDialog = () => {
    if (dialogBusy) return;
    dialogGeneration.current += 1;
    searchGeneration.current += 1;
    setDialog(null);
  };
  const openAdd = () => {
    dialogGeneration.current += 1;
    searchGeneration.current += 1;
    setMenu(null);
    setDialog("add");
    setQuery("");
    setSearchResult(null);
    setSearching(false);
  };
  const onQuery = value => {
    searchGeneration.current += 1;
    setQuery(value);
    setSearchResult(null);
    setSearching(false);
  };
  const search = async () => {
    const generation = ++searchGeneration.current;
    const term = query.trim();
    if (!term) return;
    setSearching(true);
    try {
      const result = await call("resolve_member", term);
      if (alive.current && generation === searchGeneration.current) setSearchResult(result);
    } catch {
      if (generation === searchGeneration.current) setSearchResult({
        ok: false,
        error: "无法查找主播，检查网络后重试"
      });
    } finally {
      if (generation === searchGeneration.current) setSearching(false);
    }
  };
  const add = async () => {
    if (!searchResult?.ok || dialogBusy) return;
    setDialogBusy(true);
    try {
      const result = await invoke("add_member", [query.trim()]);
      if (result?.ok) {
        setDialog(null);
        toast(`已添加 ${result.member?.name || searchResult.member.name}`);
        await refresh();
      } else setSearchResult(result);
    } finally {
      if (alive.current) setDialogBusy(false);
    }
  };
  const openMedals = async () => {
    const generation = ++dialogGeneration.current;
    setMenu(null);
    setDialog("medals");
    setMedals({
      data: [],
      loading: true,
      error: ""
    });
    setMedalSelection(new Set());
    try {
      const result = await call("medals");
      if (!alive.current || generation !== dialogGeneration.current) return;
      const data = result?.medals || [];
      setMedals({
        data,
        loading: false,
        error: result?.ok ? "" : result?.error || "无法读取粉丝牌"
      });
      setMedalSelection(new Set(data.filter(item => !item.watched).map(item => item.uid)));
    } catch {
      if (generation === dialogGeneration.current) setMedals({
        data: [],
        loading: false,
        error: "无法读取粉丝牌，检查网络后重试"
      });
    }
  };
  const loadDiagnosticPreview = async anonymizeValue => {
    const generation = dialogGeneration.current;
    setDiagLoading(true);
    try {
      const result = await call("diagnostic_preview", "", Boolean(anonymizeValue));
      if (!alive.current || generation !== dialogGeneration.current) return;
      if (result?.ok) setDiagPreview(result);else setDiagStatus(result?.error || "无法预览诊断信息，仍可直接尝试导出。");
    } catch {
      if (alive.current && generation === dialogGeneration.current) {
        setDiagStatus("无法读取诊断预览，仍可直接尝试导出。");
      }
    } finally {
      if (alive.current && generation === dialogGeneration.current) setDiagLoading(false);
    }
  };
  const openDiagnostics = () => {
    dialogGeneration.current += 1;
    setMenu(null);
    setDiagExported(null);
    setDiagStatus("");
    setDialog("diagnostic");
    loadDiagnosticPreview(diagAnonymize);
  };
  const changeDiagAnonymize = checked => {
    setDiagAnonymize(checked);
    setDiagExported(null);
    setDiagStatus("");
    loadDiagnosticPreview(checked);
  };
  const exportDiagnostic = async () => {
    if (diagExporting) return;
    setDiagExporting(true);
    setDiagStatus("");
    try {
      const result = await invoke("export_diagnostic", [{
        anonymize: diagAnonymize,
        include_state: diagIncludeState
      }]);
      if (!alive.current) return;
      if (result?.ok) {
        setDiagExported(result);
        setDiagStatus("脱敏诊断包已生成，可打开文件夹或复制摘要反馈给开发者。");
      } else {
        setDiagStatus(result?.error || "导出诊断包失败，请查看日志目录。");
      }
    } finally {
      if (alive.current) setDiagExporting(false);
    }
  };
  const copyDiagnosticSummary = async () => {
    const text = diagExported?.summary_markdown || diagPreview?.summary_markdown;
    if (!text) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        throw new Error("no clipboard");
      }
      setDiagStatus("已复制 Markdown 问题摘要，可直接粘贴到反馈中。");
      toast("问题摘要已复制到剪贴板");
    } catch {
      try {
        const box = document.createElement("textarea");
        box.value = text;
        box.style.position = "fixed";
        box.style.opacity = "0";
        document.body.appendChild(box);
        box.select();
        document.execCommand("copy");
        document.body.removeChild(box);
        setDiagStatus("已复制 Markdown 问题摘要，可直接粘贴到反馈中。");
        toast("问题摘要已复制到剪贴板");
      } catch {
        setDiagStatus("剪贴板复制受限，请直接打开诊断包内的 summary.md。");
      }
    }
  };
  const importMedals = async () => {
    if (dialogBusy) return;
    setDialogBusy(true);
    try {
      const result = await invoke("import_medals", [[...medalSelection]]);
      if (result?.ok) {
        setDialog(null);
        toast(`已导入 ${result.count} 位主播`);
        await refresh();
      }
    } finally {
      if (alive.current) setDialogBusy(false);
    }
  };
  const openSafety = (targetAccount = null) => {
    setSafetyProbe({
      loading: false,
      result: null
    });
    setDialog({
      type: "safety",
      account: targetAccount || accounts.find(item => item.id === activeId) || null
    });
  };
  const checkSafety = async (autoResume = true, accountId = null) => {
    setSafetyProbe(prev => ({
      ...prev,
      loading: true
    }));
    const targetId = accountId || null;
    try {
      const args = targetId ? [Boolean(autoResume), targetId] : [Boolean(autoResume)];
      const result = await invoke("check_safety", args);
      if (!alive.current) return;
      const probeResult = {
        passed: Boolean(result?.passed),
        summary: result?.summary || (result?.passed ? "只读自检通过" : "只读自检未通过"),
        checks: Array.isArray(result?.checks) ? result.checks : [],
        at: Date.now() / 1000
      };
      setSafetyProbe({
        loading: false,
        result: probeResult
      });
      if (result?.resumed || result?.ok && !result?.hold?.blocked) {
        setDialog(null);
        toast(result?.summary || "只读自检通过，保护暂停已解除", "info");
        await refresh();
      } else if (result?.hold?.kind === "auth") {
        toast(result?.summary || "登录凭证已失效，请重新扫码登录", "error");
        await refresh();
      } else if (result && result.passed === false) {
        toast(result.summary || "只读自检未通过", "error");
        await refresh();
      }
    } catch {
      if (alive.current) {
        setSafetyProbe(prev => ({
          ...prev,
          loading: false
        }));
      }
    }
  };
  const openSafetyLink = (kind, room) => invoke("open_safety_link", [kind || "live", room || null]);
  const clearRoomBlock = async (room, capability = null) => {
    const result = await invoke("clear_room_block", [room, capability || null], "已解除该直播间互动限制");
    if (result?.ok) await refresh();
  };
  const dismissTaskError = async room => {
    const result = await invoke("dismiss_task_error", [room]);
    if (result?.ok) await refresh();
  };
  const switchAccount = async accountId => {
    if (!accountId) return;
    if (accountId === activeId) {
      // Silent no-ops read as a broken control; say why nothing changed.
      toast("当前已是这个账号");
      return;
    }
    const target = accounts.find(item => item.id === accountId);
    if (!target) return;
    if (!target.signed_in || target.status === "needs_login") {
      openQr(accountId);
      return;
    }
    if (target.status === "blocked") {
      openSafety(target);
      return;
    }
    const result = await invoke("switch_account", [accountId]);
    if (result?.ok) {
      selectionInitialized.current = false;
      setSelectedId(null);
      toast(`已切换至「${target.name}」`);
      await refresh();
    }
  };
  const confirmAction = async () => {
    if (dialogBusy) return;
    const kind = dialog?.type;
    setDialogBusy(true);
    try {
      let result;
      if (kind === "remove") result = await invoke("remove_member", [dialog.room.room], `已移除 ${dialog.room.name}`);else if (kind === "logout") {
        closeQr();
        result = await invoke("logout", [dialog.account?.id || ""], "已退出登录");
      } else if (kind === "safety") {
        const args = dialog.account?.id ? [dialog.account.id] : [];
        result = await invoke("resume_safety", args, "保护暂停已解除");
      } else if (kind === "quit") result = await invoke("quit");else if (kind === "switch") {
        result = await invoke("switch_account", [dialog.account.id]);
        if (result?.ok) {
          selectionInitialized.current = false;
          setSelectedId(null);
        }
      } else if (kind === "removeAccount") {
        result = await invoke("remove_account", [dialog.account.id]);
        if (result?.ok) {
          selectionInitialized.current = false;
          setSelectedId(null);
        }
      } else if (kind === "batchRemove") {
        const ids = (dialog.rooms || []).map(r => r.room || r);
        result = await invoke("remove_members", [ids], `已批量移除 ${ids.length} 位主播`);
        if (result?.ok) {
          selectionInitialized.current = false;
          setSelectedId(null);
        }
      }
      if (result?.ok) {
        setDialog(null);
        if (kind !== "quit") await refresh();
      }
    } finally {
      if (alive.current) setDialogBusy(false);
    }
  };
  const recover = async () => {
    const route = snap.recovery || {};
    if (route.action === "login") openQr(activeId);else if (route.action === "resume") control("toggle_pause");else if (route.action === "switch") {
      setPage("monitor");
    } else if (route.action === "safety") {
      if (snap.safety?.kind === "auth" || snap.safety?.kind === "credentials") openQr(activeId);else openSafety();
    } else if (route.action === "room") {
      setPage("monitor");
      setSelectedId(route.room);
    } else if (route.action === "logs") invoke("open_logs", [activeId]);else if (route.action === "refresh") control("refresh");else control("check_now");
  };
  handlers.current = {
    openQr,
    openAdd,
    openMedals,
    openDiagnostics,
    refresh
  };
  const select = id => {
    userSelected.current = id;
    setSelectedId(id);
  };
  const remove = room => {
    setMenu(null);
    setDialog({
      type: "remove",
      room
    });
  };
  const batchRemove = roomList => {
    setMenu(null);
    setDialog({
      type: "batchRemove",
      rooms: roomList
    });
  };
  const onContextMenu = (event, id) => {
    event.preventDefault();
    select(id);
    setMenu({
      room: id,
      x: event.clientX,
      y: event.clientY
    });
  };
  const dialogCopy = {
    remove: {
      title: "移除主播？",
      desc: `将从关注列表中移除「${dialog?.room?.name || ""}」，后续可随时重新添加。`,
      confirmLabel: "移除主播",
      danger: true
    },
    batchRemove: {
      title: `批量移除 ${dialog?.rooms?.length || 0} 位主播？`,
      desc: "将从关注列表中移除所选主播，后续可随时重新添加。",
      confirmLabel: "确认批量移除",
      danger: true
    },
    logout: {
      title: "退出当前账号？",
      desc: "退出后将停止挂机并清除登录凭证，关注列表与记录仍会保留。",
      confirmLabel: "退出登录",
      danger: true
    },
    quit: {
      title: "退出 ビリ推し？",
      desc: "将停止所有任务并退出程序。如需后台挂机，直接关闭窗口即可。",
      confirmLabel: "退出应用",
      danger: true
    },
    switch: {
      title: "切换挂机账号？",
      desc: "切换后将使用新账号开始挂机，当前任务进度会自动保存。",
      confirmLabel: "切换并挂机"
    },
    removeAccount: {
      title: "移除这个账号？",
      desc: "将从列表中移除此账号并清除凭证，关注列表与记录仍会保留。",
      confirmLabel: "移除账号",
      danger: true
    }
  };
  const modalOpen = Boolean(qr || dialog && dialog !== "diagnostic");
  const modalAvatar = dialog?.account?.id ? dialog.account.id === activeId ? accountAvatar || accountAvatars[dialog.account.id] : accountAvatars[dialog.account.id] : "";
  const safetyAccount = dialog?.type === "safety" ? dialog.account?.id && accounts.find(item => item.id === dialog.account.id) || dialog.account || accounts.find(item => item.id === activeId) || null : null;
  const isSafetyActive = Boolean(!safetyAccount || activeId && safetyAccount.id === activeId);
  const safetyHold = isSafetyActive ? snap.safety : safetyAccount?.safety?.blocked ? safetyAccount.safety : {
    blocked: true,
    kind: "review",
    reason: "该账号处于保护暂停状态"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: `app ${collapsed ? "side-collapsed" : ""}`
  }, /*#__PURE__*/React.createElement(Sidebar, {
    page: page,
    onPage: setPage,
    account: account,
    avatar: accountAvatar || accountAvatars[activeId],
    onQuit: () => setDialog({
      type: "quit"
    }),
    brandHidden: true,
    collapsed: collapsed,
    inert: modalOpen
  }), /*#__PURE__*/React.createElement("main", {
    className: "main",
    "aria-busy": !connected,
    inert: modalOpen ? "" : undefined
  }, /*#__PURE__*/React.createElement("header", {
    className: "chrome pywebview-drag-region"
  }, /*#__PURE__*/React.createElement(SidebarToggle, {
    collapsed: collapsed,
    onToggle: toggleSidebar
  }), /*#__PURE__*/React.createElement("div", {
    className: "chrome-brand"
  }, /*#__PURE__*/React.createElement("span", {
    className: "logo"
  }, /*#__PURE__*/React.createElement(Pulse, {
    size: 15
  })), /*#__PURE__*/React.createElement("span", {
    className: "chrome-name"
  }, "\u30D3\u30EA\u63A8\u3057")), /*#__PURE__*/React.createElement("span", {
    className: "chrome-divider",
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("h1", {
    className: "chrome-title",
    tabIndex: -1,
    ref: titleRef
  }, pageTitles[page]), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("div", {
    className: "chrome-actions"
  }, page === "monitor" && /*#__PURE__*/React.createElement(window.OverviewActions, {
    paused: snap.paused,
    onTogglePause: () => control("toggle_pause"),
    onCheck: () => control("check_now"),
    checking: snap.checking,
    controlBusy: controlBusy,
    closing: closing
  })), /*#__PURE__*/React.createElement(WindowButtons, null)), page === "monitor" && accounts.length > 0 && /*#__PURE__*/React.createElement(window.AccountTabs, {
    accounts: accounts,
    activeId: activeId,
    avatars: accountAvatars,
    onSelect: switchAccount,
    onAdd: () => openQr("")
  }), /*#__PURE__*/React.createElement("div", {
    className: "page",
    id: "monitor-body"
  }, page === "monitor" && /*#__PURE__*/React.createElement(window.Overview, {
    key: activeId,
    rooms: rooms,
    selectedId: selectedId,
    onSelect: select,
    paused: snap.paused,
    onAction: roomAction,
    onOpen: id => invoke("open_room", [id]),
    onAddMember: openAdd,
    onSyncMedals: openMedals,
    onRemove: remove,
    onContextMenu: onContextMenu,
    busyRoom: busyRoom,
    controlBusy: controlBusy,
    error: snap.error || snap.ui_error,
    recovery: snap.recovery,
    onRecovery: recover,
    interval: snap.settings?.check_minutes || 5,
    lastCheck: snap.last_check,
    checking: snap.checking,
    images: images,
    signedIn: account.signed_in,
    closing: closing,
    bridgeConnected: connected,
    onBatchRemove: batchRemove,
    onClearRoomBlock: clearRoomBlock,
    onDismissTaskError: dismissTaskError
  }), page === "growth" && /*#__PURE__*/React.createElement(window.GrowthPage, {
    viewId: activeId,
    images: images,
    onNeedAvatar: fetchAvatar,
    onOpenAccount: () => setPage("account"),
    onOpenMonitor: () => setPage("monitor")
  }), page === "automation" && /*#__PURE__*/React.createElement(window.SettingsPage, {
    settings: snap.settings || DEFAULT_SETTINGS,
    onSetting: setSetting,
    pendingSettings: pendingSettings,
    theme: theme,
    onTheme: chooseTheme,
    dayTheme: dayTheme,
    onDayTheme: chooseDayTheme,
    scope: accounts.find(item => item.id === activeId) || null,
    scopeAll: false,
    onLogs: () => invoke("open_logs", [activeId]),
    onHostLogs: () => invoke("open_logs", [""]),
    onDiagnostics: openDiagnostics,
    version: snap.version
  }), page === "account" && /*#__PURE__*/React.createElement(window.AccountPage, {
    accounts: accounts,
    activeId: activeId,
    viewId: activeId,
    account: account,
    avatar: accountAvatar,
    avatars: accountAvatars,
    onScan: openQr,
    onView: () => setPage("monitor"),
    onSwitch: switchAccount,
    onLogout: id => setDialog({
      type: "logout",
      account: accounts.find(item => item.id === id)
    }),
    onRemove: id => setDialog({
      type: "removeAccount",
      account: accounts.find(item => item.id === id)
    }),
    onProtection: id => openSafety(accounts.find(item => item.id === id)),
    onResumeSafety: () => openSafety(),
    onCheckSafety: checkSafety,
    safetyProbe: safetyProbe,
    onCheck: () => control("check_now"),
    busy: closing,
    version: snap.version
  }))), /*#__PURE__*/React.createElement("div", {
    className: "toasts",
    "aria-live": "polite"
  }, toasts.map(item => /*#__PURE__*/React.createElement("div", {
    key: item.id,
    className: `toast ${item.tone}`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: item.tone === "info" ? "check" : "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, item.text)))), qr && /*#__PURE__*/React.createElement(window.QrModal, {
    qr: qr,
    onClose: closeQr,
    onRetry: () => openQr(qr.account_id || "")
  }), dialog === "add" && /*#__PURE__*/React.createElement(window.AddMemberModal, {
    query: query,
    onQuery: onQuery,
    result: searchResult,
    loading: searching,
    adding: dialogBusy,
    onSearch: search,
    onAdd: add,
    onClose: closeDialog,
    onSyncMedals: openMedals
  }), dialog === "medals" && /*#__PURE__*/React.createElement(window.MedalsModal, {
    data: medals.data,
    loading: medals.loading,
    error: medals.error,
    selected: medalSelection,
    onToggle: uid => setMedalSelection(current => {
      const next = new Set(current);
      if (next.has(uid)) next.delete(uid);else next.add(uid);
      return next;
    }),
    onImport: importMedals,
    importing: dialogBusy,
    onClose: closeDialog,
    onRetry: openMedals
  }), dialog === "diagnostic" && /*#__PURE__*/React.createElement(window.DiagnosticModal, {
    preview: diagPreview,
    loading: diagLoading,
    anonymize: diagAnonymize,
    includeState: diagIncludeState,
    onChangeAnonymize: changeDiagAnonymize,
    onChangeIncludeState: checked => {
      setDiagIncludeState(checked);
      setDiagExported(null);
    },
    exporting: diagExporting,
    exported: diagExported,
    statusText: diagStatus,
    onExport: exportDiagnostic,
    onCopySummary: copyDiagnosticSummary,
    onOpenExports: () => invoke("open_exports"),
    onClose: () => {
      if (!diagExporting) {
        dialogGeneration.current += 1;
        setDialog(null);
      }
    }
  }), dialog?.type === "safety" && /*#__PURE__*/React.createElement(window.SafetyModal, {
    hold: safetyHold,
    account: safetyAccount,
    isActive: isSafetyActive,
    probeState: safetyProbe,
    busy: dialogBusy,
    onCheck: autoResume => checkSafety(autoResume, safetyAccount?.id),
    onResume: confirmAction,
    onOpenLink: openSafetyLink,
    onScan: openQr,
    onClose: closeDialog
  }), dialog?.type && dialogCopy[dialog.type] && /*#__PURE__*/React.createElement(window.ConfirmModal, _extends({}, dialogCopy[dialog.type], {
    body: dialog.type === "switch" || dialog.type === "logout" || dialog.type === "removeAccount" ? /*#__PURE__*/React.createElement("div", {
      className: "account-preview"
    }, /*#__PURE__*/React.createElement(window.AccountAvatar, {
      account: dialog.account,
      size: "lg",
      image: modalAvatar
    }), /*#__PURE__*/React.createElement("div", {
      className: "account-preview-main"
    }, /*#__PURE__*/React.createElement("strong", null, dialog.account?.name), /*#__PURE__*/React.createElement("span", null, "UID ", dialog.account?.uid, " \xB7 \u5173\u6CE8 ", dialog.account?.room_count, " \u4F4D\u4E3B\u64AD"))) : null,
    onConfirm: confirmAction,
    onClose: closeDialog,
    busy: dialogBusy
  })), menu && /*#__PURE__*/React.createElement(window.RoomMenu, {
    menu: menu,
    room: rooms.find(room => room.room === menu.room),
    onClose: () => setMenu(null),
    onOpen: id => invoke("open_room", [id]),
    onAction: roomAction,
    onRemove: remove
  }));
}
ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(App, null));
})();
