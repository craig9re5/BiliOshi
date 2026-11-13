/* BiliOshi JSX {"code_sha256":"330b04187ab9d0490330b201ae15c2c923b0c0396f13e56cbafa271c78d42531","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"overview.jsx","source_sha256":"c0248df83f11f627bc4e1e74b1e78afbc2c914967a0e6812366636943153d864"} */
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
const RoomRow = ({
  room,
  selected,
  onSelect,
  onContextMenu,
  image,
  managing,
  checked,
  onToggleCheck
}) => /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: `room ${managing ? "managing" : ""} ${checked ? "batch-checked" : ""}`,
  role: "option",
  "aria-selected": managing ? checked : selected,
  "data-room": room.room,
  onClick: () => managing ? onToggleCheck(room.room) : onSelect(room.room),
  onDoubleClick: () => !managing && window.call("open_room", room.room).catch(() => {}),
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
}, room.title), /*#__PURE__*/React.createElement("span", {
  className: "room-meta"
}, room.healthy && /*#__PURE__*/React.createElement("span", null, "\u5DF2\u8FDE\u63A5 ", durationLabel(room.minutes)), room.healthy && room.gain !== null && /*#__PURE__*/React.createElement("span", {
  className: "sep"
}, "\xB7"), room.gain !== null && /*#__PURE__*/React.createElement("span", null, "\u4ECA\u65E5 +", numberLabel(room.gain)))), room.state !== "未开播" && /*#__PURE__*/React.createElement("span", {
  className: "room-side"
}, /*#__PURE__*/React.createElement("span", {
  className: `pill ${room.tone}`
}, room.state)));
const DetailPanel = ({
  room,
  busy,
  onAction,
  onOpen,
  onMore,
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
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-identity"
  }, /*#__PURE__*/React.createElement("div", {
    className: "detail-name"
  }, room.name), /*#__PURE__*/React.createElement("div", {
    className: "detail-title",
    title: room.title
  }, room.live ? room.title || "直播中" : room.state)), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost icon-button",
    title: "\u66F4\u591A\u64CD\u4F5C",
    "aria-label": "\u66F4\u591A\u64CD\u4F5C",
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
  }, room.healthy ? `已连接 ${durationLabel(room.minutes)}` : room.live ? "开播后自动建立连接" : "等待恢复正常", room.last_heartbeat && room.active ? ` · ${relativeTime(room.last_heartbeat)}同步` : "")), /*#__PURE__*/React.createElement("button", {
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
    className: "gain-medal"
  }, room.medal_name, " Lv.", room.medal_level)), /*#__PURE__*/React.createElement("div", {
    className: "gain-value"
  }, room.gain === null ? "—" : `+${numberLabel(room.gain)}`), /*#__PURE__*/React.createElement("div", {
    className: "gain-foot"
  }, /*#__PURE__*/React.createElement("span", null, room.gain === null ? "等待更新" : "今日已获得"), room.day_limit > 0 && /*#__PURE__*/React.createElement("span", null, "\u6BCF\u65E5\u4E0A\u9650 ", numberLabel(room.day_limit))), knownExperience && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "bar thin",
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
  }, /*#__PURE__*/React.createElement("span", null, "\u7B49\u7EA7\u7ECF\u9A8C"), /*#__PURE__*/React.createElement("span", {
    className: "tnum"
  }, numberLabel(room.intimacy), " / ", numberLabel(room.next_intimacy))))), (room.connection_warning || room.watch_warning || room.task_error) && /*#__PURE__*/React.createElement("div", {
    className: "notice",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, room.connection_warning || room.watch_warning || room.task_error)), note && /*#__PURE__*/React.createElement("div", {
    className: "notice neutral"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, note)), room.reconnect_message && /*#__PURE__*/React.createElement("div", {
    className: "inline-status",
    role: "status"
  }, room.reconnect_message), /*#__PURE__*/React.createElement("section", {
    className: "block"
  }, /*#__PURE__*/React.createElement("div", {
    className: "block-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "block-title"
  }, "\u4ECA\u65E5\u4EFB\u52A1"), /*#__PURE__*/React.createElement("span", {
    className: "block-note"
  }, room.tasks_stale ? "等待更新" : `${taskCount} 项已完成`)), /*#__PURE__*/React.createElement("div", {
    className: "task-table"
  }, room.tasks.map(task => /*#__PURE__*/React.createElement("div", {
    className: "task",
    key: task.key
  }, /*#__PURE__*/React.createElement("span", {
    className: "task-name"
  }, task.name), /*#__PURE__*/React.createElement("span", {
    className: `task-val ${task.done ? "done" : !task.text ? "pending" : ""}`
  }, task.done && /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 11
  }), task.text || "待更新")))))), /*#__PURE__*/React.createElement("div", {
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
  onTogglePause,
  onCheck,
  checking,
  controlBusy,
  closing
}) => /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "btn",
  onClick: onCheck,
  title: "\u68C0\u67E5\u5F00\u64AD\u72B6\u6001\u4E0E\u4EFB\u52A1\u8FDB\u5EA6",
  disabled: checking || controlBusy || closing
}, /*#__PURE__*/React.createElement(Icon, {
  name: "refresh",
  size: 13,
  className: checking ? "spin" : ""
}), checking ? "检查中…" : "立即检查"), /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: `btn ${paused ? "primary" : ""}`,
  onClick: onTogglePause,
  disabled: controlBusy || closing
}, /*#__PURE__*/React.createElement(Icon, {
  name: paused ? "play" : "pause",
  size: 13
}), paused ? "恢复挂机" : "暂停挂机"));
const Overview = ({
  rooms,
  selectedId,
  onSelect,
  paused,
  onAction,
  onOpen,
  onAddMember,
  onSyncMedals,
  onRemove,
  onContextMenu,
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
  onBatchRemove
}) => {
  const [managing, setManaging] = React.useState(false);
  const [selectedBatch, setSelectedBatch] = React.useState(new Set());
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
    if (managing || !rooms.length) return;
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const focused = event.target.closest?.(".room");
    const current = focused ? Number(focused.dataset.room) : selectedId;
    const index = rooms.findIndex(room => room.room === current);
    const next = event.key === "Home" ? 0 : event.key === "End" ? rooms.length - 1 : index < 0 ? 0 : (index + (event.key === "ArrowDown" ? 1 : -1) + rooms.length) % rooms.length;
    onSelect(rooms[next].room);
    event.currentTarget.querySelector(`[data-room="${rooms[next].room}"]`)?.focus();
  };
  const selected = rooms.find(room => room.room === selectedId);
  const healthy = rooms.filter(room => room.healthy).length;
  const unknown = rooms.filter(room => room.live_status == null).length;
  const status = closing ? "正在退出…" : !bridgeConnected ? "正在连接后台…" : paused ? "已暂停挂机" : !signedIn ? "等待登录" : error ? "需要处理" : healthy ? `${healthy} 个直播间挂机中` : unknown ? "等待检查" : "等待开播";
  // The cadence and the last check belong together: the title bar keeps only
  // the page name, so the footer is the single place this is reported.
  const cadence = `每 ${interval} 分钟检查一次${lastCheck ? ` · 上次检查 ${relativeTime(lastCheck)}` : ""}`;
  return /*#__PURE__*/React.createElement(React.Fragment, null, (error || recovery?.action === "login") && /*#__PURE__*/React.createElement("div", {
    className: "banner",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: recovery?.action === "login" ? "user" : "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, !signedIn ? "请先登录 B 站账号以开始挂机" : error || recovery?.message), recovery?.action && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onRecovery
  }, recovery.label || "查看详情")), /*#__PURE__*/React.createElement("div", {
    className: "workspace"
  }, /*#__PURE__*/React.createElement("section", {
    className: "list card",
    "aria-label": "\u5173\u6CE8\u7684\u76F4\u64AD\u95F4"
  }, !managing ? /*#__PURE__*/React.createElement("header", {
    className: "list-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "list-title"
  }, "\u5173\u6CE8\u7684\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("span", {
    className: "list-count"
  }, rooms.length), /*#__PURE__*/React.createElement("span", {
    className: "spacer"
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: onAddMember,
    disabled: closing
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "plus",
    size: 12
  }), "\u6DFB\u52A0\u4E3B\u64AD"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn ghost sm",
    onClick: () => setManaging(true),
    disabled: closing || !rooms.length
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
  }, "\u5B8C\u6210")), /*#__PURE__*/React.createElement("div", {
    className: "rooms",
    role: "listbox",
    "aria-label": "\u76F4\u64AD\u95F4\u5217\u8868",
    onKeyDown: onRoomKey
  }, rooms.length ? rooms.map(room => /*#__PURE__*/React.createElement(RoomRow, {
    key: room.room,
    room: room,
    selected: room.room === selectedId,
    image: images[room.uid],
    onSelect: onSelect,
    onContextMenu: onContextMenu,
    managing: managing,
    checked: selectedBatch.has(room.room),
    onToggleCheck: toggleCheck
  })) : /*#__PURE__*/React.createElement("div", {
    className: "empty list-empty"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "monitor",
    size: 24
  }), /*#__PURE__*/React.createElement("strong", null, "\u8FD8\u6CA1\u6709\u5173\u6CE8\u4E3B\u64AD"), /*#__PURE__*/React.createElement("span", null, "\u6DFB\u52A0\u4E3B\u64AD\u6216\u540C\u6B65\u7C89\u4E1D\u724C\u540E\u5373\u53EF\u81EA\u52A8\u6302\u673A"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm primary",
    onClick: onAddMember
  }, "\u6DFB\u52A0\u4E3B\u64AD")))), /*#__PURE__*/React.createElement(DetailPanel, {
    room: selected,
    busy: busyRoom === selected?.room,
    onAction: onAction,
    onOpen: onOpen,
    dimmed: managing,
    onMore: event => {
      if (!selected) return;
      const rect = event.currentTarget.getBoundingClientRect();
      onContextMenu({
        preventDefault() {},
        clientX: rect.right - 190,
        clientY: rect.bottom + 6
      }, selected.room);
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
