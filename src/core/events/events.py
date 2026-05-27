"""结构化事件类型 — 所有事件的基类与具体事件数据类。"""

import time
from dataclasses import dataclass, field
from typing import Any

from src.core.variables.scope import VariableScope


@dataclass(kw_only=True, frozen=True)
class BaseEvent:
    """所有事件的基类，自动记录创建时间戳。"""

    timestamp: float = field(default_factory=time.time)


# ---- 执行引擎事件 ----


@dataclass(frozen=True)
class ExecutionStartedEvent(BaseEvent):
    graph_id: str
    node_count: int


@dataclass(frozen=True)
class ExecutionCompletedEvent(BaseEvent):
    graph_id: str
    total_steps: int
    elapsed_seconds: float
    success: bool


@dataclass(frozen=True)
class NodeStartedEvent(BaseEvent):
    node_id: str
    node_type: str
    step_index: int


@dataclass(frozen=True)
class NodeCompletedEvent(BaseEvent):
    node_id: str
    node_type: str
    success: bool
    elapsed_ms: float
    output_vars: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class NodeFailedEvent(BaseEvent):
    node_id: str
    node_type: str
    error: Exception  # shallow frozen: reference immutable, object itself mutable
    error_config: str
    retry_count: int


@dataclass(frozen=True)
class NodeRetryingEvent(BaseEvent):
    node_id: str
    attempt: int
    max_attempts: int
    last_error: str


@dataclass(frozen=True)
class NodeSkippedEvent(BaseEvent):
    node_id: str
    reason: str


@dataclass(frozen=True)
class StepHighlightEvent(BaseEvent):
    node_id: str
    is_active: bool


# ---- 执行器状态事件 ----


@dataclass(frozen=True)
class ExecutorStateChangedEvent(BaseEvent):
    old_state: str
    new_state: str


@dataclass(frozen=True)
class LoopIterationEvent(BaseEvent):
    node_id: str
    iteration: int
    max_iterations: int | None


# ---- 监控事件 ----


@dataclass(frozen=True)
class PopupDetectedEvent(BaseEvent):
    """已弃用: 请使用 MonitorTriggeredEvent。"""
    monitor_id: str
    match_position: tuple[int, int]
    action_taken: str


@dataclass(frozen=True)
class MonitorTriggeredEvent(BaseEvent):
    monitor_id: str
    match_position: tuple[int, int]
    action_taken: str
    consecutive_count: int


@dataclass(frozen=True)
class MonitorStateChangedEvent(BaseEvent):
    monitor_id: str
    old_status: str
    new_status: str
    trigger_count: int


@dataclass(frozen=True)
class BlackScreenDetectedEvent(BaseEvent):
    duration_seconds: float
    action_taken: str


@dataclass(frozen=True)
class FailSafeTriggeredEvent(BaseEvent):
    mouse_position: tuple[int, int]


# ---- FSM 事件 ----


@dataclass(frozen=True)
class TransitionEvent(BaseEvent):
    from_node: str
    to_node: str
    trigger_event: str


@dataclass(frozen=True)
class GlobalTransitionTriggeredEvent(BaseEvent):
    event_name: str
    target_id: str
    current_state: str


# ---- 调试事件 ----


@dataclass(frozen=True)
class BreakpointHitEvent(BaseEvent):
    node_id: str


@dataclass(frozen=True)
class VariableChangedEvent(BaseEvent):
    var_name: str
    old_value: Any
    new_value: Any
    scope: VariableScope


@dataclass(frozen=True)
class DebugScreenshotEvent(BaseEvent):
    file_path: str
    reason: str
    node_id: str
