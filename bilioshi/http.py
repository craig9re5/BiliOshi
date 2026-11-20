"""One HTTP/JSON boundary. Failures have explicit, credential-free metadata."""

from collections import deque
import hashlib
import http.client
import json
import logging
import select
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request
import time
from email.utils import parsedate_to_datetime
from .login_fields import parse_cookie_header
from .redaction import redact, register_secrets
from . import safety
from .task_window import (
    MIN_READ_WINDOW,
    MIN_WRITE_WINDOW,
    check_window,
    require_window,
    request_timeout,
    wait,
    read_cache,
)
from .operating_mode import current_profile

NAV_URL = "https://api.bilibili.com/x/web-interface/nav"
_POOL_IDLE_TTL = 15.0
_POOL_MAX_PER_HOST = 4
_DEFAULT_SSL_CONTEXT = ssl.create_default_context()


def _socket_unusable(sock):
    try:
        readable, _, errored = select.select([sock], [], [sock], 0.0)
        return bool(readable or errored)
    except (OSError, ValueError):
        return True


class _ConnectionPool:
    """Thread-safe HTTP/1.1 keep-alive connection pool keyed by origin."""

    def __init__(self, *, idle_ttl=_POOL_IDLE_TTL, max_per_host=_POOL_MAX_PER_HOST):
        self._idle_ttl = idle_ttl
        self._max_per_host = max_per_host
        self._lock = threading.Lock()
        self._idle = {}

    def acquire(self, key):
        now = time.monotonic()
        stale = []
        chosen = None
        with self._lock:
            bucket = self._idle.get(key)
            while bucket:
                conn, returned_at = bucket.pop()
                if now - returned_at > self._idle_ttl or conn.sock is None or _socket_unusable(conn.sock):
                    stale.append(conn)
                    continue
                chosen = conn
                break
            if bucket is not None and not bucket:
                self._idle.pop(key, None)
        for conn in stale:
            try:
                conn.close()
            except OSError:
                pass
        return chosen

    def release(self, key, conn):
        now = time.monotonic()
        evicted = None
        with self._lock:
            bucket = self._idle.setdefault(key, deque())
            while bucket and len(bucket) >= self._max_per_host:
                old_conn, _ = bucket.popleft()
                evicted = old_conn
                break
            bucket.append((conn, now))
        if evicted is not None:
            try:
                evicted.close()
            except OSError:
                pass

    def close_all(self):
        with self._lock:
            buckets = list(self._idle.values())
            self._idle.clear()
        for bucket in buckets:
            for conn, _ in bucket:
                try:
                    conn.close()
                except OSError:
                    pass


_POOL = _ConnectionPool()


def _session_pool_bucket(headers) -> str:
    cookie_header = headers.get("Cookie") or headers.get("cookie") or ""
    if not cookie_header:
        return "anon"
    try:
        sessdata = parse_cookie_header(cookie_header).get("SESSDATA", "")
    except Exception:
        sessdata = ""
    if not sessdata:
        return "anon"
    return hashlib.sha256(sessdata.encode("utf-8")).hexdigest()[:16]


class _PooledOpenMixin:
    """Reuse persistent HTTP/1.1 connections inside urllib OpenerDirector."""

    def do_open(self, http_class, req, **http_conn_args):
        host = req.host
        if not host:
            raise urllib.error.URLError("no host given")
        if getattr(req, "_tunnel_host", None) or host != urllib.parse.urlsplit(req.full_url).netloc:
            return super().do_open(http_class, req, **http_conn_args)

        headers = dict(req.unredirected_hdrs)
        headers.update({k: v for k, v in req.headers.items() if k not in headers})
        headers = {name.title(): val for name, val in headers.items()}
        headers["Connection"] = "keep-alive"

        req_timeout = getattr(req, "timeout", None)
        timeout = req_timeout if req_timeout is not None else 10
        scheme = req.type or "http"
        bucket = _session_pool_bucket(headers)
        pool_key = (
            (scheme, host, id(http_conn_args.get("context")))
            if bucket == "anon"
            else (scheme, host, id(http_conn_args.get("context")), bucket)
        )

        conn = _POOL.acquire(pool_key)
        reused = conn is not None
        if conn is None:
            conn = http_class(host, timeout=timeout, **http_conn_args)
            conn.set_debuglevel(self._debuglevel)
        else:
            conn.timeout = timeout
            if conn.sock is not None:
                conn.sock.settimeout(timeout)

        try:
            try:
                conn.request(
                    req.get_method(),
                    req.selector,
                    req.data,
                    headers,
                    encode_chunked=req.has_header("Transfer-encoding"),
                )
                response = conn.getresponse()
            except (http.client.RemoteDisconnected, ConnectionResetError, BrokenPipeError) as err:
                conn.close()
                # Replaying a non-idempotent POST could duplicate writes; retry fresh sockets for GET only.
                if not (reused and req.get_method() == "GET"):
                    raise urllib.error.URLError(err)
                conn = http_class(host, timeout=timeout, **http_conn_args)
                conn.set_debuglevel(self._debuglevel)
                conn.request(
                    req.get_method(),
                    req.selector,
                    req.data,
                    headers,
                    encode_chunked=req.has_header("Transfer-encoding"),
                )
                response = conn.getresponse()
        except urllib.error.URLError:
            conn.close()
            raise
        except (OSError, http.client.HTTPException) as err:
            conn.close()
            raise urllib.error.URLError(err)

        response.url = req.get_full_url()
        response.msg = response.reason
        orig_close = response.close
        released = False

        def pooled_close():
            nonlocal released
            orig_close()
            if released:
                return
            released = True
            if (
                response.isclosed()
                and not response.will_close
                and 200 <= response.status < 400
                and conn.sock is not None
            ):
                _POOL.release(pool_key, conn)
            else:
                conn.close()

        response.close = pooled_close
        return response


class _PooledHTTPHandler(_PooledOpenMixin, urllib.request.HTTPHandler):
    pass


class _PooledHTTPSHandler(_PooledOpenMixin, urllib.request.HTTPSHandler):
    pass


class SameOriginRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        before, after = urllib.parse.urlsplit(request.full_url), urllib.parse.urlsplit(newurl)
        if (before.scheme, before.netloc) != (after.scheme, after.netloc):
            raise urllib.error.HTTPError(request.full_url, 403, "拒绝跨域会话重定向", headers, fp)
        return super().redirect_request(request, fp, code, message, headers, newurl)


class ApiError(RuntimeError):

    def __init__(self, code, message, *, kind="api"):
        self.code, self.kind = (code, kind)
        super().__init__(redact(message))


def _safe_url(url):
    parsed = urllib.parse.urlsplit(str(url))
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" if parsed.netloc else str(url).split("?", 1)[0]


_AUTH_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    SameOriginRedirect(),
    _PooledHTTPHandler(),
    _PooledHTTPSHandler(context=_DEFAULT_SSL_CONTEXT),
)
_PLAIN_OPENER = urllib.request.build_opener(
    urllib.request.ProxyHandler({}),
    _PooledHTTPHandler(),
    _PooledHTTPSHandler(context=_DEFAULT_SSL_CONTEXT),
)


def _once(url, headers=None, *, data=None, method=None, timeout=10):
    request = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        if headers and headers.get("Cookie"):
            open_request = _AUTH_OPENER.open
        elif getattr(urllib.request.urlopen, "__module__", None) != "urllib.request":
            open_request = urllib.request.urlopen
        else:
            open_request = _PLAIN_OPENER.open
        with open_request(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("expected JSON object")
        return value
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read(256).decode("utf-8", errors="replace").strip() if hasattr(exc, "read") else ""
        except Exception:
            detail = ""
        finally:
            try:
                exc.close()
            except Exception:
                pass
        logging.warning(
            "HTTP error url=%s status=%s reason=%s detail=%s",
            _safe_url(url),
            exc.code,
            redact(str(getattr(exc, "reason", ""))),
            redact(detail[:160]),
        )
        value = {"code": exc.code, "http_status": exc.code, "message": f"HTTP {exc.code}", "error_kind": "http"}
        if detail.startswith("{"):
            try:
                parsed_err = json.loads(detail)
            except ValueError:
                parsed_err = None
            if isinstance(parsed_err, dict):
                bili_code = parsed_err.get("code")
                if isinstance(bili_code, int) and not isinstance(bili_code, bool):
                    value["bili_code"] = bili_code
                bili_msg = str(parsed_err.get("message") or parsed_err.get("msg") or "").strip()
                if bili_msg:
                    value["message"] = f"HTTP {exc.code}: {bili_msg[:120]}"
        retry_after = exc.headers.get("Retry-After") if exc.headers else None
        if retry_after and retry_after.isdigit():
            value["retry_after"] = int(retry_after)
        elif retry_after:
            try:
                value["retry_after"] = max(
                    0, int(parsedate_to_datetime(retry_after).timestamp() - time.time())
                )
            except (TypeError, ValueError, OverflowError):
                pass
        return value
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        logging.warning(
            "HTTP request failed url=%s err=%s: %s",
            _safe_url(url),
            type(exc).__name__,
            redact(str(exc)),
        )
        return {"code": -1, "message": "网络请求失败", "error_kind": "network"}
    except (ValueError, UnicodeError) as exc:
        logging.warning(
            "HTTP response decode failed url=%s err=%s: %s",
            _safe_url(url),
            type(exc).__name__,
            redact(str(exc)),
        )
        return {"code": -1, "message": "服务端响应格式无效", "error_kind": "data"}


def get_json(url, headers, timeout=10):
    return request_json(url, headers, timeout=timeout)


def request_json(
    url,
    headers=None,
    *,
    data=None,
    method=None,
    timeout=10,
    auth_probe=False,
    safety_probe=False,
):
    """Retry reads only; never replay a write after an ambiguous outcome."""
    check_window()
    headers = headers or {}
    parts = parse_cookie_header(headers.get("Cookie", "")) if headers.get("Cookie") else {}
    register_secrets(parts)
    sessdata = parts.get("SESSDATA")
    parsed = urllib.parse.urlsplit(url)
    if sessdata and (
        parsed.scheme != "https"
        or parsed.hostname
        not in {
            "api.bilibili.com",
            "api.live.bilibili.com",
            "api.vc.bilibili.com",
            "live-trace.bilibili.com",
        }
    ):
        return {"code": -1, "message": "拒绝向非预期地址发送登录会话", "error_kind": "safety"}
    effective_method = method or ("POST" if data is not None else "GET")
    mutation = effective_method != "GET" and parsed.path not in safety.READ_POST_PATHS
    op = safety.operation(url, data, effective_method)
    if sessdata:
        hold = safety.status(sessdata)
        watch_allowed = safety.is_interaction_only(hold) and safety.is_watch_operation(
            op, mutation=mutation
        )
        may_read = (hold.get("kind") == "uncertain" or safety_probe) and not mutation
        if (
            hold["blocked"]
            and not may_read
            and not watch_allowed
            and not (auth_probe and parsed.path == "/x/web-interface/nav")
        ):
            return safety.blocked_response(hold)
        if mutation and not safety.identity(sessdata).startswith("uid-"):
            verified = request_json(NAV_URL, headers, timeout=timeout)
            if not safety.identity(sessdata).startswith("uid-"):
                return (
                    verified
                    if verified.get("code") != 0
                    else {
                        "code": -101,
                        "message": "无法认证账号身份，本次跳过操作",
                        "error_kind": "auth",
                    }
                )
    cache = (
        read_cache()
        if parsed.path == "/x/web-interface/nav" and not auth_probe and not safety_probe
        else None
    )
    cache_key = (sessdata, url)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    min_window = MIN_WRITE_WINDOW if mutation else MIN_READ_WINDOW
    attempt_timeout = request_timeout(timeout, minimum=min_window)
    if sessdata and mutation:
        denied = safety.reserve(sessdata, op)
        if denied:
            return denied
    delays = () if mutation else current_profile().read_retry_delays
    for attempt in range(len(delays) + 1):
        if attempt:
            attempt_timeout = request_timeout(timeout, minimum=min_window)
        response = _once(url, headers, data=data, method=method, timeout=attempt_timeout)
        if response.get("error_kind") != "network" or attempt == len(delays):
            break
        require_window(delays[attempt] + min(timeout, min_window))
        wait(delays[attempt])
        if sessdata:
            hold = safety.status(sessdata)
            if (
                hold["blocked"]
                and hold.get("kind") != "uncertain"
                and not safety.is_interaction_only(hold)
                and not safety_probe
            ):
                return safety.blocked_response(hold)
    if sessdata and not safety_probe:
        safety.observe(sessdata, url, response, mutation=mutation, op=op)
    if isinstance(response.get("message"), str):
        response["message"] = redact(response["message"])
    if cache is not None and response.get("code") == 0:
        cache[cache_key] = response
    return response


def post_form(url, data, headers, timeout=10):
    return request_json(
        url,
        {**headers, "Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode(data).encode("utf-8"),
        timeout=timeout,
    )


def post_empty(url, headers, timeout=10):
    return request_json(url, headers, method="POST", timeout=timeout)


def require_data(response, operation):
    if not response or response.get("code") != 0:
        value = response or {}
        raise ApiError(
            value.get("code", -1),
            f"{operation}失败：{value.get('message', '无响应')}",
            kind=value.get("error_kind", "api"),
        )
    return response.get("data") or {}
