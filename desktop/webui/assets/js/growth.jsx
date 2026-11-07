/* Growth page: daily fan-medal intimacy per room, from Api.growth.
   Missing samples stay "未记录"/"尚未同步" and never become 0. */

const { useState, useEffect, useRef } = React;
const { Icon, call, colorFor, bridgeReady } = window;

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
const GROWTH_DAYS = 7;
const GROWTH_REFRESH_MS = 60000;

const pad2 = (value) => String(value).padStart(2, "0");

function dayParts(iso) {
  const [year, month, day] = String(iso || "").split("-").map(Number);
  const date = new Date(Date.UTC(year, (month || 1) - 1, day || 1));
  if (!year || !month || !day || Number.isNaN(date.getTime())) {
    return { md: String(iso || "—"), week: "" };
  }
  return { md: `${pad2(month)}/${pad2(day)}`, week: WEEKDAYS[date.getUTCDay()] };
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
  return room.cells[index] || { recorded: false, value: null };
}

const GrowthState = ({ icon, title, text, action, onAction }) => (
  <section className="growth-state card">
    <Icon name={icon} size={20} />
    <strong>{title}</strong>
    {text ? <span>{text}</span> : null}
    {action ? <button type="button" className="btn sm" onClick={onAction}>{action}</button> : null}
  </section>
);

function GrowthPage({ viewId, onOpenAccount, onOpenMonitor }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [attempt, setAttempt] = useState(0);
  const request = useRef(0);

  useEffect(() => {
    let live = true;
    const generation = ++request.current;
    setData(null);
    setError("");
    setSelectedRoom(null);

    const load = async (silent) => {
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

  const retry = () => setAttempt((value) => value + 1);
  const accountName = data?.account_name || "";

  if (!data) {
    return (
      <div className="growth-page">
        <div className="growth-inner">
          <span className="growth-sr" aria-live="polite">{announcement}</span>
          <div className="growth-head">
            <p className="growth-meta">粉丝牌今日亲密度 · 每日 00:00 重置</p>
          </div>
          {error
            ? <GrowthState icon="alert" title="成长记录暂时无法读取" text={error} action="重试" onAction={retry} />
            : <GrowthState icon="clock" title="正在读取成长记录…" />}
        </div>
      </div>
    );
  }

  const days = Array.isArray(data.days) ? data.days : [];
  const rooms = (Array.isArray(data.rooms) ? data.rooms : []).map((room) => ({
    ...room,
    cells: Array.isArray(room.cells) ? room.cells : [],
  }));
  const foundToday = days.indexOf(data.today);
  const todayIndex = foundToday >= 0 ? foundToday : Math.max(0, days.length - 1);
  const today = days[todayIndex] || "";
  const todayHasRecords = rooms.some((room) => cellAt(room, todayIndex).recorded);
  const recordedDays = days.reduce(
    (count, _day, index) => count + (rooms.some((room) => cellAt(room, index).recorded) ? 1 : 0), 0);
  const dayValue = (index) => rooms.reduce(
    (total, room) => { const cell = cellAt(room, index); return cell.recorded ? total + cell.value : total; }, 0);
  const todayTotal = dayValue(todayIndex);
  const grandTotal = rooms.reduce((total, room) => (
    total + (Number.isFinite(room.recorded_total) ? room.recorded_total : 0)), 0);
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

  const tracked = rooms.filter((room) => room.tracked);
  const untracked = rooms.filter((room) => !room.tracked);
  const compareRooms = (left, right) => {
    const a = cellAt(left, todayIndex);
    const b = cellAt(right, todayIndex);
    if (!a.recorded && !b.recorded) return (right.recorded_total || 0) - (left.recorded_total || 0);
    if (!a.recorded) return 1;
    if (!b.recorded) return -1;
    return b.value - a.value;
  };
  const trackedRows = tracked.slice().sort(compareRooms);
  const untrackedRows = untracked.slice().sort(compareRooms);

  let maxMini = 1;
  for (const room of rooms) {
    for (const cell of room.cells) {
      if (cell.recorded && cell.value > maxMini) maxMini = cell.value;
    }
  }

  const selected = selectedRoom !== null
    ? rooms.find((room) => room.room === selectedRoom) || null
    : null;
  const chartValues = selected
    ? days.map((_day, index) => (cellAt(selected, index).recorded ? cellAt(selected, index).value : null))
    : days.map((_day, index) => (
      rooms.some((room) => cellAt(room, index).recorded) ? dayValue(index) : null));
  const chartTitle = selected
    ? `${selected.name || `直播间 ${selected.room}`} · 近 7 日`
    : "每日总成长";
  let maxChart = 1;
  for (const value of chartValues) {
    if (Number.isFinite(value) && value > maxChart) maxChart = value;
  }
  const chartLabel = `近 7 日${selected ? selected.name || `直播间 ${selected.room}` : "每日总成长"}：` + days.map((day, index) => {
    const value = chartValues[index];
    const missing = !Number.isFinite(value);
    return `${index === todayIndex ? "今天" : dayParts(day).md} ${
      missing ? (index === todayIndex ? "尚未同步" : "未记录") : `+${numberText(value)}`}`;
  }).join("，");

  let banner = null;
  if (data.status === "needs_login") {
    banner = { text: "此账号需要重新登录，历史仍可查看。", action: "去账号页", run: onOpenAccount };
  } else if (data.status === "protection") {
    banner = { text: "账号处于保护暂停，历史仍可查看；请先完成平台验证。", action: "去账号页", run: onOpenAccount };
  } else if (!data.running && data.status === "global_paused") {
    banner = {
      text: `全部挂机已暂停，${lastSample ? `数据停在 ${chinaClock(lastSample)}。` : ""}恢复后继续记录。`,
      action: "去直播总览", run: onOpenMonitor,
    };
  } else if (!data.running && data.paused) {
    banner = {
      text: `此账号已暂停，${lastSample ? `数据停在 ${chinaClock(lastSample)}。` : ""}恢复挂机后继续记录。`,
      action: "去直播总览", run: onOpenMonitor,
    };
  } else if (!data.running) {
    banner = {
      text: `此账号当前未挂机，${lastSample ? `数据停在 ${chinaClock(lastSample)}。` : ""}恢复挂机后继续记录。`,
      action: "去直播总览", run: onOpenMonitor,
    };
  }

  const todaySub = todayHasRecords
    ? `${data.running ? "截至" : "上次记录"} ${chinaClock(todayLast, false)}`
    : (data.running ? "等待首次同步" : "尚未同步");

  const roomRow = (room) => {
    const todayCell = cellAt(room, todayIndex);
    const name = room.name || `直播间 ${room.room}`;
    const isSelected = selectedRoom === room.room;
    const todayMissing = !todayCell.recorded;
    const todayLabel = todayMissing
      ? (room.tracked ? "尚未同步" : "未记录")
      : `${todayCell.value > 0 ? "+" : ""}${numberText(todayCell.value)}`;
    const todayClass = `growth-room-today${todayMissing ? " missing" : todayCell.value === 0 ? " zero" : ""}`;
    const totalLabel = room.recorded_days ? `+${numberText(room.recorded_total)}` : "—";
    return (
      <button type="button" key={room.room} className="growth-row" aria-pressed={isSelected}
        title={`${name}${room.tracked ? "" : " · 已移除"} · 查看近 7 日`}
        onClick={() => setSelectedRoom((current) => (current === room.room ? null : room.room))}>
        <span className="growth-room-id">
          <span className="growth-avatar" style={{ background: colorFor(room.room) }}>
            {Array.from(name.trim())[0] || "?"}
          </span>
          <span className="growth-room-name">{name}</span>
        </span>
        <span className="growth-mini" aria-hidden="true">
          {room.cells.map((cell, index) => {
            const missing = !cell.recorded;
            const zero = !missing && cell.value === 0;
            const height = missing ? 0 : Math.max(zero ? 0 : 2, Math.round((cell.value / maxMini) * 100));
            return (
              <i key={cell.day || index}
                className={`${missing ? "missing" : zero ? "zero" : ""}${
                  index === todayIndex && !missing && !zero ? " today" : ""}`}
                style={missing ? undefined : { height: `${height}%` }}
                title={`${dayParts(cell.day).md} ${missing
                  ? (index === todayIndex && room.tracked ? "尚未同步" : "未记录")
                  : `· +${numberText(cell.value)}`}`} />
            );
          })}
        </span>
        <span className={todayClass}>{todayLabel}</span>
        <span className={`growth-room-total${room.recorded_days ? "" : " missing"}`}>{totalLabel}</span>
      </button>
    );
  };

  const rowNodes = [];
  const firstMissing = trackedRows.findIndex((room) => !cellAt(room, todayIndex).recorded);
  trackedRows.forEach((room, index) => {
    if (firstMissing > 0 && index === firstMissing) {
      rowNodes.push(
        <div className="growth-group" key="missing-today">今日未记录 · {trackedRows.length - firstMissing} 间</div>);
    }
    rowNodes.push(roomRow(room));
  });
  if (untrackedRows.length) {
    rowNodes.push(
      <div className="growth-group" key="removed">已移除 · {untrackedRows.length} 间</div>);
    untrackedRows.forEach((room) => rowNodes.push(roomRow(room)));
  }

  return (
    <div className="growth-page">
      <div className="growth-inner">
        <span className="growth-sr" aria-live="polite">{announcement}</span>
        <div className="growth-head">
          <p className="growth-meta">粉丝牌今日亲密度 · 每日 00:00 重置</p>
          {accountName ? <div className="growth-head-side">
            <span className="growth-scope" title={`当前账号：${accountName}`}>
              <span className="growth-scope-avatar">{Array.from(accountName.trim())[0] || "?"}</span>
              {accountName}
            </span>
          </div> : null}
        </div>

        {banner ? <div className={`growth-banner${data.status === "needs_login" || data.status === "protection" ? " warn" : ""}`}>
          <Icon name="info" size={14} />
          <span>{banner.text}</span>
          {banner.action ? <button type="button" className="growth-link" onClick={banner.run}>{banner.action}</button> : null}
        </div> : null}

        {rooms.length === 0
          ? <GrowthState icon="trend" title="还没有可记录的直播间"
            text="关注主播并开始挂机后，这里会自动记录每天的粉丝牌亲密度。"
            action={onOpenMonitor ? "去直播总览" : ""} onAction={onOpenMonitor} />
          : <>
            <div className="growth-summary">
              <section className="growth-stat card">
                <div className="growth-stat-label" title="账号当日累计，可能包含手机或网页端的收益">
                  <i className="growth-dot" />今日成长
                </div>
                <div className={`growth-stat-value${todayHasRecords ? "" : " muted"}`}>
                  {todayHasRecords ? <><span className="plus">+</span>{numberText(todayTotal)}</> : "—"}
                </div>
                <div className="growth-stat-sub">{todaySub}</div>
              </section>
              <section className="growth-stat card">
                <div className="growth-stat-label" title="仅合计已记录的直播间；未记录不补 0">
                  <i className="growth-dot" />近 7 日
                </div>
                <div className={`growth-stat-value${recordedDays ? "" : " muted"}`}>
                  {recordedDays ? <><span className="plus">+</span>{numberText(grandTotal)}</> : "—"}
                </div>
                <div className="growth-stat-sub">
                  {recordedDays ? `${recordedDays} 天 · 日均 +${numberText(average)}` : "暂无记录"}
                </div>
              </section>
            </div>

            <section className="growth-panel card">
              <div className="growth-panel-head">
                <div className="growth-panel-title" title={selected ? "该直播间每日观测峰值；未记录不补 0" : "柱高为当日有记录直播间的合计；未记录不补 0"}>
                  {chartTitle}
                </div>
                {selected ? <div className="growth-panel-note">
                  <button type="button" className="growth-link" onClick={() => setSelectedRoom(null)}>查看全部</button>
                </div> : null}
              </div>
              <div className="growth-chart" role="img" aria-label={chartLabel}>
                {days.map((day, index) => {
                  const value = chartValues[index];
                  const missing = !Number.isFinite(value);
                  const zero = !missing && value === 0;
                  const isToday = index === todayIndex;
                  const height = missing ? 0 : Math.max(zero ? 0 : 2, Math.round((value / maxChart) * 100));
                  const coverage = data.coverage?.[day] || {};
                  const coverageText = !selected && coverage.rooms_recorded > 0
                    && coverage.rooms_recorded < coverage.rooms_recordable
                    ? ` · ${coverage.rooms_recorded}/${coverage.rooms_recordable}` : "";
                  const tip = missing
                    ? `${dayParts(day).md} ${isToday ? "尚未同步" : "未记录"}`
                    : (selected
                      ? `${dayParts(day).md} · +${numberText(value)}`
                      : `${dayParts(day).md} · 合计 ${numberText(value)} · 当前 ${coverage.rooms_recorded}/${coverage.rooms_recordable} 间有记录`);
                  return (
                    <div className="growth-chart-col" key={day} title={tip}>
                      <div className={`growth-chart-value${missing ? " missing" : isToday ? " strong" : ""}`}>
                        {missing ? (isToday ? "—" : "未记录") : shortNumber(value)}
                      </div>
                      <div className="growth-chart-area">
                        {missing
                          ? <div className="growth-chart-missing" />
                          : <div className={`growth-chart-bar${zero ? " zero" : ""}${isToday ? " today" : ""}`}
                            style={{ height: `${height}%` }} />}
                      </div>
                      <div className="growth-chart-day">
                        {isToday ? <strong>今天</strong> : dayParts(day).md}
                        <span className="cover">
                          {isToday
                            ? (missing ? "尚未同步" : data.running ? <span className="ongoing">进行中</span> : "未挂机")
                            : dayParts(day).week}
                          {coverageText}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="growth-rooms card">
              <div className="growth-rooms-head"><span className="growth-rooms-title">各直播间</span></div>
              <div className="growth-cols"><span>直播间</span><span>近 7 日</span><span>今日</span><span>合计</span></div>
              {rowNodes}
            </section>
          </>}
      </div>
    </div>
  );
}

Object.assign(window, { GrowthPage });
