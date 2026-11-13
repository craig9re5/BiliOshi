"""Shared application entry for CLI adapters, desktop workers and manual actions."""

from pathlib import Path
import time
import urllib.parse
from . import heartbeat as live
from . import http
from .check_auth import check_login_profile
from .context import RuntimeContext, use_context
from .runtime import data_dir, read_json, task_day, update_json
from .members import load_members, validate_members
from .session_headers import session_headers
from .launch import watch_arguments
from . import safety


class AppContext:

    def __init__(self, root=None, *, observer=None, notify=None, gateway=live):
        self.root = Path(root) if root is not None else data_dir()
        self.runtime = RuntimeContext(self.root, observer, notify)
        self.gateway = gateway

    def call(self, method, *args, **kwargs):
        with use_context(self.runtime):
            return getattr(self.gateway, method)(*args, **kwargs)

    def credentials(self):
        saved = read_json(self.root / "credentials.json", {})
        if not saved.get("SESSDATA") or not saved.get("bili_jct"):
            raise ValueError("尚未配置登录凭证，请打开登录设置")
        return (saved["SESSDATA"], saved["bili_jct"])

    def run_watch(self, member, policy):
        return self.call("main", watch_arguments(member, policy)) or 0

    def redo(self, room, uid, task_type="all"):
        return self.call("redo_member_tasks", room, uid, *self.credentials(), task_type)

    def resolve(self, query):
        saved = read_json(self.root / "credentials.json", {})
        return self.call(
            "resolve_anchor_info", query, saved.get("SESSDATA", ""), saved.get("bili_jct", "")
        )

    def validate_credentials_profile(self, sessdata, bili_jct):
        from .credentials import parse_login_import
        import json

        try:
            parse_login_import(json.dumps({"SESSDATA": sessdata, "bili_jct": bili_jct}))
        except ValueError:
            return False, "凭证格式不正确，请重新扫码或检查输入", {}
        with use_context(self.runtime):
            return check_login_profile(sessdata, bili_jct)

    def validate_credentials(self, sessdata, bili_jct):
        valid, message, _profile = self.validate_credentials_profile(sessdata, bili_jct)
        return valid, message

    def account_profile(self):
        """Resolve the public profile of the saved login without exposing credentials."""
        try:
            valid, _message, profile = self.validate_credentials_profile(*self.credentials())
        except (OSError, ValueError, RuntimeError):
            return {}
        return profile if valid else {}

    def safety_status(self):
        try:
            saved = read_json(self.root / "credentials.json", {})
        except RuntimeError:
            return {
                "blocked": True,
                "kind": "credentials",
                "reason": "凭证无法解密，请重新扫码登录",
            }
        hold = safety.status(saved.get("SESSDATA"), self.root)
        mult = safety.pace_multiplier(saved.get("SESSDATA"), self.root)
        if mult > 1.0:
            hold["pace_multiplier"] = mult
        return hold

    def room_safety_blocks(self):
        try:
            saved = read_json(self.root / "credentials.json", {})
        except RuntimeError:
            return {}
        return safety.room_blocks(saved.get("SESSDATA"), self.root)

    def clear_room_safety_block(self, room, capability=None):
        credentials = self.credentials()
        cleared = safety.clear_room_block(credentials[0], room, capability, root=self.root)
        if cleared:
            return True, "已解除该直播间的互动限制"
        return False, "该直播间当前没有生效中的互动限制"

    def resume_safety(self, confirmed=False):
        credentials = self.credentials()
        hold = self.safety_status()
        if hold.get("until") or hold.get("kind") == "auth":
            return safety.resume(credentials[0], confirmed=confirmed, root=self.root)
        if not confirmed:
            return False, "请先在平台处理异常并确认"
        ok, message = self.validate_credentials(*credentials)
        if not ok:
            return False, "登录或平台验证未通过，保护暂停保留"
        return safety.resume(credentials[0], confirmed=True, root=self.root)

    def _probe_live_endpoints(self, sessdata, bili_jct, hold):
        """Query read-only live endpoints with safety_probe=True to test current risk state."""
        checks = []
        summary = "只读自检通过：账号会话与直播只读接口均返回正常"
        with use_context(self.runtime):
            members = load_members(self.root)
            op_room = str((hold.get("operation") or {}).get("room") or "")
            target = next((m for m in members if str(m.get("room")) == op_room), None) or (
                members[0] if members else None
            )
            if not target:
                return checks, True, False, summary
            room = str(target["room"])
            uid = str(target["uid"])
            status_resp = http.request_json(
                "https://api.live.bilibili.com/room/v1/Room/get_status_info_by_uids",
                {
                    **session_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room}"),
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=urllib.parse.urlencode([("uids[]", uid)]).encode("utf-8"),
                safety_probe=True,
            )
            status_ok = status_resp.get("code") == 0
            status_code = status_resp.get("code")
            status_msg = str(status_resp.get("message") or "").strip()
            checks.append(
                {
                    "name": "直播状态接口",
                    "ok": status_ok,
                    "code": status_code,
                    "detail": (
                        f"正常（{target.get('name', room)}）"
                        if status_ok
                        else f"[{status_code}] {status_msg or '请求异常'}"
                    ),
                }
            )
            params = {
                "csrf": bili_jct,
                "platform": "pc",
                "room_id": room,
                "scene": "club",
                "target_id": uid,
                "web_location": "444.260",
            }
            club_url = (
                "https://api.live.bilibili.com/xlive/app-ucenter/v1/fansMedal/GetActivatedMedalInfo?"
                + urllib.parse.urlencode(params)
            )
            club_resp = http.request_json(
                club_url,
                session_headers(sessdata, bili_jct, f"https://live.bilibili.com/{room}"),
                safety_probe=True,
            )
            club_ok = club_resp.get("code") == 0
            club_code = club_resp.get("code")
            club_msg = str(club_resp.get("message") or "").strip()
            checks.append(
                {
                    "name": "粉丝团接口",
                    "ok": club_ok,
                    "code": club_code,
                    "detail": "只读返回正常" if club_ok else f"[{club_code}] {club_msg or '请求异常'}",
                }
            )
            for resp in (status_resp, club_resp):
                if resp.get("code") in (-101, -111) or resp.get("error_kind") == "auth":
                    safety.hold_account(
                        sessdata,
                        "auth",
                        "登录已失效，请重新扫码登录",
                        code=resp.get("code"),
                        operation=hold.get("operation"),
                        raw_message=str(resp.get("message") or ""),
                        root=self.root,
                    )
                    return checks, False, True, "登录会话已失效，请重新扫码登录"
            if status_ok and club_ok:
                return checks, True, False, summary
            if {status_code, club_code} & {-352, -412, 412}:
                return checks, False, False, "只读复检仍触发 B 站风控/验证限制，请先在网页端完成验证后重试"
            failed = next((item for item in checks if not item["ok"]), None)
            return (
                checks,
                False,
                False,
                f"{failed['name']}未通过：{failed['detail']}" if failed else "只读复检未通过",
            )

    def probe_safety(self, *, auto=False, auto_resume=False):
        """Run read-only live checks against the active safety hold and optionally recover."""
        hold = self.safety_status()
        if not hold.get("blocked"):
            return {
                "ok": True, "passed": True, "resumed": False,
                "hold": hold, "summary": "当前没有保护暂停", "checks": [],
            }
        if hold.get("kind") == "credentials":
            return {
                "ok": False, "passed": False, "resumed": False, "hold": hold,
                "summary": "凭证无法解密，请重新扫码登录",
                "checks": [{"name": "凭证解密", "ok": False, "detail": "需要重新扫码登录"}],
            }
        try:
            sessdata, bili_jct = self.credentials()
        except ValueError as exc:
            return {"ok": False, "passed": False, "resumed": False, "hold": hold, "summary": str(exc), "checks": []}

        valid, msg, _profile = self.validate_credentials_profile(sessdata, bili_jct)
        checks = [{"name": "账号会话", "ok": bool(valid), "detail": msg or ("登录有效" if valid else "会话验证失败")}]
        if not valid:
            if not str(msg).startswith("认证接口请求失败"):
                safety.hold_account(
                    sessdata, "auth", "登录已失效，请重新扫码登录",
                    code=-101, operation=hold.get("operation"), raw_message=str(msg or ""), root=self.root,
                )
                return {
                    "ok": False, "passed": False, "resumed": False,
                    "hold": self.safety_status(), "summary": f"会话验证失败：{msg}", "checks": checks,
                }
            updated = safety.record_probe(
                sessdata, checks, passed=False, summary=str(msg or "网络请求失败"), auto=auto, root=self.root
            )
            return {
                "ok": True, "passed": False, "resumed": False,
                "hold": updated, "summary": str(msg or "网络请求失败"), "checks": checks,
            }

        live_checks, all_passed, auth_failed, summary = self._probe_live_endpoints(sessdata, bili_jct, hold)
        checks.extend(live_checks)
        if auth_failed:
            return {
                "ok": False, "passed": False, "resumed": False,
                "hold": self.safety_status(), "summary": summary, "checks": checks,
            }

        safety.record_probe(sessdata, checks, passed=all_passed, summary=summary, auto=auto, root=self.root)
        resumed = False
        if all_passed:
            if auto and hold.get("kind") in safety.AUTO_PROBE_DELAYS and not hold.get("until"):
                ok_resume, resume_msg = safety.auto_resume(sessdata, checks, summary=summary, root=self.root)
                resumed = bool(ok_resume)
                summary = resume_msg
            elif auto_resume and not hold.get("until") and hold.get("kind") != "auth":
                ok_resume, resume_msg = self.resume_safety(confirmed=True)
                resumed = bool(ok_resume)
                if ok_resume:
                    summary = resume_msg

        return {
            "ok": True, "passed": all_passed, "resumed": resumed,
            "hold": self.safety_status(), "summary": summary, "checks": checks,
        }

    def add_members(self, additions):
        additions = [{key: member[key] for key in ("name", "uid", "room")} for member in additions]

        def change(saved):
            members = list(saved or [])
            existing = {m["room"] for m in members}
            for member in additions:
                if member["room"] not in existing:
                    members.append(member)
                    existing.add(member["room"])
            return validate_members(members)

        return update_json(self.root / "members.json", change, [])

    def remove_member(self, room):
        return update_json(
            self.root / "members.json",
            lambda members: [m for m in members if m["room"] != room],
            [],
        )

    def medals(self):
        return self.call("get_all_user_medals", *self.credentials())

    def wear(self, uid):
        credentials = self.credentials()
        medals = self.call("get_my_medals", *credentials)
        info = medals.get(uid) or medals.get(str(uid))
        if not info or not info.get("medal_id"):
            return "no_medal"
        return "ok" if self.call("wear_medal", info["medal_id"], *credentials) else "fail"

    def probe(self, members):
        credentials = self.credentials()
        hold = self.safety_status()
        if hold["blocked"]:
            return {"error": hold["reason"], "safety": hold}
        valid, message = self.validate_credentials(*credentials)
        if not valid:
            return {
                "error": f"登录验证失败：{message}",
                "auth_invalid": not message.startswith("认证接口请求失败"),
            }
        statuses = self.call("check_live_status", [m["room"] for m in members], *credentials)
        medals = self.call("get_my_medals", *credentials)
        # Fan-medal counters were read here; task queries may take long enough
        # to cross midnight, so growth samples use this timestamp, not the end
        # of the whole probe.
        medals_at = time.time()
        tasks, errors = self._query_tasks(members, credentials)
        missing = [m["name"] for m in members if m["room"] not in statuses]
        result = {
            "statuses": statuses,
            "account": message,
            "medals": medals,
            "medals_at": medals_at,
            "tasks": tasks,
            "task_errors": errors,
            "observed": time.time(),
            "warning": "无法查询：" + "、".join(missing) if missing else "",
        }
        self.call(
            "_log",
            {
                "type": "check",
                "source": "desktop",
                "live": [
                    {"name": m["name"], "title": statuses[m["room"]].get("title", "")}
                    for m in members
                    if statuses.get(m["room"], {}).get("live_status") == 1
                ],
                "offline": [
                    m["name"]
                    for m in members
                    if statuses.get(m["room"], {}).get("live_status") in (0, 2)
                ],
                "unknown": missing,
            },
        )
        return result

    def _query_tasks(self, members, credentials):
        tasks, errors = ({}, {})
        for member in members:
            club = self.call("get_fans_club_task_info", member["room"], member["uid"], *credentials)
            if not club:
                errors[str(member["room"])] = "任务进度查询失败"
                continue
            tasks[str(member["room"])] = {
                "tasks": club.get("task_info", []),
                "intimacy": club.get("intimacy", 0),
                "next_intimacy": club.get("next_intimacy", 0),
                "task_light_days": club.get("task_light_days", 0),
                "is_lighted": club.get("is_lighted", False),
                "updated": time.time(),
                "day": task_day(),
            }
        return (tasks, errors)
