"""ThemedCheckbox — Canvas 自绘圆角勾选框。

替代原生 tk.Checkbutton，带勾选动画。
API 与 tk.Checkbutton 兼容。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from src.panel.canvas.theme import CanvasTheme, current_theme, theme_registry


class ThemedCheckbox(tk.Frame):
    """Canvas 自绘圆角勾选框 + 文字标签。"""

    _BOX_SIZE = 18
    _BOX_RADIUS = 4
    _ANIM_STEPS = 5
    _ANIM_INTERVAL = 20

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "",
        variable: tk.BooleanVar | tk.Variable | None = None,
        command: Callable[[], None] | None = None,
        **kw: Any,
    ) -> None:
        th = current_theme()
        self._text = text
        self._command = command
        self._variable = variable
        self._checked = variable.get() if variable else False
        self._anim_id: str | None = None
        self._anim_progress = 1.0 if self._checked else 0.0

        bg = kw.pop("bg", th.page_bg)
        super().__init__(parent, bg=bg, cursor="hand2")
        self._bg = bg

        self._canvas = tk.Canvas(
            self, width=self._BOX_SIZE, height=self._BOX_SIZE,
            bg=bg, highlightthickness=0, cursor="hand2",
        )
        self._canvas.pack(side=tk.LEFT, padx=(0, 6))

        self._label = tk.Label(
            self, text=text, bg=bg, fg=th.text_primary,
            font=th.font_body, cursor="hand2",
        )
        self._label.pack(side=tk.LEFT, fill=tk.Y)

        self._theme_colors: dict[str, str] = {
            "box_bg": th.input_bg,
            "box_border": th.border_strong,
            "box_fill": th.accent_blue,
            "check_color": th.text_on_accent,
            "text_fg": th.text_primary,
            "bg": bg,
        }
        self._draw()

        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self._label.bind("<ButtonPress-1>", self._on_click)
        self.bind("<ButtonPress-1>", self._on_click)
        self.bind("<Destroy>", self._on_destroy)

        if self._variable:
            self._variable.trace_add("write", self._on_var_change)

        self._theme_reg_id = theme_registry().register(self)

    @staticmethod
    def _round_rect_coords(x1: float, y1: float, x2: float, y2: float,
                           r: float) -> list[float]:
        """生成圆角矩形的 Canvas 坐标点列表。"""
        return [
            x1 + r, y1, x2 - r, y1,
            x2, y1, x2, y1 + r,
            x2, y2 - r, x2, y2,
            x2 - r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r,
            x1, y1 + r, x1, y1,
        ]

    def _draw(self) -> None:
        if not self._canvas.winfo_exists():
            return
        self._canvas.delete("all")
        s = self._BOX_SIZE
        r = self._BOX_RADIUS
        colors = self._theme_colors

        fill_color = colors["box_fill"] if self._anim_progress > 0 else colors["box_bg"]
        coords = self._round_rect_coords(1, 1, s - 1, s - 1, r)
        self._canvas.create_polygon(
            coords, smooth=True,
            fill=fill_color, outline=colors["box_border"], width=1,
        )

        if self._anim_progress > 0:
            self._draw_checkmark(colors["check_color"], self._anim_progress)

    def _draw_checkmark(self, color: str, progress: float) -> None:
        s = self._BOX_SIZE
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

    def _on_click(self, _event: tk.Event) -> None:
        self._checked = not self._checked
        if self._variable:
            self._variable.set(self._checked)
        self._animate_toggle()
        if self._command:
            self._command()

    def _on_var_change(self, *_args: Any) -> None:
        try:
            new_val = bool(self._variable.get())  # type: ignore[union-attr]
        except (tk.TclError, ValueError):
            return
        if new_val != self._checked:
            self._checked = new_val
            self._animate_toggle()

    def _cancel_anim(self) -> None:
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _animate_toggle(self) -> None:
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

    def _on_destroy(self, _event: tk.Event) -> None:
        self._cancel_anim()
        theme_registry().unregister(self._theme_reg_id)

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        if not self.winfo_exists():
            return
        self._theme_colors = {
            "box_bg": theme.input_bg,
            "box_border": theme.border_strong,
            "box_fill": theme.accent_blue,
            "check_color": theme.text_on_accent,
            "text_fg": theme.text_primary,
            "bg": self._bg,
        }
        self._canvas.configure(bg=self._bg)
        self._label.configure(bg=self._bg, fg=theme.text_primary)
        self.configure(bg=self._bg)
        self._draw()

    # ── tk.Checkbutton 兼容 API ──

    def configure(self, **kw: Any) -> None:
        if "text" in kw:
            self._text = kw.pop("text")
            self._label.configure(text=self._text)
        if "variable" in kw:
            self._variable = kw.pop("variable")
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
        return super().cget(key)

    def select(self) -> None:
        self._checked = True
        if self._variable:
            self._variable.set(True)
        self._anim_progress = 1.0
        self._draw()

    def deselect(self) -> None:
        self._checked = False
        if self._variable:
            self._variable.set(False)
        self._anim_progress = 0.0
        self._draw()

    def toggle(self) -> None:
        self._on_click(None)  # type: ignore[arg-type]
