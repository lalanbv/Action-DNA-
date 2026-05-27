"""tkinter TimerScheduler 实现 — 包装 Frame.after / after_cancel / after_idle。"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable


class TkTimerScheduler:
    """基于 tkinter Frame 的定时器调度器。

    实现 abstract.timer.TimerScheduler Protocol。
    """

    def __init__(self, frame: tk.Widget) -> None:
        self._frame = frame

    def schedule(self, ms: int, callback: Callable[[], None]) -> str:
        tid = self._frame.after(ms, callback)
        return tid

    def cancel(self, token: Any) -> None:
        try:
            self._frame.after_cancel(token)
        except tk.TclError:
            pass

    def schedule_idle(self, callback: Callable[[], None]) -> None:
        if self._frame.winfo_exists():
            self._frame.after_idle(callback)

    def is_alive(self) -> bool:
        try:
            return bool(self._frame.winfo_exists())
        except tk.TclError:
            return False
