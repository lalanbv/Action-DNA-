"""QtDNAWidget — Qt component base class with auto theme-update."""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from src.panel.canvas.theme import ThemeCallbackMixin, current_theme, on_theme_change, remove_theme_change


class QtDNAWidget(ThemeCallbackMixin, QWidget):
    """Base class for shared Qt UI components.

    - Auto-registers for theme change notifications
    - Calls apply_theme() when theme changes
    - Auto-unregisters on destruction
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._init_theme_guard(self.apply_theme, RuntimeError)

    def apply_theme(self) -> None:
        """Override to respond to theme changes."""

    def destroy_widget(self) -> None:
        """Call during cleanup to unregister theme listener."""
        self._unregister_theme_callback()
        self.deleteLater()
