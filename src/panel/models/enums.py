"""Panel 枚举常量 — 边样式、节点执行状态等类型安全的字符串枚举。"""

from __future__ import annotations

from enum import StrEnum


class EdgeStyle(StrEnum):
    """连线渲染样式。"""

    BEZIER = "bezier"
    ORTHOGONAL = "orthogonal"
    STRAIGHT = "straight"


class NodeExecutionState(StrEnum):
    """节点执行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    SUCCESS = "success"
    ERROR = "error"
    PAUSED = "paused"
    DISABLED = "disabled"


class EdgeLabel(StrEnum):
    """边标签枚举。"""

    DEFAULT = "default"
    TRUE = "true"
    FALSE = "false"
    TIMEOUT = "timeout"
    LOOP = "loop"
    EXIT = "exit"
