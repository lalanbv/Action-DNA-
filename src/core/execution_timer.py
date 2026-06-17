"""ExecutionTimer — 线程安全的活跃执行计时器。

记录启动时刻与暂停累计,``elapsed()`` 返回排除暂停时长的活跃秒数。
停止后冻结最终值,直至下次 ``start()`` 重置。

使用 ``time.monotonic()``,不受系统时钟调整影响。
"""

from __future__ import annotations

import threading
import time


class ExecutionTimer:
    """活跃执行计时器 — 排除暂停时长。线程安全。

    生命周期: start → (pause/resume)* → stop。
    stop 后 elapsed() 恒返回冻结的最终值, 直至下次 start 重置。
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._start: float | None = None
        self._paused_total: float = 0.0
        self._pause_at: float | None = None
        self._final: float | None = None

    def start(self) -> None:
        """开始计时,清零所有累计与冻结值。"""
        with self._lock:
            self._start = time.monotonic()
            self._paused_total = 0.0
            self._pause_at = None
            self._final = None

    def pause(self) -> None:
        """标记暂停起点(仅当运行中且未暂停)。"""
        with self._lock:
            if self._start is not None and self._pause_at is None:
                self._pause_at = time.monotonic()

    def resume(self) -> None:
        """结束暂停,把暂停时长累加到 _paused_total。"""
        with self._lock:
            if self._pause_at is not None and self._start is not None:
                self._paused_total += time.monotonic() - self._pause_at
                self._pause_at = None

    def stop(self) -> None:
        """冻结当前活跃时长为最终值(幂等)。"""
        with self._lock:
            if self._start is not None:
                self._final = self._elapsed_locked()

    def reset(self) -> None:
        """清零全部状态。"""
        with self._lock:
            self._start = None
            self._paused_total = 0.0
            self._pause_at = None
            self._final = None

    def elapsed(self) -> float | None:
        """返回活跃秒数(排除暂停);未启动返回 None。"""
        with self._lock:
            return self._elapsed_locked()

    def _elapsed_locked(self) -> float | None:
        if self._start is None:
            return None
        if self._final is not None:
            return self._final
        now = time.monotonic()
        active = now - self._start - self._paused_total
        if self._pause_at is not None:
            active -= now - self._pause_at
        return max(0.0, active)
