"""ThreeColumnLayout — 三栏布局共享组件

统一 ActionChainPage 和 WorkflowPage 的 PanedWindow 三栏布局。
左面板 | 中心内容 | 右面板，支持拖拽调整宽度。
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable

from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme


class ThreeColumnLayout:
    """三栏 PanedWindow 布局。

    Args:
        parent: 父容器
        left_builder: 左面板构建回调 (parent_widget) -> None
        center_builder: 中心面板构建回调 (parent_widget) -> None
        right_builder: 右面板构建回调 (parent_widget) -> None
    """

    def __init__(
        self,
        parent: tk.Widget,
        left_builder: Callable[[tk.Widget], None],
        center_builder: Callable[[tk.Widget], None],
        right_builder: Callable[[tk.Widget], None],
    ) -> None:
        th = current_theme()
        sm = scale_manager()

        self._paned = ttk.PanedWindow(
            parent, orient=tk.HORIZONTAL,
        )
        self._paned.pack(fill=tk.BOTH, expand=True, padx=sm.s(4), pady=sm.s(4))

        self._left_frame = tk.Frame(self._paned, bg=th.panel_bg)
        self._center_frame = tk.Frame(self._paned, bg=th.panel_bg)
        self._right_frame = tk.Frame(self._paned, bg=th.panel_bg)

        left_builder(self._left_frame)
        center_builder(self._center_frame)
        right_builder(self._right_frame)

        self._paned.add(self._left_frame, weight=0)
        self._paned.add(self._center_frame, weight=1)
        self._paned.add(self._right_frame, weight=0)

    @property
    def paned(self) -> ttk.PanedWindow:
        return self._paned

    @property
    def left_panel(self) -> tk.Frame:
        return self._left_frame

    @property
    def center_panel(self) -> tk.Frame:
        return self._center_frame

    @property
    def right_panel(self) -> tk.Frame:
        return self._right_frame

    def apply_theme(self) -> None:
        th = current_theme()
        for panel in (self._left_frame, self._center_frame, self._right_frame):
            if panel.winfo_exists():
                try:
                    panel.configure(bg=th.panel_bg)
                except tk.TclError:
                    pass
