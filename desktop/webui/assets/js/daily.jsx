/* Main-site Daily EXP dashboard (login + watch + share + optional coin). */

const { Icon, numberLabel, relativeTime } = window;

function dailyCoinNote(settings) {
  if (!settings?.do_coin) return "自动投币已关闭";
  const target = Math.max(0, Math.min(5, Number(settings?.coin_target ?? 5)));
  if (target <= 0) return "自动投币已关闭";
  return settings.prefer_medals ? `每日自动投 ${target} 枚 · 优先关注主播` : `每日自动投 ${target} 枚`;
}

function DailyPage({
  daily,
  dailyRunning,
  today,
  settings,
  account,
  profile,
  busy,
  onRun,
  onRefresh,
  onOpenLogin,
  onOpenSafety,
  onOpenSettings,
}) {
  const signedIn = Boolean(account?.signed_in);
  const hold = account?.safety || {};
  const blocked = Boolean(hold.blocked && hold.scope !== "interaction");
  const validDaily = daily && typeof daily === "object" ? daily : {};
  const isToday = Boolean(validDaily.day && (!today || validDaily.day === today));
  const user = validDaily.user || profile || {};
  const ledger = isToday ? (validDaily.ledger || validDaily.ledger_after || {}) : {};

  const level = Number.isFinite(user.level) ? user.level : null;
  const maxLevel = Boolean(user.is_max_level) || (level !== null && level >= 6);
  const currentExp = Number.isFinite(user.current_exp) ? user.current_exp : null;
  const nextExp = Number.isFinite(user.next_exp) ? user.next_exp : null;
  const levelPercent = maxLevel
    ? 100
    : currentExp !== null && nextExp > 0
      ? Math.min(100, Math.max(0, (currentExp / nextExp) * 100))
      : 0;
  const coinsBalance = Number.isFinite(user.coins) ? user.coins : null;

  const loginDone = Boolean(isToday && ledger.login);
  const watchDone = Boolean(isToday && ledger.watch);
  const shareDone = Boolean(isToday && ledger.share);
  const coinsExp = isToday && Number.isFinite(ledger.coins_exp) ? ledger.coins_exp : 0;
  const coinsCount = isToday && Number.isFinite(ledger.coins_count) ? ledger.coins_count : Math.floor(coinsExp / 10);
  const earnedExp = isToday && Number.isFinite(ledger.earned_exp)
    ? ledger.earned_exp
    : (loginDone ? 5 : 0) + (watchDone ? 5 : 0) + (shareDone ? 5 : 0) + coinsExp;
  const daysLeft = isToday && Number.isFinite(validDaily.days_to_next_level) ? validDaily.days_to_next_level : null;
  const pendingSettlement = Boolean(isToday && validDaily.pending_settlement);
  const working = Boolean(busy || dailyRunning);
  const canExecute = signedIn && !blocked && !working;

  const taskResults = isToday && Array.isArray(validDaily.tasks)
    ? Object.fromEntries(validDaily.tasks.filter((t) => t?.task).map((t) => [t.task, t]))
    : {};
  const failedError = isToday && validDaily.ok === false
    ? (validDaily.error || Object.values(taskResults).find((t) => t && t.success === false && t.error)?.error || "")
    : "";

  const tasks = [
    {
      key: "login",
      icon: "user",
      name: "每日登录",
      gain: "+5 经验",
      done: loginDone,
      statusText: !isToday ? "等待获取" : loginDone ? "已完成" : "登录即领",
      actionLabel: "",
    },
    {
      key: "watch",
      icon: "video",
      name: "观看视频",
      gain: "+5 经验",
      done: watchDone,
      statusText: !isToday ? "等待获取" : watchDone ? "已完成" : "未完成",
      actionLabel: watchDone ? "" : "去完成",
    },
    {
      key: "share",
      icon: "share",
      name: "分享视频",
      gain: "+5 经验",
      done: shareDone,
      statusText: !isToday ? "等待获取" : shareDone ? "已完成" : "未完成",
      actionLabel: shareDone ? "" : "去完成",
    },
    {
      key: "coin",
      icon: "coin",
      name: "视频投币",
      gain: `${coinsExp} / 50 经验`,
      sub: `${coinsCount} / 5 枚 · ${dailyCoinNote(settings)}`,
      done: coinsCount >= 5,
      partial: coinsCount > 0 && coinsCount < 5,
      statusText: !isToday ? "等待获取" : coinsCount >= 5 ? "已领满" : `${coinsCount} / 5 枚`,
      actionLabel: coinsCount < 5 ? (coinsCount > 0 ? "继续投币" : "投币") : "",
    },
  ];

  return (
    <div className="daily-page" data-screen-label="每日签到">
      <div className="daily-inner">
        {!signedIn ? (
          <div className="banner" role="status">
            <Icon name="user" size={14} />
            <span>请先登录 B 站账号后再查看或执行每日签到。</span>
            <button type="button" className="btn sm" onClick={onOpenLogin}>扫码登录</button>
          </div>
        ) : blocked ? (
          <div className="banner" role="status">
            <Icon name="alert" size={14} />
            <span>{hold.reason || "当前账号处于保护暂停状态，签到任务已暂缓。"}</span>
            <button type="button" className="btn sm" onClick={onOpenSafety}>查看详情</button>
          </div>
        ) : failedError ? (
          <div className="banner" role="status">
            <Icon name="alert" size={14} />
            <span>{failedError}</span>
          </div>
        ) : pendingSettlement ? (
          <div className="notice neutral daily-notice" role="status">
            <Icon name="info" size={14} />
            <span>今日任务已提交，B 站经验到账存在几秒延迟，稍后可点击刷新确认。</span>
          </div>
        ) : null}

        <section className="card daily-hero">
          <div className="daily-hero-left">
            <div className="daily-identity">
              <strong>{user.name || account?.name || (signedIn ? "已登录账号" : "未登录")}</strong>
              {level !== null && <span className="daily-badge accent">Lv.{level}</span>}
              {user.vip_label && <span className="daily-badge">{user.vip_label}</span>}
              {coinsBalance !== null && (
                <span className="daily-badge tnum">硬币 {coinsBalance}</span>
              )}
            </div>
            <div className="daily-level-wrap">
              <div className="bar level-bar" role="progressbar" aria-label="B 站账号升级进度"
                aria-valuenow={currentExp || 0} aria-valuemin={0} aria-valuemax={maxLevel ? Math.max(1, currentExp || 1) : (nextExp || 1)}>
                <i style={{ width: `${levelPercent}%` }} />
              </div>
              <div className="daily-level-meta">
                <span className="tnum">
                  {level === null
                    ? "点击刷新获取等级与经验"
                    : maxLevel
                      ? `累计经验 ${numberLabel(currentExp)} · 已满级`
                      : `经验 ${numberLabel(currentExp)} / ${numberLabel(nextExp)}`}
                </span>
                {!maxLevel && daysLeft !== null && (
                  <span className="daily-hint">
                    {daysLeft === 0 ? "今日完成任务即可升级" : `按当前设置约 ${daysLeft} 天升至 Lv.${level + 1}`}
                  </span>
                )}
              </div>
            </div>
          </div>
          <div className="daily-hero-right">
            <div className="daily-kpi">
              <span className="daily-kpi-label">今日经验</span>
              <strong className="daily-kpi-val tnum">{earnedExp}<small> / 65</small></strong>
              <span className="daily-kpi-time">
                {validDaily.updated ? `更新于 ${relativeTime(validDaily.updated)}` : "尚未获取今日进度"}
              </span>
            </div>
            <div className="daily-actions">
              <button type="button" className="btn" disabled={!signedIn || working} onClick={onRefresh}>
                <Icon name="refresh" size={13} className={working ? "spin" : ""} />刷新进度
              </button>
              <button type="button" className="btn primary" disabled={!canExecute} onClick={() => onRun(null)}>
                <Icon name={working ? "refresh" : "sparkles"} size={13} className={working ? "spin" : ""} />
                {working ? "签到中…" : "立即签到"}
              </button>
            </div>
          </div>
        </section>

        <section className="daily-grid" aria-label="每日经验任务">
          {tasks.map((task) => {
            const err = taskResults[task.key]?.success === false ? taskResults[task.key]?.error : "";
            return (
              <div className={`card daily-task ${task.done ? "done" : ""}`} key={task.key}>
                <div className="daily-task-top">
                  <span className={`daily-task-icon ${task.done ? "done" : ""}`} aria-hidden="true">
                    <Icon name={task.icon} size={16} />
                  </span>
                  <div className="daily-task-info">
                    <div className="daily-task-name">{task.name}</div>
                    <div className="daily-task-gain tnum">{task.gain}</div>
                  </div>
                  <span className={`pill ${task.done ? "live" : task.partial ? "" : "muted"}`}>
                    {task.statusText}
                  </span>
                </div>
                {(task.sub || err || task.actionLabel) && (
                  <div className="daily-task-foot">
                    <span className={`daily-task-sub ${err ? "warn" : ""}`} title={err || task.sub || ""}>
                      {err || task.sub || ""}
                    </span>
                    {task.key === "coin" && onOpenSettings && !task.actionLabel && (
                      <button type="button" className="link-btn" onClick={onOpenSettings}>投币设置</button>
                    )}
                    {task.actionLabel && (
                      <button type="button" className="btn sm" disabled={!canExecute} onClick={() => onRun(task.key)}>
                        {task.actionLabel}
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      </div>
    </div>
  );
}

Object.assign(window, { DailyPage });
