"""ProgressRing — 圆形进度指示器，用于加载/执行进度展示。"""

from __future__ import annotations

import tkinter as tk

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.components.base import DNAWidget


class ProgressRing(DNAWidget):
    """圆形进度指示器。

    支持确定进度（0.0-1.0）和不确定（旋转动画）两种模式。
    自动跟随主题更新颜色。
    """

    __slots__ = ("_canvas", "_arc_id", "_bg_arc_id", "_progress",
                 "_indeterminate", "_anim_id", "_angle", "_size")

    def __init__(
        self,
        parent: tk.Widget,
        size: int = 36,
        progress: float = 0.0,
        indeterminate: bool = False,
        **kw,
    ) -> None:
        self._progress = max(0.0, min(1.0, progress))
        self._indeterminate = indeterminate
        self._anim_id: str | None = None
        self._angle: float = 0.0

        th = current_theme()
        sm = scale_manager()
        self._size = sm.s(size)
        kw.setdefault("bg", th.page_bg)
        super().__init__(parent, **kw)

        self._canvas = tk.Canvas(
            self,
            width=self._size,
            height=self._size,
            bg=th.page_bg,
            highlightthickness=0,
        )
        self._canvas.pack()

        pad = sm.s(3)
        ring_w = sm.s(3)
        coords = (pad, pad, self._size - pad, self._size - pad)
        self._bg_arc_id = self._canvas.create_arc(
            *coords,
            start=90, extent=359.9,
            style=tk.ARC,
            outline=th.border_default,
            width=ring_w,
        )
        self._arc_id = self._canvas.create_arc(
            *coords,
            start=90, extent=0,
            style=tk.ARC,
            outline=th.accent_blue,
            width=ring_w,
        )

        if indeterminate:
            self._start_animation()

    def set_progress(self, value: float) -> None:
        """设置进度值 0.0-1.0。"""
        self._progress = max(0.0, min(1.0, value))
        if not self._indeterminate:
            extent = self._progress * 359.9
            self._canvas.itemconfig(self._arc_id, extent=extent)

    def start_indeterminate(self) -> None:
        """启动不确定模式旋转动画。"""
        self._indeterminate = True
        self._start_animation()

    def stop(self) -> None:
        """停止动画。"""
        self._indeterminate = False
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _start_animation(self) -> None:
        if self._anim_id is not None:
            return
        self._animate_step()

    def _animate_step(self) -> None:
        if not self.winfo_exists():
            return
        self._angle = (self._angle + 8) % 360
        self._canvas.itemconfig(
            self._arc_id, start=90 - self._angle, extent=90,
        )
        self._anim_id = self.after(30, self._animate_step)

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        super().apply_theme(theme)
        if theme is None:
            theme = current_theme()
        self._canvas.configure(bg=theme.page_bg)
        self.configure(bg=theme.page_bg)
        self._canvas.itemconfig(self._bg_arc_id, outline=theme.border_default)
        self._canvas.itemconfig(self._arc_id, outline=theme.accent_blue)

    def destroy(self) -> None:
        self.stop()
        super().destroy()
