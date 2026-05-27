"""WaitDescriptor + WaitRandomDescriptor 单元测试。

验证固定等待、随机等待的核心逻辑，以及停止信号响应。
所有等待操作通过 mock stop_event 隔离，测试无需实际 sleep。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.descriptors.wait_descriptor import (
    WaitDescriptor,
    WaitRandomDescriptor,
)
from src.core.engine.node_result import NodeResult

from .conftest import _make_ctx as _base_make_ctx


# ---- Fixtures ----


def _make_ctx(
    action: BaseStep,
    *,
    stop: bool = False,
) -> MagicMock:
    """构建模拟 ExecutionContext。"""
    ctx = _base_make_ctx(action=action, stop=stop)
    ctx.pause_event = None
    return ctx


# ---- WaitDescriptor 测试 ----


class TestWaitDescriptor:
    def test_action_type(self) -> None:
        assert WaitDescriptor.action_type() == "WAIT"

    def test_display_name(self) -> None:
        assert WaitDescriptor.display_name() == "等待"

    def test_category(self) -> None:
        assert WaitDescriptor.category() == "基础动作"

    def test_input_types(self) -> None:
        inputs = WaitDescriptor.input_types()
        assert "wait_seconds" in inputs
        assert inputs["wait_seconds"].required

    def test_output_types_empty(self) -> None:
        assert WaitDescriptor.output_types() == {}

    def test_execute_success(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=2.0)
        ctx = _make_ctx(action)

        result = WaitDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success
        assert result.cooldown == 0
        ctx.stop_event.wait.assert_called_once_with(timeout=2.0)

    def test_execute_zero_wait(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=0.0)
        ctx = _make_ctx(action)

        result = WaitDescriptor().execute(ctx)

        assert result.success
        ctx.stop_event.wait.assert_called_once_with(timeout=0.0)

    def test_execute_stopped_mid_wait(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=5.0)
        ctx = _make_ctx(action, stop=True)

        result = WaitDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert not result.success
        assert "停止信号" in str(result.error)

    def test_execute_no_action(self) -> None:
        ctx = _make_ctx(STEP_CLASSES[ActionType.WAIT]())
        ctx.current_node.action = None

        result = WaitDescriptor().execute(ctx)

        assert not result.success
        assert "缺少" in str(result.error)

    def test_metadata_consistency(self) -> None:
        desc = WaitDescriptor()
        assert desc.action_type() == "WAIT"
        assert desc.display_name() == "等待"
        assert desc.category() == "基础动作"

    def test_execute_negative_seconds_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=-1.5)
        ctx = _make_ctx(action)

        result = WaitDescriptor().execute(ctx)

        assert not result.success
        assert "负数" in str(result.error)
        ctx.stop_event.wait.assert_not_called()

    def test_execute_nan_seconds_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=float("nan"))
        ctx = _make_ctx(action)

        result = WaitDescriptor().execute(ctx)

        assert not result.success
        assert "无效" in str(result.error)
        ctx.stop_event.wait.assert_not_called()

    def test_execute_inf_seconds_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=float("inf"))
        ctx = _make_ctx(action)

        result = WaitDescriptor().execute(ctx)

        assert not result.success
        assert "无效" in str(result.error)
        ctx.stop_event.wait.assert_not_called()


# ---- WaitRandomDescriptor 测试 ----


class TestWaitRandomDescriptor:
    def test_action_type(self) -> None:
        assert WaitRandomDescriptor.action_type() == "WAIT_RANDOM"

    def test_display_name(self) -> None:
        assert WaitRandomDescriptor.display_name() == "随机等待"

    def test_category(self) -> None:
        assert WaitRandomDescriptor.category() == "基础动作"

    def test_input_types(self) -> None:
        inputs = WaitRandomDescriptor.input_types()
        assert "wait_min" in inputs
        assert "wait_max" in inputs

    def test_output_types_empty(self) -> None:
        assert WaitRandomDescriptor.output_types() == {}

    def test_execute_success(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=0.5,
            wait_max=2.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success
        ctx.stop_event.wait.assert_called_once()
        call_args = ctx.stop_event.wait.call_args
        timeout = call_args[1]["timeout"]
        assert 0.5 <= timeout <= 2.0

    def test_execute_swapped_min_max(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=3.0,
            wait_max=1.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert result.success
        call_args = ctx.stop_event.wait.call_args
        timeout = call_args[1]["timeout"]
        assert 1.0 <= timeout <= 3.0

    def test_execute_stopped_mid_wait(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=1.0,
            wait_max=5.0,
        )
        ctx = _make_ctx(action, stop=True)

        result = WaitRandomDescriptor().execute(ctx)

        assert not result.success
        assert "停止信号" in str(result.error)

    def test_execute_no_action(self) -> None:
        ctx = _make_ctx(STEP_CLASSES[ActionType.WAIT_RANDOM]())
        ctx.current_node.action = None

        result = WaitRandomDescriptor().execute(ctx)

        assert not result.success
        assert "缺少" in str(result.error)

    def test_execute_equal_min_max(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=2.0,
            wait_max=2.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert result.success
        call_args = ctx.stop_event.wait.call_args
        assert call_args[1]["timeout"] == 2.0

    def test_metadata_consistency(self) -> None:
        desc = WaitRandomDescriptor()
        assert desc.action_type() == "WAIT_RANDOM"
        assert desc.display_name() == "随机等待"
        assert desc.category() == "基础动作"

    def test_execute_both_negative_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=-3.0,
            wait_max=-1.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert not result.success
        assert "负数" in str(result.error)
        ctx.stop_event.wait.assert_not_called()

    def test_execute_negative_min_clamped(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=-1.0,
            wait_max=2.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert result.success
        call_args = ctx.stop_event.wait.call_args
        timeout = call_args[1]["timeout"]
        assert 0.0 <= timeout <= 2.0

    def test_execute_nan_min_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=float("nan"),
            wait_max=2.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert not result.success
        assert "无效" in str(result.error)
        ctx.stop_event.wait.assert_not_called()

    def test_execute_nan_max_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=0.5,
            wait_max=float("nan"),
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert not result.success
        assert "无效" in str(result.error)

    def test_execute_inf_min_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=float("inf"),
            wait_max=2.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert not result.success
        assert "无效" in str(result.error)

    def test_execute_inf_max_fails(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=0.5,
            wait_max=float("inf"),
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert not result.success
        assert "无效" in str(result.error)

    def test_execute_zero_zero(self) -> None:
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=0.0,
            wait_max=0.0,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert result.success
        call_args = ctx.stop_event.wait.call_args
        assert call_args[1]["timeout"] == 0.0


# ---- D18 边界条件补充 ----


class TestWaitDescriptorBoundary:
    """WaitDescriptor 额外边界条件。"""

    def test_execute_very_large_seconds(self) -> None:
        """极大等待时间应正常接受（由 stop_event 控制中断）。"""
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=86400.0)
        ctx = _make_ctx(action)

        result = WaitDescriptor().execute(ctx)

        assert result.success
        ctx.stop_event.wait.assert_called_once_with(timeout=86400.0)


class TestWaitRandomDescriptorBoundary:
    """WaitRandomDescriptor 额外边界条件。"""

    def test_execute_very_small_range(self) -> None:
        """极小范围 [0.001, 0.002] 应正常工作。"""
        action = STEP_CLASSES[ActionType.WAIT_RANDOM](
            wait_min=0.001,
            wait_max=0.002,
        )
        ctx = _make_ctx(action)

        result = WaitRandomDescriptor().execute(ctx)

        assert result.success
        timeout = ctx.stop_event.wait.call_args[1]["timeout"]
        assert 0.001 <= timeout <= 0.002
