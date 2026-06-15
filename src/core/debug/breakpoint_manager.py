"""BreakpointManager — 断点管理器。

管理 FlowGraph 节点上的断点，支持三种类型：
LINE（经过时暂停）、CONDITIONAL（条件满足时暂停）、LOG（只记录不暂停）。

与 BreakpointLayer 集成，断点存储在内存中不持久化。
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum

from src.utils.i18n import t

logger = logging.getLogger(__name__)


class BreakpointType(Enum):
    """断点类型。"""

    LINE = "line"
    CONDITIONAL = "conditional"
    LOG = "log"


@dataclass
class Breakpoint:
    """断点定义。"""

    node_id: str
    bp_type: BreakpointType = BreakpointType.LINE
    condition: str = ""
    log_message: str = ""
    enabled: bool = True
    hit_count: int = 0
    one_shot: bool = False


class BreakpointManager:
    """断点管理器，管理 FlowGraph 中节点上的断点。"""

    def __init__(self) -> None:
        self._breakpoints: dict[str, Breakpoint] = {}
        self._lock = threading.Lock()

    def add_breakpoint(
        self,
        node_id: str,
        bp_type: BreakpointType = BreakpointType.LINE,
        condition: str = "",
        log_message: str = "",
    ) -> Breakpoint:
        """添加断点。"""
        bp = Breakpoint(
            node_id=node_id,
            bp_type=bp_type,
            condition=condition,
            log_message=log_message,
        )
        with self._lock:
            self._breakpoints[node_id] = bp
        logger.debug(t("debug.log.breakpoint_added", node_id=node_id, bp_type=bp_type.value))
        return bp

    def remove_breakpoint(self, node_id: str) -> None:
        """移除断点。"""
        with self._lock:
            self._breakpoints.pop(node_id, None)

    def toggle_breakpoint(self, node_id: str) -> bool:
        """切换断点（有则移除，无则添加），返回 True 表示已添加。"""
        with self._lock:
            if node_id in self._breakpoints:
                del self._breakpoints[node_id]
                return False
            self._breakpoints[node_id] = Breakpoint(node_id=node_id)
            return True

    def has_breakpoint(self, node_id: str) -> bool:
        """检查是否有启用的断点。"""
        with self._lock:
            bp = self._breakpoints.get(node_id)
        return bp is not None and bp.enabled

    def get_breakpoint(self, node_id: str) -> Breakpoint | None:
        """获取指定节点的断点。"""
        with self._lock:
            return self._breakpoints.get(node_id)

    def get_all(self) -> list[Breakpoint]:
        """获取所有断点。"""
        with self._lock:
            return list(self._breakpoints.values())

    def clear_all(self) -> None:
        """清除所有断点。"""
        with self._lock:
            self._breakpoints.clear()
