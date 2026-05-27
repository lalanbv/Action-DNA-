"""Breadcrumb — 页面层级导航，显示当前页面路径并可点击返回。"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.components.base import DNAWidget


class Breadcrumb(DNAWidget):
    """面包屑导航条。

    接收路径段列表和回调，渲染为可点击的层级路径。
    例: ["主页", "工作流编辑器"] → 主页 › 工作流编辑器
    """

    __slots__ = ("_segments", "_on_navigate", "_sep", "_items")

    def __init__(
        self,
        parent: tk.Widget,
        segments: list[str] | None = None,
        on_navigate: Callable[[int], None] | None = None,
        **kw,
    ) -> None:
        th = current_theme()
        sm = scale_manager()
        kw.setdefault("bg", th.breadcrumb_bg)
        super().__init__(parent, **kw)

        self._segments = segments or []
        self._on_navigate = on_navigate
        self._sep = " › "
        self._items: list[tuple[tk.Label, str]] = []

        self.configure(height=sm.s(th.breadcrumb_height))
        self.pack_propagate(False)
        self._rebuild()

    def set_segments(self, segments: list[str]) -> None:
        """更新面包屑路径段。"""
        self._segments = segments
        self._rebuild()

    def _rebuild(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self._items.clear()

        th = current_theme()
        sm = scale_manager()
        pad_left = sm.s(th.pad_sm)

        for i, seg in enumerate(self._segments):
            is_last = i == len(self._segments) - 1
            fg = th.text_primary if is_last else th.text_secondary
            cursor = "arrow" if is_last else "hand2"

            lbl = tk.Label(
                self,
                text=seg,
                bg=th.breadcrumb_bg,
                fg=fg,
                font=th.font_small,
                cursor=cursor,
                padx=sm.s(2),
                pady=sm.s(2),
            )
            lbl.pack(side=tk.LEFT, padx=(pad_left if i == 0 else 0, 0))
            pad_left = 0

            if not is_last and self._on_navigate:
                lbl.bind("<Button-1>", lambda _e, idx=i: self._on_navigate(idx))
                lbl.bind("<Enter>", lambda _e, l=lbl: l.configure(fg=th.text_primary))
                lbl.bind("<Leave>", lambda _e, l=lbl, c=fg: l.configure(fg=c))

            self._items.append((lbl, seg))

            if not is_last:
                sep_lbl = tk.Label(
                    self,
                    text=self._sep,
                    bg=th.breadcrumb_bg,
                    fg=th.text_muted,
                    font=th.font_small,
                )
                sep_lbl.pack(side=tk.LEFT)
                self._items.append((sep_lbl, self._sep))

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        super().apply_theme(theme)
        if theme is None:
            theme = current_theme()
        sm = scale_manager()
        self.configure(bg=theme.breadcrumb_bg, height=sm.s(theme.breadcrumb_height))
        self._rebuild()
