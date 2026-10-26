"""Fixed HTTPS destination and dedicated opener; no Bilibili cookies or retries."""

import json
import socket
import urllib.error
import urllib.request
from .. import notifications

URL = "https://www.pushplus.plus/send"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def send(token, message, *, opener=None):
    if not notifications.AVAILABLE:
        return {"state": "failed", "reason": notifications.UNAVAILABLE_REASON, "blocked": True}
    payload = {"token": token, "channel": "qq", "template": "txt",
               "title": message["title"], "content": message["content"],
               "timestamp": int(message["expires"] * 1000)}
    request = urllib.request.Request(URL, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                                    headers={"Content-Type": "application/json", "User-Agent": "BiliOshi-Daily"},
                                    method="POST")
    client = opener or urllib.request.build_opener(NoRedirect())
    try:
        with client.open(request, timeout=12) as response:
            raw = response.read(65537)
        if len(raw) > 65536:
            return {"state": "unknown", "reason": "响应过大，结果未知；请查看 PushPlus 消息记录"}
        result = json.loads(raw)
    except urllib.error.HTTPError as exc:
        return {"state": "unknown", "reason": f"HTTP {exc.code}，结果未知；请查看 PushPlus 消息记录"}
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, socket.gaierror):
            return {"state": "retry", "reason": "域名解析失败，稍后有限重试"}
        return {"state": "unknown", "reason": "网络中断，结果未知；请查看 PushPlus 消息记录"}
    except (TimeoutError, OSError, ValueError):
        return {"state": "unknown", "reason": "请求或响应异常，结果未知；请查看 PushPlus 消息记录"}
    if not isinstance(result, dict) or type(result.get("code")) is not int:
        return {"state": "unknown", "reason": "响应格式异常，结果未知；请查看 PushPlus 消息记录"}
    code, short = result["code"], result.get("data")
    if code == 200:
        if isinstance(short, str) and 0 < len(short) <= 128 and short.isalnum():
            return {"state": "accepted", "reason": "服务已受理；手机是否收到需自行确认", "short_code": short}
        return {"state": "unknown", "reason": "服务返回成功但无有效流水号，请查看 PushPlus 消息记录"}
    reasons = {900: "PushPlus 限制或额度暂停，请处理后恢复通知", 903: "PushPlus Token 无效，请更新",
               905: "PushPlus 需要实名，请处理后恢复通知"}
    return {"state": "failed", "reason": reasons.get(code, f"PushPlus 拒绝请求（{code}），请检查实名和 QQ 绑定"),
            "blocked": True, "code": code}
