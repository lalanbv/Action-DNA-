"""QtBadge — pill-shaped status indicator label."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QWidget

from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.components.base import QtDNAWidget
from src.panel.qt_backend.scale import qt_scale_manager

_VARIANT_TOKENS: dict[str, dict[str, str]] = {
    "success": {"bg": "accent_green", "fg": "text_on_accent"},
    "warning": {"bg": "accent_orange", "fg": "text_on_accent"},
    "error": {"bg": "accent_red", "fg": "text_on_accent"},
    "info": {"bg": "accent_blue", "fg": "text_on_accent"},
    "neutral": {"bg": "bg_surface", "fg": "text_secondary"},
}


class QtBadge(QtDNAWidget):
    """Compact pill-shaped status indicator."""

    def __init__(
        self,
        parent: QWidget | None = None,
        text: str = "",
        variant: str = "neutral",
    ) -> None:
        super().__init__(parent)
        self._variant = variant
        self._label = QLabel(text, self)
        self._apply_style()

    def set_text(self, text: str) -> None:
        self._label.setText(text)

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self._apply_style()

    def configure(self, *, text: str | None = None, variant: str | None = None) -> None:
        if text is not None:
            self._label.setText(text)
        if variant is not None:
            self._variant = variant
        self._apply_style()

    def apply_theme(self) -> None:
        self._apply_style()

    def _apply_style(self) -> None:
        th = current_theme()
        sm = qt_scale_manager()
        tokens = _VARIANT_TOKENS.get(self._variant, _VARIANT_TOKENS["neutral"])
        bg = getattr(th, tokens["bg"])
        fg = getattr(th, tokens["fg"])
        self._label.setStyleSheet(f"""
            color: {fg};
            background-color: {bg};
            border-radius: {sm.s(8)}px;
            padding: {sm.s(2)}px {sm.s(8)}px;
            font-size: {sm.s(11)}px;
        """)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
