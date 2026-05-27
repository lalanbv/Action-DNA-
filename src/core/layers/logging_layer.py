"""LoggingLayer — 执行日志记录层。

记录每个节点的开始/完成/错误日志，以及图执行的开始/结束日志。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.layers.layer import ErrorContext, GraphLayer

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.engine.node_result import NodeResult

__all__ = ["LoggingLayer"]

logger = logging.getLogger(__name__)


class LoggingLayer(GraphLayer):
    """执行日志层 — 记录节点生命周期日志。"""

    def __init__(self, log_level: int = logging.DEBUG) -> None:
        self._log_level = log_level
        self._graph_start_time: float = 0.0
        self._total_nodes: int = 0

    @property
    def name(self) -> str:
        return "logging"

    @property
    def priority(self) -> int:
        return SystemPriority.OBSERVE

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        self._graph_start_time = time.monotonic()
        self._total_nodes = 0

        graph_name = getattr(ctx.graph, "name", "unknown") or "unknown"
        node_count = len(ctx.graph.nodes)

        logger.log(
            self._log_level,
            "[GRAPH_START] 图执行开始: %s, 节点数=%d",
            graph_name,
            node_count,
        )

    def on_graph_end(self, ctx: ExecutionContext) -> None:
        elapsed_ms = (time.monotonic() - self._graph_start_time) * 1000
        graph_name = getattr(ctx.graph, "name", "unknown") or "unknown"

        logger.log(
            self._log_level,
            "[GRAPH_END] 图执行结束: %s, 总步骤=%d, 耗时=%.0fms",
            graph_name,
            self._total_nodes,
            elapsed_ms,
        )

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        self._total_nodes += 1

        node = ctx.current_node
        node_label = node.node_type.name
        if hasattr(node, "action") and node.action is not None:
            node_label = node.action.action_type.name

        logger.log(
            self._log_level,
            "[NODE_ENTER] >>> 执行节点: %s (%s) 步骤=%d",
            node.node_id,
            node_label,
            ctx.step_index,
        )
        return ctx

    def on_node_exit(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult:
        status = "成功" if result.success else "失败"
        detail = result.output_vars if result.success else str(result.error)
        logger.log(
            self._log_level,
            "[NODE_EXIT] <<< 节点完成: %s (%s) %s",
            ctx.current_node.node_id,
            status,
            detail,
        )
        return result

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        logger.error(
            "[NODE_ERROR] !!! 节点异常: %s (%s) %s",
            ctx.current_node.node_id,
            type(err_ctx.error).__name__,
            err_ctx.error,
        )
        return err_ctx
