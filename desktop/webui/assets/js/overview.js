/* BiliOshi JSX {"code_sha256":"b9c1d7b41fdb2bb7732f793612ea03cb0ae1b2c6e08d8700b271be348c20cbaf","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"overview.jsx","source_sha256":"659466f9c8ed78969567db0e1a26bde15e5d84317d323b34d8aa8f5ef425602c"} */
(function () {
"use strict";
/* Overview and room detail. Labels describe verified state from the engine. */

const {
  Icon,
  relativeTime,
  absoluteTime,
  durationLabel,
  numberLabel
} = window;
const copyTimers = new WeakMap();
let lastCopyMessage = "";
function legacyCopyText(text) {
  const field = Object.assign(document.createElement("textarea"), {
    value: text
  });
  field.setAttribute("readonly", "");
  field.style.cssText = "position:fixed;inset-block-start:0;opacity:0";
  document.body.append(field);
  field.select();
  try {
    return document.execCommand("copy");
  } finally {
    field.remove();
  }
}
function reportCopyStatus(button, ok) {
  const tip = button.nextElementSibling;
  window.clearTimeout(copyTimers.get(button));
  button.removeAttribute("data-copied");
  button.removeAttribute("data-failed");
  let message = ok ? "已复制" : "复制失败";
  if (message === lastCopyMessage) message += "\u00A0";
  lastCopyMessage = message;
  if (tip) tip.textContent = "";
  void button.offsetWidth;
  button.setAttribute(ok ? "data-copied" : "data-failed", "");
  window.requestAnimationFrame(() => {
    if (tip) tip.textContent = message;
  });
  copyTimers.set(button, window.setTimeout(() => {
    button.removeAttribute("data-copied");
    button.removeAttribute("data-failed");
    if (tip) tip.textContent = "";
  }, 1800));
}
async function copyTargetText(button, target) {
  const raw = target.matches?.("input, textarea") ? target.value : target.innerText || target.textContent || "";
  const text = String(raw).trim();
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);else if (!legacyCopyText(text)) throw new Error("Copy failed");
    reportCopyStatus(button, true);
  } catch {
    if (legacyCopyText(text)) reportCopyStatus(button, true);else reportCopyStatus(button, false);
  }
}
if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  if ("CommandEvent" in window) {
    document.addEventListener("command", event => {
      if (event.command === "--copy" && event.source && event.target) {
        copyTargetText(event.source, event.target);
      }
    }, true);
  } else {
    document.addEventListener("click", event => {
      const button = event.target?.closest?.('button[command="--copy"]');
      if (!button) return;
      const target = document.getElementById(button.getAttribute("commandfor"));
      if (target) copyTargetText(button, target);
    });
  }
}
const Avatar = ({
  room,
  image
}) => /*#__PURE__*/React.createElement("span", {
  className: "avatar",
  style: {
    background: room.color
  },
  "aria-hidden": "true"
}, image ? /*#__PURE__*/React.createElement("img", {
  src: image,
  alt: ""
}) : room.initial);
const TASK_ICONS = {
  danmaku: "chat",
  like: "heart",
  watch: "monitor",
  light: "medal"
};
const RoomRow = ({
  room,
  selected,
  onSelect,
  onContextMenu,
  image,
  managing,
  checked,
  onToggleCheck
}) => {
  const metaParts = [];
  if (room.healthy) metaParts.push(`已连接 ${durationLabel(room.minutes)}`);else if (room.live && room.live_duration) metaParts.push(room.live_duration);
  if (room.gain !== null && (room.gain > 0 || room.healthy)) {
    metaParts.push(`今日 +${numberLabel(room.gain)}`);
  } else if (!room.live && room.medal_name) {
    metaParts.push(`${room.medal_name} Lv.${room.medal_level}`);
  }
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: `room ${managing ? "managing" : ""} ${checked ? "batch-checked" : ""}`,
    role: "option",
    "aria-selected": managing ? checked : selected,
    "data-room": room.room,
    onClick: () => managing ? onToggleCheck(room.room) : onSelect(room.room),
    onContextMenu: event => !managing && onContextMenu(event, room.room)
  }, managing && /*#__PURE__*/React.createElement("span", {
    className: `room-check ${checked ? "checked" : ""}`,
    "aria-hidden": "true"
  }, checked && /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 11
  })), /*#__PURE__*/React.createElement(Avatar, {
    room: room,
    image: image
  }), /*#__PURE__*/React.createElement("span", {
    className: "room-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "room-name"
  }, room.live && /*#__PURE__*/React.createElement("i", {
    className: "live-dot",
    title: "\u76F4\u64AD\u4E2D"
  }), /*#__PURE__*/React.createElement("span", null, room.name)), room.live && room.title && /*#__PURE__*/React.createElement("span", {
    className: "room-title",
    title: room.title
  }, room.title), metaParts.length > 0 && /*#__PURE__*/React.createElement("span", {
    className: "room-meta"
  }, metaParts.map((part, idx) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: idx
  }, idx > 0 && /*#__PURE__*/React.createElement("span", {
    className: "sep"
  }, "\xB7"), /*#__PURE__*/React.createElement("span", null, part))))), room.state !== "未开播" && /*#__PURE__*/React.createElement("span", {
    className: "room-side"
  }, /*#__PURE__*/React.createElement("span", {
    className: `pill ${room.tone}`
  }, room.state)));
};
const DetailPanel = ({
  room,
  image,
  busy,
  autoWatch = true,
  onAction,
  onOpen,
  onMore,
  moreOpen,
  onClearRoomBlock,
  onDismissTaskError,
  onDismissWatchWarning,
  dimmed
}) => {
  const classes = `detail card${dimmed ? " detail-dim" : ""}`;
  if (!room) return /*#__PURE__*/React.createElement("aside", {
    className: classes,
    "aria-label": "\u76F4\u64AD\u95F4\u8BE6\u60C5",
    "aria-hidden": dimmed || undefined
  }, /*#__PURE__*/React.createElement("div", {
    className: "empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "monitor",
    size: 24
  }), /*#__PURE__*/React.createElement("strong", null, "\u9009\u62E9\u4E00\u4E2A\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("span", null, "\u67E5\u770B\u8FDE\u63A5\u72B6\u6001\u4E0E\u4ECA\u65E5\u4EFB\u52A1")));
  const taskCount = room.tasks.filter(task => task.done).length;
  const reason = room.actions.redo || "";
  const operation = room.operation;
  const pending = busy || operation.pending;
  const knownExperience = !room.tasks_stale && room.next_intimacy > 0;
  const progress = knownExperience ? Math.min(100, Math.max(0, room.intimacy / room.next_intimacy * 100)) : 0;
  const note = room.watch_note || "";
  const showStateRow = room.live || room.active || room.reconnecting || room.tone === "warn";
  const showReason = reason && (room.live || room.tone === "warn");
  const medalLit = !room.tasks_stale && room.is_lighted === 1;
  const medalUnlit = !room.tasks_stale && room.is_lighted === 0;
  return /*#__PURE__*/React.createElement("aside", {
    className: classes,
    "aria-label": "\u76F4\u64AD\u95F4\u8BE6\u60C5",
    "aria-hidden": dimmed || undefined,
    "data-screen-label": `详情 · ${room.name}`
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-scroll",
    key: room.room
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-heading"
  }, /*#__PURE__*/React.createElement(Avatar, {
    room: room,
    image: image
  }), /*#__PURE__*/React.createElement("div", {
    className: "detail-identity"
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-name"
  }, room.name), /*#__PURE__*/React.createElement("div", {
    className: "detail-title",
    title: room.title
  }, room.live ? room.title || "直播中" : room.state), /*#__PURE__*/React.createElement("div", {
    className: "detail-submeta"
  }, /*#__PURE__*/React.createElement("span", {
    className: "tnum"
  }, "\u623F\u95F4 ", /*#__PURE__*/React.createElement("span", {
    id: `room-code-${room.room}`
  }, room.room)), /*#__PURE__*/React.createElement("span", {
    className: "copy-inline"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "copy-room-btn",
    command: "--copy",
    commandfor: `room-code-${room.room}`,
    "aria-label": "\u590D\u5236\u76F4\u64AD\u95F4\u53F7",
    title: "\u590D\u5236\u76F4\u64AD\u95F4\u53F7"
  }, /*#__PURE__*/React.createElement("span", {
    className: "copy-ico copy-ico-default",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 11
  })), /*#__PURE__*/React.createElement("span", {
    className: "copy-ico copy-ico-done",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 11
  }))), /*#__PURE__*/React.createElement("span", {
    className: "copy-tip",
    role: "status"
  })), room.live && room.area_name && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "sep"
  }, "\xB7"), /*#__PURE__*/React.createElement("span", null, room.area_name)), room.live && room.live_duration && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
    className: "sep"
  }, "\xB7"), /*#__PURE__*/React.createElement("span", null, room.live_duration)))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: `btn ghost icon-button${moreOpen ? " active" : ""}`,
    title: "\u66F4\u591A\u64CD\u4F5C",
    "aria-label": "\u66F4\u591A\u64CD\u4F5C",
    "aria-haspopup": "menu",
    "aria-expanded": Boolean(moreOpen),
    onPointerDown: event => {
      if (moreOpen) event.stopPropagation();
    },
    onMouseDown: event => {
      if (moreOpen) event.stopPropagation();
    },
    onClick: onMore
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "more",
    size: 17
  }))), showStateRow && /*#__PURE__*/React.createElement("div", {
    className: "state-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: `state-label ${room.tone === "warn" ? "warn" : ""}`
  }, room.state, /*#__PURE__*/React.createElement("span", {
    className: "state-sub",
    title: absoluteTime(room.last_heartbeat)
  }, room.healthy ? `已连接 ${durationLabel(room.minutes)}` : room.daily_complete && !room.active ? "已自动结束看播，让出结算名额" : !autoWatch ? "已关闭此账号直播自动挂机" : room.live ? "开播后自动建立连接" : "等待恢复正常", room.last_heartbeat && room.active ? ` · ${relativeTime(room.last_heartbeat)}同步` : "")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "link-btn state-action",
    onClick: () => onAction("reconnect", room.room),
    disabled: pending || Boolean(room.actions.reconnect),
    title: room.actions.reconnect || "重新建立看播连接"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "reconnect",
    size: 11,
    className: room.reconnecting ? "spin" : ""
  }), room.reconnecting ? "重连中…" : "重新连接")), /*#__PURE__*/React.createElement("div", {
    className: "gain-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "gain-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "gain-label"
  }, "\u4ECA\u65E5\u4EB2\u5BC6\u5EA6"), room.medal_name && /*#__PURE__*/React.createElement("span", {
    className: `gain-medal ${medalLit ? "lit" : medalUnlit ? "unlit" : ""}`
  }, room.medal_name, " Lv.", room.medal_level, medalUnlit ? " · 未点亮" : "")), /*#__PURE__*/React.createElement("div", {
    className: "gain-value"
  }, room.gain === null ? "—" : `+${numberLabel(room.gain)}`), /*#__PURE__*/React.createElement("div", {
    className: "gain-foot"
  }, /*#__PURE__*/React.createElement("span", null, room.gain === null ? room.no_medal ? "无此主播粉丝牌" : "等待更新" : "今日已获得"), room.day_limit > 0 && /*#__PURE__*/React.createElement("span", {
    className: "tnum"
  }, "\u6BCF\u65E5\u4E0A\u9650 ", numberLabel(room.day_limit))), knownExperience && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "bar level-bar",
    role: "progressbar",
    "aria-label": "\u7C89\u4E1D\u724C\u5347\u7EA7\u8FDB\u5EA6",
    "aria-valuenow": room.intimacy,
    "aria-valuemin": 0,
    "aria-valuemax": room.next_intimacy
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: `${progress}%`
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "gain-foot"
  }, /*#__PURE__*/React.createElement("span", null, "\u7B49\u7EA7\u7ECF\u9A8C\uFF08", Math.round(progress), "%\uFF09"), /*#__PURE__*/React.createElement("span", {
    className: "tnum"
  }, numberLabel(room.intimacy), " / ", numberLabel(room.next_intimacy))))), (room.connection_warning || room.watch_warning || room.task_error) && (() => {
    const dismissHandler = room.connection_warning || room.protectedAccount ? null : room.watch_warning ? onDismissWatchWarning : room.task_error ? onDismissTaskError : null;
    return /*#__PURE__*/React.createElement("div", {
      className: `notice${dismissHandler ? " notice-action" : ""}`,
      role: "status"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "alert",
      size: 14
    }), /*#__PURE__*/React.createElement("span", {
      className: "notice-body"
    }, room.connection_warning || room.watch_warning || room.task_error), dismissHandler && /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn sm",
      disabled: pending,
      onClick: () => dismissHandler(room.room)
    }, "\u77E5\u9053\u4E86"));
  })(), note && /*#__PURE__*/React.createElement("div", {
    className: "notice neutral"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, note)), Array.isArray(room.room_blocks) && room.room_blocks.map(block => /*#__PURE__*/React.createElement("div", {
    className: "notice notice-action",
    key: `${block.kind || "cap"}-${block.since || 0}`,
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("div", {
    className: "notice-body"
  }, /*#__PURE__*/React.createElement("strong", null, block.kind_label || "单房间互动受限"), /*#__PURE__*/React.createElement("span", null, block.reason || "该直播间互动权限受限，不影响挂机看播。")), onClearRoomBlock && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    disabled: pending,
    onClick: () => onClearRoomBlock(room.room, block.kind || null)
  }, "\u89E3\u9664\u9650\u5236"))), room.reconnect_message && /*#__PURE__*/React.createElement("div", {
    className: "inline-status",
    role: "status"
  }, room.reconnect_message), /*#__PURE__*/React.createElement("section", {
    className: "block"
  }, /*#__PURE__*/React.createElement("div", {
    className: "block-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "block-title"
  }, "\u4ECA\u65E5\u4EFB\u52A1"), /*#__PURE__*/React.createElement("span", {
    className: "block-note tnum"
  }, room.no_medal ? "未持有粉丝牌" : room.tasks_stale ? "等待更新" : `${taskCount} / ${room.tasks.length} 已完成`)), room.no_medal ? /*#__PURE__*/React.createElement("p", {
    className: "action-hint"
  }, "\u5F53\u524D\u8D26\u53F7\u5C1A\u672A\u62E5\u6709\u8BE5\u4E3B\u64AD\u7684\u7C89\u4E1D\u724C\uFF0C\u6682\u4E0D\u7EDF\u8BA1\u6BCF\u65E5\u4EB2\u5BC6\u5EA6\u4EFB\u52A1\u3002") : /*#__PURE__*/React.createElement("div", {
    className: "task-table"
  }, room.tasks.map(task => {
    const canRedoSingle = !room.tasks_stale && !task.done && !pending && !reason && (task.key === "danmaku" || task.key === "like");
    return /*#__PURE__*/React.createElement("div", {
      className: "task",
      key: task.key
    }, /*#__PURE__*/React.createElement("span", {
      className: "task-left"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: TASK_ICONS[task.key] || "circle",
      size: 13
    }), /*#__PURE__*/React.createElement("span", {
      className: "task-name"
    }, task.name)), /*#__PURE__*/React.createElement("span", {
      className: "task-right"
    }, /*#__PURE__*/React.createElement("span", {
      className: `task-val ${task.done ? "done" : !task.text ? "pending" : ""}`
    }, task.done && /*#__PURE__*/React.createElement(Icon, {
      name: "check",
      size: 11
    }), task.text || "待更新"), canRedoSingle && /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "task-redo-btn",
      onClick: () => onAction("redo", room.room, task.key),
      title: `单独补齐${task.name}任务`
    }, "\u8865\u505A")));
  })))), /*#__PURE__*/React.createElement("div", {
    className: "detail-action-area"
  }, operation.message && /*#__PURE__*/React.createElement("p", {
    className: "action-hint",
    role: "status"
  }, operation.message), showReason && /*#__PURE__*/React.createElement("p", {
    className: "action-hint"
  }, reason), /*#__PURE__*/React.createElement("div", {
    className: "detail-foot"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: () => onOpen(room.room),
    disabled: Boolean(room.actions.open)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "external",
    size: 13
  }), "\u6253\u5F00\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: () => onAction("redo", room.room),
    disabled: pending || Boolean(reason),
    title: reason || "自动补齐今日未完成的互动任务"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: pending ? "refresh" : "check",
    size: 13,
    className: pending ? "spin" : ""
  }), pending ? "正在处理…" : "补齐今日任务"))));
};
const OverviewActions = ({
  paused,
  globalPaused,
  signedIn = true,
  blocked = false,
  multiAccount = false,
  viewedRunning = true,
  onTogglePause,
  onStartWatch,
  onStopWatch,
  onOpenLogin,
  onOpenSafety,
  onCheck,
  checking,
  controlBusy,
  closing
}) => {
  if (globalPaused) {
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn primary",
      onClick: onTogglePause,
      disabled: controlBusy || closing
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "play",
      size: 13
    }), "\u6062\u590D\u5168\u90E8");
  }
  if (multiAccount && !viewedRunning) {
    if (!signedIn) {
      return /*#__PURE__*/React.createElement("button", {
        type: "button",
        className: "btn primary",
        onClick: onOpenLogin,
        disabled: closing
      }, /*#__PURE__*/React.createElement(Icon, {
        name: "qr",
        size: 13
      }), "\u626B\u7801\u767B\u5F55");
    }
    if (blocked) {
      return /*#__PURE__*/React.createElement("button", {
        type: "button",
        className: "btn",
        onClick: onOpenSafety,
        disabled: closing
      }, /*#__PURE__*/React.createElement(Icon, {
        name: "alert",
        size: 13
      }), "\u67E5\u770B\u539F\u56E0");
    }
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn primary",
      onClick: onStartWatch,
      disabled: controlBusy || closing,
      title: "\u5F00\u542F\u5F53\u524D\u8D26\u53F7\u7684\u76F4\u64AD\u6302\u673A\u4E0E\u81EA\u52A8\u5DE1\u68C0"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: "play",
      size: 13
    }), "\u5F00\u542F\u6302\u673A");
  }
  const effectivelyPaused = Boolean(paused);
  const noAccountReady = !signedIn && !effectivelyPaused;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onCheck,
    title: noAccountReady ? "请先登录 B 站账号" : "检查开播状态与任务进度",
    disabled: checking || controlBusy || closing || noAccountReady
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13,
    className: checking ? "spin" : ""
  }), checking ? "检查中…" : "立即检查"), multiAccount && !effectivelyPaused && onStopWatch ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onStopWatch,
    title: "\u505C\u6B62\u5F53\u524D\u8D26\u53F7\u7684\u76F4\u64AD\u6302\u673A\uFF08\u4E0D\u5F71\u54CD\u5176\u4ED6\u6302\u673A\u4E2D\u7684\u8D26\u53F7\uFF09",
    disabled: controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "pause",
    size: 13
  }), "\u505C\u6B62\u6302\u673A") : /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: `btn ${effectivelyPaused ? "primary" : ""}`,
    onClick: onTogglePause,
    title: noAccountReady ? "请先登录 B 站账号" : "",
    disabled: controlBusy || closing || noAccountReady
  }, /*#__PURE__*/React.createElement(Icon, {
    name: effectivelyPaused ? "play" : "pause",
    size: 13
  }), effectivelyPaused ? "恢复挂机" : "暂停挂机"));
};
const Overview = ({
  rooms,
  selectedId,
  onSelect,
  paused,
  globalPaused,
  viewedRunning = true,
  multiAccount = false,
  autoWatch = true,
  onEnableAutoWatch,
  accountName = "",
  blocked = false,
  onStartWatch,
  onOpenLogin,
  onOpenSafety,
  onAction,
  onOpen,
  onAddMember,
  onSyncMedals,
  onRemove,
  onContextMenu,
  menuRoom,
  menuMode,
  busyRoom,
  controlBusy,
  error,
  recovery,
  onRecovery,
  interval,
  lastCheck,
  checking,
  images,
  signedIn,
  closing,
  bridgeConnected,
  onBatchRemove,
  onClearRoomBlock,
  onDismissTaskError,
  onDismissWatchWarning
}) => {
  const [managing, setManaging] = React.useState(false);
  const [selectedBatch, setSelectedBatch] = React.useState(new Set());
  const [roomQuery, setRoomQuery] = React.useState("");
  const [roomFilter, setRoomFilter] = React.useState("all");
  const searchInputRef = React.useRef(null);
  const liveCount = rooms.filter(r => r.live).length;
  const warnCount = rooms.filter(r => r.tone === "warn").length;
  const activeFilter = roomFilter === "live" && liveCount === 0 || roomFilter === "warn" && warnCount === 0 ? "all" : roomFilter;
  const keyword = roomQuery.trim().toLowerCase();
  const showToolbar = !managing && rooms.length >= 4;
  React.useEffect(() => {
    if (!showToolbar) return undefined;
    const onKeyDown = event => {
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "f") {
        event.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select?.();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showToolbar]);
  const filteredRooms = showToolbar ? rooms.filter(r => {
    if (activeFilter === "live" && !r.live) return false;
    if (activeFilter === "warn" && r.tone !== "warn") return false;
    if (!keyword) return true;
    return [r.name, r.title, r.medal_name, r.area_name, r.room, r.uid].some(field => String(field || "").toLowerCase().includes(keyword));
  }) : rooms;
  const allChecked = rooms.length > 0 && rooms.every(r => selectedBatch.has(r.room));
  const toggleAll = () => {
    if (allChecked) setSelectedBatch(new Set());else setSelectedBatch(new Set(rooms.map(r => r.room)));
  };
  const toggleCheck = roomId => {
    setSelectedBatch(current => {
      const next = new Set(current);
      if (next.has(roomId)) next.delete(roomId);else next.add(roomId);
      return next;
    });
  };
  const handleBatchRemove = () => {
    if (selectedBatch.size === 0 || typeof onBatchRemove !== "function") return;
    const targetRooms = rooms.filter(r => selectedBatch.has(r.room));
    onBatchRemove(targetRooms);
    setManaging(false);
    setSelectedBatch(new Set());
  };
  const onRoomKey = event => {
    if (managing || !filteredRooms.length) return;
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const focused = event.target.closest?.(".room");
    const current = focused ? Number(focused.dataset.room) : selectedId;
    const index = filteredRooms.findIndex(room => room.room === current);
    const next = event.key === "Home" ? 0 : event.key === "End" ? filteredRooms.length - 1 : index < 0 ? 0 : (index + (event.key === "ArrowDown" ? 1 : -1) + filteredRooms.length) % filteredRooms.length;
    onSelect(filteredRooms[next].room);
    event.currentTarget.querySelector(`[data-room="${filteredRooms[next].room}"]`)?.focus();
  };
  const selected = rooms.find(room => room.room === selectedId);
  const healthy = rooms.filter(room => room.healthy).length;
  const doneCount = rooms.filter(room => room.live && room.daily_complete && !room.healthy).length;
  const unknown = rooms.filter(room => room.live_status == null).length;
  const readOnlyInactive = Boolean(multiAccount && !viewedRunning && !globalPaused);
  const watchDisabled = Boolean(!readOnlyInactive && !globalPaused && !paused && signedIn && !blocked && autoWatch === false);
  const status = closing ? "正在退出…" : !bridgeConnected ? "正在连接后台…" : globalPaused ? "全部挂机已暂停" : !signedIn ? "等待登录" : blocked ? "保护暂停中" : readOnlyInactive ? "当前账号未挂机" : paused ? "已暂停挂机" : watchDisabled ? "已关闭直播挂机" : error ? "需要处理" : healthy ? `${healthy} 个直播间挂机中` : doneCount ? `${doneCount} 个直播间今日已完成` : unknown ? "等待检查" : "等待开播";
  // The cadence and the last check belong together: the title bar keeps only
  // the page name, so the footer is the single place this is reported.
  const cadence = readOnlyInactive ? lastCheck ? `仅查看模式 · 上次同步 ${relativeTime(lastCheck)}` : "仅查看模式 · 不会自动开始挂机" : watchDisabled ? lastCheck ? `仅每日签到 · 上次检查 ${relativeTime(lastCheck)}` : "仅每日签到 · 已停止直播自动挂机" : `每 ${interval} 分钟检查一次${lastCheck ? ` · 上次检查 ${relativeTime(lastCheck)}` : ""}`;
  const showErrorBanner = Boolean(error || recovery?.action === "login" || recovery?.action === "resume_global");
  const showInactiveStrip = !showErrorBanner && readOnlyInactive;
  const showWatchDisabledStrip = !showErrorBanner && !showInactiveStrip && watchDisabled;
  const bannerMessage = error || recovery?.message || (!signedIn ? "请先登录 B 站账号以开始挂机" : "");
  const listMutationDisabled = closing || readOnlyInactive;
  const inactiveTip = "开启此账号挂机后可管理关注列表";
  return /*#__PURE__*/React.createElement(React.Fragment, null, showErrorBanner && /*#__PURE__*/React.createElement("div", {
    className: "banner",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: recovery?.action === "login" ? "user" : "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, bannerMessage), recovery?.action && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onRecovery
  }, recovery.label || "查看详情")), showInactiveStrip && /*#__PURE__*/React.createElement("div", {
    className: `view-status-bar ${!signedIn || blocked ? "warn" : ""}`,
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: !signedIn ? "user" : blocked ? "alert" : "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, !signedIn ? `「${accountName || "此账号"}」尚未登录或登录已失效，当前仅展示上次记录。` : blocked ? `「${accountName || "此账号"}」处于保护暂停状态，当前仅展示上次记录。` : `「${accountName || "此账号"}」当前未开启挂机，正在只读查看上次同步的数据。`), !signedIn && onOpenLogin ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: onOpenLogin,
    disabled: closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "qr",
    size: 12
  }), "\u91CD\u65B0\u626B\u7801") : blocked && onOpenSafety ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onOpenSafety,
    disabled: closing
  }, "\u67E5\u770B\u539F\u56E0") : onStartWatch ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: onStartWatch,
    disabled: controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 12
  }), "\u5F00\u542F\u6302\u673A") : null), showWatchDisabledStrip && /*#__PURE__*/React.createElement("div", {
    className: "view-status-bar",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, "\u300C", accountName || "此账号", "\u300D\u5DF2\u5173\u95ED\u76F4\u64AD\u81EA\u52A8\u6302\u673A\uFF0C\u4EC5\u4FDD\u7559\u6BCF\u65E5\u7B7E\u5230\u4E0E\u624B\u52A8\u64CD\u4F5C\u3002"), onEnableAutoWatch && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: onEnableAutoWatch,
    disabled: controlBusy || closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "play",
    size: 12
  }), "\u5F00\u542F\u76F4\u64AD\u6302\u673A")), /*#__PURE__*/React.createElement("div", {
    className: "workspace"
  }, /*#__PURE__*/React.createElement("section", {
    className: "list card",
    "aria-label": "\u5173\u6CE8\u7684\u76F4\u64AD\u95F4"
  }, !managing ? /*#__PURE__*/React.createElement("header", {
    className: "list-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "list-title"
  }, "\u5173\u6CE8\u7684\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("span", {
    className: "list-count tnum"
  }, rooms.length), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: onAddMember,
    disabled: listMutationDisabled,
    title: readOnlyInactive ? inactiveTip : ""
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 12
  }), "\u6DFB\u52A0\u4E3B\u64AD"), onSyncMedals && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: onSyncMedals,
    disabled: listMutationDisabled || !signedIn,
    title: readOnlyInactive ? inactiveTip : !signedIn ? "请先登录账号" : "从账号已有粉丝牌批量导入"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "medal",
    size: 12
  }), "\u540C\u6B65\u7C89\u4E1D\u724C"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: () => setManaging(true),
    disabled: listMutationDisabled || !rooms.length,
    title: readOnlyInactive ? inactiveTip : ""
  }, "\u6279\u91CF\u7BA1\u7406")) : /*#__PURE__*/React.createElement("header", {
    className: "list-head managing-head"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "batch-all-btn",
    onClick: toggleAll,
    "aria-label": "\u5168\u9009"
  }, /*#__PURE__*/React.createElement("span", {
    className: `room-check ${allChecked ? "checked" : ""}`,
    "aria-hidden": "true"
  }, allChecked && /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 11
  })), /*#__PURE__*/React.createElement("span", null, "\u5168\u9009 (", selectedBatch.size, "/", rooms.length, ")")), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn danger sm",
    disabled: selectedBatch.size === 0 || closing,
    onClick: handleBatchRemove
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "trash",
    size: 12
  }), "\u6279\u91CF\u79FB\u9664 ", selectedBatch.size ? `(${selectedBatch.size})` : ""), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: () => {
      setManaging(false);
      setSelectedBatch(new Set());
    }
  }, "\u5B8C\u6210")), showToolbar && /*#__PURE__*/React.createElement("div", {
    className: "list-toolbar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "search-box"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 13
  }), /*#__PURE__*/React.createElement("input", {
    ref: searchInputRef,
    className: "search-input",
    value: roomQuery,
    onChange: e => setRoomQuery(e.target.value),
    onKeyDown: e => {
      if (e.key === "Escape" && roomQuery) {
        e.stopPropagation();
        setRoomQuery("");
      }
    },
    "aria-label": "\u7B5B\u9009\u76F4\u64AD\u95F4",
    placeholder: "\u641C\u7D22\u4E3B\u64AD\u3001\u6807\u9898\u6216\u623F\u95F4\u53F7\u2026 (Ctrl+F)"
  }), roomQuery && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "search-clear",
    "aria-label": "\u6E05\u9664\u641C\u7D22",
    onClick: () => setRoomQuery("")
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "close",
    size: 11
  }))), (liveCount > 0 || warnCount > 0) && /*#__PURE__*/React.createElement("div", {
    className: "list-filters",
    role: "group",
    "aria-label": "\u72B6\u6001\u7B5B\u9009"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "growth-filter-btn",
    "aria-pressed": activeFilter === "all",
    onClick: () => setRoomFilter("all")
  }, "\u5168\u90E8"), liveCount > 0 && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "growth-filter-btn",
    "aria-pressed": activeFilter === "live",
    onClick: () => setRoomFilter("live")
  }, "\u76F4\u64AD\u4E2D ", liveCount), warnCount > 0 && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "growth-filter-btn",
    "aria-pressed": activeFilter === "warn",
    onClick: () => setRoomFilter("warn")
  }, "\u9700\u5173\u6CE8 ", warnCount))), /*#__PURE__*/React.createElement("div", {
    className: "rooms",
    role: "listbox",
    "aria-label": "\u76F4\u64AD\u95F4\u5217\u8868",
    onKeyDown: onRoomKey
  }, !rooms.length ? /*#__PURE__*/React.createElement("div", {
    className: "empty list-empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "monitor",
    size: 24
  }), /*#__PURE__*/React.createElement("strong", null, "\u8FD8\u6CA1\u6709\u5173\u6CE8\u4E3B\u64AD"), /*#__PURE__*/React.createElement("span", null, "\u6DFB\u52A0\u4E3B\u64AD\u6216\u540C\u6B65\u7C89\u4E1D\u724C\u540E\u5373\u53EF\u81EA\u52A8\u6302\u673A"), /*#__PURE__*/React.createElement("div", {
    className: "empty-actions"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: onAddMember
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 12
  }), "\u6DFB\u52A0\u4E3B\u64AD"), onSyncMedals && signedIn && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onSyncMedals
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "medal",
    size: 12
  }), "\u540C\u6B65\u7C89\u4E1D\u724C"))) : !filteredRooms.length ? /*#__PURE__*/React.createElement("div", {
    className: "empty list-empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "search",
    size: 22
  }), /*#__PURE__*/React.createElement("strong", null, "\u6CA1\u6709\u5339\u914D\u7684\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("span", null, "\u8BD5\u8BD5\u5176\u4ED6\u5173\u952E\u8BCD\u6216\u5207\u6362\u7B5B\u9009\u6761\u4EF6"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => {
      setRoomQuery("");
      setRoomFilter("all");
    }
  }, "\u6E05\u9664\u7B5B\u9009")) : filteredRooms.map(room => /*#__PURE__*/React.createElement(RoomRow, {
    key: room.room,
    room: room,
    selected: room.room === selectedId,
    image: images[room.uid],
    onSelect: onSelect,
    onContextMenu: onContextMenu,
    managing: managing,
    checked: selectedBatch.has(room.room),
    onToggleCheck: toggleCheck
  })))), /*#__PURE__*/React.createElement(DetailPanel, {
    room: selected,
    image: images[selected?.uid],
    busy: busyRoom === selected?.room,
    autoWatch: autoWatch,
    onAction: onAction,
    onOpen: onOpen,
    onClearRoomBlock: onClearRoomBlock,
    onDismissTaskError: onDismissTaskError,
    onDismissWatchWarning: onDismissWatchWarning,
    dimmed: managing,
    moreOpen: Boolean(selected && menuMode === "overflow" && menuRoom === selected.room),
    onMore: event => {
      if (!selected) return;
      onContextMenu(event, selected.room, "overflow");
    }
  })), /*#__PURE__*/React.createElement("footer", {
    className: "statusbar"
  }, /*#__PURE__*/React.createElement("span", {
    className: healthy && !closing ? "dot-live" : "dot-paused",
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("strong", null, status), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "low-priority"
  }, checking ? "正在检查直播状态…" : cadence)));
};
Object.assign(window, {
  Overview,
  OverviewActions,
  Avatar
});
})();
