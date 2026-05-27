"""QtProgressRing — PySide6 圆形进度指示器。

替代 tkinter ProgressRing，使用 QPainter + QPropertyAnimation。
支持确定进度（0.0-1.0）和不确定（旋转动画）两种模式。
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, QRectF, Property, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QPainter, QColor, QPen
from PySide6.QtWidgets import QWidget

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.qt_backend.scale import qt_scale_manager


class QtProgressRing(QWidget):
    """圆形进度指示器。

    支持确定进度（0.0-1.0）和不确定（旋转动画）两种模式。
    自动跟随主题更新颜色。
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        size: int = 36,
        progress: float = 0.0,
        indeterminate: bool = False,
    ) -> None:
        sm = qt_scale_manager()
        self._ring_size = sm.s(size)
        super().__init__(parent)
        self.setFixedSize(self._ring_size, self._ring_size)

        self._progress = max(0.0, min(1.0, progress))
        self._indeterminate = indeterminate
        self._angle: float = 0.0

        th = current_theme()
        self._track_color = QColor(th.border_default)
        self._progress_color = QColor(th.accent_blue)
        self._bg_color = QColor(th.page_bg)
        self._ring_width = sm.s(3)
        self._padding = sm.s(3)

        self._anim_timer: QTimer | None = None
        if indeterminate:
            self._start_animation()

    def set_progress(self, value: float) -> None:
        """设置进度值 0.0-1.0。"""
        self._progress = max(0.0, min(1.0, value))
        if not self._indeterminate:
            self.update()

    def start_indeterminate(self) -> None:
        """启动不确定模式旋转动画。"""
        self._indeterminate = True
        self._start_animation()

    def stop(self) -> None:
        """停止动画。"""
        self._indeterminate = False
        if self._anim_timer is not None:
            self._anim_timer.stop()
            self._anim_timer = None

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        self._track_color = QColor(theme.border_default)
        self._progress_color = QColor(theme.accent_blue)
        self._bg_color = QColor(theme.page_bg)
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), self._bg_color)

        pad = self._padding
        rect = QRectF(pad, pad, self._ring_size - 2 * pad, self._ring_size - 2 * pad)
        pen_w = self._ring_width

        track_pen = QPen(self._track_color, pen_w, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 90 * 16, 3599 * 16 // 10)

        progress_pen = QPen(self._progress_color, pen_w, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(progress_pen)

        if self._indeterminate:
            start_angle = int((90 - self._angle) * 16)
            painter.drawArc(rect, start_angle, 90 * 16)
        else:
            extent = int(self._progress * 359.9 * 16)
            painter.drawArc(rect, 90 * 16, -extent)

        painter.end()

    def _start_animation(self) -> None:
        if self._anim_timer is not None:
            return
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(30)
        self._anim_timer.timeout.connect(self._animate_step)
        self._anim_timer.start()

    def _animate_step(self) -> None:
        self._angle = (self._angle + 8) % 360
        self.update()

    def cleanup(self) -> None:
        """停止动画并清理资源。"""
        self.stop()
