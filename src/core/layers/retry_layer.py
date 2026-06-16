"""RetryLayer — 重试逻辑层。

跟踪重试计数，与 GraphEngine 的 ErrorConfig.RETRY 策略配合。
不直接执行重试（重试由引擎调度），只提供重试上下文信息。
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.layers.layer import ErrorContext, GraphLayer
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.engine.node_result import NodeResult

__all__ = ["RetryLayer"]

logger = logging.getLogger(__name__)


class RetryLayer(GraphLayer):
    """重试逻辑层 — 跟踪重试计数，发射重试事件。"""

    def __init__(self) -> None:
        self._retry_counts: dict[str, int] = {}
        self._total_retries: int = 0
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return "retry"

    @property
    def priority(self) -> int:
        return SystemPriority.CORE

    @property
    def total_retries(self) -> int:
        return self._total_retries

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        with self._lock:
            self._retry_counts.clear()
            self._total_retries = 0

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        node_id = ctx.current_node.node_id
        with self._lock:
            if node_id not in self._retry_counts:
                self._retry_counts[node_id] = 0
        return ctx

    def on_node_exit(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult:
        if result.success:
            with self._lock:
                self._retry_counts.pop(ctx.current_node.node_id, None)
        return result

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        node_id = ctx.current_node.node_id
        with self._lock:
            current_retry = self._retry_counts.get(node_id, 0)
            self._retry_counts[node_id] = current_retry + 1
            self._total_retries += 1

        logger.info(
            t(
                "engine.log.retry_layer_attempt",
                node_id=node_id, attempt=current_retry + 1, error=err_ctx.error,
            )
        )

        err_ctx.actions.append(
            f"retry:{node_id}:attempt={current_retry + 1}"
        )

        if ctx.event_bus is not None:
            from src.core.events.events import NodeRetryingEvent

            ctx.event_bus.publish(
                NodeRetryingEvent(
                    node_id=node_id,
                    attempt=current_retry + 1,
                    max_attempts=0,
                    last_error=str(err_ctx.error),
                )
            )

        return err_ctx

    def get_retry_count(self, node_id: str) -> int:
        with self._lock:
            return self._retry_counts.get(node_id, 0)

    def reset_retry_count(self, node_id: str) -> None:
        with self._lock:
            self._retry_counts.pop(node_id, None)
