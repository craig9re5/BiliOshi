"""Daily-only mobile configuration with IO callbacks marshalled to Tk."""

import tkinter as tk
from tkinter import messagebox
import webbrowser

from bilioshi.notifications import settings
from bilioshi.notifications.outbox import Outbox
from .widgets import (BG_CARD, BG_WINDOW, TEXT_MAIN, TEXT_MUTED, FONT_FAMILY,
                      CardFrame, ModernButton, ToggleSwitch, create_setting_row)

STATES = {"pending": "排队中", "rebuild": "等待重新核验", "submitting": "提交中", "accepted": "服务已受理",
          "unknown": "结果未知", "failed": "失败", "expired": "已过期", "superseded": "已取消"}


class NotificationSettings(tk.Frame):
    def __init__(self, parent, engine, px):
        super().__init__(parent, bg=BG_WINDOW)
        self.engine, self.px, self.busy = engine, px, False
        try:
            config = settings.load(engine.root)
        except (OSError, ValueError, RuntimeError):
            config = settings.DEFAULTS
        tk.Label(self, text="手机每日总结 · QQ（实验性）", bg=BG_WINDOW, fg=TEXT_MUTED,
                 font=(FONT_FAMILY, 10, "bold")).pack(anchor="w", pady=(0, px(4)))
        card = CardFrame(self, px=px)
        card.pack(fill="x", pady=(0, px(14)))
        tk.Label(card, text="尚未实测成功，功能暂不可用；以下设置不会生效，也不会发送任何消息。",
                 bg=BG_CARD, fg="#a65c00", justify="left", anchor="w",
                 wraplength=px(580)).pack(fill="x", pady=(0, px(8)))
        self.enabled = tk.BooleanVar(value=False)
        self.anonymous = tk.BooleanVar(value=config["anonymous"])
        self.at = tk.StringVar(value=config["summary_at"])
        self.secret = tk.StringVar(value="")
        create_setting_row(card, "每天发送一条收益总结", "实验性功能，暂未开放",
                           lambda row: ToggleSwitch(row, variable=self.enabled, px=px, state="disabled"),
                           px=px)
        create_setting_row(card, "隐藏主播名称", "实验性功能，暂未开放",
                           lambda row: ToggleSwitch(row, variable=self.anonymous, px=px, state="disabled"),
                           px=px)
        row = tk.Frame(card, bg=BG_CARD)
        row.pack(fill="x", pady=px(5))
        tk.Label(row, text="每日发送时间（UTC+8）", bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")
        tk.Entry(row, textvariable=self.at, width=7, justify="center", state="disabled").pack(side="right")
        row = tk.Frame(card, bg=BG_CARD)
        row.pack(fill="x", pady=px(5))
        tk.Label(row, text="PushPlus 消息 Token", bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")
        self.token_entry = tk.Entry(row, textvariable=self.secret, show="●", width=32, state="disabled")
        self.token_entry.pack(side="right")
        self.feedback = tk.StringVar(value="实验性功能：等待实测通过后开放。")
        tk.Label(card, textvariable=self.feedback, bg=BG_CARD, fg=TEXT_MUTED,
                 justify="left", anchor="w", wraplength=px(580)).pack(fill="x", pady=px(5))
        self.buttons = []
        for actions in (
            (("保存每日总结", self.save_clicked), ("预览今日总结", self.preview), ("发送测试消息", self.test)),
            (("恢复通知通道", self.resume), ("清空待发消息", self.clear), ("删除 Token 并关闭", self.delete)),
        ):
            row = tk.Frame(card, bg=BG_CARD)
            row.pack(fill="x", pady=px(4))
            for title, callback in actions:
                button = ModernButton(row, text=title, command=callback, px=px, state="disabled")
                button.pack(side="left", padx=(0, px(6)))
                self.buttons.append(button)
        ModernButton(card, text="打开 PushPlus QQ 配置说明", px=px, state="disabled",
                     command=lambda: webbrowser.open("https://www.pushplus.plus/doc/channel/qq.html")).pack(anchor="w", pady=px(4))
        self.bind("<Destroy>", self._destroyed, add="+")

    def _destroyed(self, event):
        pass

    def config(self):
        return settings.validate({"enabled": False, "anonymous": self.anonymous.get(),
                                  "summary_at": self.at.get().strip()})

    def save_values(self):
        """Experimental: persist nothing and never enable sending until实测通过."""
        self.secret.set("")

    def _async(self, function, done):
        if self.busy:
            return
        self.busy = True
        for button in self.buttons:
            button.configure(state="disabled")
        def work():
            try:
                result, error = function(), ""
            except ValueError as exc:
                result, error = None, str(exc)
            except Exception as exc:
                result, error = None, f"操作失败（{type(exc).__name__}），请检查本机配置"
            def finish():
                if not self.winfo_exists():
                    return
                self.busy = False
                for button in self.buttons:
                    button.configure(state="normal")
                if error:
                    self.feedback.set(error)
                else:
                    done(result)
            self.engine.dispatcher.post(finish)
        if self.engine.dispatcher.submit(work) is None:
            self.busy = False
            self.feedback.set("程序正在退出，下次启动后重试")

    def save_clicked(self):
        # Capture Tk values before submitting IO.
        try:
            config, replacement = self.config(), self.secret.get().strip() or None
        except ValueError as exc:
            self.feedback.set(str(exc))
            return
        self._async(lambda: settings.save(self.engine.root, config, replacement),
                    lambda _: (self.secret.set(""), self.feedback.set("每日总结已保存；后台将按新配置发送。")))

    def preview(self):
        self.feedback.set("正在只读核验今日收益，请稍候…")
        self._async(self.engine.notifications.preview, self.show_preview)

    def show_preview(self, message):
        window = tk.Toplevel(self)
        window.title("今日总结预览 · 不发送")
        window.geometry(f"{self.px(660)}x{self.px(420)}")
        text = tk.Text(window, wrap="word", padx=self.px(12), pady=self.px(12))
        text.pack(fill="both", expand=True)
        text.insert("1.0", message["title"] + "\n\n" + message["content"])
        text.configure(state="disabled")
        self.feedback.set("预览完成；内容来自现有登录的只读查询。")

    def test(self):
        if messagebox.askyesno("发送测试消息", "将用已保存的 Token 向 QQ 私聊本人发送一条合成日报。\n"
                               "这会消耗一次 PushPlus 发送额度。是否发送？", parent=self):
            self._async(self.engine.notifications.queue_test, self.feedback.set)

    def resume(self):
        self._async(self.engine.notifications.resume, self.feedback.set)

    def clear(self):
        def clear():
            Outbox(self.engine.root).clear_pending()
            return "待发消息已清空；今日防重和发送预算保留。"
        self._async(clear, self.feedback.set)

    def delete(self):
        try:
            config = self.config()
        except ValueError:
            config = dict(settings.DEFAULTS)
        config["enabled"] = False
        def remove():
            settings.save(self.engine.root, config, "")
            Outbox(self.engine.root).clear_pending()
        self._async(remove, lambda _: (self.enabled.set(False), self.secret.set(""),
                                      self.feedback.set("Token 已删除，每日总结已关闭。")))

    def refresh(self):
        """Experimental section stays inert: no polling, no status writes."""
        return

    def show_status(self, status):
        config = status["config"]
        mode = ("未配置 Token" if not status["configured"] else
                f"每日 {config['summary_at']}" if config["enabled"] else "每日总结已关闭")
        text = f"{mode} · 待发 {status['pending']} · 今日发送尝试 {status['attempts_today']}/100"
        if status["blocked"]:
            text += "\n通道已暂停：" + status["blocked"]
        if status.get("error"):
            text += "\n" + status["error"]
        if status["recent"]:
            last = status["recent"][0]
            text += f"\n最近：{last['day']} {STATES.get(last['state'], last['state'])} · {last['reason']}"
        self.feedback.set(text)
