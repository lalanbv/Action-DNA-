"""ClickPosDescriptor — 固定坐标点击描述符。

支持直接坐标和从变量池读取坐标。
迁移自 ActionExecutor CLICK_POS case (action_executor.py:432-441)。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult
from src.core.step_types import ClickPosStep
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["ClickPosDescriptor"]


@auto_register
class ClickPosDescriptor(NodeDescriptor):
    """固定坐标点击描述符 — 点击指定位置或从变量读取坐标。

    两种模式：
    - 直接坐标：使用 pos_x, pos_y
    - 变量坐标：use_coord_var=True 时从 VariablePool 读取 coord_var_name
    """

    @classmethod
    def action_type(cls) -> str:
        return "CLICK_POS"

    @classmethod
    def display_name(cls) -> str:
        return "点击坐标"

    @classmethod
    def category(cls) -> str:
        return "基础动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "pos_x": PortDef("number", "X 坐标", required=False, default=0),
            "pos_y": PortDef("number", "Y 坐标", required=False, default=0),
            "use_coord_var": PortDef("bool", "使用坐标变量", required=False, default=False),
            "coord_var_name": PortDef("string", "坐标变量名", required=False, default=""),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        if action is None:
            return NodeResult.fail(t("engine.node_fail.missing_step_config", node_type="CLICK_POS"))

        if not isinstance(action, ClickPosStep):
            return NodeResult.fail(
                t("engine.node_fail.step_config_type_error", node_type="CLICK_POS", expected_type="ClickPosStep", actual_type=type(action).__name__),
            )

        step: ClickPosStep = action

        if step.use_coord_var and step.coord_var_name:
            coords = ctx.variables.get(step.coord_var_name)
            if coords is None:
                return NodeResult.fail(
                    t("engine.node_fail.coord_var_undefined", coord_var_name=step.coord_var_name),
                )
            if (
                not isinstance(coords, (list, tuple))
                or len(coords) < 2
            ):
                return NodeResult.fail(
                    t("engine.node_fail.coord_var_format_error", coord_var_name=step.coord_var_name, coords=coords),
                )
            x, y = coords[0], coords[1]
            logger.info(
                t("engine.log.click_pos_coord_var", name=step.coord_var_name, x=x, y=y)
            )
        else:
            x, y = step.pos_x, step.pos_y

        if step.path_points:
            ctx.input_ctrl.replay_path(
                step.path_points,
                time_scale=step.move_speed / max(step.recorded_duration, 0.01),
            )

        if step.hold_duration > 0.3:
            ctx.input_ctrl.long_press(x, y, duration=step.hold_duration)
            logger.info(
                t(
                    "engine.log.click_pos_hold",
                    x=x, y=y, button=step.button, duration=step.hold_duration,
                )
            )
        else:
            ctx.input_ctrl.click(
                x, y, button=step.button, clicks=step.clicks,
            )
            logger.info(
                t(
                    "engine.log.click_pos",
                    x=x, y=y, button=step.button, clicks=step.clicks,
                )
            )

        return NodeResult.ok()
