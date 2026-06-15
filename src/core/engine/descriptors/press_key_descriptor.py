"""PressKeyDescriptor — 按键/鼠标点击描述符。

支持键盘按键和特殊鼠标键（mouse_ 前缀）。
迁移自 ActionExecutor PRESS_KEY case (action_executor.py:427-431)。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult
from src.core.step_types import PressKeyStep
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["PressKeyDescriptor"]


@auto_register
class PressKeyDescriptor(NodeDescriptor):
    """按键描述符 — 执行键盘按键或鼠标点击。

    key 字段支持两种格式：
    - 普通按键（如 "enter", "space", "a"）→ input_ctrl.press_key()
    - 鼠标键（如 "mouse_left", "mouse_right"）→ input_ctrl.click_current_pos()
    """

    @classmethod
    def action_type(cls) -> str:
        return "PRESS_KEY"

    @classmethod
    def display_name(cls) -> str:
        return "按键"

    @classmethod
    def category(cls) -> str:
        return "基础动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "key": PortDef("string", "按键名称", required=True),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        if action is None:
            return NodeResult.fail("PRESS_KEY 节点缺少步骤配置")

        if not isinstance(action, PressKeyStep):
            return NodeResult.fail(
                f"PRESS_KEY 节点配置类型错误，期望 PressKeyStep，实际: {type(action).__name__}",
            )

        key = action.key
        if not key:
            return NodeResult.fail("PRESS_KEY 节点未指定按键")

        if key.startswith("mouse_"):
            button = key.removeprefix("mouse_")
            ctx.input_ctrl.click_current_pos(button)
            logger.info(t("engine.log.mouse_click_current", button=button))
        else:
            ctx.input_ctrl.press_key(key)
            logger.info(t("engine.log.press_key", key_name=key))

        return NodeResult.ok()
