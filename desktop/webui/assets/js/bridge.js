/* BiliOshi JSX {"code_sha256":"ea90c4a62dd9dcfc25ab8835cd7cb8945578c21aa78404c9992ea8022099a7b1","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"bridge.jsx","source_sha256":"8e82453051d21871009c4ef19755a45868bfbdffda65630cc5f4f9359a6dbcd7"} */
(function () {
"use strict";
/* Transport and presentation adapters. Business decisions stay in Python. */

function call(method, ...args) {
  const api = window.pywebview?.api;
  if (typeof api?.[method] !== "function") return Promise.reject(new Error("bridge-unavailable"));
  return Promise.resolve(api[method](...args));
}
function bridgeReady() {
  if (window.pywebview?.api) return Promise.resolve(true);
  return new Promise(resolve => {
    let attempts = 0;
    const timer = window.setInterval(() => {
      if (window.pywebview?.api || ++attempts >= 200) {
        window.clearInterval(timer);
        resolve(Boolean(window.pywebview?.api));
      }
    }, 50);
  });
}
function relativeTime(timestamp) {
  if (!Number.isFinite(timestamp) || timestamp <= 0) return "尚未更新";
  const delta = Math.max(0, Date.now() / 1000 - timestamp);
  if (delta < 60) return "刚刚";
  if (delta < 3600) return `${Math.floor(delta / 60)} 分钟前`;
  if (delta < 86400) return `${Math.floor(delta / 3600)} 小时前`;
  return new Date(timestamp * 1000).toLocaleDateString("zh-CN", {
    month: "numeric",
    day: "numeric"
  });
}
function absoluteTime(timestamp) {
  return timestamp > 0 ? new Date(timestamp * 1000).toLocaleString("zh-CN", {
    hour12: false
  }) : "尚未更新";
}
function durationLabel(minutes) {
  if (minutes < 1) return "不到 1 分钟";
  const hours = Math.floor(minutes / 60);
  const remainder = Math.floor(minutes % 60);
  return hours ? `${hours} 小时${remainder ? ` ${remainder} 分钟` : ""}` : `${remainder} 分钟`;
}
function numberLabel(value) {
  return typeof value === "number" && Number.isFinite(value) ? value.toLocaleString("zh-CN") : "—";
}
function taskPair(row, words) {
  if (row.tasks_stale) return null;
  const task = (Array.isArray(row.tasks) ? row.tasks : []).find(item => words.some(word => String(item.title || "").includes(word)));
  if (!task) return null;
  const match = String(task.sub_title || "").match(/(\d+)\s*\/\s*(\d+)/);
  return {
    current: match ? Number(match[1]) : null,
    total: match ? Number(match[2]) : null,
    done: Boolean(task.is_done),
    text: match ? `${match[1]} / ${match[2]}` : task.is_done ? "已完成" : "未完成"
  };
}
function colorFor(room) {
  const colors = ["#3d7a6c", "#6a5f8f", "#8a7b62", "#7a6270", "#4f6f8a", "#7d6a4f"];
  let hash = 0;
  for (const letter of String(room)) hash = (hash * 31 + letter.charCodeAt(0)) % 997;
  return colors[hash % colors.length];
}
function toRoom(row, snap) {
  const paused = Boolean(snap.paused);
  const protectedAccount = Boolean(snap.safety?.blocked && snap.safety?.scope !== "interaction");
  // A viewed account that is not running shows its last known state; it must
  // never look like a live connection.
  const inactive = Boolean(row.inactive || snap.inactive);
  const live = !inactive && row.live_status === 1;
  const healthy = Boolean(row.heartbeat_healthy && !paused && !protectedAccount && !inactive);
  const tasks = [{
    key: "danmaku",
    name: "弹幕",
    ...taskPair(row, ["弹幕"])
  }, {
    key: "like",
    name: "点赞",
    ...taskPair(row, ["点赞"])
  }, {
    key: "watch",
    name: "观看",
    ...taskPair(row, ["观看", "看播"])
  }];
  const lightKnown = Boolean(row.medal_name && !row.tasks_stale);
  tasks.push({
    key: "light",
    name: "粉丝牌",
    done: lightKnown && row.is_lighted === 1,
    text: lightKnown ? row.is_lighted === 1 ? "已点亮" : "未点亮" : "待更新"
  });
  const hasRoomBlock = Array.isArray(row.room_blocks) && row.room_blocks.length > 0;
  let state = "未开播",
    tone = "muted";
  if (inactive) state = "上次直播中";else if (snap.global_paused) state = "全部暂停";else if (paused) state = "已暂停";else if (protectedAccount) {
    state = "保护暂停";
    tone = "warn";
  } else if (row.state_error) {
    state = "状态异常";
    tone = "warn";
  } else if (row.reconnecting) state = "正在重连";else if (row.heartbeat_stale || row.connection_warning) {
    state = "连接异常";
    tone = "warn";
  } else if (row.status_error) {
    state = "查询失败";
    tone = "warn";
  } else if (row.watch_warning) {
    state = "收益待确认";
    tone = "warn";
  } else if (row.active && row.phase === "执行任务中") {
    state = "执行任务中";
    tone = "live";
  } else if (row.active && row.phase === "正在重试") {
    state = "连接重试中";
    tone = "warn";
  } else if (healthy) {
    if (row.task_error) {
      state = "任务待处理";
      tone = "warn";
    } else if (hasRoomBlock) {
      state = "互动受限";
      tone = "warn";
    } else {
      state = "挂机中";
      tone = "live";
    }
  } else if (row.active) state = "正在连接";else if (row.phase === "等待重试") {
    state = "等待重试";
    tone = "warn";
  } else if (live) {
    if (row.task_error) {
      state = "任务待处理";
      tone = "warn";
    } else state = "等待连接";
  } else if (row.task_error || hasRoomBlock) {
    state = row.task_error ? "任务异常" : "互动受限";
    tone = "warn";
  } else if (row.status_stale && row.status_updated) state = "状态已过期";else if (row.live_status == null) state = "等待检查";
  const fallback = "状态尚未确认，更新后可操作";
  return {
    ...row,
    live,
    healthy,
    state,
    tone,
    tasks,
    gain: !row.tasks_stale && Number.isFinite(row.intimacy_gain) ? row.intimacy_gain : null,
    minutes: row.started ? Math.max(0, Math.floor((Date.now() / 1000 - row.started) / 60)) : 0,
    initial: Array.from(String(row.name || "?").trim())[0],
    color: colorFor(row.room),
    actions: row.actions || {
      open: "",
      redo: fallback,
      reconnect: fallback,
      wear: fallback
    },
    operation: row.operation || {},
    paused,
    protectedAccount,
    inactive
  };
}
function roomSortTier(room) {
  if (room.tone === "warn") return 0;
  if (room.healthy || room.active || room.reconnecting) return 1;
  if (room.live) return 2;
  return 3;
}
Object.assign(window, {
  call,
  bridgeReady,
  relativeTime,
  absoluteTime,
  durationLabel,
  numberLabel,
  toRoom,
  roomSortTier,
  colorFor
});
})();
