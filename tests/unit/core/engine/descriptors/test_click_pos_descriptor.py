"""ClickPosDescriptor 单元测试。

验证固定坐标点击描述符：直接坐标、变量坐标、空配置校验。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.engine.descriptors.click_pos_descriptor import ClickPosDescriptor
from src.core.step_types import ClickPosStep

from .conftest import _FakeFlowNode, _make_ctx as _base_make_ctx


# ---- Fixtures ----


def _make_ctx(
    *,
    pos_x: int = 100,
    pos_y: int = 200,
    use_coord_var: bool = False,
    coord_var_name: str = "",
    var_coords: tuple[int, int] | None = None,
    action: ClickPosStep | None = None,
) -> MagicMock:
    action = action or ClickPosStep(
        pos_x=pos_x, pos_y=pos_y,
        use_coord_var=use_coord_var, coord_var_name=coord_var_name,
    )
    ctx = _base_make_ctx(action=action)

    if var_coords is not None:
        ctx.variables.get.return_value = var_coords
    else:
        ctx.variables.get.return_value = None

    return ctx


# ---- Tests ----


class TestClickPosMetadata:
    def test_action_type(self) -> None:
        assert ClickPosDescriptor.action_type() == "CLICK_POS"

    def test_display_name(self) -> None:
        assert ClickPosDescriptor.display_name() == "点击坐标"

    def test_category(self) -> None:
        assert ClickPosDescriptor.category() == "基础动作"

    def test_input_types(self) -> None:
        types = ClickPosDescriptor.input_types()
        assert "pos_x" in types
        assert "pos_y" in types
        assert "use_coord_var" in types
        assert "coord_var_name" in types

    def test_output_types_empty(self) -> None:
        assert ClickPosDescriptor.output_types() == {}


class TestClickPosDirectCoords:
    def test_click_direct_coords(self) -> None:
        ctx = _make_ctx(pos_x=150, pos_y=250)
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click.assert_called_once_with(150, 250, button="left", clicks=1)

    def test_click_zero_coords(self) -> None:
        ctx = _make_ctx(pos_x=0, pos_y=0)
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click.assert_called_once_with(0, 0, button="left", clicks=1)


class TestClickPosVariableCoords:
    def test_variable_coords(self) -> None:
        ctx = _make_ctx(
            use_coord_var=True,
            coord_var_name="target_pos",
            var_coords=(300, 400),
        )
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click.assert_called_once_with(300, 400, button="left", clicks=1)
        ctx.variables.get.assert_called_once_with("target_pos")

    def test_variable_undefined_fails(self) -> None:
        ctx = _make_ctx(
            use_coord_var=True,
            coord_var_name="missing_var",
            var_coords=None,
        )
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is False
        assert "missing_var" in str(result.error)

    def test_use_coord_var_false_ignores_variable(self) -> None:
        ctx = _make_ctx(
            pos_x=50, pos_y=60,
            use_coord_var=False,
            coord_var_name="ignored_var",
            var_coords=(999, 999),
        )
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click.assert_called_once_with(50, 60, button="left", clicks=1)


class TestClickPosNoAction:
    def test_no_action_fails(self) -> None:
        ctx = _make_ctx()
        ctx.current_node = _FakeFlowNode(action=None)
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is False
        assert "缺少步骤配置" in str(result.error)


# ---- D18 边界条件 & 输入验证 ----


class TestClickPosBoundary:
    """坐标边界与极端值验证。"""

    def test_negative_coords(self) -> None:
        """负坐标不应崩溃。"""
        ctx = _make_ctx(pos_x=-100, pos_y=-200)
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click.assert_called_once_with(-100, -200, button="left", clicks=1)

    def test_large_coords(self) -> None:
        """超大坐标（超出屏幕）不应崩溃。"""
        ctx = _make_ctx(pos_x=99999, pos_y=99999)
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is True
        ctx.input_ctrl.click.assert_called_once_with(99999, 99999, button="left", clicks=1)

    def test_variable_coords_tuple_types(self) -> None:
        """变量坐标应接受 float 或 int 元组。"""
        ctx = _make_ctx(
            use_coord_var=True,
            coord_var_name="pos",
            var_coords=(100.5, 200.5),
        )
        result = ClickPosDescriptor().execute(ctx)
        assert result.success is True
