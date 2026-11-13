/* Dialogs keep focus inside the active view and restore it on close. */

const { Icon } = window;
const { useEffect, useRef } = React;

function Modal({ title, desc, children, actions, onClose, wide }) {
  const element = useRef(null);
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const node = element.current;
    const items = () => [...node.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex="0"]')];
    (node.querySelector("[autofocus]") || items()[0] || node).focus();
    const keydown = (event) => {
      if (event.key === "Escape") { event.preventDefault(); close.current(); }
      if (event.key !== "Tab") return;
      const controls = items();
      if (!controls.length) { event.preventDefault(); return; }
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && (document.activeElement === first || !node.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !node.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    };
    node.addEventListener("keydown", keydown);
    return () => { node.removeEventListener("keydown", keydown); previous?.focus?.(); };
  }, []);
  return (
    <div className="scrim" onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section className={`modal ${wide ? "wide" : ""}`} role="dialog" aria-modal="true"
        aria-label={title} ref={element} tabIndex={-1}>
        <h3>{title}</h3>{desc && <p>{desc}</p>}{children}
        {actions && <div className="modal-actions">{actions}</div>}
      </section>
    </div>
  );
}

const QrModal = ({ qr, onClose, onRetry }) => {
  const messages = {
    starting: "正在生成二维码…", waiting: "等待扫码", scanned: "已扫码，在手机上确认登录",
    confirmed: "登录已确认", expired: "二维码已过期，刷新后重新扫描", error: qr.message || "无法连接登录服务，稍后重试"
  };
  const relogin = Boolean(qr.account_id);
  return (
    <Modal title={qr.state === "confirmed" ? "已登录" : relogin ? "重新登录" : "扫码登录 B 站"}
      desc={qr.state === "confirmed" ? qr.account
        : relogin ? "重新扫码仅更新当前账号凭证，不影响其他账号。"
          : "请使用哔哩哔哩客户端扫码"} onClose={onClose}
      actions={<>
        <button type="button" className="btn" onClick={onClose}>{qr.state === "confirmed" ? "完成" : "取消"}</button>
        {qr.state !== "confirmed" && <button type="button" className="btn primary" onClick={onRetry} disabled={qr.state === "starting"}>
          刷新二维码</button>}
      </>}>
      <div className={`qr-wrap ${qr.state === "expired" ? "expired" : ""}`}>
        {qr.data_uri ? <img src={qr.data_uri} alt="B 站登录二维码" />
          : <span className="qr-placeholder"><Icon name={qr.state === "error" ? "alert" : "refresh"} size={24}
            className={qr.state === "starting" ? "spin" : ""} /></span>}
      </div>
      <div className="qr-hint" role="status">{messages[qr.state]}</div>
    </Modal>
  );
};

const AddMemberModal = ({ query, onQuery, result, loading, adding, onSearch, onAdd, onClose, onSyncMedals }) => (
  <Modal title="添加主播" desc="通过直播间号、UID 或直播间链接查找" onClose={onClose}
    actions={<>
      <button type="button" className="btn" onClick={onClose}>取消</button>
      <button type="button" className="btn primary" onClick={onAdd} disabled={!result?.ok || loading || adding}>
        {adding ? "正在添加…" : "添加主播"}</button>
    </>}>
    <form className="field-row" onSubmit={(event) => { event.preventDefault(); if (!loading && query.trim()) onSearch(); }}>
      <input className="input" value={query} onChange={(event) => onQuery(event.target.value)}
        aria-label="直播间号、UID 或链接" placeholder="直播间号、UID 或链接" autoFocus disabled={adding} />
      <button type="submit" className="btn" disabled={loading || adding || !query.trim()}>{loading ? "查找中…" : "查找"}</button>
    </form>
    {result?.ok && <div className="member-preview"><span className="account-avatar">{Array.from(result.member.name || "?")[0]}</span>
      <div><div className="account-name">{result.member.name}</div>
        <div className="account-meta">直播间 {result.member.room} · UID {result.member.uid}</div></div></div>}
    {result && !result.ok && <div className="field-error" role="alert">{result.error}</div>}
    {onSyncMedals && <div className="field-note" style={{ marginTop: "12px", textAlign: "center" }}>
      <button type="button" className="link-btn" onClick={() => { onClose(); onSyncMedals(); }}>
        从已有粉丝牌批量同步 →
      </button>
    </div>}
  </Modal>
);

const MedalsModal = ({ data, selected, onToggle, onImport, onClose, loading, importing, error, onRetry }) => (
  <Modal title="同步粉丝牌" desc="选择要关注的主播（已关注的自动跳过）" wide onClose={onClose}
    actions={<>
      <button type="button" className="btn" onClick={onClose}>取消</button>
      <button type="button" className="btn primary" onClick={onImport} disabled={loading || importing || selected.size === 0 || Boolean(error)}>
        {importing ? "正在导入…" : selected.size ? `导入 ${selected.size} 位主播` : "导入主播"}</button>
    </>}>
    <div className="medal-list">
      {loading ? <div className="field-note">正在读取粉丝牌…</div>
        : error ? <div className="field-note"><p>{error}</p><button type="button" className="btn sm" onClick={onRetry}>重试</button></div>
        : !data.length ? <div className="field-note">暂无可同步的粉丝牌</div>
        : data.map((medal) => <label key={medal.uid} className={`medal-row ${medal.watched ? "watched" : ""}`}>
          <input type="checkbox" checked={selected.has(medal.uid)} disabled={medal.watched || importing}
            onChange={() => onToggle(medal.uid)} />
          <span className="account-avatar small">{Array.from(medal.name || medal.medal_name || "?")[0]}</span>
          <span className="medal-main"><span className="account-name">{medal.name || medal.medal_name}</span>
            <span className="account-meta">{medal.medal_name} Lv.{medal.level}{medal.watched ? " · 已关注" : ""}</span></span>
        </label>)}
    </div>
  </Modal>
);

const ConfirmModal = ({ title, desc, confirmLabel, danger, onConfirm, onClose, busy, body }) => (
  <Modal title={title} desc={desc} onClose={onClose} actions={<>
    <button type="button" className="btn" onClick={onClose} disabled={busy}>取消</button>
    <button type="button" className={`btn ${danger ? "danger" : "primary"}`} onClick={onConfirm} disabled={busy}>
      {busy ? "正在处理…" : confirmLabel}</button>
  </>}>
    {body}
  </Modal>
);

const RoomMenu = ({ menu, room, onClose, onOpen, onAction, onRemove }) => {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    const previous = document.activeElement;
    const node = ref.current;
    const items = () => Array.from(node?.querySelectorAll('[role="menuitem"]:not([disabled])') || []);
    const focusTimer = window.setTimeout(() => { (items()[0] || node)?.focus(); }, 0);
    const close = (event) => { if (!node?.contains(event.target)) closeRef.current(); };
    const key = (event) => {
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
      const next = event.key === "Home" ? 0
        : event.key === "End" ? enabled.length - 1
          : idx < 0 ? (event.key === "ArrowUp" ? enabled.length - 1 : 0)
            : (idx + (event.key === "ArrowDown" ? 1 : -1) + enabled.length) % enabled.length;
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
  const invoke = (fn) => { onClose(); fn(); };
  return <div className="room-menu" role="menu" aria-label="直播间操作" ref={ref} tabIndex={-1}
    style={{
      left: Math.max(8, Math.min(menu.x, window.innerWidth - 198)),
      top: Math.max(8, Math.min(menu.y, window.innerHeight - 210)),
    }}>
    <button type="button" role="menuitem" onClick={() => invoke(() => onOpen(room.room))}>打开直播间</button>
    <button type="button" role="menuitem" disabled={Boolean(room.actions.reconnect) || room.operation.pending}
      title={room.actions.reconnect} onClick={() => invoke(() => onAction("reconnect", room.room))}>重新连接</button>
    <button type="button" role="menuitem" disabled={Boolean(room.actions.redo) || room.operation.pending}
      title={room.actions.redo} onClick={() => invoke(() => onAction("redo", room.room))}>补齐今日任务</button>
    <button type="button" role="menuitem" disabled={Boolean(room.actions.wear) || room.operation.pending}
      title={room.actions.wear} onClick={() => invoke(() => onAction("wear", room.room))}>佩戴粉丝牌</button>
    <div className="menu-divider" />
    <button type="button" role="menuitem" className="destructive-text" onClick={() => invoke(() => onRemove(room))}>移除主播</button>
  </div>;
};

const DiagnosticModal = ({
  preview, loading, anonymize, includeState, onChangeAnonymize, onChangeIncludeState,
  exporting, exported, statusText, onExport, onCopySummary, onOpenExports, onClose
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
      const outside = (e) => {
        const r = dialog.getBoundingClientRect();
        return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
      };
      let pressedOutside = false;
      const onDown = (e) => { pressedOutside = outside(e); };
      const onUp = (e) => { if (pressedOutside && outside(e)) dialog.close(); };
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

  return (
    <dialog ref={dialogRef} className="modal wide diag-dialog" closedby="any" aria-labelledby="diag-dialog-title">
      <div className="diag-head">
        <div>
          <h3 id="diag-dialog-title">导出脱敏诊断包</h3>
          <p className="diag-sub">汇总运行日志与环境信息用于问题排查。已严格剔除登录凭证、Cookie、Token 与本机用户名路径。</p>
        </div>
        {env.app_version && <span className="version-pill">v{env.app_version}</span>}
      </div>

      <div className="diag-summary-bar">
        {loading ? (
          <span>正在扫描最近日志…</span>
        ) : errCount > 0 ? (
          <span className="diag-warn"><Icon name="alert" size={13} />近期发现 {errCount} 条告警或错误记录</span>
        ) : (
          <span className="diag-ok"><Icon name="check" size={13} />近期错误日志无异常记录</span>
        )}
        {env.account_count > 0 && <span className="diag-meta">{env.account_count} 个账号 · {env.multi_account_mode}</span>}
      </div>

      {errors.length > 0 && (
        <details className="diag-details" open={errCount > 0}>
          <summary>最近错误节选（已脱敏，展示最新 {Math.min(errors.length, 20)} 条）</summary>
          <pre className="diag-preview">{errors.slice(-12).join("\n")}</pre>
        </details>
      )}

      <form className="diag-form" onSubmit={(event) => { event.preventDefault(); onExport(); }}>
        <fieldset className="diag-fieldset">
          <legend>脱敏与包含内容</legend>
          <label className="diag-check" htmlFor="diag-anonymize">
            <input type="checkbox" id="diag-anonymize" name="anonymize" autoFocus
              checked={anonymize} disabled={exporting} onChange={(e) => onChangeAnonymize(e.target.checked)} />
            <span>隐藏 UID、账号名、主播名与房间号（公开反馈推荐开启）</span>
          </label>
          <label className="diag-check" htmlFor="diag-include-state">
            <input type="checkbox" id="diag-include-state" name="include_state"
              checked={includeState} disabled={exporting} onChange={(e) => onChangeIncludeState(e.target.checked)} />
            <span>包含非敏感运行设置、房间状态与最近活动记录尾部</span>
          </label>
        </fieldset>

        <div className="diag-status-region" role="status" aria-live="polite">
          {exported?.ok && (
            <div className="diag-result">
              <div className="diag-result-main">
                <strong><Icon name="check" size={13} />已导出：{exported.filename}（{sizeKb}）</strong>
                <span className="diag-path" title={exported.zip_path}>{exported.zip_path}</span>
              </div>
              <button type="button" className="btn sm" onClick={onOpenExports}>
                <Icon name="folder" size={13} />打开所在文件夹
              </button>
            </div>
          )}
          {!exported?.ok && statusText && <div className="diag-feedback">{statusText}</div>}
          {exported?.ok && statusText && <div className="diag-feedback ok">{statusText}</div>}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn" onClick={() => dialogRef.current?.close()} disabled={exporting}>关闭</button>
          <button type="button" className="btn" onClick={onCopySummary}
            disabled={loading || (!exported?.summary_markdown && !preview?.summary_markdown)}>
            <Icon name="copy" size={13} />复制摘要
          </button>
          <button type="submit" className="btn primary" disabled={exporting}>
            <Icon name="download" size={13} />{exporting ? "正在打包…" : exported ? "重新导出 (.zip)" : "导出诊断包 (.zip)"}
          </button>
        </div>
      </form>
    </dialog>
  );
};

const formatCountdown = (targetSec, nowSec) => {
  const diff = Math.max(0, Math.floor((targetSec || 0) - nowSec));
  if (diff <= 0) return "即将执行";
  const mins = Math.floor(diff / 60);
  const secs = diff % 60;
  if (mins >= 60) {
    const hours = Math.floor(mins / 60);
    return `约 ${hours} 小时 ${mins % 60} 分钟后`;
  }
  if (mins > 0) return `${mins} 分 ${String(secs).padStart(2, "0")} 秒后`;
  return `${secs} 秒后`;
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
  onClose,
}) => {
  const dialogRef = useModalDialog(onClose);
  const info = hold || {};
  const [nowSec, setNowSec] = React.useState(() => Math.floor(Date.now() / 1000));
  React.useEffect(() => {
    const timer = window.setInterval(() => setNowSec(Math.floor(Date.now() / 1000)), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const cooldown = Boolean(info.blocked && info.until && info.until > nowSec);
  const needsLogin = info.kind === "auth" || info.kind === "credentials";
  const canAct = Boolean(isActive || account?.id);
  const lastProbe = probeState?.result || info.last_probe || null;
  const checking = Boolean(probeState?.loading);
  const checks = Array.isArray(lastProbe?.checks) ? lastProbe.checks : [];
  const steps = Array.isArray(info.steps) ? info.steps : [];
  const roomId = info.operation?.room || "";
  const locationParts = [info.room_label, info.operation_label].filter(Boolean);

  return (
    <dialog ref={dialogRef} className="modal wide safety-dialog" closedby="any" aria-labelledby="safety-dialog-title">
      <div className="safety-modal-head">
        <div className="safety-modal-title">
          <Icon name="shield" size={16} />
          <div>
            <h3 id="safety-dialog-title">{info.kind_label || "账号保护暂停"}</h3>
            <p className="safety-modal-sub">
              {account?.name ? `${account.name} · ` : ""}
              {info.since ? `触发于 ${absoluteTime(info.since)}` : "已暂停互动操作以保护账号"}
            </p>
          </div>
        </div>
        {info.code !== undefined && info.code !== null && (
          <span className="version-pill">错误码 {info.code}</span>
        )}
      </div>

      <div className="safety-reason-box">
        <strong>{info.reason || "检测到平台安全验证或操作受限，已暂停自动化操作。"}</strong>
        {info.raw_message && info.raw_message !== info.reason && (
          <div className="safety-raw-msg">平台返回：{info.raw_message}</div>
        )}
      </div>

      <div className="safety-meta-grid">
        {locationParts.length > 0 && (
          <div className="safety-meta-item">
            <span>触发位置</span>
            <strong>{locationParts.join(" · ")}</strong>
          </div>
        )}
        {cooldown && (
          <div className="safety-meta-item">
            <span>自动恢复时间</span>
            <strong>{absoluteTime(info.until)}（{formatCountdown(info.until, nowSec)}）</strong>
          </div>
        )}
        {!cooldown && info.next_probe_at && (
          <div className="safety-meta-item">
            <span>下次自动复检</span>
            <strong>
              {absoluteTime(info.next_probe_at)}（{formatCountdown(info.next_probe_at, nowSec)}）
              {typeof info.auto_recover_remaining === "number" && ` · 今日自动恢复剩余 ${info.auto_recover_remaining} 次`}
            </strong>
          </div>
        )}
        {info.pace_multiplier > 1 && (
          <div className="safety-meta-item">
            <span>今日防风控降频</span>
            <strong>已自动放慢至 {info.pace_multiplier}× 互动发送间隔</strong>
          </div>
        )}
        {!cooldown && !info.next_probe_at && (info.kind === "uncertain" || info.kind === "review") && (
          <div className="safety-meta-item">
            <span>自动复检状态</span>
            <strong>已达本轮自动复检或今日恢复上限，请人工确认后恢复</strong>
          </div>
        )}
      </div>

      {steps.length > 0 && (
        <div className="safety-steps">
          <div className="safety-section-label">排查与处理步骤</div>
          <ol>
            {steps.map((step, index) => <li key={index}>{step}</li>)}
          </ol>
        </div>
      )}

      {lastProbe && (
        <div className={`safety-probe-box ${lastProbe.passed ? "ok" : "fail"}`} role="status" aria-live="polite">
          <div className="safety-probe-summary">
            <Icon name={lastProbe.passed ? "check" : "alert"} size={13} />
            <span>{lastProbe.summary || (lastProbe.passed ? "只读自检通过" : "只读自检未通过")}</span>
            {lastProbe.at && <small>{absoluteTime(lastProbe.at)}</small>}
          </div>
          {checks.length > 0 && (
            <ul className="safety-probe-checks">
              {checks.map((item, idx) => (
                <li key={idx} className={item.ok ? "ok" : "fail"}>
                  <Icon name={item.ok ? "check" : "alert"} size={12} />
                  <strong>{item.name}</strong>
                  <span>{item.detail}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="safety-links-row">
        {roomId && (
          <button type="button" className="btn sm" onClick={() => onOpenLink("live", roomId)} disabled={busy || checking}>
            打开对应直播间
          </button>
        )}
        <button type="button" className="btn sm" onClick={() => onOpenLink("live", null)} disabled={busy || checking}>
          打开 B 站直播首页
        </button>
        <button type="button" className="btn sm" onClick={() => onOpenLink("security", null)} disabled={busy || checking}>
          账号安全中心
        </button>
      </div>

      <div className="modal-actions">
        <button type="button" className="btn" onClick={() => dialogRef.current?.close()} disabled={busy || checking}>
          关闭
        </button>
        {canAct && needsLogin && (
          <button type="button" className="btn primary" onClick={() => { dialogRef.current?.close(); onScan(account?.id || ""); }} disabled={busy}>
            重新扫码登录
          </button>
        )}
        {canAct && !needsLogin && !cooldown && (
          <>
            <button type="button" className="btn" onClick={onResume} disabled={busy || checking}>
              {busy ? "处理中…" : "确认已处理并恢复"}
            </button>
            <button type="button" className="btn primary" onClick={() => onCheck(true)} disabled={busy || checking}>
              <Icon name="refresh" size={13} className={checking ? "spin" : ""} />
              {checking ? "检测中…" : "检测并自动恢复"}
            </button>
          </>
        )}
        {!canAct && (
          <button type="button" className="btn primary" onClick={() => dialogRef.current?.close()}>
            知道了
          </button>
        )}
      </div>
    </dialog>
  );
};

Object.assign(window, { Modal, QrModal, AddMemberModal, MedalsModal, ConfirmModal, RoomMenu, DiagnosticModal, SafetyModal });
