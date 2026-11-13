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
    <Icon name={icon} size={24} />
    <strong>{title}</strong>
    {text ? <span>{text}</span> : null}
    {action ? <button type="button" className="btn sm" onClick={onAction}>{action}</button> : null}
  </section>
);

function GrowthPage({ viewId, images = {}, onNeedAvatar, onOpenAccount, onOpenMonitor }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [announcement, setAnnouncement] = useState("");
  const [selectedRoom, setSelectedRoom] = useState(null);
  const [onlyGained, setOnlyGained] = useState(false);
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
    setOnlyGained(false);

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

  const followedRooms = rooms.filter((room) => room.tracked);
  const activeRooms = followedRooms.filter((room) =>
    (room.recorded_total || 0) > 0 || (cellAt(room, todayIndex).value || 0) > 0
  );
  const visibleRooms = onlyGained ? activeRooms : followedRooms;
  const compareRooms = (left, right) => {
    const a = cellAt(left, todayIndex);
    const b = cellAt(right, todayIndex);
    if (a.recorded !== b.recorded) return a.recorded ? -1 : 1;
    if (a.recorded && b.recorded && b.value !== a.value) return b.value - a.value;
    const totalDiff = (right.recorded_total || 0) - (left.recorded_total || 0);
    if (totalDiff !== 0) return totalDiff;
    return (right.recorded_days || 0) - (left.recorded_days || 0);
  };
  const trackedRows = visibleRooms.slice().sort(compareRooms);

  let maxMini = 1;
  for (const room of followedRooms) {
    for (const cell of room.cells) {
      if (cell.recorded && cell.value > maxMini) maxMini = cell.value;
    }
  }

  const selected = selectedRoom !== null
    ? visibleRooms.find((room) => room.room === selectedRoom) || null
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
      missing ? "" : `+${numberText(value)}`}`;
  }).join("，");

  let banner = null;
  if (data.status === "needs_login") {
    banner = { text: "当前账号登录已失效，历史记录仍可查看。", action: "前往重新登录", run: onOpenAccount };
  } else if (data.status === "protection") {
    banner = { text: "账号已暂停互动，请先在平台完成安全验证。", action: "前往查看", run: onOpenAccount };
  } else if (!data.running && data.status === "global_paused") {
    banner = {
      text: "全部挂机已暂停，恢复后将继续记录成长。",
      action: "去直播总览", run: onOpenMonitor,
    };
  } else if (!data.running && data.paused) {
    banner = {
      text: "当前账号已暂停挂机，恢复后将继续记录成长。",
      action: "去直播总览", run: onOpenMonitor,
    };
  } else if (!data.running) {
    banner = {
      text: "当前账号未挂机，开启挂机后将自动记录成长。",
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
    const image = images?.[room.uid];
    const todayMissing = !todayCell.recorded;
    const todayLabel = todayMissing
      ? (room.tracked ? "尚未同步" : "未记录")
      : `${todayCell.value > 0 ? "+" : ""}${numberText(todayCell.value)}`;
    const todayClass = `growth-room-today${todayMissing ? " missing" : todayCell.value === 0 ? " zero" : ""}`;
    const totalGain = room.recorded_total || 0;
    const hasDays = Boolean(room.recorded_days);
    const totalLabel = hasDays ? (totalGain > 0 ? `+${numberText(totalGain)}` : "0") : "无记录";
    const totalClass = `growth-room-total${!hasDays ? " missing" : totalGain === 0 ? " zero" : ""}`;
    const statusTag = !hasDays && todayMissing
      ? "尚无同步记录"
      : (hasDays && totalGain === 0 && (todayMissing || todayCell.value === 0) ? "近7日无增量" : "");
    return (
      <button type="button" key={room.room} className="growth-row" aria-pressed={isSelected}
        title={`${name}${room.tracked ? "" : " · 已移除"} · 查看近 7 日`}
        onClick={() => setSelectedRoom((current) => (current === room.room ? null : room.room))}>
        <span className="growth-room-id">
          <span className="growth-avatar" style={{ background: colorFor(room.room) }}>
            {image ? <img src={image} alt="" /> : Array.from(name.trim())[0] || "?"}
          </span>
          <span className="growth-room-meta">
            <span className="growth-room-name">{name}</span>
            {statusTag && <span className="growth-room-tag">{statusTag}</span>}
          </span>
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
        <span className={totalClass}>{totalLabel}</span>
      </button>
    );
  };

  const rowNodes = trackedRows.map((room) => roomRow(room));
  const isWarnBanner = data.status === "needs_login" || data.status === "protection";
  const showFilter = activeRooms.length < followedRooms.length || onlyGained;

  return (
    <div className="growth-page">
      <div className="growth-inner">
        <span className="growth-sr" aria-live="polite">{announcement}</span>

        {banner ? <div className={`growth-banner${isWarnBanner ? " warn" : ""}`} role="status">
          <Icon name={isWarnBanner ? "alert" : "info"} size={14} />
          <span>{banner.text}</span>
          {banner.action ? <button type="button" className="btn sm" onClick={banner.run}>{banner.action}</button> : null}
        </div> : null}

        {followedRooms.length === 0
          ? <GrowthState icon="trend" title="还没有关注的直播间"
            text="关注主播并开始挂机后，这里会自动记录每天的粉丝牌亲密度。"
            action={onOpenMonitor ? "去直播总览" : ""} onAction={onOpenMonitor} />
          : <>
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
                    ? `${dayParts(day).md}`
                    : (selected
                      ? `${dayParts(day).md} · +${numberText(value)}`
                      : `${dayParts(day).md} · 合计 ${numberText(value)} · 当前 ${coverage.rooms_recorded}/${coverage.rooms_recordable} 间有记录`);
                  return (
                    <div className="growth-chart-col" key={day} title={tip}>
                      <div className={`growth-chart-value${missing ? " missing" : isToday ? " strong" : ""}`}>
                        {missing ? "" : shortNumber(value)}
                      </div>
                      <div className="growth-chart-area">
                        {missing
                          ? <div className="growth-chart-missing" aria-hidden="true" />
                          : <div className={`growth-chart-bar${zero ? " zero" : ""}${isToday ? " today" : ""}`}
                            style={{ height: `${height}%` }} />}
                      </div>
                      <div className="growth-chart-day">
                        {isToday ? <strong>今天</strong> : dayParts(day).md}
                        <span className="cover">
                          {isToday
                            ? (missing ? "" : data.running ? <span className="ongoing">进行中</span> : "未挂机")
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
              <div className="growth-rooms-bar">
                <span className="growth-rooms-summary">
                  当前关注 {followedRooms.length} 位
                  {activeRooms.length < followedRooms.length ? ` · ${activeRooms.length} 位近 7 日有增长` : ""}
                </span>
                {showFilter && (
                  <div className="growth-filter" role="group" aria-label="直播间筛选">
                    <button type="button" className="growth-filter-btn" aria-pressed={!onlyGained}
                      onClick={() => setOnlyGained(false)}>全部 {followedRooms.length}</button>
                    <button type="button" className="growth-filter-btn" aria-pressed={onlyGained}
                      onClick={() => setOnlyGained(true)}>有增长 {activeRooms.length}</button>
                  </div>
                )}
              </div>
              <div className="growth-cols"><span>直播间</span><span>近 7 日</span><span>今日</span><span>合计</span></div>
              {rowNodes.length ? rowNodes : (
                <div className="growth-filter-empty">
                  <span>近 7 日暂无亲密度增长记录</span>
                  <button type="button" className="btn sm" onClick={() => setOnlyGained(false)}>显示全部关注</button>
                </div>
              )}
            </section>
          </>}
      </div>
    </div>
  );
}

Object.assign(window, { GrowthPage });
