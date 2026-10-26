"""Validated public settings and a separately encrypted PushPlus credential."""

import re
from pathlib import Path
from ..runtime import read_json, update_json
from .. import notifications

DEFAULTS = {"enabled": False, "summary_at": "23:50", "anonymous": False}


def validate(value):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("每日手机总结配置必须是对象")
    config = {**DEFAULTS, **value}
    for key in ("enabled", "anonymous"):
        if type(config[key]) is not bool:
            raise ValueError("每日总结开关必须为 true 或 false")
    if not isinstance(config["summary_at"], str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", config["summary_at"]
    ):
        raise ValueError("发送时间应为 HH:MM，例如 23:50（UTC+8）")
    return {key: config[key] for key in DEFAULTS}


def load(root):
    settings = read_json(Path(root) / "settings.json", {})
    return validate(settings.get("daily_notification"))


def token(root):
    value = read_json(Path(root) / "pushplus.credentials.json", {})
    saved = value.get("pushplus_token", "")
    if saved and (not isinstance(saved, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", saved)):
        raise ValueError("已保存的 PushPlus Token 格式无效，请重新配置")
    return saved


def save(root, config, replacement=None):
    """None keeps the saved secret; empty string explicitly deletes and disables."""
    config = validate(config)
    if config["enabled"] and not notifications.AVAILABLE:
        raise ValueError(notifications.UNAVAILABLE_REASON)
    if replacement is not None:
        replacement = replacement.strip()
        if replacement and not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", replacement):
            raise ValueError("PushPlus Token 应为 16–128 位字母、数字、下划线或短横线")
        if not replacement:
            config["enabled"] = False
    saved = token(root) if replacement is None else replacement
    if config["enabled"] and not saved:
        raise ValueError("请先填写 PushPlus 消息 Token")
    if replacement is not None:
        update_json(Path(root) / "pushplus.credentials.json",
                    lambda _: {"pushplus_token": saved} if saved else {}, {})
    update_json(Path(root) / "settings.json",
                lambda settings: {**settings, "daily_notification": config}, {})
    return config
