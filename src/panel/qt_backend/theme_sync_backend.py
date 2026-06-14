"""Qt 主题同步后端 — 提供 marshal 原语 + 实时 colorSchemeChanged（B3）。

实现 theme_sync.ThemeSyncBackend Protocol，并额外在 Qt 6.5+ 连接
``QGuiApplication.styleHints().colorSchemeChanged`` 实现 OS 主题实时响应；
低版本降级为 SystemThemeSync 的 worker 线程轮询。

refresh_theme 通过模块引用调用（``theme_manager.refresh_theme()``），
便于测试 monkeypatch。
"""

from __future__ import annotations

import logging
from typing import Callable

from src.panel.canvas.theme import theme_manager

logger = logging.getLogger(__name__)


class QtThemeSyncBackend:
    """Qt 后端主题同步原语 + 实时信号。

    实现 :class:`theme_sync.ThemeSyncBackend` Protocol。
    """

    def __init__(self, app) -> None:
        self._app = app
        self._has_signal = _detect_color_scheme_signal(app)
        self._signal_connected = False

    @property
    def has_color_scheme_signal(self) -> bool:
        """是否支持 Qt 6.5+ colorSchemeChanged（运行时探测）。"""
        return self._has_signal

    def marshal_main(self, fn: Callable[[], None]) -> None:
        """回 UI 主线程：QTimer.singleShot(0)。"""
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, fn)

    def start_timer(self, interval_ms: int, fn: Callable[[], None]) -> object:
        from PySide6.QtCore import QTimer

        timer = QTimer(self._app)
        timer.setInterval(interval_ms)
        timer.timeout.connect(fn)
        timer.start()
        return timer

    def stop_timer(self, handle: object) -> None:
        try:
            handle.stop()
        except Exception:
            logger.debug("Failed to stop Qt theme timer", exc_info=True)

    def connect_real_time(self) -> None:
        """连接 colorSchemeChanged 实时信号（B3）。仅在 has_color_scheme_signal 时有效。"""
        if not self._has_signal or self._signal_connected:
            return
        try:
            from PySide6.QtGui import QGuiApplication

            QGuiApplication.styleHints().colorSchemeChanged.connect(
                self._on_color_scheme_changed
            )
            self._signal_connected = True
        except Exception:
            logger.debug("colorSchemeChanged connect failed", exc_info=True)

    def _on_color_scheme_changed(self) -> None:
        """OS 主题变化实时回调（已在主线程，直接刷新）。"""
        theme_manager.refresh_theme()


def _detect_color_scheme_signal(app) -> bool:
    """探测 Qt 是否支持 styleHints().colorSchemeChanged（Qt 6.5+）。"""
    try:
        from PySide6.QtGui import QGuiApplication

        sh = QGuiApplication.styleHints()
        return hasattr(sh, "colorScheme") and hasattr(sh, "colorSchemeChanged")
    except Exception:
        return False
