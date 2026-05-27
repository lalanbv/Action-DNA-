"""ConditionDescriptor — 条件分支节点。

评估 FlowNode.condition 中的条件表达式，根据结果走 "true" 或 "false" 边。
迁移自 ActionExecutor._evaluate_condition_branch (action_executor.py:295-307)。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["ConditionDescriptor"]


@auto_register
class ConditionDescriptor(NodeDescriptor):
    """条件分支描述符 — 评估条件，走 true/false 边。

    出边标签约定：
    - "true":  条件成立
    - "false": 条件不成立

    GraphEngine._resolve_next_node 根据 next_label 决定下一条边。
    """

    @classmethod
    def action_type(cls) -> str:
        return "CONDITION"

    @classmethod
    def display_name(cls) -> str:
        return "条件"

    @classmethod
    def category(cls) -> str:
        return "流程控制"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "condition": PortDef("condition", "条件表达式", required=False),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "result": PortDef("bool", "条件评估结果", required=False),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        node = ctx.current_node
        condition = node.condition

        if condition is None:
            logger.info("条件节点 %s: 无条件配置，默认走 true", node.node_id)
            return NodeResult(
                success=True,
                next_label="true",
                output_vars={"result": True},
            )

        evaluator = ctx.evaluator
        if evaluator is None:
            logger.warning(
                "条件节点 %s: 求值器未初始化，默认走 true", node.node_id,
            )
            return NodeResult(
                success=True,
                next_label="true",
                output_vars={"result": True},
            )

        try:
            result = evaluator.evaluate(condition)
        except Exception as exc:
            logger.warning("条件节点 %s: 评估异常，默认走 true: %s", node.node_id, exc)
            return NodeResult(
                success=True,
                next_label="true",
                output_vars={"result": True},
            )

        label = "true" if result else "false"
        logger.info(
            "条件节点 %s: %s (条件: %s)",
            node.node_id, label, condition.describe(),
        )
        return NodeResult(
            success=True,
            next_label=label,
            output_vars={"result": result},
        )
