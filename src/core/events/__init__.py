"""事件系统公共 API。"""

from src.core.events.bus import TypedEventBus
from src.core.events.events import (
    BaseEvent,
    ExecutionStartedEvent,
    ExecutionCompletedEvent,
    NodeStartedEvent,
    NodeCompletedEvent,
    NodeFailedEvent,
    NodeRetryingEvent,
    NodeSkippedEvent,
    StepHighlightEvent,
    ExecutorStateChangedEvent,
    LoopIterationEvent,
    PopupDetectedEvent,
    MonitorTriggeredEvent,
    MonitorStateChangedEvent,
    BlackScreenDetectedEvent,
    FailSafeTriggeredEvent,
    TransitionEvent,
    GlobalTransitionTriggeredEvent,
    BreakpointHitEvent,
    VariableChangedEvent,
    DebugScreenshotEvent,
)

EventBus = TypedEventBus

__all__ = [
    "EventBus",
    "TypedEventBus",
    "BaseEvent",
    "ExecutionStartedEvent",
    "ExecutionCompletedEvent",
    "NodeStartedEvent",
    "NodeCompletedEvent",
    "NodeFailedEvent",
    "NodeRetryingEvent",
    "NodeSkippedEvent",
    "StepHighlightEvent",
    "ExecutorStateChangedEvent",
    "LoopIterationEvent",
    "PopupDetectedEvent",
    "MonitorTriggeredEvent",
    "MonitorStateChangedEvent",
    "BlackScreenDetectedEvent",
    "FailSafeTriggeredEvent",
    "TransitionEvent",
    "GlobalTransitionTriggeredEvent",
    "BreakpointHitEvent",
    "VariableChangedEvent",
    "DebugScreenshotEvent",
]
