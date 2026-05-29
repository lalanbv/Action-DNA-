"""DNAToggle — 统一开关/复选框/单选组件。

替代 ThemedCheckbox 和 ThemedRadio，继承 DNAWidget 获得自动主题注册。
支持三种模式：checkbox、radio、switch。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.components.base import DNAWidget


class DNAToggle(DNAWidget):
    """统一开关/复选框/单选组件。

    三种绘制模式：
    - checkbox: 圆角矩形 + 勾选动画
    - radio: 圆环 + 圆点动画
    - switch: 药丸轨道 + 滑块动画
    """

    _CHECKBOX = "checkbox"
    _RADIO = "radio"
    _SWITCH = "switch"

    _CANVAS_SIZE = 18
    _CHECKBOX_RADIUS = 4
    _RADIO_OUTER_R = 9
    _RADIO_INNER_R = 4
    _SWITCH_WIDTH = 36
    _SWITCH_HEIGHT = 20
    _SWITCH_THUMB_R = 8
    _ANIM_STEPS = 5
    _ANIM_INTERVAL = 20

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "",
        mode: str = "checkbox",
        variable: tk.Variable | None = None,
        value: Any = None,
        command: Callable[[], None] | None = None,
        *,
        checked: bool = False,
        animated: bool = True,
        **kw: Any,
    ) -> None:
        th = current_theme()
        self._text = text
        self._mode = mode
        self._variable = variable
        self._value = value
        self._command = command
        self._animated = animated
        self._anim_id: str | None = None
        self._var_trace_name: str | None = None

        if mode == self._RADIO:
            self._checked = self._check_radio_selected()
        elif variable is not None:
            try:
                self._checked = bool(variable.get())
            except (tk.TclError, ValueError):
                self._checked = checked
        else:
            self._checked = checked

        self._anim_progress = 1.0 if self._checked else 0.0
        bg = kw.pop("bg", th.page_bg)
        self._bg = bg

        canvas_w = self._SWITCH_WIDTH if mode == self._SWITCH else self._CANVAS_SIZE
        canvas_h = self._SWITCH_HEIGHT if mode == self._SWITCH else self._CANVAS_SIZE

        super().__init__(parent, bg=bg, cursor="hand2")

        self._canvas = tk.Canvas(
            self, width=canvas_w, height=canvas_h,
            bg=bg, highlightthickness=0, cursor="hand2",
        )
        self._canvas.pack(side=tk.LEFT, padx=(0, 6))

        self._label = tk.Label(
            self, text=text, bg=bg, fg=th.text_primary,
            font=th.font_body, cursor="hand2",
        )
        self._label.pack(side=tk.LEFT, fill=tk.Y)

        self._theme_colors: dict[str, str] = self._build_theme_colors(th)
        self._draw()

        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self._label.bind("<ButtonPress-1>", self._on_click)
        self.bind("<ButtonPress-1>", self._on_click)

        if self._variable:
            self._var_trace_name = self._variable.trace_add("write", self._on_var_change)

    # ── 主题颜色 ──

    def _build_theme_colors(self, th: CanvasTheme) -> dict[str, str]:
        return {
            "box_bg": th.input_bg,
            "box_border": th.border_strong,
            "box_fill": th.accent_blue,
            "check_color": th.text_on_accent,
            "track_off": th.input_bg,
            "track_on": th.accent_blue,
            "thumb_color": th.text_on_accent,
            "text_fg": th.text_primary,
            "bg": self._bg,
        }

    # ── 绘制 ──

    def _draw(self) -> None:
        if not self._canvas.winfo_exists():
            return
        self._canvas.delete("all")
        if self._mode == self._CHECKBOX:
            self._draw_checkbox()
        elif self._mode == self._RADIO:
            self._draw_radio()
        elif self._mode == self._SWITCH:
            self._draw_switch()

    def _draw_checkbox(self) -> None:
        s = self._CANVAS_SIZE
        r = self._CHECKBOX_RADIUS
        colors = self._theme_colors
        fill = colors["box_fill"] if self._anim_progress > 0 else colors["box_bg"]
        coords = self._round_rect_coords(1, 1, s - 1, s - 1, r)
        self._canvas.create_polygon(
            coords, smooth=True,
            fill=fill, outline=colors["box_border"], width=1,
        )
        if self._anim_progress > 0:
            self._draw_checkmark(colors["check_color"], self._anim_progress)

    def _draw_checkmark(self, color: str, progress: float) -> None:
        s = self._CANVAS_SIZE
        p1 = (s * 0.22, s * 0.50)
        p2 = (s * 0.40, s * 0.68)
        p3 = (s * 0.78, s * 0.30)
        if progress <= 0.5:
            t = progress * 2
            x = p1[0] + (p2[0] - p1[0]) * t
            y = p1[1] + (p2[1] - p1[1]) * t
            self._canvas.create_line(
                p1[0], p1[1], x, y,
                fill=color, width=2, capstyle=tk.ROUND,
            )
        else:
            t = (progress - 0.5) * 2
            self._canvas.create_line(
                p1[0], p1[1], p2[0], p2[1],
                fill=color, width=2, capstyle=tk.ROUND,
            )
            x = p2[0] + (p3[0] - p2[0]) * t
            y = p2[1] + (p3[1] - p2[1]) * t
            self._canvas.create_line(
                p2[0], p2[1], x, y,
                fill=color, width=2, capstyle=tk.ROUND,
            )

    def _draw_radio(self) -> None:
        s = self._CANVAS_SIZE
        cx, cy = s // 2, s // 2
        colors = self._theme_colors
        r = self._RADIO_OUTER_R
        ring_color = colors["box_fill"] if self._anim_progress > 0 else colors["box_border"]
        self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=ring_color, width=2, fill="",
        )
        if self._anim_progress > 0:
            inner_r = self._RADIO_INNER_R * self._anim_progress
            self._canvas.create_oval(
                cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
                fill=colors["check_color"], outline="",
            )

    def _draw_switch(self) -> None:
        w = self._SWITCH_WIDTH
        h = self._SWITCH_HEIGHT
        colors = self._theme_colors
        r = h // 2
        p = self._anim_progress

        track_color = colors["track_on"] if p > 0.5 else colors["track_off"]
        coords = self._round_rect_coords(0, 0, w, h, r)
        self._canvas.create_polygon(
            coords, smooth=True,
            fill=track_color, outline=colors["box_border"], width=1,
        )

        thumb_x = r + p * (w - 2 * r)
        thumb_r = self._SWITCH_THUMB_R
        cy = h // 2
        self._canvas.create_oval(
            thumb_x - thumb_r, cy - thumb_r,
            thumb_x + thumb_r, cy + thumb_r,
            fill=colors["thumb_color"], outline="",
        )

    @staticmethod
    def _round_rect_coords(x1: float, y1: float, x2: float, y2: float,
                           r: float) -> list[float]:
        return [
            x1 + r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1,
        ]

    # ── 交互 ──

    def _check_radio_selected(self) -> bool:
        if self._variable is None:
            return False
        try:
            return self._variable.get() == self._value
        except (tk.TclError, ValueError):
            return False

    def _on_click(self, _event: tk.Event | None = None) -> None:
        if self._mode == self._RADIO:
            if self._variable:
                self._variable.set(self._value)
            else:
                self._checked = True
                self._animate_toggle()
        else:
            self._checked = not self._checked
            if self._variable:
                self._variable.set(self._checked)
            self._animate_toggle()
        if self._command:
            self._command()

    def _on_var_change(self, *_args: Any) -> None:
        if self._mode == self._RADIO:
            new_val = self._check_radio_selected()
        else:
            try:
                new_val = bool(self._variable.get())
            except (tk.TclError, ValueError):
                return
        if new_val != self._checked:
            self._checked = new_val
            self._animate_toggle()

    # ── 动画 ──

    def _cancel_anim(self) -> None:
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _animate_toggle(self) -> None:
        if not self._animated:
            self._anim_progress = 1.0 if self._checked else 0.0
            self._draw()
            return
        self._cancel_anim()
        start = self._anim_progress
        target = 1.0 if self._checked else 0.0
        if start == target:
            self._draw()
            return
        counter = [0]
        steps = self._ANIM_STEPS

        def step() -> None:
            counter[0] += 1
            t = min(counter[0] / steps, 1.0)
            self._anim_progress = start + (target - start) * t
            self._draw()
            if counter[0] < steps and self.winfo_exists():
                self._anim_id = self.after(self._ANIM_INTERVAL, step)
            else:
                self._anim_progress = target
                self._anim_id = None

        step()

    # ── 公共 API ──

    def select(self) -> None:
        self._checked = True
        if self._mode == self._RADIO:
            if self._variable:
                self._variable.set(self._value)
        else:
            if self._variable:
                self._variable.set(True)
        self._anim_progress = 1.0
        self._draw()

    def deselect(self) -> None:
        self._checked = False
        if self._mode != self._RADIO and self._variable:
            self._variable.set(False)
        self._anim_progress = 0.0
        self._draw()

    def toggle(self) -> None:
        self._on_click(None)

    def is_checked(self) -> bool:
        return self._checked

    def get_value(self) -> Any:
        if self._mode == self._RADIO:
            return self._value if self._checked else None
        return self._checked

    def configure(self, **kw: Any) -> None:
        if "text" in kw:
            self._text = kw.pop("text")
            self._label.configure(text=self._text)
        if "variable" in kw:
            old_var = self._variable
            old_trace = self._var_trace_name
            self._variable = kw.pop("variable")
            self._var_trace_name = None
            if old_var is not None and old_trace is not None:
                try:
                    old_var.trace_remove("write", old_trace)
                except (tk.TclError, ValueError):
                    pass
            if self._variable:
                self._var_trace_name = self._variable.trace_add("write", self._on_var_change)
        if "value" in kw:
            self._value = kw.pop("value")
        if "command" in kw:
            self._command = kw.pop("command")
        if "fg" in kw:
            self._label.configure(fg=kw.pop("fg"))
        if "bg" in kw:
            self._bg = kw.pop("bg")
            super().configure(bg=self._bg)
            self._canvas.configure(bg=self._bg)
            self._label.configure(bg=self._bg)
        if "state" in kw:
            state = kw.pop("state")
            cursor = "arrow" if state == "disabled" else "hand2"
            self.configure(cursor=cursor)
            self._canvas.configure(cursor=cursor)
            self._label.configure(cursor=cursor)

    config = configure

    def cget(self, key: str) -> Any:
        if key == "text":
            return self._text
        if key == "variable":
            return self._variable
        if key == "value":
            return self._value
        if key == "checked":
            return self._checked
        return super().cget(key)

    # ── 主题 ──

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        if not self.winfo_exists():
            return
        try:
            parent_bg = self.master.cget("bg")
            if parent_bg and isinstance(parent_bg, str) and parent_bg.startswith("#"):
                self._bg = parent_bg
        except (tk.TclError, AttributeError):
            pass
        self._theme_colors = self._build_theme_colors(theme)
        self._canvas.configure(bg=self._bg)
        self._label.configure(bg=self._bg, fg=theme.text_primary)
        self.configure(bg=self._bg)
        self._draw()
