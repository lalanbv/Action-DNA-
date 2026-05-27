"""GraphLayer 中间件抽象基类 — 洋葱模型管道。

借鉴 Dify 的 GraphLayer 模式，将横切关注点提取为可组合的中间件层。
所有钩子方法都有默认空实现，子类只需覆盖关心的方法。

on_node_error 使用 ErrorContext 组合模式：每个层返回修改后的 ErrorContext，
多个层可以链式处理同一个错误（记录、重试、安全停止等）。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.engine.node_result import NodeResult

__all__ = ["ErrorContext", "GraphLayer"]


@dataclass
class ErrorContext:
    """传递给各层的错误上下文，支持组合处理。

    多个层可以链式处理同一个错误：
    - LoggingLayer: 记录错误但不设置 handled
    - RetryLayer: 设置 handled=True，记录重试动作
    - DebugScreenshotLayer: 保存截图但不设置 handled

    引擎在所有层处理完后检查 handled：
    - handled=True → 使用 node_result（如果设置了）
    - handled=False → 继续走引擎自身的错误策略
    """

    error: Exception
    node_result: NodeResult | None = None
    handled: bool = False
    actions: list[str] = field(default_factory=list)


class GraphLayer(ABC):
    """图执行中间件抽象基类（洋葱模型）。

    生命周期钩子：

    ┌───────────────────────────────────────────────────────────┐
    │  on_graph_start(ctx)          图执行开始时调用一次         │
    │      │                                                    │
    │      ├── on_node_enter(ctx)     每个节点执行前调用         │
    │      │       │                                            │
    │      │       ├── [节点执行]                                │
    │      │       │                                            │
    │      │       ├── on_node_exit(ctx, result)    成功时      │
    │      │       └── on_node_error(ctx, err_ctx)  失败时      │
    │      │                                                    │
    │      ├── ... (下一个节点)                                   │
    │      │                                                    │
    │      └── on_graph_end(ctx)          图执行结束时调用一次    │
    └───────────────────────────────────────────────────────────┘

    执行顺序：
    - on_node_enter:  按 priority 升序（正序）
    - on_node_exit:   按 priority 降序（LIFO 逆序）
    - on_node_error:  按 priority 降序（LIFO 逆序），链式 ErrorContext
    - on_graph_start: 按 priority 升序（正序）
    - on_graph_end:   按 priority 降序（LIFO 逆序）
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """层名称（用于标识、排序、日志）。"""

    @property
    def priority(self) -> int:
        """层优先级（数字越小越先执行 on_node_enter）。

        推荐使用 SystemPriority 枚举常量（src.core.engine.priority）：
        - SystemPriority.SAFETY_CHECK:    FailSafeLayer (-400)
        - SystemPriority.PRE_PROCESS:     MonitorCoordinationLayer (-300)
        - SystemPriority.FLOW_CONTROL:    PauseLayer (-200)
        - SystemPriority.BRIDGE:          EventBridgeLayer (-100)
        - SystemPriority.OBSERVE:         LoggingLayer (-100)
        - SystemPriority.MEASURE:         TimingLayer (-50)
        - SystemPriority.CORE:            RetryLayer (0)
        - SystemPriority.POST_PROCESS:    DebugScreenshotLayer (50)
        - SystemPriority.DEBUG:           BreakpointLayer (50)
        """
        return 0

    # ---- 图级生命周期 ----

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        """整个图执行开始时调用（一次）。按 priority 升序。"""
        pass

    def on_graph_end(self, ctx: ExecutionContext) -> None:
        """整个图执行结束时调用（一次）。按 priority 降序（LIFO）。"""
        pass

    # ---- 节点级生命周期 ----

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        """节点执行前调用。可返回修改后的 ctx。按 priority 升序。"""
        return ctx

    def on_node_exit(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult:
        """节点成功执行后调用。可返回修改后的 result。按 priority 降序。"""
        return result

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        """节点抛异常时调用。返回修改后的 ErrorContext，多层可链式处理。LIFO 逆序。"""
        return err_ctx
