"""QtSkeletonLoader — PySide6 加载占位符，在数据加载前显示内容轮廓。

替代 tkinter SkeletonLoader，使用 QPropertyAnimation 实现平滑脉冲动画。
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor
from PySide6.QtWidgets import QWidget, QVBoxLayout

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.qt_backend.scale import qt_scale_manager


class QtSkeletonLine(QWidget):
    """单行骨架占位条。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        width: int = 200,
        height: int = 12,
    ) -> None:
        sm = qt_scale_manager()
        th = current_theme()
        super().__init__(parent)
        self.setFixedHeight(sm.s(height))
        self.setMaximumWidth(sm.s(width))
        self._bar_color = QColor(th.bg_surface)
        self._hover_color = QColor(th.bg_surface_hover)
        self._bg_color = QColor(th.page_bg)
        self._pulse_state = False
        self._anim_timer: QTimer | None = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self._bg_color)

        bar_rect = self.rect().adjusted(0, 0, 0, 0)
        color = self._hover_color if self._pulse_state else self._bar_color
        painter.setBrush(color)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(bar_rect, 4, 4)
        painter.end()

    def start_pulse(self) -> None:
        if self._anim_timer is not None:
            return
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(600)
        self._anim_timer.timeout.connect(self._pulse_step)
        self._anim_timer.start()

    def stop_pulse(self) -> None:
        if self._anim_timer is not None:
            self._anim_timer.stop()
            self._anim_timer = None

    def _pulse_step(self) -> None:
        self._pulse_state = not self._pulse_state
        self.update()

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        self._bar_color = QColor(theme.bg_surface)
        self._hover_color = QColor(theme.bg_surface_hover)
        self._bg_color = QColor(theme.page_bg)
        self.update()

    def cleanup(self) -> None:
        self.stop_pulse()


class QtSkeletonLoader(QWidget):
    """多行骨架加载器，模拟内容区块的加载状态。"""

    def __init__(
        self,
        parent: QWidget | None = None,
        lines: int = 3,
        line_width: int = 200,
        line_height: int = 12,
        spacing: int = 8,
    ) -> None:
        sm = qt_scale_manager()
        th = current_theme()
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(sm.s(spacing))

        self._lines: list[QtSkeletonLine] = []
        for i in range(lines):
            w = line_width if i < lines - 1 else int(line_width * 0.6)
            line = QtSkeletonLine(self, width=w, height=line_height)
            layout.addWidget(line)
            self._lines.append(line)

    def start_pulse(self) -> None:
        for line in self._lines:
            line.start_pulse()

    def stop_pulse(self) -> None:
        for line in self._lines:
            line.stop_pulse()

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        for line in self._lines:
            line.apply_theme(theme)

    def cleanup(self) -> None:
        self.stop_pulse()
