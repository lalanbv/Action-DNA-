"""PauseLayer — 事件驱动的暂停/恢复支持。

使用 threading.Event 替代轮询：暂停时等待 resume_event 信号，
恢复或停止时立即响应，无需 100ms 轮询间隔。
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.layers.layer import GraphLayer

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

__all__ = ["PauseLayer"]


class PauseLayer(GraphLayer):
    """在暂停状态下阻塞节点执行，直到恢复或停止。

    使用 _resume_event 实现事件驱动等待，避免轮询。
    外部调用 resume() 唤醒等待中的线程。
    """

    def __init__(self) -> None:
        self._resume_event = threading.Event()

    @property
    def name(self) -> str:
        return "pause"

    @property
    def priority(self) -> int:
        return SystemPriority.FLOW_CONTROL

    def resume(self) -> None:
        """唤醒暂停等待中的线程。"""
        self._resume_event.set()

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        """暂停等待：事件驱动，阻塞直到恢复或停止。"""
        while ctx.is_paused and not ctx.is_stopping:
            self._resume_event.clear()
            if ctx.is_paused and not ctx.is_stopping:
                self._resume_event.wait(timeout=1.0)
        return ctx
