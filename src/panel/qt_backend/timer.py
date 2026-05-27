"""Qt TimerScheduler 实现 — 包装 QTimer。"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import QTimer, QCoreApplication


class QtTimerScheduler:
    """基于 QTimer 的定时器调度器。

    实现 abstract.timer.TimerScheduler Protocol。
    """

    def __init__(self) -> None:
        self._timers: dict[int, QTimer] = {}
        self._next_id: int = 0

    def schedule(self, ms: int, callback: Callable[[], None]) -> int:
        timer = QTimer()
        timer.setSingleShot(True)
        timer.setInterval(max(0, ms))

        token = self._next_id
        self._next_id += 1

        def _on_timeout():
            self._timers.pop(token, None)
            callback()

        timer.timeout.connect(_on_timeout)
        self._timers[token] = timer
        timer.start()
        return token

    def cancel(self, token: Any) -> None:
        timer = self._timers.pop(token, None)
        if timer is not None:
            timer.stop()

    def schedule_idle(self, callback: Callable[[], None]) -> None:
        """通过 QTimer.singleShot(0) 在事件循环空闲时执行。"""
        QTimer.singleShot(0, callback)

    def is_alive(self) -> bool:
        """Qt 应用始终在线（由 QApplication 生命周期管理）。"""
        app = QCoreApplication.instance()
        return app is not None
