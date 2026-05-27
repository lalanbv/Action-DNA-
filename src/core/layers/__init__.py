"""中间件管道 — GraphLayer ABC + 内置层。

按推荐顺序注册：
1. LoggingLayer   (priority=-100) — 最外层，记录所有事件
2. TimingLayer    (priority=-50)  — 计时包裹所有操作
3. RetryLayer     (priority=0)    — 重试逻辑
4. BreakpointLayer(priority=50)   — 断点调试（最内层）
"""

from src.core.layers.layer import GraphLayer
from src.core.layers.logging_layer import LoggingLayer
from src.core.layers.timing_layer import TimingLayer, TimingStats, TimingEntry
from src.core.layers.retry_layer import RetryLayer
from src.core.layers.breakpoint_layer import (
    BreakpointLayer,
    StopExecution,
)

__all__ = [
    "GraphLayer",
    "LoggingLayer",
    "TimingLayer",
    "TimingStats",
    "TimingEntry",
    "RetryLayer",
    "BreakpointLayer",
    "StopExecution",
    "create_default_layers",
]


def create_default_layers() -> list[GraphLayer]:
    """创建默认的层管道（按推荐顺序）。"""
    return [
        LoggingLayer(),
        TimingLayer(),
        RetryLayer(),
        BreakpointLayer(),
    ]
