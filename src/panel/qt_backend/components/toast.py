"""QtToastManager — PySide6 应用内轻量通知弹窗。

替代 tkinter ToastManager，使用 QFrame + QGraphicsOpacityEffect 实现淡入淡出。
出现在主窗口右上角，自动消失（默认 3s），支持堆叠。
级别颜色：info=蓝/success=绿/warning=黄/error=红。
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QGraphicsOpacityEffect, QHBoxLayout, QLabel, QFrame, QVBoxLayout, QWidget,
)

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.qt_backend.scale import qt_scale_manager

_LEVEL_COLORS = {
    "info": "accent_blue",
    "success": "accent_green",
    "warning": "accent_orange",
    "error": "accent_red",
}

_TOAST_DURATION_MS = 3000


class QtToastNotification(QFrame):
    """单条 toast 通知，带淡入淡出效果。"""

    _border_radius = 6

    def __init__(
        self,
        parent: QWidget,
        message: str,
        level: str = "info",
        duration_ms: int = _TOAST_DURATION_MS,
    ) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        accent_attr = _LEVEL_COLORS.get(level, "accent_blue")
        accent = getattr(th, accent_attr, th.accent_blue)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        outer = QFrame()
        outer.setStyleSheet(f"""
            QFrame {{
                background-color: {th.bg_surface};
                border: 1px solid {accent};
                border-left: {sm.s(3)}px solid {accent};
                border-radius: {self._border_radius}px;
                padding: {sm.s(8)}px {sm.s(12)}px;
            }}
        """)

        inner_layout = QHBoxLayout(outer)
        inner_layout.setContentsMargins(sm.s(8), sm.s(4), sm.s(8), sm.s(4))

        label = QLabel(message)
        label.setWordWrap(True)
        label.setMaximumWidth(sm.s(280))
        label.setStyleSheet(f"""
            QLabel {{
                color: {th.text_primary};
                background: transparent;
                border: none;
            }}
        """)
        inner_layout.addWidget(label)
        layout.addWidget(outer)

        self._opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._opacity_effect.setOpacity(1.0)

        self.setFixedSize(self.sizeHint())

        self._auto_close_timer = QTimer(self)
        self._auto_close_timer.setSingleShot(True)
        self._auto_close_timer.setInterval(duration_ms)
        self._auto_close_timer.timeout.connect(self._fade_out)
        self._auto_close_timer.start()

    def show_at(self, x: int, y: int) -> None:
        self.move(x, y)
        self.show()
        self.raise_()

    def _fade_out(self) -> None:
        self._fade_anim = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._fade_anim.setDuration(300)
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._fade_anim.finished.connect(self.close)
        self._fade_anim.start()

    def closeEvent(self, event) -> None:
        if self._auto_close_timer.isActive():
            self._auto_close_timer.stop()
        super().closeEvent(event)


class QtToastManager:
    """管理 toast 通知的堆叠显示。"""

    def __init__(self, main_window: QWidget) -> None:
        self._main_window = main_window
        self._active: list[QtToastNotification] = []
        self._stack_offset: int = 0

    def show(
        self,
        message: str,
        level: str = "info",
        duration_ms: int = _TOAST_DURATION_MS,
    ) -> None:
        sm = qt_scale_manager()
        toast = QtToastNotification(
            self._main_window, message, level, duration_ms,
        )

        geo = self._main_window.geometry()
        toast.adjustSize()
        px = geo.x() + geo.width() - toast.width() - sm.s(16)
        py = geo.y() + sm.s(40)

        if self._active:
            last = self._active[-1]
            if last.isVisible():
                py = last.y() + last.height() + sm.s(4)
                px = last.x()

        toast.show_at(px, py)
        self._active.append(toast)
        self._stack_offset += 1

        toast.destroyed.connect(lambda: self._remove_toast(toast))

    def _remove_toast(self, toast: QtToastNotification) -> None:
        if toast in self._active:
            self._active.remove(toast)
            self._stack_offset = max(0, self._stack_offset - 1)
