"""Extended descriptors 单元测试 — HoldKey / MouseScroll / MouseDrag / KeyCombo / MultiKeySequence / IdleBehavior / StartTimer。

所有描述符通过 mock 隔离外部依赖。占位描述符（委托 executor）验证委托路径正确。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from unittest.mock import MagicMock

import pytest

from src.core.engine.descriptors.extended_descriptors import (
    HoldKeyDescriptor,
    IdleBehaviorDescriptor,
    KeyComboDescriptor,
    MouseScrollDescriptor,
    MouseDragDescriptor,
    MultiKeySequenceDescriptor,
    StartTimerDescriptor,
)
from src.core.engine.node_result import NodeResult

from .conftest import _FakeFlowNode, _make_ctx as _base_make_ctx


# ---- Fixtures ----


@dataclass
class _FakeAction:
    """最小 ActionStep 替身。"""

    keys_hold: str = ""
    key: str = ""
    hold_duration: float = 1.0
    scroll_clicks: int = 3
    offset_x: int = 0
    offset_y: int = 0
    move_speed: float = 0.3
    curve_amount: float = 0.0
    combo_keys: str = ""
    combo_mode: str = "hold_tap"
    key_sequence: str = ""
    key_interval_min: float = 0.05
    key_interval_max: float = 0.15
    idle_duration: float = 5.0
    jitter_intensity: int = 10
    timer_name: str = "timer1"
    timer_timeout: float = 0.0
    path_points: list[tuple[int, int, float]] = field(default_factory=list)
    recorded_duration: float = 0.0
    start_x: int = 0
    start_y: int = 0
    end_x: int = 0
    end_y: int = 0
    button: str = "left"
    duration: float = 0.5


def _make_ctx(
    *,
    action: _FakeAction | None = None,
    has_executor: bool = True,
) -> MagicMock:
    extra = {"_executor": MagicMock()} if has_executor else {}
    ctx = _base_make_ctx(
        action=action or _FakeAction(),
        input_ctrl=MagicMock(),
        extra=extra,
    )
    return ctx


# ---- HoldKeyDescriptor ----


class TestHoldKeyDescriptor:
    def test_action_type(self) -> None:
        assert HoldKeyDescriptor.action_type() == "HOLD_KEY"

    def test_display_name(self) -> None:
        assert HoldKeyDescriptor.display_name() == "长按按键"

    def test_category(self) -> None:
        assert HoldKeyDescriptor.category() == "高级动作"

    def test_input_types_has_hold_duration(self) -> None:
        inputs = HoldKeyDescriptor.input_types()
        assert "hold_duration" in inputs
        assert inputs["hold_duration"].required is True

    def test_output_types_empty(self) -> None:
        assert HoldKeyDescriptor.output_types() == {}

    def test_execute_delegates_to_executor(self) -> None:
        action = _FakeAction(key="shift", hold_duration=2.0)
        ctx = _make_ctx(action=action)

        result = HoldKeyDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_hold_key.assert_called_once_with(action, 0)

    def test_execute_no_executor_fails(self) -> None:
        action = _FakeAction()
        ctx = _make_ctx(action=action, has_executor=False)

        result = HoldKeyDescriptor().execute(ctx)

        assert result.success is False
        assert "executor not available" in str(result.error)

    def test_execute_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)

        result = HoldKeyDescriptor().execute(ctx)

        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- MouseScrollDescriptor ----


class TestMouseScrollDescriptor:
    def test_action_type(self) -> None:
        assert MouseScrollDescriptor.action_type() == "MOUSE_SCROLL"

    def test_display_name(self) -> None:
        assert MouseScrollDescriptor.display_name() == "鼠标滚轮"

    def test_category(self) -> None:
        assert MouseScrollDescriptor.category() == "基础动作"

    def test_input_types(self) -> None:
        inputs = MouseScrollDescriptor.input_types()
        assert "scroll_clicks" in inputs
        assert inputs["scroll_clicks"].required is True

    def test_output_types_empty(self) -> None:
        assert MouseScrollDescriptor.output_types() == {}

    def test_execute_calls_scroll(self) -> None:
        action = _FakeAction(scroll_clicks=5)
        ctx = _make_ctx(action=action)

        result = MouseScrollDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        ctx.input_ctrl.scroll.assert_called_once_with(5)

    def test_execute_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)

        result = MouseScrollDescriptor().execute(ctx)

        assert result.success is False
        assert "缺少步骤配置" in str(result.error)

    def test_execute_negative_scroll(self) -> None:
        action = _FakeAction(scroll_clicks=-3)
        ctx = _make_ctx(action=action)

        result = MouseScrollDescriptor().execute(ctx)

        assert result.success is True
        ctx.input_ctrl.scroll.assert_called_once_with(-3)


# ---- MouseDragDescriptor ----


class TestMouseDragDescriptor:
    def test_action_type(self) -> None:
        assert MouseDragDescriptor.action_type() == "MOUSE_DRAG"

    def test_display_name(self) -> None:
        assert MouseDragDescriptor.display_name() == "鼠标拖拽"

    def test_category(self) -> None:
        assert MouseDragDescriptor.category() == "基础动作"

    def test_input_types(self) -> None:
        inputs = MouseDragDescriptor.input_types()
        assert "start_x" in inputs
        assert "start_y" in inputs
        assert "end_x" in inputs
        assert "end_y" in inputs

    def test_output_types_empty(self) -> None:
        assert MouseDragDescriptor.output_types() == {}

    def test_execute_calls_drag_to(self) -> None:
        action = _FakeAction()
        action.start_x = 10
        action.start_y = 20
        action.end_x = 100
        action.end_y = 200
        action.duration = 0.5
        ctx = _make_ctx(action=action)

        result = MouseDragDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        ctx.input_ctrl.drag_to.assert_called_once_with(
            10, 20, 100, 200, duration=0.5,
        )

    def test_execute_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)

        result = MouseDragDescriptor().execute(ctx)

        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- KeyComboDescriptor ----


class TestKeyComboDescriptor:
    def test_action_type(self) -> None:
        assert KeyComboDescriptor.action_type() == "KEY_COMBO"

    def test_display_name(self) -> None:
        assert KeyComboDescriptor.display_name() == "组合按键"

    def test_category(self) -> None:
        assert KeyComboDescriptor.category() == "高级动作"

    def test_input_types(self) -> None:
        inputs = KeyComboDescriptor.input_types()
        assert "combo_keys" in inputs
        assert "combo_mode" in inputs

    def test_output_types_empty(self) -> None:
        assert KeyComboDescriptor.output_types() == {}

    def test_execute_delegates_to_executor(self) -> None:
        action = _FakeAction(combo_keys="ctrl,shift,esc", combo_mode="hold_tap")
        ctx = _make_ctx(action=action)

        result = KeyComboDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_key_combo.assert_called_once_with(action, 0)

    def test_execute_no_executor_fails(self) -> None:
        action = _FakeAction()
        ctx = _make_ctx(action=action, has_executor=False)

        result = KeyComboDescriptor().execute(ctx)

        assert result.success is False
        assert "executor not available" in str(result.error)

    def test_execute_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)

        result = KeyComboDescriptor().execute(ctx)

        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- MultiKeySequenceDescriptor ----


class TestMultiKeySequenceDescriptor:
    def test_action_type(self) -> None:
        assert MultiKeySequenceDescriptor.action_type() == "MULTI_KEY_SEQUENCE"

    def test_display_name(self) -> None:
        assert MultiKeySequenceDescriptor.display_name() == "多键序列"

    def test_category(self) -> None:
        assert MultiKeySequenceDescriptor.category() == "高级动作"

    def test_input_types(self) -> None:
        inputs = MultiKeySequenceDescriptor.input_types()
        assert "key_sequence" in inputs
        assert "key_interval_min" in inputs

    def test_output_types_empty(self) -> None:
        assert MultiKeySequenceDescriptor.output_types() == {}

    def test_execute_delegates_to_executor(self) -> None:
        action = _FakeAction(key_sequence="a,b,c,enter", key_interval_min=0.1, key_interval_max=0.2)
        ctx = _make_ctx(action=action)

        result = MultiKeySequenceDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_multi_key_sequence.assert_called_once_with(action, 0)

    def test_execute_no_executor_fails(self) -> None:
        action = _FakeAction()
        ctx = _make_ctx(action=action, has_executor=False)

        result = MultiKeySequenceDescriptor().execute(ctx)

        assert result.success is False
        assert "executor not available" in str(result.error)

    def test_execute_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)

        result = MultiKeySequenceDescriptor().execute(ctx)

        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- IdleBehaviorDescriptor ----


class TestIdleBehaviorDescriptor:
    def test_action_type(self) -> None:
        assert IdleBehaviorDescriptor.action_type() == "IDLE_BEHAVIOR"

    def test_display_name(self) -> None:
        assert IdleBehaviorDescriptor.display_name() == "随机空闲行为"

    def test_category(self) -> None:
        assert IdleBehaviorDescriptor.category() == "高级动作"

    def test_input_types(self) -> None:
        inputs = IdleBehaviorDescriptor.input_types()
        assert "idle_duration" in inputs
        assert "jitter_intensity" in inputs

    def test_output_types_empty(self) -> None:
        assert IdleBehaviorDescriptor.output_types() == {}

    def test_execute_delegates_to_executor(self) -> None:
        action = _FakeAction(idle_duration=3.0, jitter_intensity=15)
        ctx = _make_ctx(action=action)

        result = IdleBehaviorDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_idle_behavior.assert_called_once_with(action, 0)

    def test_execute_no_executor_fails(self) -> None:
        action = _FakeAction()
        ctx = _make_ctx(action=action, has_executor=False)

        result = IdleBehaviorDescriptor().execute(ctx)

        assert result.success is False
        assert "executor not available" in str(result.error)

    def test_execute_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)

        result = IdleBehaviorDescriptor().execute(ctx)

        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- StartTimerDescriptor ----


class TestStartTimerDescriptor:
    def test_action_type(self) -> None:
        assert StartTimerDescriptor.action_type() == "START_TIMER"

    def test_display_name(self) -> None:
        assert StartTimerDescriptor.display_name() == "启动计时器"

    def test_category(self) -> None:
        assert StartTimerDescriptor.category() == "高级动作"

    def test_input_types(self) -> None:
        inputs = StartTimerDescriptor.input_types()
        assert "timer_name" in inputs
        assert inputs["timer_name"].required is True
        assert "timer_timeout" in inputs

    def test_output_types_empty(self) -> None:
        assert StartTimerDescriptor.output_types() == {}

    def test_execute_delegates_to_executor(self) -> None:
        action = _FakeAction(timer_name="boss_timer", timer_timeout=30.0)
        ctx = _make_ctx(action=action)

        result = StartTimerDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_start_timer.assert_called_once_with(action)

    def test_execute_no_executor_fails(self) -> None:
        action = _FakeAction()
        ctx = _make_ctx(action=action, has_executor=False)

        result = StartTimerDescriptor().execute(ctx)

        assert result.success is False
        assert "executor not available" in str(result.error)

    def test_execute_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)

        result = StartTimerDescriptor().execute(ctx)

        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- 注册验证 ----


class TestExtendedRegistration:
    """验证所有扩展描述符已正确注册到 NodeRegistry。"""

    @pytest.mark.parametrize(
        "cls,expected_type",
        [
            (HoldKeyDescriptor, "HOLD_KEY"),
            (MouseScrollDescriptor, "MOUSE_SCROLL"),
            (MouseDragDescriptor, "MOUSE_DRAG"),
            (KeyComboDescriptor, "KEY_COMBO"),
            (MultiKeySequenceDescriptor, "MULTI_KEY_SEQUENCE"),
            (IdleBehaviorDescriptor, "IDLE_BEHAVIOR"),
            (StartTimerDescriptor, "START_TIMER"),
        ],
    )
    def test_registered(self, cls: type, expected_type: str) -> None:
        from src.core.engine.node_registry import NodeRegistry

        assert NodeRegistry.has(expected_type)
        assert NodeRegistry.get(expected_type) is cls


# ---- D18 边界条件 & 输入验证 ----


class TestHoldKeyBoundary:
    """HoldKeyDescriptor 边界条件。"""

    def test_zero_hold_duration(self) -> None:
        """hold_duration=0 仍应委托执行。"""
        action = _FakeAction(key="shift", hold_duration=0.0)
        ctx = _make_ctx(action=action)

        result = HoldKeyDescriptor().execute(ctx)

        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_hold_key.assert_called_once_with(action, 0)

    def test_negative_hold_duration(self) -> None:
        """hold_duration 为负仍应委托（由 executor 校验）。"""
        action = _FakeAction(key="shift", hold_duration=-1.0)
        ctx = _make_ctx(action=action)

        result = HoldKeyDescriptor().execute(ctx)

        assert result.success is True


class TestMouseScrollBoundary:
    """MouseScrollDescriptor 边界条件。"""

    def test_zero_scroll_clicks(self) -> None:
        """scroll_clicks=0 应正常调用。"""
        action = _FakeAction(scroll_clicks=0)
        ctx = _make_ctx(action=action)

        result = MouseScrollDescriptor().execute(ctx)

        assert result.success is True
        ctx.input_ctrl.scroll.assert_called_once_with(0)

    def test_large_scroll_clicks(self) -> None:
        """大值滚动量不应崩溃。"""
        action = _FakeAction(scroll_clicks=999)
        ctx = _make_ctx(action=action)

        result = MouseScrollDescriptor().execute(ctx)

        assert result.success is True
        ctx.input_ctrl.scroll.assert_called_once_with(999)


class TestStartTimerBoundary:
    """StartTimerDescriptor 边界条件。"""

    def test_empty_timer_name(self) -> None:
        """timer_name 为空字符串仍应委托执行。"""
        action = _FakeAction(timer_name="", timer_timeout=10.0)
        ctx = _make_ctx(action=action)

        result = StartTimerDescriptor().execute(ctx)

        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_start_timer.assert_called_once_with(action)

    def test_zero_timeout(self) -> None:
        """timer_timeout=0 应正常委托。"""
        action = _FakeAction(timer_name="t", timer_timeout=0.0)
        ctx = _make_ctx(action=action)

        result = StartTimerDescriptor().execute(ctx)

        assert result.success is True


class TestIdleBehaviorBoundary:
    """IdleBehaviorDescriptor 边界条件。"""

    def test_zero_idle_duration(self) -> None:
        """idle_duration=0 应正常委托。"""
        action = _FakeAction(idle_duration=0.0, jitter_intensity=0)
        ctx = _make_ctx(action=action)

        result = IdleBehaviorDescriptor().execute(ctx)

        assert result.success is True
        executor = ctx.extra["_executor"]
        executor._do_idle_behavior.assert_called_once_with(action, 0)
