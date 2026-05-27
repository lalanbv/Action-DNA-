"""暂停感知的可中断等待工具函数。"""

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext


def pause_aware_wait(ctx: ExecutionContext, seconds: float) -> bool:
    """暂停感知的可中断等待。

    暂停期间不计入等待时间，确保实际有效等待时长准确。
    返回 True 表示收到停止信号，调用方应终止执行。
    """
    pause_event = ctx.pause_event

    # 无暂停机制时（pause_event 为 None），直接等待
    if pause_event is None:
        return ctx.stop_event.wait(timeout=seconds)

    effective_remaining = seconds
    while True:
        # 暂停期间不计入等待时间
        while pause_event.is_set() and not ctx.stop_event.is_set():
            ctx.stop_event.wait(timeout=0.1)
        if ctx.stop_event.is_set():
            return True

        if effective_remaining <= 0:
            return False

        start = time.monotonic()
        chunk = min(effective_remaining, 0.2)
        was_paused_before = pause_event.is_set()
        if ctx.stop_event.wait(timeout=chunk):
            return True
        elapsed = time.monotonic() - start
        was_paused_after = pause_event.is_set()
        if not was_paused_before and not was_paused_after:
            effective_remaining -= elapsed
