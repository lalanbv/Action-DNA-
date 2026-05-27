"""SnapManager — PanedWindow 分隔条贴边吸附

当用户拖拽分隔条到接近预设位置时，自动吸附到最近的预设位置。
支持折叠（吸附到 0）和展开到常用宽度。
"""

import tkinter as tk
from tkinter import ttk


class SnapManager:
    """PanedWindow 分隔条贴边吸附管理器。

    Args:
        paned: 目标 PanedWindow 控件
        threshold: 吸附阈值（像素），默认 8px
    """

    SNAP_THRESHOLD = 8

    def __init__(
        self,
        paned: tk.PanedWindow | ttk.PanedWindow,
        threshold: int = 8,
    ) -> None:
        self._paned = paned
        self._threshold = threshold
        self._snap_positions: list[float] = []
        self._dragging = False
        self._bound = False
        self._sash_index = 0

    def add_snap_position(self, fraction: float) -> None:
        """添加吸附位置。

        Args:
            fraction: 0.0~1.0 之间的比例值，表示面板占总宽度的比例。
                      0.0 表示完全折叠。
        """
        if fraction not in self._snap_positions:
            self._snap_positions.append(fraction)
            self._snap_positions.sort()

    def add_snap_positions(self, fractions: list[float]) -> None:
        """批量添加吸附位置。"""
        for f in fractions:
            self.add_snap_position(f)

    def bind_sash_snap(self, sash_index: int = 0) -> None:
        """绑定指定分隔条的吸附行为。

        Args:
            sash_index: 分隔条索引（0=第一个，即左面板右边缘）
        """
        self._sash_index = sash_index
        self._paned.bind("<ButtonPress-1>", self._on_press)
        self._paned.bind("<ButtonRelease-1>", self._on_release)
        self._bound = True

    def _on_press(self, event: tk.Event) -> None:
        self._dragging = True

    def _on_release(self, event: tk.Event) -> None:
        if not self._dragging:
            return
        self._dragging = False

        if not self._snap_positions:
            return

        try:
            total_w = self._paned.winfo_width()
            if total_w < 10:
                return

            sash_pos = self._paned.sashpos(self._sash_index)
            current_frac = sash_pos / total_w

            best_snap = None
            best_dist = self._threshold / total_w

            for snap_frac in self._snap_positions:
                dist = abs(current_frac - snap_frac)
                if dist < best_dist:
                    best_dist = dist
                    best_snap = snap_frac

            if best_snap is not None:
                new_pos = int(total_w * best_snap)
                self._paned.sashpos(self._sash_index, new_pos)
        except (tk.TclError, IndexError):
            pass

    @staticmethod
    def standard_left_snap() -> list[float]:
        """左面板标准吸附位置：折叠 + 两个常用宽度。"""
        return [0.0, 0.15, 0.25]

    @staticmethod
    def standard_right_snap() -> list[float]:
        """右面板标准吸附位置。"""
        return [0.8, 0.85, 1.0]
