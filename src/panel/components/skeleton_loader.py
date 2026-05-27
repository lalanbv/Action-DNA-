"""SkeletonLoader — 加载占位符，在数据加载前显示内容轮廓。"""

from __future__ import annotations

import tkinter as tk

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.components.base import DNAWidget


class SkeletonLine(DNAWidget):
    """单行骨架占位条。"""

    __slots__ = ("_bar", "_anim_id", "_alpha_state")

    def __init__(
        self,
        parent: tk.Widget,
        width: int = 200,
        height: int = 12,
        **kw,
    ) -> None:
        th = current_theme()
        sm = scale_manager()
        kw.setdefault("bg", th.page_bg)
        super().__init__(parent, **kw)

        self._alpha_state = False
        self._anim_id: str | None = None
        self._bar = tk.Frame(
            self,
            bg=th.bg_surface_hover,
            width=sm.s(width),
            height=sm.s(height),
        )
        self._bar.pack(fill=tk.X)
        self._bar.pack_propagate(False)

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        super().apply_theme(theme)
        if theme is None:
            theme = current_theme()
        self.configure(bg=theme.page_bg)
        self._bar.configure(
            bg=theme.bg_surface_hover if self._alpha_state else theme.bg_surface,
        )

    def start_pulse(self) -> None:
        self._pulse_step()

    def stop_pulse(self) -> None:
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _pulse_step(self) -> None:
        if not self.winfo_exists():
            return
        self._alpha_state = not self._alpha_state
        th = current_theme()
        self._bar.configure(
            bg=th.bg_surface_hover if self._alpha_state else th.bg_surface,
        )
        self._anim_id = self.after(600, self._pulse_step)

    def destroy(self) -> None:
        self.stop_pulse()
        super().destroy()


class SkeletonLoader(DNAWidget):
    """多行骨架加载器，模拟内容区块的加载状态。"""

    __slots__ = ("_lines",)

    def __init__(
        self,
        parent: tk.Widget,
        lines: int = 3,
        line_width: int = 200,
        line_height: int = 12,
        spacing: int = 8,
        **kw,
    ) -> None:
        th = current_theme()
        sm = scale_manager()
        kw.setdefault("bg", th.page_bg)
        super().__init__(parent, **kw)

        self._lines: list[SkeletonLine] = []
        for i in range(lines):
            w = line_width if i < lines - 1 else int(line_width * 0.6)
            line = SkeletonLine(self, width=w, height=line_height)
            line.pack(pady=(sm.s(spacing) if i > 0 else 0, 0))
            self._lines.append(line)

    def start_pulse(self) -> None:
        for line in self._lines:
            line.start_pulse()

    def stop_pulse(self) -> None:
        for line in self._lines:
            line.stop_pulse()

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        super().apply_theme(theme)
        if theme is None:
            theme = current_theme()
        self.configure(bg=theme.page_bg)

    def destroy(self) -> None:
        self.stop_pulse()
        super().destroy()
