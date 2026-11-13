/* BiliOshi JSX {"code_sha256":"05e0dab82c7ad645d7e355ccd6584bb989362637039877cdf695cbc2a5afd7d1","compiler_sha256":"2623a9e22809915ce789b4461154e277ddce520d5a4320c14d44332a5d0dcea0","pipeline_sha256":"38ef510e7adae30e369b652f15eb1f93f974ca68daef2928f8b826127cbf0bc2","schema":1,"source":"dialogs.jsx","source_sha256":"eaba7bf5b6916166f8f91945668ae09ecbfd6dd791c2aabcbaeace46971030a6"} */
(function () {
"use strict";
/* Dialogs keep focus inside the active view and restore it on close. */

const {
  Icon
} = window;
const {
  useEffect,
  useRef
} = React;
function Modal({
  title,
  desc,
  children,
  actions,
  onClose,
  wide
}) {
  const element = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const node = element.current;
    const items = () => [...node.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex="0"]')];
    (node.querySelector("[autofocus]") || items()[0] || node).focus();
    const keydown = event => {
      if (event.key === "Escape") {
        event.preventDefault();
        close.current();
      }
      if (event.key !== "Tab") return;
      const controls = items();
      if (!controls.length) {
        event.preventDefault();
        return;
      }
      const first = controls[0],
        last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    };
    node.addEventListener("keydown", keydown);
    return () => {
      node.removeEventListener("keydown", keydown);
      previous?.focus?.();
    };
  }, []);
  return /*#__PURE__*/React.createElement("div", {
    className: "scrim",
    onMouseDown: event => event.target === event.currentTarget && onClose()
  }, /*#__PURE__*/React.createElement("section", {
    className: `modal ${wide ? "wide" : ""}`,
    role: "dialog",
    "aria-modal": "true",
    "aria-label": title,
    ref: element,
    tabIndex: -1
  }, /*#__PURE__*/React.createElement("h3", null, title), desc && /*#__PURE__*/React.createElement("p", null, desc), children, actions && /*#__PURE__*/React.createElement("div", {
    className: "modal-actions"
  }, actions)));
}
const QrModal = ({
  qr,
  onClose,
  onRetry
}) => {
  const messages = {
    starting: "正在生成二维码…",
    waiting: "等待扫码",
    scanned: "已扫码，在手机上确认登录",
    confirmed: "登录已确认",
    expired: "二维码已过期，刷新后重新扫描",
    error: qr.message || "无法连接登录服务，稍后重试"
  };
  const relogin = Boolean(qr.account_id);
  return /*#__PURE__*/React.createElement(Modal, {
    title: qr.state === "confirmed" ? "已登录" : relogin ? "重新登录" : "扫码登录 B 站",
    desc: qr.state === "confirmed" ? qr.account : relogin ? "重新扫码仅更新当前账号凭证，不影响其他账号。" : "请使用哔哩哔哩客户端扫码",
    onClose: onClose,
    actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn",
      onClick: onClose
    }, qr.state === "confirmed" ? "完成" : "取消"), qr.state !== "confirmed" && /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "btn primary",
      onClick: onRetry,
      disabled: qr.state === "starting"
    }, "\u5237\u65B0\u4E8C\u7EF4\u7801"))
  }, /*#__PURE__*/React.createElement("div", {
    className: `qr-wrap ${qr.state === "expired" ? "expired" : ""}`
  }, qr.data_uri ? /*#__PURE__*/React.createElement("img", {
    src: qr.data_uri,
    alt: "B \u7AD9\u767B\u5F55\u4E8C\u7EF4\u7801"
  }) : /*#__PURE__*/React.createElement("span", {
    className: "qr-placeholder"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: qr.state === "error" ? "alert" : "refresh",
    size: 24,
    className: qr.state === "starting" ? "spin" : ""
  }))), /*#__PURE__*/React.createElement("div", {
    className: "qr-hint",
    role: "status"
  }, messages[qr.state]));
};
const AddMemberModal = ({
  query,
  onQuery,
  result,
  loading,
  adding,
  onSearch,
  onAdd,
  onClose,
  onSyncMedals
}) => /*#__PURE__*/React.createElement(Modal, {
  title: "\u6DFB\u52A0\u4E3B\u64AD",
  desc: "\u901A\u8FC7\u76F4\u64AD\u95F4\u53F7\u3001UID \u6216\u76F4\u64AD\u95F4\u94FE\u63A5\u67E5\u627E",
  onClose: onClose,
  actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onClose
  }, "\u53D6\u6D88"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: onAdd,
    disabled: !result?.ok || loading || adding
  }, adding ? "正在添加…" : "添加主播"))
}, /*#__PURE__*/React.createElement("form", {
  className: "field-row",
  onSubmit: event => {
    event.preventDefault();
    if (!loading && query.trim()) onSearch();
  }
}, /*#__PURE__*/React.createElement("input", {
  className: "input",
  value: query,
  onChange: event => onQuery(event.target.value),
  "aria-label": "\u76F4\u64AD\u95F4\u53F7\u3001UID \u6216\u94FE\u63A5",
  placeholder: "\u76F4\u64AD\u95F4\u53F7\u3001UID \u6216\u94FE\u63A5",
  autoFocus: true,
  disabled: adding
}), /*#__PURE__*/React.createElement("button", {
  type: "submit",
  className: "btn",
  disabled: loading || adding || !query.trim()
}, loading ? "查找中…" : "查找")), result?.ok && /*#__PURE__*/React.createElement("div", {
  className: "member-preview"
}, /*#__PURE__*/React.createElement("span", {
  className: "account-avatar"
}, Array.from(result.member.name || "?")[0]), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("div", {
  className: "account-name"
}, result.member.name), /*#__PURE__*/React.createElement("div", {
  className: "account-meta"
}, "\u76F4\u64AD\u95F4 ", result.member.room, " \xB7 UID ", result.member.uid))), result && !result.ok && /*#__PURE__*/React.createElement("div", {
  className: "field-error",
  role: "alert"
}, result.error), onSyncMedals && /*#__PURE__*/React.createElement("div", {
  className: "field-note",
  style: {
    marginTop: "12px",
    textAlign: "center"
  }
}, /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "link-btn",
  onClick: () => {
    onClose();
    onSyncMedals();
  }
}, "\u4ECE\u5DF2\u6709\u7C89\u4E1D\u724C\u6279\u91CF\u540C\u6B65 \u2192")));
const MedalsModal = ({
  data,
  selected,
  onToggle,
  onImport,
  onClose,
  loading,
  importing,
  error,
  onRetry
}) => /*#__PURE__*/React.createElement(Modal, {
  title: "\u540C\u6B65\u7C89\u4E1D\u724C",
  desc: "\u9009\u62E9\u8981\u5173\u6CE8\u7684\u4E3B\u64AD\uFF08\u5DF2\u5173\u6CE8\u7684\u81EA\u52A8\u8DF3\u8FC7\uFF09",
  wide: true,
  onClose: onClose,
  actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onClose
  }, "\u53D6\u6D88"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: onImport,
    disabled: loading || importing || selected.size === 0 || Boolean(error)
  }, importing ? "正在导入…" : selected.size ? `导入 ${selected.size} 位主播` : "导入主播"))
}, /*#__PURE__*/React.createElement("div", {
  className: "medal-list"
}, loading ? /*#__PURE__*/React.createElement("div", {
  className: "field-note"
}, "\u6B63\u5728\u8BFB\u53D6\u7C89\u4E1D\u724C\u2026") : error ? /*#__PURE__*/React.createElement("div", {
  className: "field-note"
}, /*#__PURE__*/React.createElement("p", null, error), /*#__PURE__*/React.createElement("button", {
  type: "button",
  className: "btn sm",
  onClick: onRetry
}, "\u91CD\u8BD5")) : !data.length ? /*#__PURE__*/React.createElement("div", {
  className: "field-note"
}, "\u6682\u65E0\u53EF\u540C\u6B65\u7684\u7C89\u4E1D\u724C") : data.map(medal => /*#__PURE__*/React.createElement("label", {
  key: medal.uid,
  className: `medal-row ${medal.watched ? "watched" : ""}`
}, /*#__PURE__*/React.createElement("input", {
  type: "checkbox",
  checked: selected.has(medal.uid),
  disabled: medal.watched || importing,
  onChange: () => onToggle(medal.uid)
}), /*#__PURE__*/React.createElement("span", {
  className: "account-avatar small"
}, Array.from(medal.name || medal.medal_name || "?")[0]), /*#__PURE__*/React.createElement("span", {
  className: "medal-main"
}, /*#__PURE__*/React.createElement("span", {
  className: "account-name"
}, medal.name || medal.medal_name), /*#__PURE__*/React.createElement("span", {
  className: "account-meta"
}, medal.medal_name, " Lv.", medal.level, medal.watched ? " · 已关注" : ""))))));
const ConfirmModal = ({
  title,
  desc,
  confirmLabel,
  danger,
  onConfirm,
  onClose,
  busy,
  body
}) => /*#__PURE__*/React.createElement(Modal, {
  title: title,
  desc: desc,
  onClose: onClose,
  actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onClose,
    disabled: busy
  }, "\u53D6\u6D88"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: `btn ${danger ? "danger" : "primary"}`,
    onClick: onConfirm,
    disabled: busy
  }, busy ? "正在处理…" : confirmLabel))
}, body);
const RoomMenu = ({
  menu,
  room,
  onClose,
  onOpen,
  onAction,
  onRemove
}) => {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const node = ref.current;
    const items = () => Array.from(node?.querySelectorAll('[role="menuitem"]:not([disabled])') || []);
    const focusTimer = window.setTimeout(() => {
      (items()[0] || node)?.focus();
    }, 0);
    const close = event => {
      if (!node?.contains(event.target)) closeRef.current();
    };
    const key = event => {
      if (event.key === "Escape") {
        event.preventDefault();
        closeRef.current();
        previous?.focus?.();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      const enabled = items();
      if (!enabled.length) return;
      event.preventDefault();
      const idx = enabled.indexOf(document.activeElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? enabled.length - 1 : idx < 0 ? event.key === "ArrowUp" ? enabled.length - 1 : 0 : (idx + (event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length;
      enabled[next]?.focus();
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", key);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", key);
    };
  }, []);
  if (!room) return null;
  const invoke = fn => {
    onClose();
    fn();
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "room-menu",
    role: "menu",
    "aria-label": "\u76F4\u64AD\u95F4\u64CD\u4F5C",
    ref: ref,
    tabIndex: -1,
    style: {
      left: Math.max(8, Math.min(menu.x, window.innerWidth - 198)),
      top: Math.max(8, Math.min(menu.y, window.innerHeight - 210))
    }
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    onClick: () => invoke(() => onOpen(room.room))
  }, "\u6253\u5F00\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    disabled: Boolean(room.actions.reconnect) || room.operation.pending,
    title: room.actions.reconnect,
    onClick: () => invoke(() => onAction("reconnect", room.room))
  }, "\u91CD\u65B0\u8FDE\u63A5"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    disabled: Boolean(room.actions.redo) || room.operation.pending,
    title: room.actions.redo,
    onClick: () => invoke(() => onAction("redo", room.room))
  }, "\u8865\u9F50\u4ECA\u65E5\u4EFB\u52A1"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    disabled: Boolean(room.actions.wear) || room.operation.pending,
    title: room.actions.wear,
    onClick: () => invoke(() => onAction("wear", room.room))
  }, "\u4F69\u6234\u7C89\u4E1D\u724C"), /*#__PURE__*/React.createElement("div", {
    className: "menu-divider"
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    className: "destructive-text",
    onClick: () => invoke(() => onRemove(room))
  }, "\u79FB\u9664\u4E3B\u64AD"));
};
const DiagnosticModal = ({
  preview,
  loading,
  anonymize,
  includeState,
  onChangeAnonymize,
  onChangeIncludeState,
  exporting,
  exported,
  statusText,
  onExport,
  onCopySummary,
  onOpenExports,
  onClose
}) => {
  const dialogRef = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return undefined;
    if (!dialog.open) dialog.showModal();
    const handleClose = () => {
      dialog.returnValue = "";
      closeRef.current();
    };
    dialog.addEventListener("close", handleClose);

    // Fallback for engines without <dialog closedby="any"> light-dismiss support.
    let cleanupOutside = null;
    if (!("closedBy" in HTMLDialogElement.prototype)) {
      const outside = e => {
        const r = dialog.getBoundingClientRect();
        return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      };
      let pressedOutside = false;
      const onDown = e => {
        pressedOutside = outside(e);
      };
      const onUp = e => {
        if (pressedOutside && outside(e)) dialog.close();
      };
      dialog.addEventListener("pointerdown", onDown);
      dialog.addEventListener("pointerup", onUp);
      cleanupOutside = () => {
        dialog.removeEventListener("pointerdown", onDown);
        dialog.removeEventListener("pointerup", onUp);
      };
    }
    return () => {
      dialog.removeEventListener("close", handleClose);
      cleanupOutside?.();
      if (dialog.open) dialog.close();
    };
  }, []);
  const errors = exported?.recent_errors || preview?.recent_errors || [];
  const env = preview?.environment || {};
  const errCount = preview?.recent_error_count ?? errors.length;
  const sizeKb = exported?.size_bytes ? `${Math.max(1, Math.round(exported.size_bytes / 1024))} KB` : "";
  return /*#__PURE__*/React.createElement("dialog", {
    ref: dialogRef,
    className: "modal wide diag-dialog",
    closedby: "any",
    "aria-labelledby": "diag-dialog-title"
  }, /*#__PURE__*/React.createElement("div", {
    className: "diag-head"
  }, /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h3", {
    id: "diag-dialog-title"
  }, "\u5BFC\u51FA\u8131\u654F\u8BCA\u65AD\u5305"), /*#__PURE__*/React.createElement("p", {
    className: "diag-sub"
  }, "\u6C47\u603B\u8FD0\u884C\u65E5\u5FD7\u4E0E\u73AF\u5883\u4FE1\u606F\u7528\u4E8E\u95EE\u9898\u6392\u67E5\u3002\u5DF2\u4E25\u683C\u5254\u9664\u767B\u5F55\u51ED\u8BC1\u3001Cookie\u3001Token \u4E0E\u672C\u673A\u7528\u6237\u540D\u8DEF\u5F84\u3002")), env.app_version && /*#__PURE__*/React.createElement("span", {
    className: "version-pill"
  }, "v", env.app_version)), /*#__PURE__*/React.createElement("div", {
    className: "diag-summary-bar"
  }, loading ? /*#__PURE__*/React.createElement("span", null, "\u6B63\u5728\u626B\u63CF\u6700\u8FD1\u65E5\u5FD7\u2026") : errCount > 0 ? /*#__PURE__*/React.createElement("span", {
    className: "diag-warn"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "alert",
    size: 13
  }), "\u8FD1\u671F\u53D1\u73B0 ", errCount, " \u6761\u544A\u8B66\u6216\u9519\u8BEF\u8BB0\u5F55") : /*#__PURE__*/React.createElement("span", {
    className: "diag-ok"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 13
  }), "\u8FD1\u671F\u9519\u8BEF\u65E5\u5FD7\u65E0\u5F02\u5E38\u8BB0\u5F55"), env.account_count > 0 && /*#__PURE__*/React.createElement("span", {
    className: "diag-meta"
  }, env.account_count, " \u4E2A\u8D26\u53F7 \xB7 ", env.multi_account_mode)), errors.length > 0 && /*#__PURE__*/React.createElement("details", {
    className: "diag-details",
    open: errCount > 0
  }, /*#__PURE__*/React.createElement("summary", null, "\u6700\u8FD1\u9519\u8BEF\u8282\u9009\uFF08\u5DF2\u8131\u654F\uFF0C\u5C55\u793A\u6700\u65B0 ", Math.min(errors.length, 20), " \u6761\uFF09"), /*#__PURE__*/React.createElement("pre", {
    className: "diag-preview"
  }, errors.slice(-12).join("\n"))), /*#__PURE__*/React.createElement("form", {
    className: "diag-form",
    onSubmit: event => {
      event.preventDefault();
      onExport();
    }
  }, /*#__PURE__*/React.createElement("fieldset", {
    className: "diag-fieldset"
  }, /*#__PURE__*/React.createElement("legend", null, "\u8131\u654F\u4E0E\u5305\u542B\u5185\u5BB9"), /*#__PURE__*/React.createElement("label", {
    className: "diag-check",
    htmlFor: "diag-anonymize"
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    id: "diag-anonymize",
    name: "anonymize",
    autoFocus: true,
    checked: anonymize,
    disabled: exporting,
    onChange: e => onChangeAnonymize(e.target.checked)
  }), /*#__PURE__*/React.createElement("span", null, "\u9690\u85CF UID\u3001\u8D26\u53F7\u540D\u3001\u4E3B\u64AD\u540D\u4E0E\u623F\u95F4\u53F7\uFF08\u516C\u5F00\u53CD\u9988\u63A8\u8350\u5F00\u542F\uFF09")), /*#__PURE__*/React.createElement("label", {
    className: "diag-check",
    htmlFor: "diag-include-state"
  }, /*#__PURE__*/React.createElement("input", {
    type: "checkbox",
    id: "diag-include-state",
    name: "include_state",
    checked: includeState,
    disabled: exporting,
    onChange: e => onChangeIncludeState(e.target.checked)
  }), /*#__PURE__*/React.createElement("span", null, "\u5305\u542B\u975E\u654F\u611F\u8FD0\u884C\u8BBE\u7F6E\u3001\u623F\u95F4\u72B6\u6001\u4E0E\u6700\u8FD1\u6D3B\u52A8\u8BB0\u5F55\u5C3E\u90E8"))), /*#__PURE__*/React.createElement("div", {
    className: "diag-status-region",
    role: "status",
    "aria-live": "polite"
  }, exported?.ok && /*#__PURE__*/React.createElement("div", {
    className: "diag-result"
  }, /*#__PURE__*/React.createElement("div", {
    className: "diag-result-main"
  }, /*#__PURE__*/React.createElement("strong", null, /*#__PURE__*/React.createElement(Icon, {
    name: "check",
    size: 13
  }), "\u5DF2\u5BFC\u51FA\uFF1A", exported.filename, "\uFF08", sizeKb, "\uFF09"), /*#__PURE__*/React.createElement("span", {
    className: "diag-path",
    title: exported.zip_path
  }, exported.zip_path)), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: onOpenExports
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "folder",
    size: 13
  }), "\u6253\u5F00\u6240\u5728\u6587\u4EF6\u5939")), !exported?.ok && statusText && /*#__PURE__*/React.createElement("div", {
    className: "diag-feedback"
  }, statusText), exported?.ok && statusText && /*#__PURE__*/React.createElement("div", {
    className: "diag-feedback ok"
  }, statusText)), /*#__PURE__*/React.createElement("div", {
    className: "modal-actions"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: () => dialogRef.current?.close(),
    disabled: exporting
  }, "\u5173\u95ED"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onCopySummary,
    disabled: loading || !exported?.summary_markdown && !preview?.summary_markdown
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "copy",
    size: 13
  }), "\u590D\u5236\u6458\u8981"), /*#__PURE__*/React.createElement("button", {
    type: "submit",
    className: "btn primary",
    disabled: exporting
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "download",
    size: 13
  }), exporting ? "正在打包…" : exported ? "重新导出 (.zip)" : "导出诊断包 (.zip)"))));
};
const SafetyModal = ({
  hold,
  account,
  isActive = true,
  probeState,
  busy,
  onCheck,
  onResume,
  onOpenLink,
  onScan,
  onClose
}) => {
  const dialogRef = useModalDialog(onClose);
  const info = hold || {};
  const nowSec = Math.floor(Date.now() / 1000);
  const cooldown = Boolean(info.blocked && info.until && info.until > nowSec);
  const needsLogin = info.kind === "auth" || info.kind === "credentials";
  const lastProbe = probeState?.result || info.last_probe || null;
  const checking = Boolean(probeState?.loading);
  const checks = Array.isArray(lastProbe?.checks) ? lastProbe.checks : [];
  const steps = Array.isArray(info.steps) ? info.steps : [];
  const roomId = info.operation?.room || "";
  const locationParts = [info.room_label, info.operation_label].filter(Boolean);
  return /*#__PURE__*/React.createElement("dialog", {
    ref: dialogRef,
    className: "modal wide safety-dialog",
    closedby: "any",
    "aria-labelledby": "safety-dialog-title"
  }, /*#__PURE__*/React.createElement("div", {
    className: "safety-modal-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "safety-modal-title"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "shield",
    size: 16
  }), /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement("h3", {
    id: "safety-dialog-title"
  }, info.kind_label || "账号保护暂停"), /*#__PURE__*/React.createElement("p", {
    className: "safety-modal-sub"
  }, account?.name ? `${account.name} · ` : "", info.since ? `触发于 ${absoluteTime(info.since)}` : "已暂停互动操作以保护账号"))), info.code !== undefined && info.code !== null && /*#__PURE__*/React.createElement("span", {
    className: "version-pill"
  }, "\u9519\u8BEF\u7801 ", info.code)), /*#__PURE__*/React.createElement("div", {
    className: "safety-reason-box"
  }, /*#__PURE__*/React.createElement("strong", null, info.reason || "检测到平台安全验证或操作受限，已暂停自动化操作。"), info.raw_message && info.raw_message !== info.reason && /*#__PURE__*/React.createElement("div", {
    className: "safety-raw-msg"
  }, "\u5E73\u53F0\u8FD4\u56DE\uFF1A", info.raw_message)), /*#__PURE__*/React.createElement("div", {
    className: "safety-meta-grid"
  }, locationParts.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "safety-meta-item"
  }, /*#__PURE__*/React.createElement("span", null, "\u89E6\u53D1\u4F4D\u7F6E"), /*#__PURE__*/React.createElement("strong", null, locationParts.join(" · "))), cooldown && /*#__PURE__*/React.createElement("div", {
    className: "safety-meta-item"
  }, /*#__PURE__*/React.createElement("span", null, "\u81EA\u52A8\u6062\u590D\u65F6\u95F4"), /*#__PURE__*/React.createElement("strong", null, absoluteTime(info.until))), !cooldown && info.next_probe_at && /*#__PURE__*/React.createElement("div", {
    className: "safety-meta-item"
  }, /*#__PURE__*/React.createElement("span", null, "\u4E0B\u6B21\u81EA\u52A8\u590D\u68C0"), /*#__PURE__*/React.createElement("strong", null, absoluteTime(info.next_probe_at), typeof info.auto_recover_remaining === "number" && `（今日自动恢复剩余 ${info.auto_recover_remaining} 次）`)), !cooldown && !info.next_probe_at && (info.kind === "uncertain" || info.kind === "review") && /*#__PURE__*/React.createElement("div", {
    className: "safety-meta-item"
  }, /*#__PURE__*/React.createElement("span", null, "\u81EA\u52A8\u590D\u68C0\u72B6\u6001"), /*#__PURE__*/React.createElement("strong", null, "\u5DF2\u8FBE\u672C\u8F6E\u81EA\u52A8\u590D\u68C0\u6216\u4ECA\u65E5\u6062\u590D\u4E0A\u9650\uFF0C\u8BF7\u4EBA\u5DE5\u786E\u8BA4\u540E\u6062\u590D"))), steps.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "safety-steps"
  }, /*#__PURE__*/React.createElement("div", {
    className: "safety-section-label"
  }, "\u6392\u67E5\u4E0E\u5904\u7406\u6B65\u9AA4"), /*#__PURE__*/React.createElement("ol", null, steps.map((step, index) => /*#__PURE__*/React.createElement("li", {
    key: index
  }, step)))), lastProbe && /*#__PURE__*/React.createElement("div", {
    className: `safety-probe-box ${lastProbe.passed ? "ok" : "fail"}`,
    role: "status",
    "aria-live": "polite"
  }, /*#__PURE__*/React.createElement("div", {
    className: "safety-probe-summary"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: lastProbe.passed ? "check" : "alert",
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, lastProbe.summary || (lastProbe.passed ? "只读自检通过" : "只读自检未通过")), lastProbe.at && /*#__PURE__*/React.createElement("small", null, absoluteTime(lastProbe.at))), checks.length > 0 && /*#__PURE__*/React.createElement("ul", {
    className: "safety-probe-checks"
  }, checks.map((item, idx) => /*#__PURE__*/React.createElement("li", {
    key: idx,
    className: item.ok ? "ok" : "fail"
  }, /*#__PURE__*/React.createElement(Icon, {
    name: item.ok ? "check" : "alert",
    size: 12
  }), /*#__PURE__*/React.createElement("strong", null, item.name), /*#__PURE__*/React.createElement("span", null, item.detail))))), /*#__PURE__*/React.createElement("div", {
    className: "safety-links-row"
  }, roomId && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onOpenLink("live", roomId),
    disabled: busy || checking
  }, "\u6253\u5F00\u5BF9\u5E94\u76F4\u64AD\u95F4"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onOpenLink("live", null),
    disabled: busy || checking
  }, "\u6253\u5F00 B \u7AD9\u76F4\u64AD\u9996\u9875"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn sm",
    onClick: () => onOpenLink("security", null),
    disabled: busy || checking
  }, "\u8D26\u53F7\u5B89\u5168\u4E2D\u5FC3")), /*#__PURE__*/React.createElement("div", {
    className: "modal-actions"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: () => dialogRef.current?.close(),
    disabled: busy || checking
  }, "\u5173\u95ED"), isActive && needsLogin && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: () => {
      dialogRef.current?.close();
      onScan(account?.id || "");
    },
    disabled: busy
  }, "\u91CD\u65B0\u626B\u7801\u767B\u5F55"), isActive && !needsLogin && !cooldown && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn",
    onClick: onResume,
    disabled: busy || checking
  }, busy ? "处理中…" : "确认已处理并恢复"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: () => onCheck(true),
    disabled: busy || checking
  }, /*#__PURE__*/React.createElement(Icon, {
    name: "refresh",
    size: 13
  }), checking ? "检测中…" : "检测并自动恢复")), !isActive && /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "btn primary",
    onClick: () => dialogRef.current?.close()
  }, "\u77E5\u9053\u4E86")));
};
Object.assign(window, {
  Modal,
  QrModal,
  AddMemberModal,
  MedalsModal,
  ConfirmModal,
  RoomMenu,
  DiagnosticModal,
  SafetyModal
});
})();
