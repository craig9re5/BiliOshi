/* Overview and room detail. Labels describe verified state from the engine. */

const { Icon, relativeTime, absoluteTime, durationLabel, numberLabel } = window;

const copyTimers = new WeakMap();
let lastCopyMessage = "";

function legacyCopyText(text) {
  const field = Object.assign(document.createElement("textarea"), { value: text });
  field.setAttribute("readonly", "");
  field.style.cssText = "position:fixed;inset-block-start:0;opacity:0";
  document.body.append(field);
  field.select();
  try { return document.execCommand("copy"); } finally { field.remove(); }
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
  window.requestAnimationFrame(() => { if (tip) tip.textContent = message; });
  copyTimers.set(button, window.setTimeout(() => {
    button.removeAttribute("data-copied");
    button.removeAttribute("data-failed");
    if (tip) tip.textContent = "";
  }, 1800));
}

async function copyTargetText(button, target) {
  const raw = target.matches?.("input, textarea") ? target.value : (target.innerText || target.textContent || "");
  const text = String(raw).trim();
  if (!text) return;
  try {
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
    else if (!legacyCopyText(text)) throw new Error("Copy failed");
    reportCopyStatus(button, true);
  } catch {
    if (legacyCopyText(text)) reportCopyStatus(button, true);
    else reportCopyStatus(button, false);
  }
}

if (typeof document !== "undefined" && typeof document.addEventListener === "function") {
  if ("CommandEvent" in window) {
    document.addEventListener("command", (event) => {
      if (event.command === "--copy" && event.source && event.target) {
        copyTargetText(event.source, event.target);
      }
    }, true);
  } else {
    document.addEventListener("click", (event) => {
      const button = event.target?.closest?.('button[command="--copy"]');
      if (!button) return;
      const target = document.getElementById(button.getAttribute("commandfor"));
      if (target) copyTargetText(button, target);
    });
  }
}

const Avatar = ({ room, image }) => (
  <span className="avatar" style={{ background: room.color }} aria-hidden="true">
    {image ? <img src={image} alt="" /> : room.initial}
  </span>
);

const TASK_ICONS = {
  danmaku: "chat",
  like: "heart",
  watch: "monitor",
  light: "medal",
};

const RoomRow = ({ room, selected, onSelect, onContextMenu, image, managing, checked, onToggleCheck }) => {
  const metaParts = [];
  if (room.healthy) metaParts.push(`已连接 ${durationLabel(room.minutes)}`);
  else if (room.live && room.live_duration) metaParts.push(room.live_duration);
  if (room.gain !== null && (room.gain > 0 || room.healthy)) {
    metaParts.push(`今日 +${numberLabel(room.gain)}`);
  } else if (!room.live && room.medal_name) {
    metaParts.push(`${room.medal_name} Lv.${room.medal_level}`);
  }
  return (
    <button type="button" className={`room ${managing ? "managing" : ""} ${checked ? "batch-checked" : ""}`} role="option"
      aria-selected={managing ? checked : selected}
      data-room={room.room} onClick={() => (managing ? onToggleCheck(room.room) : onSelect(room.room))}
      onContextMenu={(event) => !managing && onContextMenu(event, room.room)}>
      {managing && <span className={`room-check ${checked ? "checked" : ""}`} aria-hidden="true">
        {checked && <Icon name="check" size={11} />}
      </span>}
      <Avatar room={room} image={image} />
      <span className="room-main">
        <span className="room-name">
          {room.live && <i className="live-dot" title="直播中" />}
          <span>{room.name}</span>
        </span>
        {room.live && room.title && <span className="room-title" title={room.title}>{room.title}</span>}
        {metaParts.length > 0 && (
          <span className="room-meta">
            {metaParts.map((part, idx) => (
              <React.Fragment key={idx}>
                {idx > 0 && <span className="sep">·</span>}
                <span>{part}</span>
              </React.Fragment>
            ))}
          </span>
        )}
      </span>
      {room.state !== "未开播" && <span className="room-side">
        <span className={`pill ${room.tone}`}>{room.state}</span>
      </span>}
    </button>
  );
};

const DetailPanel = ({ room, image, busy, onAction, onOpen, onMore, moreOpen, onClearRoomBlock, onDismissTaskError, onDismissWatchWarning, dimmed }) => {
  const classes = `detail card${dimmed ? " detail-dim" : ""}`;
  if (!room) return (
    <aside className={classes} aria-label="直播间详情" aria-hidden={dimmed || undefined}>
      <div className="empty">
        <Icon name="monitor" size={24} />
        <strong>选择一个直播间</strong>
        <span>查看连接状态与今日任务</span>
      </div>
    </aside>
  );
  const taskCount = room.tasks.filter((task) => task.done).length;
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
  return (
    <aside className={classes} aria-label="直播间详情" aria-hidden={dimmed || undefined}
      data-screen-label={`详情 · ${room.name}`}>
      <div className="detail-scroll" key={room.room}>
        <div className="detail-heading">
          <Avatar room={room} image={image} />
          <div className="detail-identity">
            <div className="detail-name">{room.name}</div>
            <div className="detail-title" title={room.title}>{room.live ? room.title || "直播中" : room.state}</div>
            <div className="detail-submeta">
              <span className="tnum">房间 <span id={`room-code-${room.room}`}>{room.room}</span></span>
              <span className="copy-inline">
                <button type="button" className="copy-room-btn" command="--copy" commandfor={`room-code-${room.room}`}
                  aria-label="复制直播间号" title="复制直播间号">
                  <span className="copy-ico copy-ico-default" aria-hidden="true"><Icon name="copy" size={11} /></span>
                  <span className="copy-ico copy-ico-done" aria-hidden="true"><Icon name="check" size={11} /></span>
                </button>
                <span className="copy-tip" role="status" />
              </span>
              {room.live && room.area_name && <><span className="sep">·</span><span>{room.area_name}</span></>}
              {room.live && room.live_duration && <><span className="sep">·</span><span>{room.live_duration}</span></>}
            </div>
          </div>
          <button type="button" className={`btn ghost icon-button${moreOpen ? " active" : ""}`} title="更多操作"
            aria-label="更多操作" aria-haspopup="menu" aria-expanded={Boolean(moreOpen)}
            onPointerDown={(event) => { if (moreOpen) event.stopPropagation(); }}
            onMouseDown={(event) => { if (moreOpen) event.stopPropagation(); }}
            onClick={onMore}><Icon name="more" size={17} /></button>
        </div>
        {showStateRow && <div className="state-row">
          <span className={`state-label ${room.tone === "warn" ? "warn" : ""}`}>
            {room.state}
            <span className="state-sub" title={absoluteTime(room.last_heartbeat)}>
              {room.healthy ? `已连接 ${durationLabel(room.minutes)}`
                : room.live ? "开播后自动建立连接" : "等待恢复正常"}
              {room.last_heartbeat && room.active ? ` · ${relativeTime(room.last_heartbeat)}同步` : ""}
            </span>
          </span>
          {/* A status line reads better with a quiet link than a button that
              competes with the page actions at the bottom. */}
          <button type="button" className="link-btn state-action" onClick={() => onAction("reconnect", room.room)}
            disabled={pending || Boolean(room.actions.reconnect)} title={room.actions.reconnect || "重新建立看播连接"}>
            <Icon name="reconnect" size={11} className={room.reconnecting ? "spin" : ""} />
            {room.reconnecting ? "重连中…" : "重新连接"}
          </button>
        </div>}
        <div className="gain-card">
          <div className="gain-head"><span className="gain-label">今日亲密度</span>
            {room.medal_name && (
              <span className={`gain-medal ${medalLit ? "lit" : medalUnlit ? "unlit" : ""}`}>
                {room.medal_name} Lv.{room.medal_level}{medalUnlit ? " · 未点亮" : ""}
              </span>
            )}
          </div>
          <div className="gain-value">{room.gain === null ? "—" : `+${numberLabel(room.gain)}`}</div>
          <div className="gain-foot">
            <span>{room.gain === null ? "等待更新" : "今日已获得"}</span>
            {room.day_limit > 0 && <span className="tnum">每日上限 {numberLabel(room.day_limit)}</span>}
          </div>
          {knownExperience && <>
            <div className="bar level-bar" role="progressbar" aria-label="粉丝牌升级进度"
              aria-valuenow={room.intimacy} aria-valuemin={0} aria-valuemax={room.next_intimacy}>
              <i style={{ width: `${progress}%` }} />
            </div>
            <div className="gain-foot"><span>等级经验（{Math.round(progress)}%）</span>
              <span className="tnum">{numberLabel(room.intimacy)} / {numberLabel(room.next_intimacy)}</span>
            </div>
          </>}
        </div>
        {(room.connection_warning || room.watch_warning || room.task_error) && (() => {
          const dismissHandler = room.connection_warning || room.protectedAccount
            ? null
            : room.watch_warning
              ? onDismissWatchWarning
              : room.task_error
                ? onDismissTaskError
                : null;
          return (
            <div className={`notice${dismissHandler ? " notice-action" : ""}`} role="status">
              <Icon name="alert" size={14} />
              <span className="notice-body">{room.connection_warning || room.watch_warning || room.task_error}</span>
              {dismissHandler && (
                <button type="button" className="btn sm" disabled={pending}
                  onClick={() => dismissHandler(room.room)}>
                  知道了
                </button>
              )}
            </div>
          );
        })()}
        {note && <div className="notice neutral"><Icon name="info" size={14} /><span>{note}</span></div>}
        {Array.isArray(room.room_blocks) && room.room_blocks.map((block) => (
          <div className="notice notice-action" key={`${block.kind || "cap"}-${block.since || 0}`} role="status">
            <Icon name="alert" size={14} />
            <div className="notice-body">
              <strong>{block.kind_label || "单房间互动受限"}</strong>
              <span>{block.reason || "该直播间互动权限受限，不影响挂机看播。"}</span>
            </div>
            {onClearRoomBlock && (
              <button type="button" className="btn sm" disabled={pending}
                onClick={() => onClearRoomBlock(room.room, block.kind || null)}>
                解除限制
              </button>
            )}
          </div>
        ))}
        {room.reconnect_message && <div className="inline-status" role="status">{room.reconnect_message}</div>}
        <section className="block">
          <div className="block-head"><span className="block-title">今日任务</span>
            <span className="block-note tnum">{room.tasks_stale ? "等待更新" : `${taskCount} / ${room.tasks.length} 已完成`}</span>
          </div>
          <div className="task-table">
            {room.tasks.map((task) => {
              const canRedoSingle = !room.tasks_stale && !task.done && !pending && !reason
                && (task.key === "danmaku" || task.key === "like");
              return (
                <div className="task" key={task.key}>
                  <span className="task-left">
                    <Icon name={TASK_ICONS[task.key] || "circle"} size={13} />
                    <span className="task-name">{task.name}</span>
                  </span>
                  <span className="task-right">
                    <span className={`task-val ${task.done ? "done" : !task.text ? "pending" : ""}`}>
                      {task.done && <Icon name="check" size={11} />}{task.text || "待更新"}
                    </span>
                    {canRedoSingle && (
                      <button type="button" className="task-redo-btn"
                        onClick={() => onAction("redo", room.room, task.key)}
                        title={`单独补齐${task.name}任务`}>
                        补做
                      </button>
                    )}
                  </span>
                </div>
              );
            })}
          </div>
        </section>
      </div>
      <div className="detail-action-area">
        {operation.message && <p className="action-hint" role="status">{operation.message}</p>}
        {showReason && <p className="action-hint">{reason}</p>}
        <div className="detail-foot">
          <button type="button" className="btn" onClick={() => onOpen(room.room)} disabled={Boolean(room.actions.open)}>
            <Icon name="external" size={13} />打开直播间
          </button>
          <button type="button" className="btn primary" onClick={() => onAction("redo", room.room)}
            disabled={pending || Boolean(reason)} title={reason || "自动补齐今日未完成的互动任务"}>
            <Icon name={pending ? "refresh" : "check"} size={13} className={pending ? "spin" : ""} />
            {pending ? "正在处理…" : "补齐今日任务"}
          </button>
        </div>
      </div>
    </aside>
  );
};

const OverviewActions = ({ paused, globalPaused, signedIn = true, onTogglePause, onCheck, checking, controlBusy, closing }) => {
  const effectivelyPaused = Boolean(paused || globalPaused);
  const noAccountReady = !signedIn && !effectivelyPaused;
  return (
    <>
      <button type="button" className="btn" onClick={onCheck}
        title={noAccountReady ? "请先登录 B 站账号" : "检查开播状态与任务进度"}
        disabled={checking || controlBusy || closing || noAccountReady}>
        <Icon name="refresh" size={13} className={checking ? "spin" : ""} />{checking ? "检查中…" : "立即检查"}</button>
      <button type="button" className={`btn ${effectivelyPaused ? "primary" : ""}`} onClick={onTogglePause}
        title={noAccountReady ? "请先登录 B 站账号" : ""}
        disabled={controlBusy || closing || noAccountReady}>
        <Icon name={effectivelyPaused ? "play" : "pause"} size={13} />
        {globalPaused ? "恢复全部" : paused ? "恢复挂机" : "暂停挂机"}</button>
    </>
  );
};

const Overview = ({ rooms, selectedId, onSelect, paused, globalPaused,
  onAction, onOpen, onAddMember, onSyncMedals, onRemove, onContextMenu, menuRoom, menuMode,
  busyRoom, controlBusy, error, recovery, onRecovery, interval, lastCheck, checking, images,
  signedIn, closing, bridgeConnected, onBatchRemove, onClearRoomBlock, onDismissTaskError, onDismissWatchWarning }) => {
  const [managing, setManaging] = React.useState(false);
  const [selectedBatch, setSelectedBatch] = React.useState(new Set());
  const [roomQuery, setRoomQuery] = React.useState("");
  const [roomFilter, setRoomFilter] = React.useState("all");
  const searchInputRef = React.useRef(null);

  const liveCount = rooms.filter((r) => r.live).length;
  const warnCount = rooms.filter((r) => r.tone === "warn").length;
  const activeFilter = (roomFilter === "live" && liveCount === 0) || (roomFilter === "warn" && warnCount === 0)
    ? "all"
    : roomFilter;
  const keyword = roomQuery.trim().toLowerCase();
  const showToolbar = !managing && rooms.length >= 4;

  React.useEffect(() => {
    if (!showToolbar) return undefined;
    const onKeyDown = (event) => {
      if ((event.ctrlKey || event.metaKey) && !event.shiftKey && !event.altKey && event.key.toLowerCase() === "f") {
        event.preventDefault();
        searchInputRef.current?.focus();
        searchInputRef.current?.select?.();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [showToolbar]);
  const filteredRooms = showToolbar
    ? rooms.filter((r) => {
        if (activeFilter === "live" && !r.live) return false;
        if (activeFilter === "warn" && r.tone !== "warn") return false;
        if (!keyword) return true;
        return [r.name, r.title, r.medal_name, r.area_name, r.room, r.uid]
          .some((field) => String(field || "").toLowerCase().includes(keyword));
      })
    : rooms;

  const allChecked = rooms.length > 0 && rooms.every((r) => selectedBatch.has(r.room));
  const toggleAll = () => {
    if (allChecked) setSelectedBatch(new Set());
    else setSelectedBatch(new Set(rooms.map((r) => r.room)));
  };
  const toggleCheck = (roomId) => {
    setSelectedBatch((current) => {
      const next = new Set(current);
      if (next.has(roomId)) next.delete(roomId);
      else next.add(roomId);
      return next;
    });
  };
  const handleBatchRemove = () => {
    if (selectedBatch.size === 0 || typeof onBatchRemove !== "function") return;
    const targetRooms = rooms.filter((r) => selectedBatch.has(r.room));
    onBatchRemove(targetRooms);
    setManaging(false);
    setSelectedBatch(new Set());
  };
  const onRoomKey = (event) => {
    if (managing || !filteredRooms.length) return;
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const focused = event.target.closest?.(".room");
    const current = focused ? Number(focused.dataset.room) : selectedId;
    const index = filteredRooms.findIndex((room) => room.room === current);
    const next = event.key === "Home" ? 0
      : event.key === "End" ? filteredRooms.length - 1
        : index < 0 ? 0
          : (index + (event.key === "ArrowDown" ? 1 : -1) + filteredRooms.length) % filteredRooms.length;
    onSelect(filteredRooms[next].room);
    event.currentTarget.querySelector(`[data-room="${filteredRooms[next].room}"]`)?.focus();
  };

  const selected = rooms.find((room) => room.room === selectedId);
  const healthy = rooms.filter((room) => room.healthy).length;
  const unknown = rooms.filter((room) => room.live_status == null).length;
  const status = closing ? "正在退出…" : !bridgeConnected ? "正在连接后台…"
    : globalPaused ? "全部挂机已暂停"
    : paused ? "已暂停挂机"
    : !signedIn ? "等待登录" : error ? "需要处理" : healthy ? `${healthy} 个直播间挂机中`
    : unknown ? "等待检查" : "等待开播";
  // The cadence and the last check belong together: the title bar keeps only
  // the page name, so the footer is the single place this is reported.
  const cadence = `每 ${interval} 分钟检查一次${lastCheck ? ` · 上次检查 ${relativeTime(lastCheck)}` : ""}`;
  const showBanner = Boolean(error || recovery?.action === "login" || recovery?.action === "resume_global" || recovery?.action === "switch_prompt");
  const bannerMessage = error || recovery?.message || (!signedIn ? "请先登录 B 站账号以开始挂机" : "");
  return (<>
    {showBanner && <div className="banner" role="status">
      <Icon name={recovery?.action === "login" || recovery?.action === "switch_prompt" ? "user" : "alert"} size={14} />
      <span>{bannerMessage}</span>
      {recovery?.action && <button type="button" className="btn sm" onClick={onRecovery}>{recovery.label || "查看详情"}</button>}
    </div>}
    <div className="workspace">
      <section className="list card" aria-label="关注的直播间">
        {!managing ? (
          <header className="list-head">
            <span className="list-title">关注的直播间</span><span className="list-count tnum">{rooms.length}</span>
            <span className="spacer" />
            <button type="button" className="btn ghost sm" onClick={onAddMember} disabled={closing}>
              <Icon name="plus" size={12} />添加主播</button>
            {onSyncMedals && (
              <button type="button" className="btn ghost sm" onClick={onSyncMedals} disabled={closing || !signedIn}
                title={!signedIn ? "请先登录账号" : "从账号已有粉丝牌批量导入"}>
                <Icon name="medal" size={12} />同步粉丝牌</button>
            )}
            <button type="button" className="btn ghost sm" onClick={() => setManaging(true)} disabled={closing || !rooms.length}>
              批量管理</button>
          </header>
        ) : (
          <header className="list-head managing-head">
            <button type="button" className="batch-all-btn" onClick={toggleAll} aria-label="全选">
              <span className={`room-check ${allChecked ? "checked" : ""}`} aria-hidden="true">
                {allChecked && <Icon name="check" size={11} />}
              </span>
              <span>全选 ({selectedBatch.size}/{rooms.length})</span>
            </button>
            <span className="spacer" />
            <button type="button" className="btn danger sm" disabled={selectedBatch.size === 0 || closing}
              onClick={handleBatchRemove}>
              <Icon name="trash" size={12} />批量移除 {selectedBatch.size ? `(${selectedBatch.size})` : ""}</button>
            <button type="button" className="btn ghost sm" onClick={() => { setManaging(false); setSelectedBatch(new Set()); }}>
              完成</button>
          </header>
        )}
        {showToolbar && (
          <div className="list-toolbar">
            <div className="search-box">
              <Icon name="search" size={13} />
              <input ref={searchInputRef} className="search-input" value={roomQuery}
                onChange={(e) => setRoomQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Escape" && roomQuery) { e.stopPropagation(); setRoomQuery(""); } }}
                aria-label="筛选直播间" placeholder="搜索主播、标题或房间号… (Ctrl+F)" />
              {roomQuery && (
                <button type="button" className="search-clear" aria-label="清除搜索" onClick={() => setRoomQuery("")}>
                  <Icon name="close" size={11} />
                </button>
              )}
            </div>
            {(liveCount > 0 || warnCount > 0) && (
              <div className="list-filters" role="group" aria-label="状态筛选">
                <button type="button" className="growth-filter-btn" aria-pressed={activeFilter === "all"}
                  onClick={() => setRoomFilter("all")}>全部</button>
                {liveCount > 0 && (
                  <button type="button" className="growth-filter-btn" aria-pressed={activeFilter === "live"}
                    onClick={() => setRoomFilter("live")}>直播中 {liveCount}</button>
                )}
                {warnCount > 0 && (
                  <button type="button" className="growth-filter-btn" aria-pressed={activeFilter === "warn"}
                    onClick={() => setRoomFilter("warn")}>需关注 {warnCount}</button>
                )}
              </div>
            )}
          </div>
        )}
        {/* A listbox promises arrow-key movement; without it keyboard users
            must Tab through every room. */}
        <div className="rooms" role="listbox" aria-label="直播间列表" onKeyDown={onRoomKey}>
          {!rooms.length ? (
            <div className="empty list-empty"><Icon name="monitor" size={24} /><strong>还没有关注主播</strong>
              <span>添加主播或同步粉丝牌后即可自动挂机</span>
              <div className="empty-actions">
                <button type="button" className="btn sm primary" onClick={onAddMember}>
                  <Icon name="plus" size={12} />添加主播</button>
                {onSyncMedals && signedIn && (
                  <button type="button" className="btn sm" onClick={onSyncMedals}>
                    <Icon name="medal" size={12} />同步粉丝牌</button>
                )}
              </div>
            </div>
          ) : !filteredRooms.length ? (
            <div className="empty list-empty">
              <Icon name="search" size={22} />
              <strong>没有匹配的直播间</strong>
              <span>试试其他关键词或切换筛选条件</span>
              <button type="button" className="btn sm" onClick={() => { setRoomQuery(""); setRoomFilter("all"); }}>
                清除筛选</button>
            </div>
          ) : filteredRooms.map((room) => <RoomRow key={room.room} room={room} selected={room.room === selectedId}
            image={images[room.uid]} onSelect={onSelect} onContextMenu={onContextMenu}
            managing={managing} checked={selectedBatch.has(room.room)} onToggleCheck={toggleCheck} />)}
        </div>
      </section>
      <DetailPanel room={selected} image={images[selected?.uid]} busy={busyRoom === selected?.room} onAction={onAction} onOpen={onOpen}
        onClearRoomBlock={onClearRoomBlock} onDismissTaskError={onDismissTaskError}
        onDismissWatchWarning={onDismissWatchWarning} dimmed={managing}
        moreOpen={Boolean(selected && menuMode === "overflow" && menuRoom === selected.room)}
        onMore={(event) => {
          if (!selected) return;
          onContextMenu(event, selected.room, "overflow");
        }} />
    </div>
    <footer className="statusbar">
      <span className={healthy && !closing ? "dot-live" : "dot-paused"} aria-hidden="true" /><strong>{status}</strong>
      <span className="spacer" /><span className="low-priority">{checking ? "正在检查直播状态…" : cadence}</span>
    </footer>
  </>);
};

Object.assign(window, { Overview, OverviewActions, Avatar });
