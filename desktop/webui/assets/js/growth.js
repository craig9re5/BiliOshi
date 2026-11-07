/* BiliOshi JSX {"code_sha256":"70242ee56ab4054ad95637a912d40abee356fdd27610a13d0b2a1f66e6af920f","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"growth.jsx","source_sha256":"b9026ab8646517aaf78f77db005e8319daf29186bccf4416a1602aa3ffda2aeb"} */
(function () {
"use strict";
/* Growth page: daily fan-medal intimacy per room, from Api.growth.
   Missing samples stay "未记录"/"尚未同步" and never become 0. */

const {
  useState,
  useEffect,
  useRef
} = React;
const {
  Icon,
  call,
  colorFor,
  bridgeReady
} = window;
const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
const GROWTH_DAYS = 7;
const GROWTH_REFRESH_MS = 60000;
const pad2 = value => String(value).padStart(2, "0");
function dayParts(iso) {
  const [year, month, day] = String(iso || "").split("-").map(Number);
  const date = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  if (!year || !month || !day || Number.isNaN(date.getTime())) {
    return {
      md: String(iso || "—"),
      week: ""
    };
  }
  return {
    md: `${pad2(month)}/${pad2(day)}`,
    week: WEEKDAYS[date.getUTCDay()]
  };
}

/* Days are UTC+8 by contract; render times in the same zone even when the
   machine clock is set elsewhere. */
function chinaClock(timestamp, withDate = true) {
  const date = new Date((Number(timestamp) + 8 * 3600) * 1000);
  if (!Number.isFinite(date.getTime())) return "";
  const time = `${pad2(date.getUTCHours())}:${pad2(date.getUTCMinutes())}`;
  return withDate ? `${pad2(date.getUTCMonth() + 1)}/${pad2(date.getUTCDate())} ${time}` : time;
}
function numberText(value) {
  return Number.isFinite(value) ? value.toLocaleString("zh-CN") : "—";
}
function shortNumber(value) {
  return value >= 10000 ? `${(value / 10000).toFixed(1).replace(/\.0$/, "")}万` : numberText(value);
}
function cellAt(room, index) {
  return room.cells[index] || {
    recorded: false,
    value: null
  };
}
const GrowthState = ({
  icon,
  title,
  text,
  action,
  onAction
}) => /*#__PURE__*/React.createElement("section", {
  className: "growth-state card"
}, /*#__PURE__*/React.createElement(Icon, {
  name: icon,
  size: 20
}), /*#__PURE__*/React.createElement("strong", null, title), text ? /*#__PURE__*/React.createElement("span", null, text) : null, action ? /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "btn sm",
  onClick: onAction
}, action) : null);
function GrowthPage({
  viewId,
  images = {},
  onNeedAvatar,
  onOpenAccount,
  onOpenMonitor
}) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const request = useRef(0);
  useEffect(() => {
    if (!data?.rooms || typeof onNeedAvatar !== "function") return;
    for (const room of data.rooms) {
      if (room.uid && !images[room.uid]) onNeedAvatar(room.uid);
    }
  }, [data?.rooms, images, onNeedAvatar]);
  useEffect(() => {
    let live = true;
    const generation = ++request.current;
    setData(null);
    setError("");
    setSelectedRoom(null);
    const load = async silent => {
      try {
        if (!(await bridgeReady())) throw new Error("bridge-unavailable");
        const result = await call("growth", GROWTH_DAYS, viewId && viewId !== "all" ? viewId : "");
        if (!live || generation !== request.current) return;
        if (!result || result.available === false) {
          const message = result?.error || "成长记录暂时无法读取。";
          setData(null);
          setError(message);
          setAnnouncement(message);
          return;
        }
        setData(result);
        setError("");
        if (!silent) {
          const count = Array.isArray(result.rooms) ? result.rooms.length : 0;
          setAnnouncement(count ? `已载入 ${count} 个直播间的成长记录。` : "还没有成长记录。");
        }
      } catch {
        if (!live || generation !== request.current) return;
        if (!silent) {
          setData(null);
          setError("无法读取成长记录，稍后重试。");
        }
        setAnnouncement("无法读取成长记录，稍后重试。");
      }
    };
    load(false);
    const timer = window.setInterval(() => load(true), GROWTH_REFRESH_MS);
    return () => {
      live = false;
      request.current += 1;
      window.clearInterval(timer);
    };
  }, [viewId, attempt]);
  const retry = () => setAttempt(value => value + 1);
  const accountName = data?.account_name || "";
  if (!data) {
    return /*#__PURE__*/React.createElement("div", {
      className: "growth-page"
    }, /*#__PURE__*/React.createElement("div", {
      className: "growth-inner"
    }, /*#__PURE__*/React.createElement("span", {
      className: "growth-sr",
      "aria-live": "polite"
    }, announcement), /*#__PURE__*/React.createElement("div", {
      className: "growth-head"
    }, /*#__PURE__*/React.createElement("p", {
      className: "growth-meta"
    }, "\u7C89\u4E1D\u724C\u4ECA\u65E5\u4EB2\u5BC6\u5EA6 \xB7 \u6BCF\u65E5 00:00 \u91CD\u7F6E")), error ? /*#__PURE__*/React.createElement(GrowthState, {
      icon: "alert",
      title: "\u6210\u957F\u8BB0\u5F55\u6682\u65F6\u65E0\u6CD5\u8BFB\u53D6",
      text: error,
      action: "\u91CD\u8BD5",
      onAction: retry
    }) : /*#__PURE__*/React.createElement(GrowthState, {
      icon: "clock",
      title: "\u6B63\u5728\u8BFB\u53D6\u6210\u957F\u8BB0\u5F55\u2026"
    })));
  }
  const days = Array.isArray(data.days) ? data.days : [];
  const rooms = (Array.isArray(data.rooms) ? data.rooms : []).map(room => ({
    ...room,
    cells: Array.isArray(room.cells) ? room.cells : []
  }));
  const foundToday = days.indexOf(data.today);
  const todayIndex = foundToday >= 0 ? foundToday : Math.max(0, days.length - 1);
  const today = days[todayIndex] || "";
  const todayHasRecords = rooms.some(room => cellAt(room, todayIndex).recorded);
  const recordedDays = days.reduce((count, _day, index) => count + (rooms.some(room => cellAt(room, index).recorded) ? 1 : 0), 0);
  const dayValue = index => rooms.reduce((total, room) => {
    const cell = cellAt(room, index);
    return cell.recorded ? total + cell.value : total;
  }, 0);
  const todayTotal = dayValue(todayIndex);
  const grandTotal = rooms.reduce((total, room) => total + (Number.isFinite(room.recorded_total) ? room.recorded_total : 0), 0);
  const average = recordedDays ? Math.round(grandTotal / recordedDays) : 0;
  let lastSample = 0;
  let todayLast = 0;
  for (const room of rooms) {
    room.cells.forEach((cell, index) => {
      if (!cell.recorded || !Number.isFinite(cell.last_at)) return;
      lastSample = Math.max(lastSample, cell.last_at);
      if (index === todayIndex) todayLast = Math.max(todayLast, cell.last_at);
    });
  }
  const recordedRooms = rooms.filter(room => room.tracked && ((room.recorded_total || 0) > 0 || (cellAt(room, todayIndex).value || 0) > 0));
  const compareRooms = (left, right) => {
    const a = cellAt(left, todayIndex);
    const b = cellAt(right, todayIndex);
    if (!a.recorded && !b.recorded) return (right.recorded_total || 0) - (left.recorded_total || 0);
    if (!a.recorded) return 1;
    if (!b.recorded) return -1;
    return b.value - a.value;
  };
  const trackedRows = recordedRooms.slice().sort(compareRooms);
  let maxMini = 1;
  for (const room of recordedRooms) {
    for (const cell of room.cells) {
      if (cell.recorded && cell.value > maxMini) maxMini = cell.value;
    }
  }
  const selected = selectedRoom !== null ? recordedRooms.find(room => room.room === selectedRoom) || null : null;
  const chartValues = selected ? days.map((_day, index) => cellAt(selected, index).recorded ? cellAt(selected, index).value : null) : days.map((_day, index) => recordedRooms.some(room => cellAt(room, index).recorded) ? dayValue(index) : null);
  const chartTitle = selected ? `${selected.name || `直播间 ${selected.room}`} · 近 7 日` : "每日总成长";
  let maxChart = 1;
  for (const value of chartValues) {
    if (Number.isFinite(value) && value > maxChart) maxChart = value;
  }
  const chartLabel = `近 7 日${selected ? selected.name || `直播间 ${selected.room}` : "每日总成长"}：` + days.map((day, index) => {
    const value = chartValues[index];
    const missing = !Number.isFinite(value);
    return `${index === todayIndex ? "今天" : dayParts(day).md} ${missing ? "" : `+${numberText(value)}`}`;
  }).join("，");
  let banner = null;
  if (data.status === "needs_login") {
    banner = {
      text: "此账号需要重新登录，历史仍可查看。",
      action: "去账号页",
      run: onOpenAccount
    };
  } else if (data.status === "protection") {
    banner = {
      text: "账号处于保护暂停，历史仍可查看；请先完成平台验证。",
      action: "去账号页",
      run: onOpenAccount
    };
  } else if (!data.running && data.status === "global_paused") {
    banner = {
      text: `全部挂机已暂停，${lastSample ? `数据停在 ${chinaClock(lastSample)}。` : ""}恢复后继续记录。`,
      action: "去直播总览",
      run: onOpenMonitor
    };
  } else if (!data.running && data.paused) {
    banner = {
      text: `此账号已暂停，${lastSample ? `数据停在 ${chinaClock(lastSample)}。` : ""}恢复挂机后继续记录。`,
      action: "去直播总览",
      run: onOpenMonitor
    };
  } else if (!data.running) {
    banner = {
      text: `此账号当前未挂机，${lastSample ? `数据停在 ${chinaClock(lastSample)}。` : ""}恢复挂机后继续记录。`,
      action: "去直播总览",
      run: onOpenMonitor
    };
  }
  const todaySub = todayHasRecords ? `${data.running ? "截至" : "上次记录"} ${chinaClock(todayLast, false)}` : data.running ? "等待首次同步" : "尚未同步";
  const roomRow = room => {
    const todayCell = cellAt(room, todayIndex);
    const name = room.name || `直播间 ${room.room}`;
    const isSelected = selectedRoom === room.room;
    const image = images?.[room.uid];
    const todayMissing = !todayCell.recorded;
    const todayLabel = todayMissing ? room.tracked ? "尚未同步" : "未记录" : `${todayCell.value > 0 ? "+" : ""}${numberText(todayCell.value)}`;
    const todayClass = `growth-room-today${todayMissing ? " missing" : todayCell.value === 0 ? " zero" : ""}`;
    const totalLabel = room.recorded_days ? `+${numberText(room.recorded_total)}` : "—";
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      key: room.room,
      className: "growth-row",
      "aria-pressed": isSelected,
      title: `${name}${room.tracked ? "" : " · 已移除"} · 查看近 7 日`,
      onClick: () => setSelectedRoom(current => current === room.room ? null : room.room)
    }, /*#__PURE__*/React.createElement("span", {
      className: "growth-room-id"
    }, /*#__PURE__*/React.createElement("span", {
      className: "growth-avatar",
      style: {
        background: colorFor(room.room)
      }
    }, image ? /*#__PURE__*/React.createElement("img", {
      src: image,
      alt: ""
    }) : Array.from(name.trim())[0] || "?"), /*#__PURE__*/React.createElement("span", {
      className: "growth-room-name"
    }, name)), /*#__PURE__*/React.createElement("span", {
      className: "growth-mini",
      "aria-hidden": "true"
    }, room.cells.map((cell, index) => {
      const missing = !cell.recorded;
      const zero = !missing && cell.value === 0;
      const height = missing ? 0 : Math.max(zero ? 0 : 2, Math.round(cell.value / maxMini * 100));
      return /*#__PURE__*/React.createElement("i", {
        key: cell.day || index,
        className: `${missing ? "missing" : zero ? "zero" : ""}${index === todayIndex && !missing && !zero ? " today" : ""}`,
        style: missing ? undefined : {
          height: `${height}%`
        },
        title: `${dayParts(cell.day).md} ${missing ? index === todayIndex && room.tracked ? "尚未同步" : "未记录" : `· +${numberText(cell.value)}`}`
      });
    })), /*#__PURE__*/React.createElement("span", {
      className: todayClass
    }, todayLabel), /*#__PURE__*/React.createElement("span", {
      className: `growth-room-total${room.recorded_days ? "" : " missing"}`
    }, totalLabel));
  };
  const rowNodes = trackedRows.map(room => roomRow(room));
  return /*#__PURE__*/React.createElement("div", {
    className: "growth-page"
  }, /*#__PURE__*/React.createElement("div", {
    className: "growth-inner"
  }, /*#__PURE__*/React.createElement("span", {
    className: "growth-sr",
    "aria-live": "polite"
  }, announcement), banner ? /*#__PURE__*/React.createElement("div", {
    className: `growth-banner${data.status === "needs_login" || data.status === "protection" ? " warn" : ""}`
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, banner.text), banner.action ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "growth-link",
    onClick: banner.run
  }, banner.action) : null) : null, recordedRooms.length === 0 ? /*#__PURE__*/React.createElement(GrowthState, {
    icon: "trend",
    title: "\u8FD8\u6CA1\u6709\u53EF\u8BB0\u5F55\u7684\u76F4\u64AD\u95F4",
    text: "\u5173\u6CE8\u4E3B\u64AD\u5E76\u5F00\u59CB\u6302\u673A\u540E\uFF0C\u8FD9\u91CC\u4F1A\u81EA\u52A8\u8BB0\u5F55\u6BCF\u5929\u7684\u7C89\u4E1D\u724C\u4EB2\u5BC6\u5EA6\u3002",
    action: onOpenMonitor ? "去直播总览" : "",
    onAction: onOpenMonitor
  }) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("section", {
    className: "growth-panel card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "growth-panel-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "growth-panel-title",
    title: selected ? "该直播间每日观测峰值；未记录不补 0" : "柱高为当日有记录直播间的合计；未记录不补 0"
  }, chartTitle), selected ? /*#__PURE__*/React.createElement("div", {
    className: "growth-panel-note"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "growth-link",
    onClick: () => setSelectedRoom(null)
  }, "\u67E5\u770B\u5168\u90E8")) : null), /*#__PURE__*/React.createElement("div", {
    className: "growth-chart",
    role: "img",
    "aria-label": chartLabel
  }, days.map((day, index) => {
    const value = chartValues[index];
    const missing = !Number.isFinite(value);
    const zero = !missing && value === 0;
    const isToday = index === todayIndex;
    const height = missing ? 0 : Math.max(zero ? 0 : 2, Math.round(value / maxChart * 100));
    const coverage = data.coverage?.[day] || {};
    const coverageText = !selected && coverage.rooms_recorded > 0 && coverage.rooms_recorded < coverage.rooms_recordable ? ` · ${coverage.rooms_recorded}/${coverage.rooms_recordable}` : "";
    const tip = missing ? `${dayParts(day).md}` : selected ? `${dayParts(day).md} · +${numberText(value)}` : `${dayParts(day).md} · 合计 ${numberText(value)} · 当前 ${coverage.rooms_recorded}/${coverage.rooms_recordable} 间有记录`;
    return /*#__PURE__*/React.createElement("div", {
      className: "growth-chart-col",
      key: day,
      title: tip
    }, /*#__PURE__*/React.createElement("div", {
      className: `growth-chart-value${missing ? " missing" : isToday ? " strong" : ""}`
    }, missing ? "" : shortNumber(value)), /*#__PURE__*/React.createElement("div", {
      className: "growth-chart-area"
    }, missing ? null : /*#__PURE__*/React.createElement("div", {
      className: `growth-chart-bar${zero ? " zero" : ""}${isToday ? " today" : ""}`,
      style: {
        height: `${height}%`
      }
    })), /*#__PURE__*/React.createElement("div", {
      className: "growth-chart-day"
    }, isToday ? /*#__PURE__*/React.createElement("strong", null, "\u4ECA\u5929") : dayParts(day).md, /*#__PURE__*/React.createElement("span", {
      className: "cover"
    }, isToday ? missing ? "" : data.running ? /*#__PURE__*/React.createElement("span", {
      className: "ongoing"
    }, "\u8FDB\u884C\u4E2D") : "未挂机" : dayParts(day).week, coverageText)));
  }))), /*#__PURE__*/React.createElement("section", {
    className: "growth-rooms card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "growth-cols"
  }, /*#__PURE__*/React.createElement("span", null, "\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("span", null, "\u8FD1 7 \u65E5"), /*#__PURE__*/React.createElement("span", null, "\u4ECA\u65E5"), /*#__PURE__*/React.createElement("span", null, "\u5408\u8BA1")), rowNodes))));
}
Object.assign(window, {
  GrowthPage
});
})();
