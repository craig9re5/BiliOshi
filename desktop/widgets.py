import math
import re
import tkinter as tk
from bilioshi.safety import format_task_errors

try:
    import pystray
    from PIL import Image, ImageColor, ImageDraw
except ImportError:
    pystray = None
    Image = ImageDraw = None


def format_task_result(name, result):
    if result.get("success"):
        return f"【{name}】所选任务已确认完成"
    detail = format_task_errors(result) or "任务进度尚未确认完成"
    return f"【{name}】任务未完成：{detail}"


BG_WINDOW = "#fcfcfb"
BG_CARD = "#ffffff"
BORDER_CARD = "#deded9"
BORDER_LIGHT = "#eaeae6"
TEXT_MAIN = "#1f1f1d"
TEXT_MUTED = "#63635e"
ACCENT_GREEN = "#2d6763"
ACCENT_GREEN_HOVER = "#245550"
ACCENT_BLUE = "#2d6763"
ACCENT_BLUE_HOVER = "#245550"
BTN_BG = "#ffffff"
BTN_BG_HOVER = "#f2f2ee"
BTN_FG = "#1f1f1d"
FONT_FAMILY = "Microsoft YaHei UI"


def _sample_arc(cx, cy, radius, start_deg, end_deg, steps=48):
    return [
        (
            cx + radius * math.cos(math.radians(start_deg + (end_deg - start_deg) * idx / steps)),
            cy + radius * math.sin(math.radians(start_deg + (end_deg - start_deg) * idx / steps)),
        )
        for idx in range(steps + 1)
    ]


def _draw_butt_stroke(draw, points, width, fill, tx, ty, sc):
    scaled = [(tx + x * sc, ty + y * sc) for x, y in points]
    half = (width * sc) / 2.0
    for idx in range(len(scaled) - 1):
        x0, y0 = scaled[idx]
        x1, y1 = scaled[idx + 1]
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy)
        if length < 1e-6:
            continue
        nx, ny = -dy / length * half, dx / length * half
        draw.polygon(
            [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)],
            fill=fill,
        )
        if idx > 0:
            draw.ellipse((x0 - half, y0 - half, x0 + half, y0 + half), fill=fill)


def icon_image(color="#f4fffb", size=64):
    """陰陽推し札 mark ([お]し): lit fan-plaque with negative-space お + positive し hook.

    Drawn on an 8x supersampled 64x64 canvas so both 64 px window icons and
    16 px tray icons keep crisp counter-spaces without subpixel mudding.
    """
    scale = 8
    side = 64 * scale
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))

    tile = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    gradient = ImageDraw.Draw(tile)
    top, bottom = (0x1e, 0x4d, 0x49), (0x0e, 0x23, 0x26)
    for y in range(side):
        mix = y / (side - 1)
        fill = tuple(round(top[i] + (bottom[i] - top[i]) * mix) for i in range(3)) + (255,)
        gradient.line([(0, y), (side, y)], fill=fill)
    mask = Image.new("L", (side, side), 0)
    pad = (2.5 if size <= 20 else 4.0) * scale
    rad = (13.0 if size <= 20 else 15.0) * scale
    ImageDraw.Draw(mask).rounded_rectangle(
        (pad, pad, side - pad, side - pad), radius=rad, fill=255
    )
    image.paste(tile, (0, 0), mask)

    base = ImageColor.getrgb(color) if isinstance(color, str) else tuple(color[:3])
    fg = base + (255,)

    span = (53.5 if size <= 20 else 50.0) * scale
    sc = span / 120.0
    tx = 32.0 * scale - 61.25 * sc
    ty = 32.0 * scale - 60.0 * sc

    glyph = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glyph)

    # Left lit plaque [お]
    gdraw.rounded_rectangle(
        (tx + 9.0 * sc, ty + 16.0 * sc, tx + 72.0 * sc, ty + 104.0 * sc),
        radius=16.0 * sc,
        fill=fg,
    )

    c1, r1 = (25.8, 77.0), 7.5
    c2, r2 = (46.0, 75.5), 14.0
    ang = math.atan2(c2[1] - c1[1], c2[0] - c1[0]) - math.acos(
        (r1 - r2) / math.hypot(c2[0] - c1[0], c2[1] - c1[1])
    )
    nx, ny = math.cos(ang), math.sin(ang)
    p2 = (c2[0] + r2 * nx, c2[1] + r2 * ny)
    n_deg = math.degrees(ang)
    stem_x = c1[0] + r1
    cut_w = 8.3 if size <= 20 else 8.0

    _draw_butt_stroke(gdraw, [(18.5, 37.0), (47.5, 37.0)], cut_w, (0, 0, 0, 0), tx, ty, sc)
    pts_o = [(stem_x, 24.0), (stem_x, 82.5)]
    pts_o += _sample_arc(c1[0], 82.5, r1, 0.0, 180.0, 36)[1:]
    pts_o += [(c1[0] - r1, c1[1])]
    pts_o += _sample_arc(c1[0], c1[1], r1, 180.0, n_deg + 360.0, 28)[1:]
    pts_o += [p2]
    pts_o += _sample_arc(c2[0], c2[1], r2, n_deg, 92.0, 56)[1:]
    _draw_butt_stroke(gdraw, pts_o, cut_w, (0, 0, 0, 0), tx, ty, sc)
    dx_c, dy_c, dr = tx + 58.2 * sc, ty + 35.0 * sc, 4.9 * sc
    gdraw.ellipse((dx_c - dr, dy_c - dr, dx_c + dr, dy_c + dr), fill=(0, 0, 0, 0))

    # Right positive support hook し
    pts_shi = [(87.5, 20.0), (87.5, 88.5)]
    pts_shi += _sample_arc(97.5, 88.5, 10.0, 180.0, 20.0, 44)[1:]
    ex, ey = pts_shi[-1]
    pts_shi.append((ex + 5.5 * math.sin(math.radians(20.0)), ey - 5.5 * math.cos(math.radians(20.0))))
    _draw_butt_stroke(gdraw, pts_shi, 11.2, fg, tx, ty, sc)

    image.alpha_composite(glyph)
    return image.resize((size, size), Image.Resampling.LANCZOS)


def navigation_icon(kind, size, color="#aac1b9"):
    scale = 4
    image = Image.new("RGBA", (24 * scale, 24 * scale))
    draw = ImageDraw.Draw(image)
    def line(points):
        draw.line([(x * scale, y * scale) for x, y in points], fill=color, width=2 * scale, joint="curve")
    def ellipse(box):
        draw.ellipse(tuple(v * scale for v in box), outline=color, width=2 * scale)
    if kind == "monitor":
        draw.rounded_rectangle(tuple(v * scale for v in (3, 4, 21, 17)), radius=2 * scale,
                               outline=color, width=2 * scale)
        line([(8, 21), (16, 21)])
        line([(12, 17), (12, 21)])
    elif kind == "automation":
        for y, x in ((6, 9), (12, 16), (18, 7)):
            line([(3, y), (x - 3, y)])
            line([(x + 3, y), (21, y)])
            ellipse((x - 3, y - 3, x + 3, y + 3))
    elif kind == "account":
        ellipse((8, 3, 16, 11))
        draw.arc(tuple(v * scale for v in (4, 13, 20, 27)), start=180, end=360,
                 fill=color, width=2 * scale)
        line([(4, 20), (20, 20)])
    else:
        ellipse((3, 3, 21, 21))
        line([(12, 7), (12, 12), (16, 14)])
    return image.resize((size, size), Image.Resampling.LANCZOS)


def format_task_mini_badge(tasks, is_lighted=1, has_medal=True):
    """格式化已开放任务简报：💬2/5 👍0/5 ⏱3/5。"""
    if not has_medal:
        return "无勋章"
    if not is_lighted:
        return "⚪待复活(0/10)"
    if not tasks:
        return "—"
    danmu = next((t for t in tasks if "弹幕" in t.get("title", "")), None)
    like = next((t for t in tasks if "点赞" in t.get("title", "")), None)
    watch = next((t for t in tasks if "观看" in t.get("title", "")), None)
    done_all = all((t.get("is_done") for t in (danmu, like, watch) if t))
    if done_all and any((danmu, like, watch)):
        return "✅ 全部完成"
    parts = []
    if danmu:
        prog = re.search("(\\d+/\\d+)", danmu.get("sub_title", ""))
        val = prog.group(1) if prog else "5/5" if danmu.get("is_done") else "0/5"
        parts.append(f"💬{val}")
    if like:
        prog = re.search("(\\d+/\\d+)", like.get("sub_title", ""))
        val = prog.group(1) if prog else "5/5" if like.get("is_done") else "0/5"
        parts.append(f"👍{val}")
    if watch:
        prog = re.search("(\\d+/\\d+)", watch.get("sub_title", ""))
        val = prog.group(1) if prog else "5/5" if watch.get("is_done") else "0/5"
        parts.append(f"⏱{val}")
    return " ".join(parts) if parts else "—"


class SlimScrollbar(tk.Canvas):
    """A narrow scroll thumb, invisible when the content already fits."""

    def __init__(self, parent, surface, px):
        super().__init__(parent, width=px(8), bg=parent.cget("bg"), bd=0,
                         highlightthickness=0, cursor="arrow")
        self.surface, self.px = surface, px
        self.first, self.last, self.drag = 0.0, 1.0, None
        self.pack(side="right", fill="y")
        surface.configure(yscrollcommand=self.set)
        self.bind("<Configure>", lambda _: self._draw())
        self.bind("<Button-1>", self._press)
        self.bind("<B1-Motion>", self._move)
        self.bind("<ButtonRelease-1>", lambda _: setattr(self, "drag", None))

    def set(self, first, last):
        self.first, self.last = float(first), float(last)
        self._draw()

    def _thumb(self):
        height = max(1, self.winfo_height())
        visible = max(0.0, min(1.0, self.last - self.first))
        size = min(height, max(self.px(24), height * visible))
        top = (height - size) * self.first / max(0.001, 1 - visible)
        return top, size, visible

    def _draw(self):
        self.delete("all")
        if self.first <= 0 and self.last >= 1:
            return
        top, size, _ = self._thumb()
        self.create_rectangle(self.px(2), top, self.winfo_width() - self.px(2),
                              top + size, fill="#c8d5d0", outline="")

    def _press(self, event):
        if self.last - self.first >= 1:
            return
        top, size, visible = self._thumb()
        if not top <= event.y <= top + size:
            fraction = event.y / max(1, self.winfo_height()) - visible / 2
            self.surface.yview_moveto(max(0, min(1 - visible, fraction)))
        self.drag = (event.y, self.first)

    def _move(self, event):
        if self.drag is None:
            return
        _, size, visible = self._thumb()
        fraction = self.drag[1] + (event.y - self.drag[0]) * (1 - visible) / max(1, self.winfo_height() - size)
        self.surface.yview_moveto(max(0, min(1 - visible, fraction)))


class ModernButton(tk.Button):
    """Native keyboard/accessibility behavior with rounded bitmap backgrounds."""

    def __init__(
        self,
        parent,
        text,
        command=None,
        primary=False,
        accent=ACCENT_GREEN,
        accent_hover=ACCENT_GREEN_HOVER,
        px=None,
        **kwargs,
    ):
        p = px or (lambda v: v)
        self.primary = primary
        self.accent = accent
        self.accent_hover = accent_hover
        self.px = p
        self.hovered = self.focused = False
        self._fills = (self.accent, self.accent_hover) if primary else (BTN_BG, BTN_BG_HOVER)
        font = (FONT_FAMILY, 9, "bold" if primary else "normal")
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=parent.cget("bg"),
            fg="#ffffff" if primary else BTN_FG,
            activebackground=parent.cget("bg"),
            activeforeground="#ffffff" if primary else BTN_FG,
            disabledforeground="#89979a",
            relief="flat",
            bd=0,
            highlightthickness=0,
            font=font,
            cursor="hand2",
            padx=0,
            pady=0,
            compound="center",
            takefocus=True,
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<FocusIn>", lambda _: self._focus(True))
        self.bind("<FocusOut>", lambda _: self._focus(False))
        self._render_background()

    def _focus(self, focused):
        self.focused = focused
        self._render_background()

    def _render_background(self):
        from tkinter import font as tkfont
        from PIL import ImageTk
        font = tkfont.Font(font=self.cget("font"))
        size = (max(1, font.measure(self.cget("text"))) + self.px(28), font.metrics("linespace") + self.px(10))
        self._photos = []
        for fill in (*self._fills, "#f2f2ee"):
            picture = Image.new("RGBA", size)
            draw = ImageDraw.Draw(picture)
            draw.rounded_rectangle((0, 0, size[0]-1, size[1]-1), radius=self.px(8), fill=fill,
                                   outline=self.accent if self.focused else (fill if self.primary else BORDER_CARD), width=1)
            self._photos.append(ImageTk.PhotoImage(picture, master=self))
        self._select_background()

    def _select_background(self):
        index = 2 if self.cget("state") == "disabled" else int(self.hovered)
        super().configure(image=self._photos[index])

    def configure(self, cnf=None, **kwargs):
        options = {**(cnf or {}), **kwargs} if isinstance(cnf, (dict, type(None))) else kwargs
        redraw = any(key in options and str(options[key]) != str(self.cget(key)) for key in ("text", "font"))
        result = super().configure(cnf, **kwargs)
        if redraw and hasattr(self, "_photos"):
            self._render_background()
        elif "state" in options and hasattr(self, "_photos"):
            self._select_background()
        return result

    config = configure

    def _on_enter(self, _):
        if self.cget("state") == "disabled":
            return
        self.hovered = True
        super().configure(image=self._photos[1])

    def _on_leave(self, _):
        self.hovered = False
        self._select_background()


class ToggleSwitch(tk.Canvas):
    """现代胶囊拨钮开关 (iOS/Win11 风格)"""

    def __init__(self, parent, variable=None, command=None, width=42, height=22, px=None, **kwargs):
        p = px or (lambda v: v)
        self.px = p
        self.w = p(width)
        self.h = p(height)
        super().__init__(
            parent,
            width=self.w,
            height=self.h,
            bg=parent.cget("bg"),
            highlightthickness=0,
            bd=0,
            cursor="hand2",
            **kwargs,
        )
        self.var = variable if variable is not None else tk.BooleanVar(value=False)
        self.command = command
        self.hovered = self.focused = False
        self.configure(takefocus=True)
        self.bind("<Button-1>", self.toggle)
        self.bind("<space>", self.toggle)
        self.bind("<Return>", self.toggle)
        self.bind("<Enter>", lambda _: self._appearance(hovered=True))
        self.bind("<Leave>", lambda _: self._appearance(hovered=False))
        self.bind("<FocusIn>", lambda _: self._appearance(focused=True))
        self.bind("<FocusOut>", lambda _: self._appearance(focused=False))
        self.trace_id = self.var.trace_add("write", lambda *_: self.render())
        self.bind("<Destroy>", self._remove_trace)
        self.render()

    def toggle(self, _=None):
        if self.cget("state") == "disabled":
            return "break"
        self.focus_set()
        self.var.set(not self.var.get())
        if self.command:
            self.command()
        return "break"

    def _appearance(self, **values):
        self.__dict__.update(values)
        self.render()

    def _remove_trace(self, event):
        if event.widget is self:
            self.var.trace_remove("write", self.trace_id)

    def render(self):
        self.delete("all")
        from PIL import ImageTk
        scale = 4
        w, h = self.w, self.h
        image = Image.new("RGBA", (w * scale, h * scale))
        draw = ImageDraw.Draw(image)
        val = bool(self.var.get())
        fill = (ACCENT_GREEN_HOVER if self.hovered else ACCENT_GREEN) if val else ("#c5c6c0" if self.hovered else "#d9dad5")
        margin = scale
        draw.rounded_rectangle((margin, margin, w * scale - margin - 1, h * scale - margin - 1),
                               radius=h * scale / 2, fill=fill,
                               outline="#71b6a6" if self.focused else (fill if val else "#c9cac4"),
                               width=scale)
        pad = max(2, self.px(3)) * scale
        diameter = h * scale - 2 * pad
        x = w * scale - pad - diameter if val else pad
        draw.ellipse((x, pad + scale / 2, x + diameter, pad + diameter + scale / 2), fill="#b2b3ad")
        draw.ellipse((x, pad, x + diameter, pad + diameter), fill="white")
        self.photo = ImageTk.PhotoImage(image.resize((w, h), Image.Resampling.LANCZOS), master=self)
        self.create_image(0, 0, anchor="nw", image=self.photo)


class CardFrame(tk.Frame):
    """纯白卡片容器，带淡雅边框与内边距"""

    def __init__(self, parent, px=None, padx=16, pady=12, **kwargs):
        p = px or (lambda v: v)
        super().__init__(
            parent,
            bg=BG_CARD,
            highlightbackground=BORDER_CARD,
            highlightthickness=1,
            padx=p(padx),
            pady=p(pady),
            **kwargs,
        )


def create_setting_row(parent, title, desc, widget_factory, px=None):
    """生成标准卡片设置行：左侧主副文案，右侧开关/输入"""
    p = px or (lambda v: v)
    row = tk.Frame(parent, bg=BG_CARD)
    row.pack(fill="x", pady=p(6))
    left = tk.Frame(row, bg=BG_CARD)
    left.pack(side="left", fill="x", expand=True)
    tk.Label(left, text=title, font=(FONT_FAMILY, 9, "bold"), bg=BG_CARD, fg=TEXT_MAIN).pack(
        anchor="w"
    )
    if desc:
        tk.Label(left, text=desc, font=(FONT_FAMILY, 8), bg=BG_CARD, fg=TEXT_MUTED).pack(
            anchor="w", pady=(p(1), 0)
        )
    right = widget_factory(row)
    right.pack(side="right")
    return right


def create_divider(parent, px=None):
    """卡片内部平滑细分割线"""
    p = px or (lambda v: v)
    div = tk.Frame(parent, height=1, bg=BORDER_LIGHT)
    div.pack(fill="x", pady=p(6))
    return div


def center_window(window, parent=None, width=None, height=None, px=None):
    """使窗口居中于父窗口或屏幕，避免靠边生硬"""
    window.update_idletasks()
    p = px or (lambda v: v)
    w = width or window.winfo_width() or p(400)
    h = height or window.winfo_height() or p(300)
    if parent and parent.winfo_ismapped():
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - w) // 2
        y = parent_y + (parent_h - h) // 2
    else:
        screen_w = window.winfo_screenwidth()
        screen_h = window.winfo_screenheight()
        x = (screen_w - w) // 2
        y = (screen_h - h) // 2
    window.geometry(f"{w}x{h}+{max(0, x)}+{max(0, y)}")


class Tooltip:
    """浮层悬浮提示卡"""

    def __init__(self, tree, get_data_func, px=None):
        self.tree = tree
        self.get_data = get_data_func
        self.px = px or (lambda v: v)
        self.tip_window = None
        self.last_iid = None
        self.after_id = None
        tree.bind("<Motion>", self.on_motion)
        tree.bind("<Leave>", self.on_leave)
        tree.bind("<MouseWheel>", lambda _: self.hide(), add="+")
        tree.bind("<Button-1>", lambda _: self.hide(), add="+")

    def on_motion(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            self.hide()
            return
        if iid != self.last_iid:
            self.hide()
            self.last_iid = iid
            self.after_id = self.tree.after(
                280, lambda: self.show(event.x_root + 15, event.y_root + 10, iid)
            )

    def on_leave(self, _):
        self.hide()

    def show(self, x, y, iid):
        if self.tip_window or not iid or iid == "_empty":
            return
        data = self.get_data(iid)
        if not data:
            return
        p = self.px
        self.tip_window = tw = tk.Toplevel(self.tree)
        tw.wm_overrideredirect(True)
        tw.configure(bg=BORDER_CARD, padx=1, pady=1)
        frame = tk.Frame(tw, bg=BG_CARD, padx=p(12), pady=p(10))
        frame.pack(fill="both", expand=True)
        lines = [f"【{data['name']} · 亲密度与今日任务】"]
        if data.get("live_status") == 1:
            dur = data.get("live_duration", "")
            title = data.get("title", "")
            area = data.get("area_name", "")
            dur_str = f" ({dur})" if dur else ""
            lines.append(f"正在直播: [{area or '直播'}] {title or '直播中'}{dur_str}")
        medal_name = data.get("medal_name")
        level = data.get("medal_level", 0)
        is_lit = data.get("is_lighted", 0)
        light_days = data.get("task_light_days", 0)
        intimacy = data.get("intimacy", 0)
        next_int = data.get("next_intimacy", 0)
        today_int = data.get("today_intimacy", 0)
        limit = data.get("day_limit", 20000)
        if medal_name:
            status_lit = f"已点亮 (余 {light_days} 天)" if is_lit else "已熄灭 (需点亮)"
            lines.append(f"勋章: {medal_name} Lv{level} · {status_lit}")
            if next_int and next_int > 0:
                pct = int(intimacy / next_int * 100)
                need = max(0, next_int - intimacy)
                lines.append(
                    f"升级经验: {intimacy}/{next_int} ({pct}%) · 距 Lv{level + 1} 还需 {need} 经验"
                )
            lines.append(f"今日已得亲密度: {today_int} / {limit}")
        else:
            lines.append("勋章: 未拥有该主播粉丝勋章")
            lines.append("提示：前往该主播直播间投喂 1 电池或赠送灯牌即可获取勋章")
        lines.append("─" * 32)
        tasks = data.get("tasks", [])
        if tasks:
            for t in tasks:
                title = t.get("title", "")
                sub = t.get("sub_title", "")
                done = " [已达成]" if t.get("is_done") else ""
                lines.append(f"• {title}: {sub}{done}")
        else:
            lines.append("• 暂无详细任务数据，巡检后自动刷新")
        lines.append("─" * 32)
        lines.append("双击进入直播间 · 右键可补齐弹幕/点赞")
        text = "\n".join(lines)
        label = tk.Label(
            frame,
            text=text,
            justify="left",
            bg=BG_CARD,
            fg=TEXT_MAIN,
            font=(FONT_FAMILY, 9),
            anchor="w",
        )
        label.pack()
        tw.update_idletasks()
        tw_w = tw.winfo_width()
        tw_h = tw.winfo_height()
        sw = tw.winfo_screenwidth()
        sh = tw.winfo_screenheight()
        target_x = max(10, min(x, sw - tw_w - p(15)))
        target_y = max(10, min(y, sh - tw_h - p(45)))
        tw.wm_geometry(f"+{target_x}+{target_y}")

    def hide(self):
        if self.after_id:
            self.tree.after_cancel(self.after_id)
            self.after_id = None
        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
        self.last_iid = None
