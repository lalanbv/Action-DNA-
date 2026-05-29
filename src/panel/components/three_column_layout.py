"""ThreeColumnLayout — 三栏布局共享组件

统一 ActionChainPage 和 WorkflowPage 的 PanedWindow 三栏布局。
左面板 | 中心内容 | 右面板，支持拖拽调整宽度。
"""

import tkinter as tk
from typing import Callable

from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme
from src.panel.widgets import themed_paned_window


class ThreeColumnLayout:
    """三栏 PanedWindow 布局。

    Args:
        parent: 父容器
        left_builder: 左面板构建回调 (parent_widget) -> None
        center_builder: 中心面板构建回调 (parent_widget) -> None
        right_builder: 右面板构建回调 (parent_widget) -> None
        left_width: 左面板初始宽度（未缩放，会自动 scale）
        right_width: 右面板初始宽度（未缩放，会自动 scale）
    """

    def __init__(
        self,
        parent: tk.Widget,
        left_builder: Callable[[tk.Widget], None],
        center_builder: Callable[[tk.Widget], None],
        right_builder: Callable[[tk.Widget], None],
        *,
        left_width: int = 0,
        right_width: int = 0,
        left_minsize: int = 80,
        right_minsize: int = 120,
    ) -> None:
        th = current_theme()
        sm = scale_manager()

        if left_width <= 0:
            left_width = th.panel_width_left
        if right_width <= 0:
            right_width = th.panel_width_right

        self._paned = themed_paned_window(parent, orient=tk.HORIZONTAL)
        self._paned.pack(fill=tk.BOTH, expand=True, padx=sm.s(4), pady=sm.s(4))

        self._left_frame = tk.Frame(
            self._paned, bg=th.panel_bg, width=sm.s(left_width),
        )
        self._left_frame.pack_propagate(False)

        self._center_frame = tk.Frame(self._paned, bg=th.panel_bg)

        self._right_frame = tk.Frame(
            self._paned, bg=th.panel_bg, width=sm.s(right_width),
        )
        self._right_frame.pack_propagate(False)

        left_builder(self._left_frame)
        center_builder(self._center_frame)
        right_builder(self._right_frame)

        self._paned.add(self._left_frame, stretch="never", minsize=left_minsize)
        self._paned.add(self._center_frame, stretch="always", minsize=200)
        self._paned.add(self._right_frame, stretch="never", minsize=right_minsize)

    @property
    def paned(self) -> tk.PanedWindow:
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
        sm = scale_manager()
        for panel in (self._left_frame, self._center_frame, self._right_frame):
            if panel.winfo_exists():
                try:
                    panel.configure(bg=th.panel_bg)
                except tk.TclError:
                    pass
        if self._paned.winfo_exists():
            try:
                self._paned.configure(bg=th.separator_color, sashwidth=sm.s(2))
            except tk.TclError:
                pass
        from src.panel.widgets import cascade_theme
        for panel in (self._left_frame, self._center_frame, self._right_frame):
            if panel.winfo_exists():
                cascade_theme(panel)
