"""QtMonitorStatusWidget — horizontal bar of monitor status cards."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.components.base import QtDNAWidget
from src.panel.qt_backend.scale import qt_scale_manager

_STATUS_COLORS = {
    "idle": "status_ready",
    "running": "status_running",
    "paused": "status_paused",
    "error": "status_error",
    "handling": "status_running",
}


class _StatusDot(QWidget):
    def __init__(self, color: str = "#808080", size: int = 10) -> None:
        super().__init__()
        self._color = color
        self._size = size
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(self._color))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(1, 1, self._size - 2, self._size - 2)
        p.end()


class QtMonitorCard(QtDNAWidget):
    """Single monitor status card."""

    def __init__(self, parent: QWidget | None, monitor_name: str) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self._status = "idle"
        self._trigger_count = 0
        self._last_trigger_time = 0.0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(sm.s(6), sm.s(4), sm.s(6), sm.s(4))
        layout.setSpacing(sm.s(4))

        dot_color = getattr(th, _STATUS_COLORS["idle"])
        self._dot = _StatusDot(dot_color, sm.s(10))
        layout.addWidget(self._dot)

        self._name_label = QLabel(monitor_name)
        self._name_label.setStyleSheet(f"color: {th.text_secondary}; background: transparent; font-size: {sm.s(11)}px;")
        layout.addWidget(self._name_label)

        self._badge = QLabel("0")
        self._badge.setStyleSheet(f"""
            color: {th.text_on_accent}; background-color: {th.accent_blue};
            border-radius: {sm.s(6)}px; padding: 0px {sm.s(4)}px;
            font-size: {sm.s(9)}px;
        """)
        layout.addWidget(self._badge)

        self._handling_label = QLabel("")
        self._handling_label.setStyleSheet(f"color: {th.status_running}; background: transparent; font-size: {sm.s(9)}px;")
        layout.addWidget(self._handling_label)

        self._time_label = QLabel("")
        self._time_label.setStyleSheet(f"color: {th.text_muted}; background: transparent; font-size: {sm.s(9)}px;")
        layout.addWidget(self._time_label)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {th.bg_surface};
                border: 1px solid {th.border_default};
                border-left: 3px solid {dot_color};
                border-radius: {sm.s(3)}px;
            }}
        """)

    def update_state(self, status: str, trigger_count: int, last_trigger_time: float) -> None:
        th = current_theme()
        sm = qt_scale_manager()

        self._status = status
        self._trigger_count = trigger_count
        self._last_trigger_time = last_trigger_time

        color_key = _STATUS_COLORS.get(status, "status_ready")
        dot_color = getattr(th, color_key)

        self._dot.set_color(dot_color)
        self._badge.setText(str(trigger_count))
        self._handling_label.setText("●" if status == "handling" else "")

        if last_trigger_time > 0:
            elapsed = time.monotonic() - last_trigger_time
            self._time_label.setText(_format_elapsed(elapsed))
        else:
            self._time_label.setText("")

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {th.bg_surface};
                border: 1px solid {th.border_default};
                border-left: 3px solid {dot_color};
                border-radius: {sm.s(3)}px;
            }}
        """)

    def apply_theme(self) -> None:
        self.update_state(self._status, self._trigger_count, self._last_trigger_time)


class QtMonitorStatusWidget(QtDNAWidget):
    """Horizontal bar of monitor status cards."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        th = current_theme()
        self._cards: dict[str, QtMonitorCard] = {}
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 2)
        self._layout.setSpacing(4)
        self._layout.addStretch()
        self.setStyleSheet(f"background-color: {th.bg_primary};")

    def update_monitors(self, states: list) -> None:
        current_ids = set()

        for state in states:
            mid = state.monitor_id
            current_ids.add(mid)

            if mid not in self._cards:
                card = QtMonitorCard(self, state.config_name)
                self._layout.insertWidget(self._layout.count() - 1, card)
                self._cards[mid] = card

            self._cards[mid].update_state(
                status=state.status,
                trigger_count=state.trigger_count,
                last_trigger_time=state.last_trigger_time,
            )

        for mid in list(self._cards.keys()):
            if mid not in current_ids:
                card = self._cards.pop(mid)
                self._layout.removeWidget(card)
                card.destroy_widget()

    def apply_theme(self) -> None:
        th = current_theme()
        self.setStyleSheet(f"background-color: {th.bg_primary};")
        for card in self._cards.values():
            card.apply_theme()


def _format_elapsed(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds / 60)}m ago"
    return f"{int(seconds / 3600)}h ago"
