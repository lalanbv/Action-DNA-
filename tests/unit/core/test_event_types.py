"""结构化事件类型测试 — BaseEvent 及子类。"""

import time

import pytest

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
    BlackScreenDetectedEvent,
    FailSafeTriggeredEvent,
    TransitionEvent,
    GlobalTransitionTriggeredEvent,
    BreakpointHitEvent,
    VariableChangedEvent,
    DebugScreenshotEvent,
)
from src.core.variables.scope import VariableScope


# ============================================================
# BaseEvent
# ============================================================


class TestBaseEvent:
    """BaseEvent 基类测试。"""

    def test_auto_timestamp(self):
        before = time.time()
        event = BaseEvent()
        after = time.time()
        assert before <= event.timestamp <= after

    def test_custom_timestamp(self):
        event = BaseEvent(timestamp=1000.0)
        assert event.timestamp == 1000.0

    def test_is_dataclass(self):
        from dataclasses import fields
        event = BaseEvent()
        assert len(fields(event)) >= 1

    def test_subclass_inheritance(self):
        assert issubclass(ExecutionStartedEvent, BaseEvent)


# ============================================================
# 执行引擎事件
# ============================================================


class TestExecutionEvents:
    """执行生命周期事件测试。"""

    def test_execution_started(self):
        event = ExecutionStartedEvent(graph_id="g1", node_count=5)
        assert event.graph_id == "g1"
        assert event.node_count == 5
        assert isinstance(event, BaseEvent)

    def test_execution_completed(self):
        event = ExecutionCompletedEvent(
            graph_id="g1",
            total_steps=42,
            elapsed_seconds=120.5,
            success=True,
        )
        assert event.graph_id == "g1"
        assert event.total_steps == 42
        assert event.elapsed_seconds == 120.5
        assert event.success is True

    def test_execution_completed_failure(self):
        event = ExecutionCompletedEvent(
            graph_id="g1",
            total_steps=10,
            elapsed_seconds=30.0,
            success=False,
        )
        assert event.success is False

    def test_node_started(self):
        event = NodeStartedEvent(
            node_id="n1",
            node_type="CLICK_IMAGE",
            step_index=3,
        )
        assert event.node_id == "n1"
        assert event.node_type == "CLICK_IMAGE"
        assert event.step_index == 3

    def test_node_completed(self):
        event = NodeCompletedEvent(
            node_id="n1",
            node_type="CLICK_IMAGE",
            success=True,
            elapsed_ms=150.0,
            output_vars={"match_pos": (320, 480)},
        )
        assert event.success is True
        assert event.elapsed_ms == 150.0
        assert event.output_vars == {"match_pos": (320, 480)}

    def test_node_completed_no_output(self):
        event = NodeCompletedEvent(
            node_id="n2",
            node_type="WAIT",
            success=True,
            elapsed_ms=2000.0,
        )
        assert event.output_vars == {}

    def test_node_failed(self):
        err = RuntimeError("模板匹配失败")
        event = NodeFailedEvent(
            node_id="n1",
            node_type="CLICK_IMAGE",
            error=err,
            error_config="RETRY",
            retry_count=2,
        )
        assert event.error is err
        assert event.error_config == "RETRY"
        assert event.retry_count == 2

    def test_node_retrying(self):
        event = NodeRetryingEvent(
            node_id="n1",
            attempt=3,
            max_attempts=5,
            last_error="模板匹配失败",
        )
        assert event.attempt == 3
        assert event.max_attempts == 5
        assert event.last_error == "模板匹配失败"

    def test_node_skipped(self):
        event = NodeSkippedEvent(
            node_id="n1",
            reason="条件不满足",
        )
        assert event.reason == "条件不满足"

    def test_step_highlight(self):
        event = StepHighlightEvent(node_id="n1", is_active=True)
        assert event.is_active is True

    def test_step_highlight_deactivate(self):
        event = StepHighlightEvent(node_id="n1", is_active=False)
        assert event.is_active is False


# ============================================================
# 执行器状态事件
# ============================================================


class TestExecutorStateEvents:
    """执行器状态变更事件测试。"""

    def test_state_changed(self):
        event = ExecutorStateChangedEvent(
            old_state="idle",
            new_state="running",
        )
        assert event.old_state == "idle"
        assert event.new_state == "running"

    def test_loop_iteration(self):
        event = LoopIterationEvent(
            node_id="loop1",
            iteration=5,
            max_iterations=10,
        )
        assert event.iteration == 5
        assert event.max_iterations == 10

    def test_loop_iteration_infinite(self):
        event = LoopIterationEvent(
            node_id="loop1",
            iteration=100,
            max_iterations=None,
        )
        assert event.max_iterations is None


# ============================================================
# 监控事件
# ============================================================


class TestMonitorEvents:
    """监控相关事件测试。"""

    def test_popup_detected(self):
        event = PopupDetectedEvent(
            monitor_id="safety",
            match_position=(500, 300),
            action_taken="closed",
        )
        assert event.match_position == (500, 300)
        assert event.action_taken == "closed"

    def test_black_screen_detected(self):
        event = BlackScreenDetectedEvent(
            duration_seconds=5.0,
            action_taken="recovery",
        )
        assert event.duration_seconds == 5.0

    def test_failsafe_triggered(self):
        event = FailSafeTriggeredEvent(mouse_position=(0, 0))
        assert event.mouse_position == (0, 0)


# ============================================================
# FSM 事件
# ============================================================


class TestFSMEvents:
    """FSM 状态转换事件测试。"""

    def test_transition(self):
        event = TransitionEvent(
            from_node="node_a",
            to_node="node_b",
            trigger_event="FINISHED",
        )
        assert event.from_node == "node_a"
        assert event.to_node == "node_b"
        assert event.trigger_event == "FINISHED"

    def test_global_transition(self):
        event = GlobalTransitionTriggeredEvent(
            event_name="POPUP",
            target_id="close_popup",
            current_state="node_b",
        )
        assert event.event_name == "POPUP"
        assert event.target_id == "close_popup"


# ============================================================
# 调试事件
# ============================================================


class TestDebugEvents:
    """调试相关事件测试。"""

    def test_breakpoint_hit(self):
        event = BreakpointHitEvent(node_id="bp1")
        assert event.node_id == "bp1"

    def test_variable_changed(self):
        event = VariableChangedEvent(
            var_name="count",
            old_value=5,
            new_value=10,
            scope=VariableScope.GLOBAL,
        )
        assert event.var_name == "count"
        assert event.old_value == 5
        assert event.new_value == 10
        assert event.scope == VariableScope.GLOBAL

    def test_debug_screenshot(self):
        event = DebugScreenshotEvent(
            file_path="/tmp/screenshot.png",
            reason="match_failed",
            node_id="n1",
        )
        assert event.reason == "match_failed"
        assert event.node_id == "n1"
