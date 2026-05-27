"""ThemedRadio — Canvas 自绘圆形单选按钮。

替代原生 tk.Radiobutton，带选中动画。
API 与 tk.Radiobutton 兼容。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from src.panel.canvas.theme import CanvasTheme, current_theme, theme_registry


class ThemedRadio(tk.Frame):
    """Canvas 自绘圆形单选按钮 + 文字标签。"""

    _DOT_SIZE = 18
    _DOT_RADIUS = 9
    _INNER_RADIUS = 4
    _ANIM_STEPS = 4
    _ANIM_INTERVAL = 20

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "",
        variable: tk.Variable | None = None,
        value: Any = None,
        command: Callable[[], None] | None = None,
        **kw: Any,
    ) -> None:
        th = current_theme()
        self._text = text
        self._variable = variable
        self._value = value
        self._command = command
        self._is_selected = self._check_selected()
        self._anim_id: str | None = None
        self._anim_progress = 1.0 if self._is_selected else 0.0

        bg = kw.pop("bg", th.page_bg)
        super().__init__(parent, bg=bg, cursor="hand2")
        self._bg = bg

        self._canvas = tk.Canvas(
            self, width=self._DOT_SIZE, height=self._DOT_SIZE,
            bg=bg, highlightthickness=0, cursor="hand2",
        )
        self._canvas.pack(side=tk.LEFT, padx=(0, 6))

        self._label = tk.Label(
            self, text=text, bg=bg, fg=th.text_primary,
            font=th.font_body, cursor="hand2",
        )
        self._label.pack(side=tk.LEFT, fill=tk.Y)

        self._theme_colors: dict[str, str] = {
            "ring_border": th.border_strong,
            "ring_fill": th.accent_blue,
            "dot_color": th.text_on_accent,
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

    def _check_selected(self) -> bool:
        if self._variable is None:
            return False
        try:
            return self._variable.get() == self._value
        except (tk.TclError, ValueError):
            return False

    def _draw(self) -> None:
        if not self._canvas.winfo_exists():
            return
        self._canvas.delete("all")
        s = self._DOT_SIZE
        cx, cy = s // 2, s // 2
        colors = self._theme_colors
        r = self._DOT_RADIUS

        ring_color = colors["ring_fill"] if self._anim_progress > 0 else colors["ring_border"]
        self._canvas.create_oval(
            cx - r, cy - r, cx + r, cy + r,
            outline=ring_color, width=2, fill="",
        )

        if self._anim_progress > 0:
            inner_r = self._INNER_RADIUS * self._anim_progress
            self._canvas.create_oval(
                cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r,
                fill=colors["dot_color"], outline="",
            )

    def _on_click(self, _event: tk.Event) -> None:
        if self._variable:
            self._variable.set(self._value)
        if self._command:
            self._command()

    def _on_var_change(self, *_args: Any) -> None:
        is_sel = self._check_selected()
        if is_sel != self._is_selected:
            self._is_selected = is_sel
            self._animate_toggle()

    def _cancel_anim(self) -> None:
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _animate_toggle(self) -> None:
        self._cancel_anim()
        start = self._anim_progress
        target = 1.0 if self._is_selected else 0.0
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
            "ring_border": theme.border_strong,
            "ring_fill": theme.accent_blue,
            "dot_color": theme.text_on_accent,
            "text_fg": theme.text_primary,
            "bg": self._bg,
        }
        self._canvas.configure(bg=self._bg)
        self._label.configure(bg=self._bg, fg=theme.text_primary)
        self.configure(bg=self._bg)
        self._draw()

    # ── tk.Radiobutton 兼容 API ──

    def configure(self, **kw: Any) -> None:
        if "text" in kw:
            self._text = kw.pop("text")
            self._label.configure(text=self._text)
        if "variable" in kw:
            self._variable = kw.pop("variable")
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
        return super().cget(key)

    def select(self) -> None:
        if self._variable:
            self._variable.set(self._value)

    def deselect(self) -> None:
        pass
