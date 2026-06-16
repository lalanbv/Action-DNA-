"""LoggingLayer — 执行日志记录层。

记录每个节点的开始/完成/错误日志，以及图执行的开始/结束日志。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.layers.layer import ErrorContext, GraphLayer
from src.utils.i18n import t

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
            t("engine.log.graph_start", name=graph_name, node_count=node_count),
        )

    def on_graph_end(self, ctx: ExecutionContext) -> None:
        elapsed_ms = (time.monotonic() - self._graph_start_time) * 1000
        graph_name = getattr(ctx.graph, "name", "unknown") or "unknown"

        logger.log(
            self._log_level,
            t(
                "engine.log.graph_end",
                name=graph_name, total_nodes=self._total_nodes, elapsed_ms=elapsed_ms,
            ),
        )

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        self._total_nodes += 1

        node = ctx.current_node
        node_label = node.node_type.name
        if hasattr(node, "action") and node.action is not None:
            node_label = node.action.action_type.name

        logger.log(
            self._log_level,
            t(
                "engine.log.node_enter",
                node_id=node.node_id, label=node_label, step=ctx.step_index,
            ),
        )
        return ctx

    def on_node_exit(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult:
        status = t("engine.log.node_status_success") if result.success else t("engine.log.node_status_failed")
        detail = result.output_vars if result.success else str(result.error)
        logger.log(
            self._log_level,
            t(
                "engine.log.node_exit",
                node_id=ctx.current_node.node_id, status=status, detail=detail,
            ),
        )
        return result

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        logger.error(
            t(
                "engine.log.node_exception",
                node_id=ctx.current_node.node_id,
                error_type=type(err_ctx.error).__name__,
                error=err_ctx.error,
            )
        )
        return err_ctx
