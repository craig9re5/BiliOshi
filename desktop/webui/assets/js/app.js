/* BiliOshi JSX {"code_sha256":"3d158825eef599a7428655b637c4018dd58aa8627fa472d320e769decd94c86b","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"app.jsx","source_sha256":"776d3b289b8a6aadad6e5968b13bc13dfc799a24c4203999ebf17f7f9415d203"} */
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
const THEME_KEYS = ["white", "paper", "mist", "apricot"];
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
  onLogs,
  onQuit,
  brandHidden,
  collapsed,
  onSwitcher,
  switcherOpen
}) => /*#__PURE__*/React.createElement("aside", {
  className: "side"
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
}, [["monitor", "monitor", "直播总览"], ["growth", "trend", "成长记录"], ["automation", "sliders", "挂机设置"], ["account", "user", "账号"]].map(([key, icon, text]) => /*#__PURE__*/React.createElement("button", {
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
  onClick: onLogs,
  "aria-label": "\u67E5\u770B\u65E5\u5FD7",
  title: "\u67E5\u770B\u65E5\u5FD7"
}, /*#__PURE__*/React.createElement(Icon, {
  name: "folder"
}), /*#__PURE__*/React.createElement("span", null, "\u67E5\u770B\u65E5\u5FD7")), /*#__PURE__*/React.createElement("button", {
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
  onClick: onSwitcher,
  title: "\u5207\u6362\u8D26\u53F7",
  "aria-haspopup": "menu",
  "aria-expanded": Boolean(switcherOpen)
}, /*#__PURE__*/React.createElement("span", {
  className: "sidebar-avatar"
}, avatar ? /*#__PURE__*/React.createElement("img", {
  src: avatar,
  alt: ""
}) : Array.from(account.name || "?")[0]), /*#__PURE__*/React.createElement("span", {
  className: "sidebar-account-text"
}, /*#__PURE__*/React.createElement("strong", null, account.name || (account.signed_in ? "等待验证" : "尚未登录")), /*#__PURE__*/React.createElement("small", null, account.subtitle || ""))));
const pageTitles = {
  monitor: "直播总览",
  growth: "成长记录",
  automation: "挂机设置",
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
  const [theme, setTheme] = useState(() => {
    const current = document.documentElement.dataset.theme;
    return THEME_KEYS.includes(current) ? current : "white";
  });
  const chooseTheme = useCallback(value => {
    if (!THEME_KEYS.includes(value)) return;
    setTheme(value);
    document.documentElement.dataset.theme = value;
    try {
      window.localStorage.setItem("bilioshi.theme", value);
    } catch {}
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
  const [query, setQuery] = useState("");
  const [searchResult, setSearchResult] = useState(null);
  const [searching, setSearching] = useState(false);
  const [medals, setMedals] = useState({
    data: [],
    loading: false,
    error: ""
  });
  const [medalSelection, setMedalSelection] = useState(new Set());
  const [qr, setQr] = useState(null);
  const [menu, setMenu] = useState(null);
  const [images, setImages] = useState({});
  const [accountAvatar, setAccountAvatar] = useState("");
  const [avatarVersion, setAvatarVersion] = useState(0);
  const [toasts, setToasts] = useState([]);
  const [switcher, setSwitcher] = useState(false);
  const latest = useRef(EMPTY_SNAPSHOT);
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
        } else if (event.type === "add_member") handlers.current.openAdd?.();else if (event.type === "sync_medals") handlers.current.openMedals?.();else if (event.type === "toast") toast(payload.message, payload.tone);else if (event.type === "settings_changed") handlers.current.refresh?.();
      }
    };
    bridgeReady().then(async ready => {
      if (!alive.current) return;
      if (!ready) {
        toast("无法连接后台，重启应用后重试", "error");
        return;
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
      toastTimers.current.forEach(timer => window.clearTimeout(timer));
    };
  }, [receiveSnapshot, toast]);
  const accounts = snap.accounts || [];
  const activeId = snap.active_account_id || "";
  const viewId = snap.view_account_id || "all";
  const isAllView = viewId === "all" || !viewId;
  // The top level stays the running account; a different account carries its
  // own snapshot so stale data is never shown as live.
  const viewed = !isAllView && viewId !== activeId && snap.view ? snap.view : snap;
  useEffect(() => {
    const rows = viewed.rows || [];
    if (!selectionInitialized.current && rows.length) {
      selectionInitialized.current = true;
      setSelectedId(rows[0].room);
    } else if (selectedId !== null && !rows.some(row => row.room === selectedId)) setSelectedId(null);
  }, [viewed.rows, selectedId]);
  useEffect(() => {
    if (!connected || !viewed.accountInfo?.signed_in) return;
    const now = Date.now();
    for (const row of viewed.rows || []) {
      if (!row.uid || images[row.uid] || avatarPending.current.has(row.uid)) continue;
      if (now < (avatarRetry.current[row.uid] || 0)) continue;
      avatarPending.current.add(row.uid);
      call("avatar", row.uid, "", viewId === "all" ? "" : viewId).then(result => {
        avatarPending.current.delete(row.uid);
        if (result?.ok && result.data_uri && alive.current) {
          delete avatarRetry.current[row.uid];
          setImages(items => ({
            ...items,
            [row.uid]: result.data_uri
          }));
        } else {
          avatarRetry.current[row.uid] = Date.now() + 60000;
        }
      }).catch(() => {
        // A failed request must release the slot or the room keeps its letter
        // placeholder until the whole app restarts.
        avatarPending.current.delete(row.uid);
        avatarRetry.current[row.uid] = Date.now() + 60000;
      });
    }
  }, [viewed.rows, connected, images, viewId]);
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
      call("account_avatar", viewId === "all" ? "" : viewId).then(result => {
        if (!live) return;
        if (result?.ok && result.data_uri) setAccountAvatar(result.data_uri);else if (result?.error) retry = window.setTimeout(load, 60000);
      }).catch(() => {
        if (live) retry = window.setTimeout(load, 60000);
      });
    };
    load();
    return () => {
      live = false;
      window.clearTimeout(retry);
    };
  }, [connected, account.signed_in, account.name, avatarVersion, viewId]);
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
        }, viewId === "all" ? "" : viewId]);
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

  /* Changing the running account is explicit: the switcher only changes the
     viewed account, so a second account never steals the running slot. */
  const requestSwitch = accountId => {
    const target = accounts.find(item => item.id === accountId);
    if (!target) return;
    if (!target.signed_in || target.status === "needs_login") {
      openQr(accountId);
      return;
    }
    if (target.status === "blocked") {
      setDialog({
        type: "protection",
        account: target
      });
      return;
    }
    setDialog({
      type: "switch",
      account: target
    });
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
      } else if (kind === "safety") result = await invoke("resume_safety");else if (kind === "quit") result = await invoke("quit");else if (kind === "protection") result = {
        ok: true
      };else if (kind === "switch") {
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
    const route = viewed.recovery || {};
    if (route.action === "login") openQr(viewId === "all" ? "" : viewId);else if (route.action === "resume") control("toggle_pause");else if (route.action === "switch") {
      setPage("monitor");
    } else if (route.action === "safety") {
      if (viewed.safety?.kind === "auth" || viewed.safety?.kind === "credentials") openQr(viewId === "all" ? "" : viewId);else if (viewed.safety?.until > Date.now() / 1000) {
        setPage("account");
      } else setDialog({
        type: "safety"
      });
    } else if (route.action === "room") {
      setPage("monitor");
      setSelectedId(route.room);
    } else if (route.action === "logs") invoke("open_logs", [viewId === "all" ? "" : viewId]);else if (route.action === "refresh") control("refresh");else control("check_now");
  };
  handlers.current = {
    openQr,
    openAdd,
    openMedals,
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
  const onContextMenu = (event, id) => {
    event.preventDefault();
    select(id);
    setMenu({
      room: id,
      x: event.clientX,
      y: event.clientY
    });
  };
  const viewAccount = async accountId => {
    setSwitcher(false);
    if (accountId === "all") {
      await invoke("set_view_account", ["all"]);
      await refresh();
      return;
    }
    await invoke("set_view_account", [accountId]);
    selectionInitialized.current = false;
    setSelectedId(null);
    await refresh();
  };
  const dialogCopy = {
    remove: {
      title: "移除主播？",
      desc: `不再对「${dialog?.room?.name || ""}」执行挂机与每日任务。可随时重新添加。`,
      confirmLabel: "移除主播",
      danger: true
    },
    logout: {
      title: "退出这个账号的登录？",
      desc: "会停止此账号的挂机并删除本机登录凭证；关注列表、任务进度、额度与保护记录保留。其他账号不受影响。",
      confirmLabel: "退出登录",
      danger: true
    },
    safety: {
      title: "恢复账号操作？",
      desc: "先在 B 站完成验证并确认限制已解除。恢复后会重新检查账号，当天发送额度不会重置。",
      confirmLabel: "确认并恢复"
    },
    quit: {
      title: "退出 ビリ推し？",
      desc: "将停止所有挂机连接。关闭窗口可继续在托盘运行。",
      confirmLabel: "退出应用",
      danger: true
    },
    switch: {
      title: "切换挂机账号？",
      desc: "连接会短暂中断；任务进度与今日额度保留，不需要重新扫码。",
      confirmLabel: "切换并挂机"
    },
    removeAccount: {
      title: "移除这个账号？",
      desc: "会删除本机登录凭证并移出账号列表。关注列表、任务进度、额度与保护记录会保留，重新添加同一账号后可继续使用。",
      confirmLabel: "移除账号",
      danger: true
    },
    protection: {
      title: "账号保护暂停",
      desc: "收到验证或异常拒绝，账号操作已暂停。重新扫码不会解除，需要先在平台处理。",
      confirmLabel: "知道了"
    }
  };
  const sidebarAccount = {
    ...account,
    subtitle: isAllView ? snap.global_paused ? "挂机：全局暂停中" : accounts.filter(item => item.running).length ? `挂机：${accounts.filter(item => item.running).map(item => item.name).join("、")}` : "挂机：无" : viewed.inactive ? "此账号未运行" : "当前挂机"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: `app ${collapsed ? "side-collapsed" : ""}`
  }, /*#__PURE__*/React.createElement(Sidebar, {
    page: page,
    onPage: setPage,
    account: sidebarAccount,
    avatar: accountAvatar,
    onLogs: () => invoke("open_logs", [viewId === "all" ? "" : viewId]),
    onQuit: () => setDialog({
      type: "quit"
    }),
    brandHidden: true,
    collapsed: collapsed,
    onSwitcher: () => setSwitcher(value => !value),
    switcherOpen: switcher
  }), /*#__PURE__*/React.createElement(window.AccountSwitcher, {
    open: switcher,
    accounts: accounts,
    viewId: viewId,
    activeId: activeId,
    onSelect: viewAccount,
    onManage: () => {
      setSwitcher(false);
      setPage("account");
    },
    onAdd: () => {
      setSwitcher(false);
      openQr("");
    },
    onClose: () => setSwitcher(false)
  }), /*#__PURE__*/React.createElement("main", {
    className: "main",
    "aria-busy": !connected
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
    className: "chrome-title"
  }, pageTitles[page]), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("div", {
    className: "chrome-actions"
  }, page === "monitor" && !isAllView && /*#__PURE__*/React.createElement(window.OverviewActions, {
    paused: viewed.paused,
    onTogglePause: () => control("toggle_pause"),
    onCheck: () => control("check_now"),
    checking: viewed.checking,
    controlBusy: controlBusy,
    closing: closing,
    inactive: Boolean(viewed.inactive)
  }), page === "monitor" && isAllView && accounts.length > 0 && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: () => control("check_now"),
    disabled: controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), "\u5168\u90E8\u68C0\u67E5"), snap.global_paused ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: () => control("set_global_paused", [false]),
    disabled: controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 13
  }), "\u6062\u590D\u5168\u90E8") : /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: () => control("set_global_paused", [true]),
    disabled: controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "pause",
    size: 13
  }), "\u5168\u90E8\u6682\u505C"))), /*#__PURE__*/React.createElement(WindowButtons, {
    key: page
  })), page === "monitor" && /*#__PURE__*/React.createElement(window.AccountTabs, {
    accounts: accounts,
    viewId: viewId,
    activeId: activeId,
    onView: viewAccount,
    onAdd: () => openQr("")
  }), /*#__PURE__*/React.createElement("div", {
    className: "page",
    id: "monitor-body"
  }, page === "monitor" && isAllView && /*#__PURE__*/React.createElement(window.AccountDashboard, {
    accounts: accounts,
    globalPaused: Boolean(snap.global_paused),
    onView: viewAccount,
    onSwitch: requestSwitch,
    onCheckAll: () => control("check_now"),
    onPauseAll: () => control("set_global_paused", [true]),
    onResumeAll: () => control("set_global_paused", [false]),
    onRelogin: id => openQr(id),
    onProtection: id => setDialog({
      type: "protection",
      account: accounts.find(item => item.id === id)
    }),
    busy: controlBusy || closing
  }), page === "monitor" && !isAllView && /*#__PURE__*/React.createElement(window.Overview, {
    rooms: rooms,
    selectedId: selectedId,
    onSelect: select,
    paused: viewed.paused,
    onAction: roomAction,
    onOpen: id => invoke("open_room", [id]),
    onAddMember: openAdd,
    onSyncMedals: openMedals,
    onRemove: remove,
    onContextMenu: onContextMenu,
    busyRoom: busyRoom,
    controlBusy: controlBusy,
    error: viewed.error || viewed.ui_error,
    recovery: viewed.recovery,
    onRecovery: recover,
    interval: viewed.settings?.check_minutes || 5,
    lastCheck: viewed.last_check,
    checking: viewed.checking,
    images: images,
    signedIn: account.signed_in,
    closing: closing,
    bridgeConnected: connected,
    accountName: accounts.find(item => item.id === viewId)?.name || "",
    inactive: Boolean(viewed.inactive),
    onSwitch: () => requestSwitch(viewId)
  }), page === "growth" && /*#__PURE__*/React.createElement(window.GrowthPage, {
    viewId: viewId,
    onOpenAccount: () => setPage("account"),
    onOpenMonitor: () => setPage("monitor")
  }), page === "automation" && /*#__PURE__*/React.createElement(window.SettingsPage, {
    settings: viewed.settings || DEFAULT_SETTINGS,
    onSetting: setSetting,
    pendingSettings: pendingSettings,
    theme: theme,
    onTheme: chooseTheme,
    scope: accounts.find(item => item.id === viewId) || null,
    scopeAll: isAllView
  }), page === "account" && /*#__PURE__*/React.createElement(window.AccountPage, {
    accounts: accounts,
    activeId: activeId,
    viewId: viewId,
    account: account,
    avatar: accountAvatar,
    onScan: openQr,
    onView: viewAccount,
    onSwitch: requestSwitch,
    onLogout: id => setDialog({
      type: "logout",
      account: accounts.find(item => item.id === id)
    }),
    onRemove: id => setDialog({
      type: "removeAccount",
      account: accounts.find(item => item.id === id)
    }),
    onProtection: id => setDialog({
      type: "protection",
      account: accounts.find(item => item.id === id)
    }),
    onResumeSafety: () => setDialog({
      type: "safety"
    }),
    onCheck: () => control("check_now"),
    busy: controlBusy || closing,
    inactive: Boolean(viewed.inactive),
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
    onClose: closeDialog
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
  }), dialog?.type && dialogCopy[dialog.type] && /*#__PURE__*/React.createElement(window.ConfirmModal, _extends({}, dialogCopy[dialog.type], {
    body: dialog.type === "switch" || dialog.type === "logout" || dialog.type === "removeAccount" ? /*#__PURE__*/React.createElement("div", {
      className: "account-preview"
    }, /*#__PURE__*/React.createElement(window.AccountAvatar, {
      account: dialog.account,
      size: "lg"
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
