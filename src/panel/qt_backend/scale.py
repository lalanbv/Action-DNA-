"""Qt DPI 缩放管理 — 基于 QScreen 的 ScaleManager。"""

from __future__ import annotations

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSize

from src.panel.canvas.scale_constants import BASE_DPI, COMPACT_THRESHOLD, WIDE_THRESHOLD, Breakpoint


class QtScaleManager:
    """基于 Qt QScreen 的 DPI 缩放管理器。

    与 tkinter ScaleManager 相同的接口，但使用 QScreen.logicalDotsPerInch()。
    """

    def __init__(self) -> None:
        self._scale_factor: float = 1.0
        self._breakpoint: Breakpoint = Breakpoint.NORMAL

    def detect(self) -> None:
        """从 QScreen 检测 DPI 缩放因子。"""
        app = QApplication.instance()
        if app is None:
            return
        screen = app.primaryScreen()
        if screen is None:
            return
        dpi = screen.logicalDotsPerInch()
        self._scale_factor = dpi / BASE_DPI
        if self._scale_factor < 1.0:
            self._scale_factor = 1.0

    @property
    def scale_factor(self) -> float:
        return self._scale_factor

    def s(self, value: int) -> int:
        """缩放像素值。"""
        return int(value * self._scale_factor)

    def s_font(self, base_size: int) -> int:
        """返回字体大小。Qt 内置 DPI 感知，无需额外缩放。"""
        return max(8, base_size)

    def breakpoint(self) -> Breakpoint:
        return self._breakpoint

    def update_breakpoint(self, width: int) -> None:
        """根据窗口宽度更新断点。"""
        if width < COMPACT_THRESHOLD:
            self._breakpoint = Breakpoint.COMPACT
        elif width > WIDE_THRESHOLD:
            self._breakpoint = Breakpoint.WIDE
        else:
            self._breakpoint = Breakpoint.NORMAL

    def initial_size(self) -> tuple[int, int]:
        """计算初始窗口大小（屏幕 72%，上限 1100x780，下限 640x480）。"""
        app = QApplication.instance()
        if app is None:
            return (1100, 780)
        screen = app.primaryScreen()
        if screen is None:
            return (1100, 780)
        geo = screen.availableGeometry()
        w = min(1100, max(640, int(geo.width() * 0.72)))
        h = min(780, max(480, int(geo.height() * 0.72)))
        return (w, h)

    def min_size(self) -> tuple[int, int]:
        """返回最小窗口大小。"""
        return (self.s(640), self.s(480))


_qt_scale_manager: QtScaleManager | None = None


def qt_scale_manager() -> QtScaleManager:
    """获取全局 QtScaleManager 单例。"""
    global _qt_scale_manager
    if _qt_scale_manager is None:
        _qt_scale_manager = QtScaleManager()
    return _qt_scale_manager
