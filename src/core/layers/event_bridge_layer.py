"""EventBridgeLayer — 将 GraphEngine 内部状态变更桥接到 EventBus。

职责：监听 GraphEngine 的 Layer 钩子，将步骤变更、启动、完成、错误等
事件通过 EventBus 发布，供 UI 层订阅。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.events.event_names import EventName
from src.core.layers.layer import ErrorContext, GraphLayer

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

__all__ = ["EventBridgeLayer"]


class EventBridgeLayer(GraphLayer):
    """将执行引擎事件桥接到 EventBus 的 Layer。

    挂载到 GraphEngine 后，自动在节点进入/图开始/图结束/节点错误时
    发布事件，供 ActionChainController / WorkflowController 订阅。
    """

    def __init__(
        self,
        publish_fn: Callable[..., None],
        on_step_enter: Callable[[int, int, str | None], None] | None = None,
    ) -> None:
        self._publish = publish_fn
        self._on_step_enter = on_step_enter

    @property
    def name(self) -> str:
        return "event_bridge"

    @property
    def priority(self) -> int:
        return SystemPriority.BRIDGE

    # ---- 图级生命周期 ----
    # 注意: executor.started/finished 由 ActionExecutor facade 统一发射，
    # Layer 不重复发射，避免循环图场景下的事件重复。

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        pass

    def on_graph_end(self, ctx: ExecutionContext) -> None:
        pass

    # ---- 节点级生命周期 ----

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        from src.core.flow import NodeType

        node = ctx.current_node
        node_id = node.node_id if node else None

        # 只有 ACTION 节点才发布 UI 事件
        is_action = (
            node is not None
            and node.node_type == NodeType.ACTION
            and node.action is not None
        )
        if is_action and ctx.step_index >= 0:
            self._publish(
                EventName.EXECUTOR_STEP_CHANGED,
                step_index=ctx.step_index,
                node_id=node_id,
            )

            if self._on_step_enter:
                self._on_step_enter(ctx.step_index, 0, node_id)

        return ctx

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        self._publish(EventName.EXECUTOR_STEP_ERROR, step_index=ctx.step_index)
        return err_ctx
