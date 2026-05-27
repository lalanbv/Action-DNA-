"""QtFloatingControls — PySide6 floating zoom controls overlay.

替代 tkinter FloatingZoomControls (270 行 Label 模拟按钮 workaround)。
使用 QPushButton + QSS 实现毛玻璃半透明风格。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QWidget,
)

from src.panel.canvas.theme import current_theme, hex_to_rgba
from src.panel.qt_backend.scale import qt_scale_manager
from src.utils.i18n import t

_ZOOM_PRESETS = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0]


class QtFloatingControls(QWidget):
    """Floating zoom control bar overlaid on the canvas bottom-center."""

    def __init__(self, canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._canvas = canvas
        self._zoom_label: QLabel | None = None

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(4)

        self._apply_style()
        self._build_buttons(layout)
        self.setVisible(True)

    def _apply_style(self) -> None:
        th = current_theme()
        sm = qt_scale_manager()
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {hex_to_rgba(th.bg_surface, 0.85)};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(6)}px;
            }}
            QPushButton {{
                background-color: {th.btn_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(3)}px;
                padding: {sm.s(2)}px {sm.s(6)}px;
                font-size: {sm.s(12)}px;
                min-width: {sm.s(28)}px;
            }}
            QPushButton:hover {{
                background-color: {th.btn_bg_hover};
                border-color: {th.accent_blue};
            }}
            QLabel {{
                color: {th.text_primary};
                font-size: {sm.s(12)}px;
                padding: 0 {sm.s(4)}px;
            }}
        """)

    def _build_buttons(self, layout: QHBoxLayout) -> None:
        zoom_out_btn = QPushButton("-")
        zoom_out_btn.setFixedWidth(28)
        zoom_out_btn.clicked.connect(self._on_zoom_out)
        layout.addWidget(zoom_out_btn)

        self._zoom_label = QLabel("100%")
        self._zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._zoom_label.mousePressEvent = lambda e: self._show_presets()
        layout.addWidget(self._zoom_label)

        zoom_in_btn = QPushButton("+")
        zoom_in_btn.setFixedWidth(28)
        zoom_in_btn.clicked.connect(self._on_zoom_in)
        layout.addWidget(zoom_in_btn)

        fit_btn = QPushButton(t("canvas.zoom_to_fit"))
        fit_btn.clicked.connect(self._on_zoom_to_fit)
        layout.addWidget(fit_btn)

        reset_btn = QPushButton("1:1")
        reset_btn.clicked.connect(self._on_zoom_reset)
        layout.addWidget(reset_btn)

    def update_zoom_display(self) -> None:
        if self._zoom_label and self._canvas:
            z = self._canvas.zoom()
            self._zoom_label.setText(f"{z:.0%}")

    def reposition(self, parent_width: int, parent_height: int) -> None:
        w = self.sizeHint().width()
        h = self.sizeHint().height()
        x = (parent_width - w) // 2
        y = parent_height - h - 10
        self.move(max(0, x), max(0, y))

    def apply_theme(self) -> None:
        self._apply_style()

    def _on_zoom_in(self) -> None:
        if self._canvas:
            self._canvas.zoom_by(1.25)

    def _on_zoom_out(self) -> None:
        if self._canvas:
            self._canvas.zoom_by(1 / 1.25)

    def _on_zoom_reset(self) -> None:
        if self._canvas:
            self._canvas.zoom_reset()

    def _on_zoom_to_fit(self) -> None:
        if self._canvas:
            self._canvas.zoom_to_fit()

    def _show_presets(self) -> None:
        if not self._canvas:
            return
        from PySide6.QtWidgets import QMenu
        menu = QMenu(self)
        for preset in _ZOOM_PRESETS:
            pct = f"{preset:.0%}"
            action = menu.addAction(pct)
            action.triggered.connect(
                lambda checked, p=preset: self._zoom_to(p),
            )
        menu.exec(self._zoom_label.mapToGlobal(QPoint(0, self._zoom_label.height())))

    def _zoom_to(self, factor: float) -> None:
        if self._canvas:
            z = self._canvas.zoom()
            if abs(z - factor) > 0.001:
                self._canvas._apply_zoom(
                    factor,
                    self._canvas.mapToScene(self._canvas.viewport().rect().center()),
                )
            self.update_zoom_display()
