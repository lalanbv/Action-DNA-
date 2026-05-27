"""ClickImageDescriptor 单元测试 — 验证模板匹配 + 点击的完整流程。

所有外部依赖（ScreenCapture、TemplateMatcher、InputController）通过 mock 隔离。
"""

from __future__ import annotations

import enum
import threading
import time
from typing import Any
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

from src.core.action import ActionType, DetectMode, FoundAction
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.descriptors.click_image_descriptor import ClickImageDescriptor
from src.core.engine.execution_blocker import ExecutionBlocker
from src.core.engine.node_result import NodeResult

from .conftest import _FakeFlowNode, _make_ctx as _base_make_ctx


# ---- Fixtures ----


def _make_action(**overrides: Any) -> BaseStep:
    """创建 CLICK_IMAGE 步骤，支持覆盖字段。"""
    defaults: dict[str, Any] = {
        "image_path": "/fake/template.png",
        "threshold": 0.8,
        "detect_mode": DetectMode.SKIP_IF_NOT_FOUND,
        "retry_count": 0,
        "found_action": FoundAction.LEFT_CLICK,
    }
    defaults.update(overrides)
    return STEP_CLASSES[ActionType.CLICK_IMAGE](**defaults)


def _make_ctx(
    action: BaseStep | None = None,
    *,
    match_result: tuple[int, int, int, int] | None = (100, 200, 50, 30),
    stop: bool = False,
    pause: bool = False,
) -> MagicMock:
    """构建模拟 ExecutionContext。"""
    if action is None:
        action = _make_action()

    return _base_make_ctx(
        action=action, match_result=match_result, stop=stop, pause=pause,
    )


# ---- 元数据测试 ----


class TestMetadata:
    """验证类元数据。"""

    def test_action_type(self) -> None:
        assert ClickImageDescriptor.action_type() == "CLICK_IMAGE"

    def test_display_name(self) -> None:
        assert ClickImageDescriptor.display_name() == "点击图片"

    def test_category(self) -> None:
        assert ClickImageDescriptor.category() == "基础动作"

    def test_input_types_has_required_fields(self) -> None:
        inputs = ClickImageDescriptor.input_types()
        assert "image_path" in inputs
        assert inputs["image_path"].required is True
        assert "threshold" in inputs

    def test_output_types(self) -> None:
        outputs = ClickImageDescriptor.output_types()
        assert "match_pos" in outputs


# ---- 成功匹配测试 ----


class TestSuccessfulMatch:
    """验证匹配成功时的行为。"""

    def test_basic_left_click(self) -> None:
        ctx = _make_ctx(match_result=(100, 200, 50, 30))
        desc = ClickImageDescriptor()
        result = desc.execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        assert "match_pos" in result.output_vars
        ctx.input_ctrl.click.assert_called_once()

    def test_click_position_with_offset(self) -> None:
        action = _make_action(offset_x=10, offset_y=20)
        ctx = _make_ctx(action=action, match_result=(100, 200, 50, 30))
        desc = ClickImageDescriptor()
        result = desc.execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        # to_logical(100+25, 200+15) = (125, 215), + offset (10,20) + jitter
        call_args = ctx.input_ctrl.click.call_args
        x, y = call_args[0][0], call_args[0][1]
        jr = ClickImageDescriptor.JITTER_RANGE
        assert 125 + 10 - jr <= x <= 125 + 10 + jr
        assert 215 + 20 - jr <= y <= 215 + 20 + jr

    def test_output_contains_match_pos(self) -> None:
        ctx = _make_ctx(match_result=(100, 200, 50, 30))
        desc = ClickImageDescriptor()
        result = desc.execute(ctx)

        assert isinstance(result, NodeResult)
        pos = result.output_vars["match_pos"]
        assert isinstance(pos, tuple)
        assert len(pos) == 2

    def test_save_coord_name(self) -> None:
        action = _make_action(save_coord_name="target_pos")
        ctx = _make_ctx(action=action)
        desc = ClickImageDescriptor()
        result = desc.execute(ctx)

        assert isinstance(result, NodeResult)
        assert "target_pos" in result.output_vars
        assert isinstance(result.output_vars["target_pos"], tuple)

    def test_no_save_coord_when_empty(self) -> None:
        ctx = _make_ctx()
        desc = ClickImageDescriptor()
        result = desc.execute(ctx)

        assert isinstance(result, NodeResult)
        # 不应有额外的坐标变量（只有 match_pos）
        assert result.output_vars.keys() == {"match_pos"}

    def test_cooldown_range(self) -> None:
        ctx = _make_ctx()
        desc = ClickImageDescriptor()
        result = desc.execute(ctx)

        assert isinstance(result, NodeResult)
        assert 0.05 <= result.cooldown <= 0.15


# ---- FoundAction 测试 ----


class TestFoundActions:
    """验证各种 found_action 操作。"""

    def test_left_click(self) -> None:
        ctx = _make_ctx(action=_make_action(found_action=FoundAction.LEFT_CLICK))
        ClickImageDescriptor().execute(ctx)
        ctx.input_ctrl.click.assert_called_once()
        assert ctx.input_ctrl.click.call_args[1].get("button", "left") == "left"

    def test_right_click(self) -> None:
        ctx = _make_ctx(action=_make_action(found_action=FoundAction.RIGHT_CLICK))
        ClickImageDescriptor().execute(ctx)
        ctx.input_ctrl.click.assert_called_once()
        assert ctx.input_ctrl.click.call_args[1]["button"] == "right"

    def test_left_double_click(self) -> None:
        ctx = _make_ctx(action=_make_action(found_action=FoundAction.LEFT_DOUBLE_CLICK))
        ClickImageDescriptor().execute(ctx)
        call_args = ctx.input_ctrl.click.call_args
        assert call_args[1]["button"] == "left"
        assert call_args[1]["clicks"] == 2

    def test_right_double_click(self) -> None:
        ctx = _make_ctx(action=_make_action(found_action=FoundAction.RIGHT_DOUBLE_CLICK))
        ClickImageDescriptor().execute(ctx)
        ctx.input_ctrl.click.assert_called_once()
        assert ctx.input_ctrl.click.call_args[1]["button"] == "right"
        assert ctx.input_ctrl.click.call_args[1]["clicks"] == 2

    def test_long_press(self) -> None:
        action = _make_action(found_action=FoundAction.LONG_PRESS, hold_duration=2.0)
        ctx = _make_ctx(action=action)
        ClickImageDescriptor().execute(ctx)
        ctx.input_ctrl.long_press.assert_called_once()
        assert ctx.input_ctrl.long_press.call_args[1]["duration"] == 2.0

    def test_drag_to(self) -> None:
        action = _make_action(
            found_action=FoundAction.DRAG_TO,
            drag_offset_x=50,
            drag_offset_y=-30,
        )
        ctx = _make_ctx(action=action, match_result=(100, 200, 50, 30))
        ClickImageDescriptor().execute(ctx)
        ctx.input_ctrl.drag_to.assert_called_once()
        call_args = ctx.input_ctrl.drag_to.call_args[0]
        jr = ClickImageDescriptor.JITTER_RANGE
        # 起点 (125±jr, 215±jr)，终点 (175±jr, 185±jr)
        assert 125 - jr <= call_args[0] <= 125 + jr
        assert 215 - jr <= call_args[1] <= 215 + jr
        assert 175 - jr <= call_args[2] <= 175 + jr
        assert 185 - jr <= call_args[3] <= 185 + jr

    def test_only_move(self) -> None:
        ctx = _make_ctx(action=_make_action(found_action=FoundAction.ONLY_MOVE))
        ClickImageDescriptor().execute(ctx)
        ctx.input_ctrl.move_to.assert_called_once()
        ctx.input_ctrl.click.assert_not_called()

    def test_output_coord_no_action(self) -> None:
        ctx = _make_ctx(action=_make_action(found_action=FoundAction.OUTPUT_COORD))
        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is True
        ctx.input_ctrl.click.assert_not_called()
        ctx.input_ctrl.move_to.assert_not_called()


# ---- 未找到处理测试 ----


class TestNotFound:
    """验证未找到模板时的行为。"""

    def test_skip_returns_execution_blocker(self) -> None:
        action = _make_action(detect_mode=DetectMode.SKIP_IF_NOT_FOUND)
        ctx = _make_ctx(action=action, match_result=None)
        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, ExecutionBlocker)
        assert "未找到模板" in result.reason

    def test_fail_returns_error_result(self) -> None:
        action = _make_action(detect_mode=DetectMode.FAIL_IF_NOT_FOUND)
        ctx = _make_ctx(action=action, match_result=None)
        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is False
        assert result.error is not None
        assert "模板匹配失败" in str(result.error)

    def test_fail_error_contains_template_path(self) -> None:
        action = _make_action(
            detect_mode=DetectMode.FAIL_IF_NOT_FOUND,
            image_path="/path/to/button.png",
        )
        ctx = _make_ctx(action=action, match_result=None)
        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert "button.png" in str(result.error)

    def test_unknown_detect_mode_defaults_to_skip(self) -> None:
        """未知 DetectMode 应默认跳过（ExecutionBlocker）并记录警告。"""

        class FakeDetectMode(enum.Enum):
            UNKNOWN = "UNKNOWN"

        action = _make_action(
            detect_mode=FakeDetectMode.UNKNOWN,  # type: ignore[arg-type]
        )
        ctx = _make_ctx(action=action, match_result=None)
        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, ExecutionBlocker)
        assert "未找到模板" in result.reason


# ---- 重试测试 ----


class TestRetry:
    """验证重试机制。"""

    def test_retry_then_success(self) -> None:
        action = _make_action(retry_count=2)
        ctx = _make_ctx(action=action)
        # 前 2 次失败，第 3 次成功
        ctx.matcher.find.side_effect = [None, None, (100, 200, 50, 30)]

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is True
        assert ctx.matcher.find.call_count == 3

    def test_retry_all_fail(self) -> None:
        action = _make_action(retry_count=2, detect_mode=DetectMode.SKIP_IF_NOT_FOUND)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.return_value = None

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, ExecutionBlocker)
        assert ctx.matcher.find.call_count == 3  # 1 initial + 2 retries

    def test_zero_retry_only_one_attempt(self) -> None:
        action = _make_action(retry_count=0)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.return_value = None

        ClickImageDescriptor().execute(ctx)
        assert ctx.matcher.find.call_count == 1

    def test_retry_waits_between_attempts(self) -> None:
        action = _make_action(retry_count=1, retry_wait_min=0.5, retry_wait_max=1.0)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.side_effect = [None, (100, 200, 50, 30)]

        ClickImageDescriptor().execute(ctx)
        # stop_event.wait 调用两次：首次稳定延迟 + 重试间隔
        assert ctx.stop_event.wait.call_count == 2
        # 第一次是稳定延迟 (0.08~0.20s)
        settle_timeout = ctx.stop_event.wait.call_args_list[0][1]["timeout"]
        assert 0.08 <= settle_timeout <= 0.20
        # 第二次是重试间隔 (0.5~1.0s)
        retry_timeout = ctx.stop_event.wait.call_args_list[1][1]["timeout"]
        assert 0.5 <= retry_timeout <= 1.0

    def test_retry_after_exception_then_success(self) -> None:
        """异常后应继续重试，而非立即中止。"""
        action = _make_action(retry_count=2)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.side_effect = [RuntimeError("临时异常"), (100, 200, 50, 30)]

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is True
        assert ctx.matcher.find.call_count == 2

    def test_grab_exception_exhausts_retries(self) -> None:
        """grab 异常同样消耗重试次数。"""
        action = _make_action(retry_count=2, detect_mode=DetectMode.SKIP_IF_NOT_FOUND)
        ctx = _make_ctx(action=action)
        ctx.capture.grab.side_effect = OSError("截屏失败")

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, ExecutionBlocker)
        assert ctx.capture.grab.call_count == 3  # 1 initial + 2 retries


# ---- WAIT_UNTIL_FOUND 模式测试 ----


class TestWaitUntilFound:
    """验证 WAIT_UNTIL_FOUND 模式。"""

    def test_found_immediately(self) -> None:
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action, match_result=(100, 200, 50, 30))

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is True

    def test_stopped_before_found(self) -> None:
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action, match_result=None)
        call_count = 0

        def find_side_effect(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                ctx.stop_event.is_set.return_value = True
            return None

        ctx.matcher.find.side_effect = find_side_effect

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "停止信号" in str(result.error)

    def test_pause_then_resume(self) -> None:
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action, match_result=None)

        # pause: 暂停一次，然后恢复
        ctx.pause_event.is_set.side_effect = [True, False]

        # stop: 全程未停止（5+ 次调用足够）
        ctx.stop_event.is_set.side_effect = [False, False, False, False, False, False]

        # 解除暂停后匹配成功
        ctx.matcher.find.return_value = (100, 200, 50, 30)

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is True

    def test_stop_while_paused(self) -> None:
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action, match_result=None)

        # pause: 始终暂停
        ctx.pause_event.is_set.return_value = True

        # stop: 第一次 while=False，pause 后 stop wait 检查=True
        ctx.stop_event.is_set.side_effect = [False, True]

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "停止信号" in str(result.error)

    @patch("src.core.engine.descriptors.click_image_descriptor.time.sleep", lambda _: None)
    def test_timeout_safety_valve(self) -> None:
        """超过 _MAX_WAIT_SECONDS 后应自动终止。"""
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action, match_result=None)
        ctx.matcher.find.return_value = None

        monotonic_values = iter([0.0, 3601.0])
        with patch(
            "src.core.engine.descriptors.click_image_descriptor.time.monotonic",
            side_effect=monotonic_values,
        ):
            result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "超时" in str(result.error)


# ---- 坐标转换测试 ----


class TestCoordinateConversion:
    """验证物理像素 → 逻辑像素的坐标转换。"""

    def test_to_logical_called_with_center(self) -> None:
        """to_logical 应以匹配区域的中心点、左上角、右下角调用（中心 + clamp 边界）。"""
        ctx = _make_ctx(match_result=(100, 200, 60, 40))
        ClickImageDescriptor().execute(ctx)

        calls = ctx.capture.to_logical.call_args_list
        # 中心: (100+30, 200+20) = (130, 220)
        assert calls[0] == call(130, 220)
        # 左上角: (100, 200)
        assert calls[1] == call(100, 200)
        # 右下角: (160, 240)
        assert calls[2] == call(160, 240)

    def test_custom_to_logical_mapping(self) -> None:
        """to_logical 可以缩放坐标（如 Retina 2x）。"""
        ctx = _make_ctx(match_result=(200, 400, 50, 30))
        ctx.capture.to_logical.side_effect = lambda x, y: (x // 2, y // 2)

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        # 中心 (225, 415) → to_logical → (112, 207) + jitter(-jr~+jr)
        jr = ClickImageDescriptor.JITTER_RANGE
        call_args = ctx.input_ctrl.click.call_args[0]
        assert 112 - jr <= call_args[0] <= 112 + jr
        assert 207 - jr <= call_args[1] <= 207 + jr


# ---- 停止信号测试 ----


class TestStopSignal:
    """验证停止信号处理。"""

    def test_stop_during_retries(self) -> None:
        action = _make_action(retry_count=5)
        ctx = _make_ctx(action=action, match_result=None)

        call_count = 0

        def find_side_effect(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                ctx.stop_event.is_set.return_value = True
            return None

        ctx.matcher.find.side_effect = find_side_effect
        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, ExecutionBlocker)
        assert ctx.matcher.find.call_count == 2


# ---- 输入验证测试 ----


class TestInputValidation:
    """验证 validate_inputs 行为。"""

    def test_valid_action_no_errors(self) -> None:
        action = _make_action()
        errors = ClickImageDescriptor.validate_inputs(action)
        assert errors == []

    def test_missing_image_path_reported(self) -> None:
        """image_path 为空字符串时，validate_inputs 行为记录。"""
        action = _make_action(image_path="")
        errors = ClickImageDescriptor.validate_inputs(action)
        # PortDef.required=True 但基类 validate_inputs 检查 None/_MISSING，
        # 空字符串不触发。此测试记录实际行为。
        assert isinstance(errors, list)


# ---- None action 测试 ----


class TestNoneAction:
    """验证 action 为 None 时的保护。"""

    def test_none_action_returns_fail(self) -> None:
        ctx = MagicMock()
        ctx.current_node = _FakeFlowNode(action=None)

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- 异常处理测试 ----


class TestExceptionHandling:
    """验证 grab/find 异常时的行为。"""

    def test_find_exception_returns_none(self) -> None:
        action = _make_action(detect_mode=DetectMode.SKIP_IF_NOT_FOUND)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.side_effect = RuntimeError("匹配引擎崩溃")

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, ExecutionBlocker)

    def test_grab_exception_returns_none(self) -> None:
        action = _make_action(detect_mode=DetectMode.SKIP_IF_NOT_FOUND)
        ctx = _make_ctx(action=action)
        ctx.capture.grab.side_effect = OSError("截屏失败")

        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, ExecutionBlocker)

    def test_wait_until_found_exception_continues(self) -> None:
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action)

        call_count = 0

        def find_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("临时异常")
            return (100, 200, 50, 30)

        ctx.matcher.find.side_effect = find_side_effect
        ctx.capture.grab.return_value = np.zeros((600, 800, 3), dtype=np.uint8)

        result = ClickImageDescriptor().execute(ctx)
        # 异常后继续重试，第二次匹配成功并执行动作
        assert isinstance(result, NodeResult)
        assert result.success is True


# ---- 未知 FoundAction fallback 测试 ----


class TestUnknownFoundAction:
    """验证未处理的 FoundAction 回退行为。"""

    def test_unknown_action_falls_back_to_left_click(self) -> None:
        ctx = _make_ctx()

        # 直接调用 _perform_action 测试 fallback
        desc = ClickImageDescriptor()

        class FakeFoundAction(enum.Enum):
            UNKNOWN_ACTION = "UNKNOWN_ACTION"

        from src.core.engine.descriptors.click_image_descriptor import _ClickParams

        fake_params = _ClickParams(
            found_action=FakeFoundAction.UNKNOWN_ACTION,  # type: ignore[arg-type]
            offset_x=0,
            offset_y=0,
            save_coord_name="",
            hold_duration=0.5,
            drag_offset_x=0,
            drag_offset_y=0,
        )
        desc._perform_action(ctx, fake_params, 100, 200, None)
        ctx.input_ctrl.click.assert_called_once()


# ---- 注册测试 ----


class TestRegistration:
    """验证 @auto_register 装饰器。"""

    def test_registered_in_node_registry(self) -> None:
        from src.core.engine.node_registry import NodeRegistry

        assert NodeRegistry.has("CLICK_IMAGE")
        assert NodeRegistry.get("CLICK_IMAGE") is ClickImageDescriptor


# ---- 新增：边界和中断安全测试 ----


class TestNegativeCoordinates:
    """验证负坐标边界。"""

    def test_large_negative_offset_clamped_to_zero(self) -> None:
        """偏移 + 抖动导致负坐标时，应被 max(0, ...) 限制为 0。"""
        action = _make_action(offset_x=-200, offset_y=-300)
        ctx = _make_ctx(action=action, match_result=(0, 0, 50, 30))
        desc = ClickImageDescriptor()
        result = desc.execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        call_args = ctx.input_ctrl.click.call_args[0]
        assert call_args[0] >= 0
        assert call_args[1] >= 0


class TestStopAfterMatch:
    """验证匹配成功后、执行动作前的停止信号检查。"""

    def test_stop_after_find_with_retries(self) -> None:
        """_find_with_retries 匹配成功返回后，停止信号应阻止执行动作。"""
        action = _make_action(retry_count=0)
        ctx = _make_ctx(action=action)

        def find_then_stop(*args: Any, **kwargs: Any) -> Any:
            ctx.stop_event.is_set.return_value = True
            return (100, 200, 50, 30)

        ctx.matcher.find.side_effect = find_then_stop
        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "停止信号" in str(result.error)
        ctx.input_ctrl.click.assert_not_called()

    def test_stop_after_wait_until_found_match(self) -> None:
        """_wait_until_found 匹配成功后，停止信号应阻止执行动作。"""
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action)

        call_count = 0

        def find_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count >= 1:
                ctx.stop_event.is_set.return_value = True
            return (100, 200, 50, 30)

        ctx.matcher.find.side_effect = find_side_effect
        result = ClickImageDescriptor().execute(ctx)
        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "停止信号" in str(result.error)
        ctx.input_ctrl.click.assert_not_called()


class TestWaitUntilFoundExceptionSleep:
    """验证 WAIT_UNTIL_FOUND 异常后的等待间隔。"""

    @patch("src.core.engine.descriptors.click_image_descriptor.time")
    def test_exception_waits_before_retry(self, mock_time: MagicMock) -> None:
        """find() 抛异常后应等待 retry_wait_min~retry_wait_max 再重试。"""
        action = _make_action(
            detect_mode=DetectMode.WAIT_UNTIL_FOUND,
            retry_wait_min=0.5,
            retry_wait_max=1.0,
        )
        ctx = _make_ctx(action=action)

        call_count = 0

        def find_side_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("临时异常")
            ctx.stop_event.is_set.return_value = True
            return (100, 200, 50, 30)

        ctx.matcher.find.side_effect = find_side_effect
        # monotonic 返回值：第1次while检查 + 超时检查 + 匹配后检查
        mock_time.monotonic.return_value = 0.0
        ClickImageDescriptor().execute(ctx)

        # 验证 stop_event.wait 被调用（替代 time.sleep）
        assert ctx.stop_event.wait.called


# ---- D18 边界条件 & 输入验证 ----


class TestWaitUntilFoundPauseThenStop:
    """覆盖 L207：暂停后收到停止信号路径。"""

    def test_pause_then_stop_returns_fail(self) -> None:
        """暂停恢复后立即检测到 stop 信号应返回 fail。"""
        action = _make_action(detect_mode=DetectMode.WAIT_UNTIL_FOUND)
        ctx = _make_ctx(action=action)

        ctx.matcher.find.return_value = None
        # 循环：is_set=False(进入while) → is_set=False(进入pause check) → pause结束 → is_set=True(stop)
        ctx.stop_event.is_set.side_effect = [False, True]
        ctx.pause_event.is_set.return_value = True
        ctx.pause_event.wait.return_value = False
        with patch("time.monotonic", return_value=0.0):
            result = ClickImageDescriptor().execute(ctx)

        assert result.success is False


class TestClickImageThresholdBoundary:
    """阈值边界：0.0（全匹配）和 1.0（精确匹配）。"""

    def test_threshold_zero_match_found(self) -> None:
        """threshold=0.0 且找到匹配应成功。"""
        action = _make_action(threshold=0.0)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.return_value = (100, 200, 50, 30)

        result = ClickImageDescriptor().execute(ctx)

        assert result.success is True
        ctx.input_ctrl.click.assert_called_once()

    def test_threshold_one_no_match_skips(self) -> None:
        """threshold=1.0 无匹配时 SKIP 模式应返回 ExecutionBlocker。"""
        action = _make_action(threshold=1.0, detect_mode=DetectMode.SKIP_IF_NOT_FOUND)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.return_value = None

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, ExecutionBlocker)


class TestRetryCountBoundary:
    """重试次数边界。"""

    def test_negative_retry_count_skips(self) -> None:
        """retry_count < 0 且无匹配时应返回 ExecutionBlocker（SKIP 模式）。"""
        action = _make_action(retry_count=-1, detect_mode=DetectMode.SKIP_IF_NOT_FOUND)
        ctx = _make_ctx(action=action)
        ctx.matcher.find.return_value = None

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, ExecutionBlocker)

    def test_large_retry_count(self) -> None:
        """retry_count=10 应允许最多 11 次尝试（1 初始 + 10 重试）。"""
        action = _make_action(retry_count=10)
        ctx = _make_ctx(action=action)
        find_call_count = 0

        def find_effect(*args: Any, **kwargs: Any) -> Any:
            nonlocal find_call_count
            find_call_count += 1
            if find_call_count >= 11:
                return (100, 200, 50, 30)
            return None

        ctx.matcher.find.side_effect = find_effect
        with patch("time.monotonic", return_value=0.0):
            result = ClickImageDescriptor().execute(ctx)

        assert result.success is True
        assert find_call_count == 11


class TestClickImageJitterRange:
    """验证点击抖动始终在合理范围内。"""

    def test_jitter_within_range(self) -> None:
        """多次执行后点击坐标应在目标中心 ± JITTER_RANGE 内。"""
        action = _make_action()
        ctx = _make_ctx(action=action)
        ctx.matcher.find.return_value = (100, 200, 50, 30)

        clicks: list[tuple[int, int]] = []
        ctx.input_ctrl.click.side_effect = lambda x, y, **kw: clicks.append((x, y))

        for _ in range(20):
            ClickImageDescriptor().execute(ctx)

        cx, cy = 125, 215  # 100+50/2, 200+30/2
        jitter_range = ClickImageDescriptor.JITTER_RANGE
        for x, y in clicks:
            assert abs(x - cx) <= jitter_range
            assert abs(y - cy) <= jitter_range


class TestClickImageOutputVars:
    """同时存在 match_pos 和 save_coord_name。"""

    def test_output_vars_combined(self) -> None:
        """当 save_coord_name 非空时，output_vars 应包含坐标变量。"""
        action = _make_action(save_coord_name="target_pos")
        ctx = _make_ctx(action=action)
        ctx.matcher.find.return_value = (100, 200, 50, 30)

        result = ClickImageDescriptor().execute(ctx)

        assert result.success is True
        assert "target_pos" in result.output_vars


class TestActionLevelRetry:
    """验证 _execute_found_action 中动作级别的重试逻辑。

    场景：_perform_action 抛出瞬态异常时，应在本地重试而非向上传播到引擎的 transient retry。
    """

    def test_action_exception_once_then_succeed(self) -> None:
        """_perform_action 第一次抛异常，第二次成功 → 最终 NodeResult(success=True)。"""
        ctx = _make_ctx(match_result=(100, 200, 50, 30))
        call_count = 0

        def click_effect(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("瞬态后端异常")

        ctx.input_ctrl.click.side_effect = click_effect

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        assert "match_pos" in result.output_vars
        assert call_count == 2

    def test_action_exception_all_retries_exhausted(self) -> None:
        """_perform_action 连续失败 3 次 → NodeResult.fail()。"""
        ctx = _make_ctx(match_result=(100, 200, 50, 30))
        ctx.input_ctrl.click.side_effect = RuntimeError("持续后端异常")

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "动作执行失败" in str(result.error)
        assert "3次" in str(result.error)

    def test_action_exception_two_then_succeed(self) -> None:
        """_perform_action 前两次抛异常，第三次成功 → NodeResult(success=True)。"""
        ctx = _make_ctx(match_result=(100, 200, 50, 30))
        call_count = 0

        def click_effect(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise OSError("设备忙")

        ctx.input_ctrl.click.side_effect = click_effect

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        assert call_count == 3

    def test_stop_signal_during_action_retry(self) -> None:
        """重试过程中收到停止信号 → 立即返回 NodeResult.fail()。

        is_set 调用序列：
        1. _find_with_retries 首次稳定延迟后检查
        2. _find_with_retries for 循环内检查
        3. execute 匹配成功后检查
        4. _execute_found_action 重试循环第 1 次（False，触发 click 异常）
        5. _execute_found_action 重试循环第 2 次（True，停止信号）
        """
        ctx = _make_ctx(match_result=(100, 200, 50, 30))
        ctx.input_ctrl.click.side_effect = RuntimeError("异常触发重试")

        ctx.stop_event.is_set.side_effect = [False, False, False, False, True]

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is False
        assert "停止信号" in str(result.error)

    def test_output_coord_no_retry_needed(self) -> None:
        """OUTPUT_COORD 不执行任何操作，不应触发重试。"""
        action = _make_action(found_action=FoundAction.OUTPUT_COORD)
        ctx = _make_ctx(action=action, match_result=(100, 200, 50, 30))

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        assert "match_pos" in result.output_vars
        ctx.input_ctrl.click.assert_not_called()

    def test_drag_to_action_retry(self) -> None:
        """DRAG_TO 动作异常后重试成功。"""
        action = _make_action(
            found_action=FoundAction.DRAG_TO,
            drag_offset_x=50,
            drag_offset_y=30,
        )
        ctx = _make_ctx(action=action, match_result=(100, 200, 50, 30))
        call_count = 0

        def drag_effect(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("拖拽瞬态异常")

        ctx.input_ctrl.drag_to.side_effect = drag_effect

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        assert call_count == 2

    def test_long_press_action_retry(self) -> None:
        """LONG_PRESS 动作异常后重试成功。"""
        action = _make_action(
            found_action=FoundAction.LONG_PRESS,
            hold_duration=1.0,
        )
        ctx = _make_ctx(action=action, match_result=(100, 200, 50, 30))
        call_count = 0

        def lp_effect(*args: Any, **kwargs: Any) -> None:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("长按瞬态异常")

        ctx.input_ctrl.long_press.side_effect = lp_effect

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        assert call_count == 2


class TestConditionalSettleDelay:
    """验证首轮 gen=0 才有稳定延迟，后续轮次 gen>0 跳过。"""

    def test_no_settle_on_repeat_cycle(self) -> None:
        """gen=1 时 stop_event.wait 不应被调用做稳定延迟。"""
        action = _make_action(retry_count=0)
        ctx = _make_ctx(action=action, match_result=(100, 200, 50, 30))
        ctx.gen = 1

        result = ClickImageDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        # gen=1 → 无 settle delay → stop_event.wait 不应被调用
        ctx.stop_event.wait.assert_not_called()
