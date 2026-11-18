/* BiliOshi JSX {"code_sha256":"2614d57c817aaf99081b96642fa5c01b2f769101f0ae8260a0597cd6b4ad5a5e","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"daily.jsx","source_sha256":"9d24a0edcb5e5cca1de311c240cd605b6c4ce83ba6eab55b469b0eb281ba433e"} */
(function () {
"use strict";
/* Main-site Daily EXP dashboard (login + watch + share + optional coin). */

const {
  Icon,
  numberLabel,
  relativeTime
} = window;
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
  onOpenSettings
}) {
  const signedIn = Boolean(account?.signed_in);
  const hold = account?.safety || {};
  const blocked = Boolean(hold.blocked && hold.scope !== "interaction");
  const validDaily = daily && typeof daily === "object" ? daily : {};
  const isToday = Boolean(validDaily.day && (!today || validDaily.day === today));
  const user = validDaily.user || profile || {};
  const ledger = isToday ? validDaily.ledger || validDaily.ledger_after || {} : {};
  const level = Number.isFinite(user.level) ? user.level : null;
  const maxLevel = Boolean(user.is_max_level) || level !== null && level >= 6;
  const currentExp = Number.isFinite(user.current_exp) ? user.current_exp : null;
  const nextExp = Number.isFinite(user.next_exp) ? user.next_exp : null;
  const levelPercent = maxLevel ? 100 : currentExp !== null && nextExp > 0 ? Math.min(100, Math.max(0, currentExp / nextExp * 100)) : 0;
  const coinsBalance = Number.isFinite(user.coins) ? user.coins : null;
  const loginDone = Boolean(isToday && ledger.login);
  const watchDone = Boolean(isToday && ledger.watch);
  const shareDone = Boolean(isToday && ledger.share);
  const coinsExp = isToday && Number.isFinite(ledger.coins_exp) ? ledger.coins_exp : 0;
  const coinsCount = isToday && Number.isFinite(ledger.coins_count) ? ledger.coins_count : Math.floor(coinsExp / 10);
  const earnedExp = isToday && Number.isFinite(ledger.earned_exp) ? ledger.earned_exp : (loginDone ? 5 : 0) + (watchDone ? 5 : 0) + (shareDone ? 5 : 0) + coinsExp;
  const daysLeft = isToday && Number.isFinite(validDaily.days_to_next_level) ? validDaily.days_to_next_level : null;
  const pendingSettlement = Boolean(isToday && validDaily.pending_settlement);
  const working = Boolean(busy || dailyRunning);
  const canExecute = signedIn && !blocked && !working;
  const taskResults = isToday && Array.isArray(validDaily.tasks) ? Object.fromEntries(validDaily.tasks.filter(t => t?.task).map(t => [t.task, t])) : {};
  const failedError = isToday && validDaily.ok === false ? validDaily.error || Object.values(taskResults).find(t => t && t.success === false && t.error)?.error || "" : "";
  const tasks = [{
    key: "login",
    icon: "user",
    name: "每日登录",
    gain: "+5 经验",
    done: loginDone,
    statusText: !isToday ? "等待获取" : loginDone ? "已完成" : "登录即领",
    actionLabel: ""
  }, {
    key: "watch",
    icon: "video",
    name: "观看视频",
    gain: "+5 经验",
    done: watchDone,
    statusText: !isToday ? "等待获取" : watchDone ? "已完成" : "未完成",
    actionLabel: watchDone ? "" : "去完成"
  }, {
    key: "share",
    icon: "share",
    name: "分享视频",
    gain: "+5 经验",
    done: shareDone,
    statusText: !isToday ? "等待获取" : shareDone ? "已完成" : "未完成",
    actionLabel: shareDone ? "" : "去完成"
  }, {
    key: "coin",
    icon: "coin",
    name: "视频投币",
    gain: `${coinsExp} / 50 经验`,
    sub: `${coinsCount} / 5 枚 · ${dailyCoinNote(settings)}`,
    done: coinsCount >= 5,
    partial: coinsCount > 0 && coinsCount < 5,
    statusText: !isToday ? "等待获取" : coinsCount >= 5 ? "已领满" : `${coinsCount} / 5 枚`,
    actionLabel: coinsCount < 5 ? coinsCount > 0 ? "继续投币" : "投币" : ""
  }];
  return /*#__PURE__*/React.createElement("div", {
    className: "daily-page",
    "data-screen-label": "\u6BCF\u65E5\u7B7E\u5230"
  }, /*#__PURE__*/React.createElement("div", {
    className: "daily-inner"
  }, !signedIn ? /*#__PURE__*/React.createElement("div", {
    className: "banner",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "user",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, "\u8BF7\u5148\u767B\u5F55 B \u7AD9\u8D26\u53F7\u540E\u518D\u67E5\u770B\u6216\u6267\u884C\u6BCF\u65E5\u7B7E\u5230\u3002"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onOpenLogin
  }, "\u626B\u7801\u767B\u5F55")) : blocked ? /*#__PURE__*/React.createElement("div", {
    className: "banner",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, hold.reason || "当前账号处于保护暂停状态，签到任务已暂缓。"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onOpenSafety
  }, "\u67E5\u770B\u8BE6\u60C5")) : failedError ? /*#__PURE__*/React.createElement("div", {
    className: "banner",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, failedError)) : pendingSettlement ? /*#__PURE__*/React.createElement("div", {
    className: "notice neutral daily-notice",
    role: "status"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "info",
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, "\u4ECA\u65E5\u4EFB\u52A1\u5DF2\u63D0\u4EA4\uFF0CB \u7AD9\u7ECF\u9A8C\u5230\u8D26\u5B58\u5728\u51E0\u79D2\u5EF6\u8FDF\uFF0C\u7A0D\u540E\u53EF\u70B9\u51FB\u5237\u65B0\u786E\u8BA4\u3002")) : null, /*#__PURE__*/React.createElement("section", {
    className: "card daily-hero"
  }, /*#__PURE__*/React.createElement("div", {
    className: "daily-hero-left"
  }, /*#__PURE__*/React.createElement("div", {
    className: "daily-identity"
  }, /*#__PURE__*/React.createElement("strong", null, user.name || account?.name || (signedIn ? "已登录账号" : "未登录")), level !== null && /*#__PURE__*/React.createElement("span", {
    className: "daily-badge accent"
  }, "Lv.", level), user.vip_label && /*#__PURE__*/React.createElement("span", {
    className: "daily-badge"
  }, user.vip_label), coinsBalance !== null && /*#__PURE__*/React.createElement("span", {
    className: "daily-badge tnum"
  }, "\u786C\u5E01 ", coinsBalance)), /*#__PURE__*/React.createElement("div", {
    className: "daily-level-wrap"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bar level-bar",
    role: "progressbar",
    "aria-label": "B \u7AD9\u8D26\u53F7\u5347\u7EA7\u8FDB\u5EA6",
    "aria-valuenow": currentExp || 0,
    "aria-valuemin": 0,
    "aria-valuemax": maxLevel ? Math.max(1, currentExp || 1) : nextExp || 1
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: `${levelPercent}%`
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "daily-level-meta"
  }, /*#__PURE__*/React.createElement("span", {
    className: "tnum"
  }, level === null ? "点击刷新获取等级与经验" : maxLevel ? `累计经验 ${numberLabel(currentExp)} · 已满级` : `经验 ${numberLabel(currentExp)} / ${numberLabel(nextExp)}`), !maxLevel && daysLeft !== null && /*#__PURE__*/React.createElement("span", {
    className: "daily-hint"
  }, daysLeft === 0 ? "今日完成任务即可升级" : `按当前设置约 ${daysLeft} 天升至 Lv.${level + 1}`)))), /*#__PURE__*/React.createElement("div", {
    className: "daily-hero-right"
  }, /*#__PURE__*/React.createElement("div", {
    className: "daily-kpi"
  }, /*#__PURE__*/React.createElement("span", {
    className: "daily-kpi-label"
  }, "\u4ECA\u65E5\u7ECF\u9A8C"), /*#__PURE__*/React.createElement("strong", {
    className: "daily-kpi-val tnum"
  }, earnedExp, /*#__PURE__*/React.createElement("small", null, " / 65")), /*#__PURE__*/React.createElement("span", {
    className: "daily-kpi-time"
  }, validDaily.updated ? `更新于 ${relativeTime(validDaily.updated)}` : "尚未获取今日进度")), /*#__PURE__*/React.createElement("div", {
    className: "daily-actions"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    disabled: !signedIn || working,
    onClick: onRefresh
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13,
    className: working ? "spin" : ""
  }), "\u5237\u65B0\u8FDB\u5EA6"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    disabled: !canExecute,
    onClick: () => onRun(null)
  }, /*#__PURE__*/React.createElement(Icon, {
    name: working ? "refresh" : "sparkles",
    size: 13,
    className: working ? "spin" : ""
  }), working ? "签到中…" : "立即签到")))), /*#__PURE__*/React.createElement("section", {
    className: "daily-grid",
    "aria-label": "\u6BCF\u65E5\u7ECF\u9A8C\u4EFB\u52A1"
  }, tasks.map(task => {
    const err = taskResults[task.key]?.success === false ? taskResults[task.key]?.error : "";
    return /*#__PURE__*/React.createElement("div", {
      className: `card daily-task ${task.done ? "done" : ""}`,
      key: task.key
    }, /*#__PURE__*/React.createElement("div", {
      className: "daily-task-top"
    }, /*#__PURE__*/React.createElement("span", {
      className: `daily-task-icon ${task.done ? "done" : ""}`,
      "aria-hidden": "true"
    }, /*#__PURE__*/React.createElement(Icon, {
      name: task.icon,
      size: 16
    })), /*#__PURE__*/React.createElement("div", {
      className: "daily-task-info"
    }, /*#__PURE__*/React.createElement("div", {
      className: "daily-task-name"
    }, task.name), /*#__PURE__*/React.createElement("div", {
      className: "daily-task-gain tnum"
    }, task.gain)), /*#__PURE__*/React.createElement("span", {
      className: `pill ${task.done ? "live" : task.partial ? "" : "muted"}`
    }, task.statusText)), (task.sub || err || task.actionLabel) && /*#__PURE__*/React.createElement("div", {
      className: "daily-task-foot"
    }, /*#__PURE__*/React.createElement("span", {
      className: `daily-task-sub ${err ? "warn" : ""}`,
      title: err || task.sub || ""
    }, err || task.sub || ""), task.key === "coin" && onOpenSettings && !task.actionLabel && /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "link-btn",
      onClick: onOpenSettings
    }, "\u6295\u5E01\u8BBE\u7F6E"), task.actionLabel && /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn sm",
      disabled: !canExecute,
      onClick: () => onRun(task.key)
    }, task.actionLabel)));
  }))));
}
Object.assign(window, {
  DailyPage
});
})();
