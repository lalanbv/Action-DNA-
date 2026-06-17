"""LoggingLayer — 执行日志记录层。

记录每个节点的开始/完成/错误日志，以及图执行的开始/结束日志。

当注入 ``ring_log`` 时，各生命周期钩子会【额外】把结构化条目写入
``RingBufferLog``，供执行日志面板实时显示。这部分写入独立于 Python
``logging`` 的控制台/文件输出，且不受 ``log_level`` 限制（UI 面板应始终
能看到执行事件）。

本层为 ``OBSERVE`` 纯观察优先级，所有钩子原样返回 ctx/result，接入管道
不改任何执行行为。
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from src.core.debug.ring_buffer_log import LogEventType, RingBufferLog
from src.core.engine.priority import SystemPriority
from src.core.layers.layer import ErrorContext, GraphLayer
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.engine.node_result import NodeResult

__all__ = ["LoggingLayer"]

logger = logging.getLogger(__name__)


class LoggingLayer(GraphLayer):
    """执行日志层 — 记录节点生命周期日志。

    ``ring_log`` 可选：注入后，on_graph_start/end、on_node_enter/exit/error
    会把结构化条目写入执行日志缓冲（供 UI 面板实时显示），与 Python
    ``logging`` 输出互不影响。未注入时行为与历史完全一致。
    """

    def __init__(
        self,
        log_level: int = logging.DEBUG,
        ring_log: RingBufferLog | None = None,
    ) -> None:
        self._log_level = log_level
        self._ring_log = ring_log
        self._graph_start_time: float = 0.0
        self._total_nodes: int = 0

    @property
    def name(self) -> str:
        return "logging"

    @property
    def priority(self) -> int:
        return SystemPriority.OBSERVE

    # ── 辅助 ──────────────────────────────────────────────

    @staticmethod
    def _node_label(node) -> str:
        """提取节点可读标签（优先动作类型，其次节点类型）。"""
        label = node.node_type.name
        action = getattr(node, "action", None)
        if action is not None and getattr(action, "action_type", None) is not None:
            label = action.action_type.name
        return label

    @staticmethod
    def _fmt_detail(value: object, limit: int = 120) -> str:
        """把 output/error 格式化为简短可读字符串（超长截断）。"""
        if not value:
            return ""
        if isinstance(value, dict):
            if not value:
                return ""
            text = ", ".join(f"{k}={v}" for k, v in value.items())
        else:
            text = str(value)
        return text if len(text) <= limit else text[:limit] + "…"

    def _emit_log(
        self,
        event_type: LogEventType,
        node_id: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        """写入一条结构化执行日志（UI 面板用）。线程安全：RingBufferLog 自带锁。

        日志写入失败不得影响执行流程，故吞掉异常并降级到 Python logging。
        """
        if self._ring_log is None:
            return
        try:
            self._ring_log.append(
                node_id=node_id,
                event_type=event_type,
                message=message,
                data=data,
            )
        except Exception:  # noqa: BLE001 — 日志写入不得影响执行
            logger.debug("ring_log 写入失败(忽略)", exc_info=True)

    # ── 图级生命周期 ──────────────────────────────────────

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        self._graph_start_time = time.monotonic()
        self._total_nodes = 0

        graph_name = getattr(ctx.graph, "name", "unknown") or "unknown"
        node_count = len(ctx.graph.nodes)

        logger.log(
            self._log_level,
            t("engine.log.graph_start", name=graph_name, node_count=node_count),
        )
        self._emit_log(
            LogEventType.EXECUTION_START,
            node_id="",
            message=t(
                "panel.execlog.graph_start",
                name=graph_name, node_count=node_count,
            ),
            data={"graph": graph_name, "node_count": node_count},
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
        self._emit_log(
            LogEventType.EXECUTION_END,
            node_id="",
            message=t(
                "panel.execlog.graph_end",
                total_nodes=self._total_nodes, elapsed_ms=elapsed_ms,
            ),
            data={"graph": graph_name, "elapsed_ms": elapsed_ms},
        )

    # ── 节点级生命周期 ────────────────────────────────────

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        self._total_nodes += 1

        node = ctx.current_node
        node_label = self._node_label(node)

        logger.log(
            self._log_level,
            t(
                "engine.log.node_enter",
                node_id=node.node_id, label=node_label, step=ctx.step_index,
            ),
        )
        self._emit_log(
            LogEventType.NODE_ENTER,
            node_id=node.node_id,
            message=t(
                "panel.execlog.node_enter",
                label=node_label, step_idx=ctx.step_index,
            ),
            data={"label": node_label, "step": ctx.step_index},
        )
        return ctx

    def on_node_exit(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult:
        node = ctx.current_node
        node_label = self._node_label(node)

        status = t("engine.log.node_status_success") if result.success else t("engine.log.node_status_failed")
        detail = result.output_vars if result.success else str(result.error)
        logger.log(
            self._log_level,
            t(
                "engine.log.node_exit",
                node_id=node.node_id, status=status, detail=detail,
            ),
        )

        # 软失败(descriptor 返回 fail,如模板未匹配)与硬失败(异常,走 on_node_error)
        # 在 GraphEngine 中互斥,不会重复。两者都归 NODE_ERROR 以进入"错误"过滤。
        if result.success:
            self._emit_log(
                LogEventType.NODE_EXIT,
                node_id=node.node_id,
                message=t(
                    "panel.execlog.node_exit_ok",
                    label=node_label, detail=self._fmt_detail(result.output_vars),
                ),
                data={"label": node_label, "success": True},
            )
        else:
            self._emit_log(
                LogEventType.NODE_ERROR,
                node_id=node.node_id,
                message=t(
                    "panel.execlog.node_exit_fail",
                    label=node_label, detail=self._fmt_detail(result.error),
                ),
                data={"label": node_label, "success": False},
            )
        return result

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        node = ctx.current_node
        node_label = self._node_label(node)
        error_msg = str(err_ctx.error)

        logger.error(
            t(
                "engine.log.node_exception",
                node_id=node.node_id,
                error_type=type(err_ctx.error).__name__,
                error=err_ctx.error,
            )
        )
        self._emit_log(
            LogEventType.NODE_ERROR,
            node_id=node.node_id,
            message=t(
                "panel.execlog.node_error",
                label=node_label, error=error_msg,
            ),
            data={
                "label": node_label,
                "error_type": type(err_ctx.error).__name__,
            },
        )
        return err_ctx
