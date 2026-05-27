"""RingBufferLog — 环形缓冲区执行日志。

固定大小的环形缓冲区，记录执行过程中的结构化日志。
自动淘汰旧记录，内存占用恒定。
"""

from __future__ import annotations

import contextlib
import datetime
import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class LogEventType(Enum):
    """日志事件类型。"""

    NODE_ENTER = "node_enter"
    NODE_EXIT = "node_exit"
    NODE_ERROR = "node_error"
    NODE_SKIP = "node_skip"
    VARIABLE_CHANGE = "variable_change"
    BREAKPOINT = "breakpoint"
    EXECUTION_START = "execution_start"
    EXECUTION_END = "execution_end"
    CUSTOM = "custom"


@dataclass(frozen=True)
class LogEntry:
    """结构化日志条目（不可变）。"""

    timestamp: float
    node_id: str
    event_type: LogEventType
    message: str
    data: dict[str, Any] | None = None

    @property
    def time_str(self) -> str:
        dt = datetime.datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%H:%M:%S.%f")[:-3]


class RingBufferLog:
    """环形缓冲区执行日志。

    特性：
    - 固定大小，自动淘汰最旧的记录
    - 结构化日志（不是纯文本）
    - 线程安全
    - 支持按类型/节点/时间过滤
    - 支持导出到 JSON 文件

    内存估算：每条 ~200 bytes，默认 1000 条 ≈ 200KB。
    """

    def __init__(self, capacity: int = 1000) -> None:
        self._capacity = capacity
        self._buffer: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()
        self._on_append_callbacks: list[Callable[[LogEntry], None]] = []

    # ---- 写入 ----

    def append(
        self,
        node_id: str = "",
        event_type: LogEventType = LogEventType.CUSTOM,
        message: str = "",
        data: dict[str, Any] | None = None,
    ) -> LogEntry:
        """添加日志条目，缓冲区满时自动淘汰最旧的条目。"""
        entry = LogEntry(
            timestamp=time.time(),
            node_id=node_id,
            event_type=event_type,
            message=message,
            data=data,
        )

        with self._lock:
            self._buffer.append(entry)

        for cb in self._on_append_callbacks:
            try:
                cb(entry)
            except Exception as e:
                logger.error("RingBufferLog 回调异常: %s", e)

        return entry

    # ---- 读取 ----

    def get_recent(self, count: int = 50) -> list[LogEntry]:
        """获取最近的 N 条日志。"""
        with self._lock:
            return list(self._buffer)[-count:]

    def get_all(self) -> list[LogEntry]:
        """获取所有日志。"""
        with self._lock:
            return list(self._buffer)

    def get_by_node(self, node_id: str) -> list[LogEntry]:
        """按节点 ID 过滤。"""
        with self._lock:
            return [e for e in self._buffer if e.node_id == node_id]

    def get_by_type(self, event_type: LogEventType) -> list[LogEntry]:
        """按事件类型过滤。"""
        with self._lock:
            return [e for e in self._buffer if e.event_type == event_type]

    def get_by_time_range(
        self,
        start: float,
        end: float | None = None,
    ) -> list[LogEntry]:
        """按时间范围过滤。"""
        with self._lock:
            if end is None:
                return [e for e in self._buffer if e.timestamp >= start]
            return [e for e in self._buffer if start <= e.timestamp <= end]

    # ---- 统计 ----

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._buffer)

    @property
    def capacity(self) -> int:
        return self._capacity

    def get_error_count(self) -> int:
        """获取错误日志数量。"""
        with self._lock:
            return sum(
                1 for e in self._buffer
                if e.event_type == LogEventType.NODE_ERROR
            )

    # ---- 导出 ----

    def export_to_file(self, filepath: str) -> None:
        """导出日志到 JSON 文件。"""
        entries = self.get_all()
        data = [
            {
                "timestamp": e.timestamp,
                "time_str": e.time_str,
                "node_id": e.node_id,
                "event_type": e.event_type.value,
                "message": e.message,
                "data": e.data,
            }
            for e in entries
        ]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("日志已导出: %s (%d 条)", filepath, len(data))

    # ---- 回调 ----

    def on_append(self, callback: Callable[[LogEntry], None]) -> None:
        """注册日志追加回调（UI 实时更新用）。"""
        self._on_append_callbacks.append(callback)

    def remove_on_append(self, callback: Callable[[LogEntry], None]) -> None:
        """注销日志追加回调。"""
        with contextlib.suppress(ValueError):
            self._on_append_callbacks.remove(callback)

    # ---- 维护 ----

    def clear(self) -> None:
        """清空日志。"""
        with self._lock:
            self._buffer.clear()
