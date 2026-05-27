"""PressKeyDescriptor 单元测试。

验证按键描述符的元数据、键盘按键、鼠标键、空键校验。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.engine.descriptors.press_key_descriptor import PressKeyDescriptor
from src.core.step_types import PressKeyStep

from .conftest import _FakeFlowNode, _make_ctx as _base_make_ctx


# ---- Fixtures ----


def _make_ctx(*, key: str = "enter", action: PressKeyStep | None = None) -> MagicMock:
    action = action or PressKeyStep(key=key)
    return _base_make_ctx(action=action)


# ---- Tests ----


class TestPressKeyMetadata:
    def test_action_type(self) -> None:
        assert PressKeyDescriptor.action_type() == "PRESS_KEY"

    def test_display_name(self) -> None:
        assert PressKeyDescriptor.display_name() == "按键"

    def test_category(self) -> None:
        assert PressKeyDescriptor.category() == "基础动作"

    def test_input_types(self) -> None:
        types = PressKeyDescriptor.input_types()
        assert "key" in types

    def test_output_types_empty(self) -> None:
        assert PressKeyDescriptor.output_types() == {}


class TestPressKeyExecute:
    def test_normal_key_calls_press_key(self) -> None:
        ctx = _make_ctx(key="space")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.press_key.assert_called_once_with("space")

    def test_mouse_key_calls_click_current_pos(self) -> None:
        ctx = _make_ctx(key="mouse_left")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click_current_pos.assert_called_once_with("left")

    def test_mouse_right(self) -> None:
        ctx = _make_ctx(key="mouse_right")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click_current_pos.assert_called_once_with("right")

    def test_empty_key_fails(self) -> None:
        ctx = _make_ctx(key="")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is False
        assert "未指定按键" in str(result.error)

    def test_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is False
        assert "缺少步骤配置" in str(result.error)

    def test_enter_key(self) -> None:
        ctx = _make_ctx(key="enter")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.press_key.assert_called_once_with("enter")

    def test_multi_char_key(self) -> None:
        ctx = _make_ctx(key="ctrl")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.press_key.assert_called_once_with("ctrl")


# ---- D18 边界条件 & 输入验证 ----


class TestPressKeyBoundary:
    """按键边界与极端值验证。"""

    def test_mouse_middle(self) -> None:
        """mouse_middle 应映射到 click_current_pos('middle')。"""
        ctx = _make_ctx(key="mouse_middle")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click_current_pos.assert_called_once_with("middle")

    def test_special_key_name(self) -> None:
        """特殊键名如 'f12' 应正常传递。"""
        ctx = _make_ctx(key="f12")
        result = PressKeyDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.press_key.assert_called_once_with("f12")
