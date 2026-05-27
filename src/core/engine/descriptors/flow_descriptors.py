"""StartDescriptor + EndDescriptor + LoopDescriptor — 流程控制节点。

StartDescriptor: 流程起点，无条件成功。
EndDescriptor:   流程终点，无条件成功，引擎检测到 END 后停止遍历。
LoopDescriptor:  循环控制，根据 loop_count 限制循环体次数。
                 loop_count=0 表示无限循环（由引擎 max_iterations 兜底）。
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

__all__ = ["StartDescriptor", "EndDescriptor", "MergeDescriptor", "LoopDescriptor"]


@auto_register
class StartDescriptor(NodeDescriptor):
    """流程起点描述符 — 标记执行开始，无条件成功。"""

    @classmethod
    def action_type(cls) -> str:
        return "START"

    @classmethod
    def display_name(cls) -> str:
        return "开始"

    @classmethod
    def category(cls) -> str:
        return "流程控制"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {}

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult.ok()


@auto_register
class EndDescriptor(NodeDescriptor):
    """流程终点描述符 — 标记执行结束，引擎检测到 END 后停止遍历。"""

    @classmethod
    def action_type(cls) -> str:
        return "END"

    @classmethod
    def display_name(cls) -> str:
        return "结束"

    @classmethod
    def category(cls) -> str:
        return "流程控制"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {}

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult.ok()


@auto_register
class MergeDescriptor(NodeDescriptor):
    """汇合节点描述符 — 多条分支汇聚后继续执行，无条件成功。"""

    @classmethod
    def action_type(cls) -> str:
        return "MERGE"

    @classmethod
    def display_name(cls) -> str:
        return "汇合"

    @classmethod
    def category(cls) -> str:
        return "流程控制"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {}

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        return NodeResult.ok()


@auto_register
class LoopDescriptor(NodeDescriptor):
    """循环控制描述符 — 管理循环体的迭代次数。

    使用 ctx.loop_counts 跟踪当前迭代计数。
    loop_count=0 表示无限循环（由引擎 max_iterations 兜底）。

    出边标签约定：
    - "loop": 继续循环 → 回到循环体起始节点
    - "exit": 退出循环 → 跳到循环后继节点

    GraphEngine._resolve_next_node 会根据 result.success 决定走哪条边。
    """

    @classmethod
    def action_type(cls) -> str:
        return "LOOP"

    @classmethod
    def display_name(cls) -> str:
        return "循环"

    @classmethod
    def category(cls) -> str:
        return "流程控制"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "loop_count": PortDef("number", "循环次数（0=无限）", required=False, default=0),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "current_iteration": PortDef("number", "当前迭代次数（从 1 开始）", required=False),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        node = ctx.current_node
        max_count = node.loop_count
        node_id = node.node_id

        current = ctx.get_loop_count(node_id) + 1

        if max_count > 0 and current > max_count:
            logger.info(
                "循环 %s 达到上限 (%d/%d)，准备退出",
                node_id, current, max_count,
            )
            return NodeResult(
                success=False,
                next_label="exit",
                output_vars={
                    "current_iteration": current,
                    "_loop_node_id": node_id,
                    "_loop_count": current,
                },
            )

        logger.info(
            "循环 %s 继续 (%s/%s)",
            node_id,
            current,
            max_count if max_count > 0 else "∞",
        )
        return NodeResult(
            success=True,
            next_label="loop",
            output_vars={
                "current_iteration": current,
                "_loop_node_id": node_id,
                "_loop_count": current,
            },
        )
