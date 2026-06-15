"""GraphEngine — 无状态 DAG 遍历引擎。

给定 FlowGraph + ExecutionContext，按图拓扑依次执行节点。
不持有状态、不管理线程、不更新 UI。

设计灵感：Dify GraphEngine.run() 遍历 + Layer 中间件管道。
"""

from __future__ import annotations

import logging
import random
import threading
import weakref
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from src.core.engine.dirty_tracker import DirtyTracker
from src.core.engine.execution_blocker import ExecutionBlocker
from src.core.engine.node_registry import NodeRegistry
from src.core.engine.pause_aware_wait import pause_aware_wait
from src.core.engine.node_result import NodeResult
from src.core.engine.snapshot import SnapshotManager
from src.core.engine.tool_filter import ToolFilter
from src.core.error.error_config import ErrorStrategy, RetryPolicy
from src.core.flow import FlowNode, NodeType
from src.core.layers.layer import ErrorContext, GraphLayer
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.flow import FlowGraph

logger = logging.getLogger(__name__)

__all__ = ["GraphEngine", "GraphEngineConfig"]


@dataclass
class GraphEngineConfig:
    """引擎配置。"""

    max_iterations: int = 10000
    default_error_strategy: ErrorStrategy = ErrorStrategy.IGNORE
    default_retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    default_exhausted_strategy: ErrorStrategy = ErrorStrategy.FAIL_FAST
    validate_graph_on_run: bool = True
    raise_on_validation_error: bool = True
    transient_retry_count: int = 1
    transient_retry_delay: float = 0.3
    node_timeout_seconds: float = 30.0
    node_timeout_enabled: bool = False
    tool_filter: ToolFilter = field(default_factory=ToolFilter.allow_all)


class GraphEngine:
    """独立的 DAG 执行引擎。

    职责：
    - 遍历 FlowGraph 节点
    - 通过 NodeRegistry 分派节点执行
    - 执行 Layer 中间件管道
    - 处理 ErrorStrategy 错误策略

    不负责：
    - 线程管理（由 ActionExecutor 负责）
    - UI 更新（由 Controller 负责）
    - 变量存储（由 VariablePool 负责）
    """

    def __init__(self, config: GraphEngineConfig | None = None) -> None:
        self._config = config or GraphEngineConfig()
        self._layers: list[GraphLayer] = []
        self._layer_map: dict[str, GraphLayer] = {}
        self._descriptor_cache: dict[type, Any] = {}
        self._validator_instance = None
        self._snapshot_manager: SnapshotManager | None = None
        self._lock_event = threading.Event()
        self._lock_event.set()
        self._pending_layers: list[tuple[str, GraphLayer | str]] = []
        self._timeout_executor: ThreadPoolExecutor | None = None
        self._executor_finalizer: weakref.finalize | None = None

    def _get_timeout_executor(self) -> ThreadPoolExecutor:
        if self._timeout_executor is None:
            self._timeout_executor = ThreadPoolExecutor(max_workers=1)
            self._executor_finalizer = weakref.finalize(
                self, self._shutdown_timeout_executor,
            )
        return self._timeout_executor

    def _shutdown_timeout_executor(self) -> None:
        executor = self._timeout_executor
        if executor is not None:
            self._timeout_executor = None
            executor.shutdown(wait=True)

    def _get_descriptor(self, cls: type):
        """缓存描述符实例（无状态，可安全复用）。"""
        descriptor = self._descriptor_cache.get(cls)
        if descriptor is None:
            descriptor = cls()
            self._descriptor_cache[cls] = descriptor
        return descriptor

    # ---- Layer 管理 ----

    def add_layer(self, layer: GraphLayer) -> None:
        """添加中间件层，按 priority 自动排序。

        执行期间（_locked=True）加入的层会延迟到 run() 结束后安装。
        """
        if layer.name in self._layer_map:
            raise ValueError(f"层 '{layer.name}' 已存在")
        if not self._lock_event.is_set():
            self._pending_layers.append(("add", layer))
            return
        self._install_layer(layer)

    def remove_layer(self, name: str) -> bool:
        """按名称移除中间件层。返回是否成功。

        执行期间（_locked=True）的移除会延迟到 run() 结束后处理。
        """
        if name not in self._layer_map:
            return False
        if not self._lock_event.is_set():
            self._pending_layers.append(("remove", name))
            return True
        del self._layer_map[name]
        self._layers = [lyr for lyr in self._layers if lyr.name != name]
        return True

    def get_layer(self, name: str) -> GraphLayer | None:
        """按名称获取层。"""
        return self._layer_map.get(name)

    def _install_layer(self, layer: GraphLayer) -> None:
        """实际安装层到列表并排序。"""
        self._layer_map[layer.name] = layer
        self._layers.append(layer)
        self._layers.sort(key=lambda lyr: lyr.priority)

    def _flush_pending(self) -> None:
        """处理执行期间延迟的层操作。"""
        pending = self._pending_layers[:]
        self._pending_layers.clear()
        for action, data in pending:
            if action == "add":
                layer = data
                if layer.name not in self._layer_map:
                    self._install_layer(layer)
            elif action == "remove":
                name = data
                if name in self._layer_map:
                    del self._layer_map[name]
                    self._layers = [lyr for lyr in self._layers if lyr.name != name]

    # ---- 快照管理 ----

    def enable_snapshots(self, max_snapshots: int = 100) -> SnapshotManager:
        """启用执行快照，返回 SnapshotManager 供查询。"""
        self._snapshot_manager = SnapshotManager(max_snapshots=max_snapshots)
        return self._snapshot_manager

    @property
    def snapshot_manager(self) -> SnapshotManager | None:
        """快照管理器（None 表示未启用）。"""
        return self._snapshot_manager

    # ---- 主入口 ----

    def run(
        self,
        graph: FlowGraph,
        ctx: ExecutionContext,
        tracker: DirtyTracker | None = None,
    ) -> DirtyTracker | None:
        """执行流程图。主循环入口。

        执行期间 _locked=True，防止并发修改层列表。

        Args:
            graph: 流程图。
            ctx: 执行上下文。
            tracker: 可选脏标记追踪器。传入时启用增量模式 — 仅重新评估脏节点，
                     跳过干净节点。首次调用传 None 或新 tracker 执行全量。

        Returns:
            传入 tracker 时返回它（便于链式调用），否则返回 None。
        """
        incremental = tracker is not None
        generation = ctx.gen if incremental else 0

        # 0. 设置迭代锁
        self._lock_event.clear()

        # 1. 验证图结构
        if self._config.validate_graph_on_run:
            errors = self._validate_graph(graph)
            if errors:
                msg = f"图结构验证失败: {'; '.join(errors)}"
                if self._config.raise_on_validation_error:
                    raise ValueError(msg)
                logger.warning(msg)

        # 2. 定位起始节点
        start_node = graph.find_by_type("START")
        if start_node is None:
            raise ValueError(t("engine.exc.missing_start_node"))

        # 3. 触发 on_graph_start（正序）
        for layer in self._layers:
            layer.on_graph_start(ctx)

        # 4. 主循环
        iteration = 0
        current_node: FlowNode | None = start_node
        action_step_idx = 0

        try:
            while current_node is not None:
                if ctx.is_stopping:
                    logger.info(t("engine.log.stop_signal_received"))
                    break

                if ctx.is_paused:
                    while ctx.is_paused and not ctx.is_stopping:
                        ctx.stop_event.wait(timeout=0.1)
                    if ctx.is_stopping:
                        logger.info(t("engine.log.stop_signal_during_pause"))
                        break

                iteration += 1
                if iteration > self._config.max_iterations:
                    logger.error(t("engine.log.max_iterations_exceeded", max_count=self._config.max_iterations))
                    break

                # 跳过禁用节点
                if not current_node.enabled:
                    logger.info(t("engine.log.node_disabled_skipped", node_id=current_node.node_id))
                    current_node = self._resolve_next_node(graph, current_node, None)
                    continue

                # 增量：跳过干净节点
                if incremental and not tracker.needs_eval(current_node.node_id, generation):
                    current_node = self._resolve_next_node(graph, current_node, None)
                    continue

                is_action = (
                    current_node.node_type == NodeType.ACTION
                    and current_node.action is not None
                )
                if is_action:
                    action_step_idx += 1

                ctx = ctx.with_node(current_node, increment_step=is_action)
                node_label = f"步骤 {action_step_idx}" if is_action else current_node.node_type.name
                logger.info(t("engine.log.execute_node", node_id=current_node.node_id, label=node_label, iteration=iteration))

                # 执行节点管道
                result = self._execute_pipeline(ctx)

                # 增量：条件分支惰性裁剪
                if (
                    incremental
                    and current_node.node_type == NodeType.CONDITION
                    and result is not None
                ):
                    taken_label = getattr(result, "next_label", None) or ("true" if result.success else "false")
                    for edge in graph.get_outgoing_edges(current_node.node_id):
                        if edge.label != taken_label:
                            self._mark_branch_clean(
                                graph, tracker, edge.to_node, generation,
                            )

                # ExecutionBlocker 哨兵 → 跳过
                if isinstance(result, ExecutionBlocker):
                    logger.info(t("engine.log.node_blocked_skipped", node_id=current_node.node_id, reason=result.reason))
                    if incremental:
                        tracker.mark_clean(current_node.node_id, generation)
                    current_node = self._resolve_next_node(graph, current_node, None)
                    continue

                # 持久化 output_vars + 更新 loop_counts（必须更新 ctx）
                if result is not None:
                    loop_node_id = result.output_vars.get("_loop_node_id")
                    loop_count = result.output_vars.get("_loop_count")
                    if loop_node_id is not None and loop_count is not None:
                        ctx = ctx.with_loop_count(loop_node_id, loop_count)
                    for key, value in result.output_vars.items():
                        if not key.startswith("_"):
                            ctx.variables.set(key, value)

                    if self._snapshot_manager is not None and is_action and result.success:
                        self._snapshot_manager.capture(ctx)

                    if result.cooldown > 0 and result.success and self._pause_aware_wait(ctx, result.cooldown):
                        break

                # 错误处理
                if (
                    result is not None
                    and not result.success
                    and result.error is not None
                ):
                    resolved = self._resolve_error_strategy(ctx, result)
                    if resolved is None:
                        if incremental:
                            tracker.mark_clean(current_node.node_id, generation)
                        current_node = self._resolve_next_node(graph, current_node, None)
                        continue
                    if not resolved.success:
                        break
                    result = resolved

                # 增量：标记为已评估（在错误处理之后）
                if incremental:
                    tracker.mark_clean(current_node.node_id, generation)

                # 解析下一个节点
                current_node = self._resolve_next_node(graph, current_node, result)
        finally:
            # 5. 触发 on_graph_end（逆序）
            for layer in reversed(self._layers):
                layer.on_graph_end(ctx)
            # 6. 释放锁并处理延迟操作
            self._lock_event.set()
            self._flush_pending()

        return tracker

    # ---- 增量执行 ----

    def run_incremental(
        self,
        graph: FlowGraph,
        ctx: ExecutionContext,
        tracker: DirtyTracker | None = None,
    ) -> DirtyTracker:
        """增量执行 — 仅重新评估脏节点及其下游，跳过干净节点。

        首次调用（tracker=None）会创建新 tracker 并全量执行。
        后续调用传入同一 tracker，只执行被标记为脏的节点。

        返回 DirtyTracker 实例，供调用方在节点编辑时 mark_dirty。
        """
        if tracker is None:
            tracker = DirtyTracker()
            tracker.mark_all_dirty(graph.get_all_node_ids())
        return self.run(graph, ctx, tracker)

    # ---- 超时执行 ----

    def _execute_with_timeout(
        self, descriptor: "Any", ctx: ExecutionContext,
    ) -> NodeResult:
        """带超时的描述符执行 — 使用实例级线程池，进程退出时自动关闭。"""
        from concurrent.futures import CancelledError
        from src.core.error.exceptions import NodeTimeoutError

        future: Future[NodeResult] = self._get_timeout_executor().submit(descriptor.execute, ctx)

        try:
            return future.result(timeout=self._config.node_timeout_seconds)
        except (TimeoutError, CancelledError):
            future.cancel()
            raise NodeTimeoutError.from_code(
                3002,
                node_id=ctx.current_node.node_id,
                node_type=self.get_action_type(ctx.current_node),
                timeout=f"{self._config.node_timeout_seconds}",
            )
        except Exception:
            future.cancel()
            raise

    # ---- 节点管道 ----

    @staticmethod
    def _safe_on_exit(descriptor: Any, ctx: ExecutionContext) -> None:
        try:
            descriptor.on_exit(ctx)
        except Exception:
            logger.exception("on_exit hook failed for descriptor %s", type(descriptor).__name__)

    def _execute_pipeline(
        self, ctx: ExecutionContext,
    ) -> NodeResult | ExecutionBlocker | None:
        """执行完整节点管道：layers → descriptor → layers。

        瞬态异常（截图失败、Quartz 调用失败等）会自动重试一次，
        避免偶发的系统级异常导致步骤被静默跳过。
        重试时只重新执行描述符，不重新进入 Layer 管道，避免重复计数。
        """
        action_type = self.get_action_type(ctx.current_node)

        max_attempts = 1 + self._config.transient_retry_count
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            if ctx.is_stopping:
                return NodeResult.fail("收到停止信号，跳过执行")

            descriptor = None
            try:
                if attempt == 0:
                    for layer in self._layers:
                        ctx = layer.on_node_enter(ctx)

                if not self._config.tool_filter.is_allowed(action_type):
                    logger.info(
                        "节点类型 %s 被工具过滤器拒绝，跳过", action_type,
                    )
                    return ExecutionBlocker(
                        reason=f"工具过滤器拒绝: {action_type}"
                    )

                try:
                    descriptor_cls = NodeRegistry.get(action_type)
                except KeyError:
                    raise RuntimeError(f"未注册的节点类型: {action_type}") from None
                descriptor = self._get_descriptor(descriptor_cls)

                if attempt == 0:
                    descriptor.on_enter(ctx)

                # 可选超时执行
                if self._config.node_timeout_enabled:
                    result = self._execute_with_timeout(descriptor, ctx)
                else:
                    result = descriptor.execute(ctx)

            except Exception as e:  # noqa: BLE001 — 描述符执行异常，需捕获后重试或走错误处理
                last_error = e
                # 瞬态重试：短暂等待后再次尝试（不调用 on_exit，保持描述符状态）
                if attempt < max_attempts - 1:
                    logger.info(
                        "节点 %s 执行异常，瞬态重试 (%d/%d): %s",
                        ctx.current_node.node_id,
                        attempt + 1,
                        self._config.transient_retry_count,
                        e,
                    )
                    self._pause_aware_wait(
                        ctx, self._config.transient_retry_delay,
                    )
                    continue

                # 重试耗尽，清理描述符后走错误处理层
                if descriptor is not None:
                    self._safe_on_exit(descriptor, ctx)
                err_ctx = ErrorContext(error=e)
                for layer in reversed(self._layers):
                    err_ctx = layer.on_node_error(ctx, err_ctx)
                if err_ctx.handled and err_ctx.node_result is not None:
                    return err_ctx.node_result
                return NodeResult.fail(e)
            else:
                # 6. on_exit 钩子（正常路径）
                if descriptor is not None:
                    self._safe_on_exit(descriptor, ctx)

            # 成功 → on_node_exit（LIFO 逆序）
            if not isinstance(result, ExecutionBlocker):
                for layer in reversed(self._layers):
                    result = layer.on_node_exit(ctx, result)

            return result

        # 不应到达此处，但安全兜底
        return NodeResult.fail(last_error or RuntimeError(t("engine.exc.unknown_execution_error")))

    # ---- 节点解析 ----

    def _resolve_next_node(
        self,
        graph: FlowGraph,
        current: FlowNode,
        result: NodeResult | None,
    ) -> FlowNode | None:
        """根据 NodeResult.next_label 选择下一个节点。

        规则优先级：
        1. END 节点 → None
        2. result.next_label 有值 → 匹配出边 label
        3. CONDITION 节点 → true/false 边
        4. LOOP 节点 → loop/exit 边
        5. 默认 → 第一条出边
        6. 无出边 → None
        """
        if current.node_type == NodeType.END:
            return None

        out_edges = graph.get_outgoing_edges(current.node_id)
        if not out_edges:
            return None

        def _follow(edge_to_node: str) -> FlowNode | None:
            node = graph.get_node(edge_to_node)
            if node is None:
                logger.error(t("engine.log.dangling_edge", from_node=current.node_id, to_node=edge_to_node))
            return node

        # 规则 1：显式指定标签
        if result is not None and result.next_label:
            for edge in out_edges:
                if edge.label == result.next_label:
                    return _follow(edge.to_node)
            logger.warning(
                "未找到标签为 '%s' 的出边，回退到默认",
                result.next_label,
            )

        # 规则 2：CONDITION 节点
        if current.node_type == NodeType.CONDITION:
            success = result.success if result else False
            label = "true" if success else "false"
            for edge in out_edges:
                if edge.label == label:
                    return _follow(edge.to_node)
            return _follow(out_edges[0].to_node)

        # 规则 3：LOOP 节点
        if current.node_type == NodeType.LOOP:
            label = "loop" if (result and result.success) else "exit"
            for edge in out_edges:
                if edge.label == label:
                    return _follow(edge.to_node)
            return _follow(out_edges[0].to_node)

        # 规则 4：默认 → 第一条出边
        return _follow(out_edges[0].to_node)

    # ---- 错误处理 ----

    def _resolve_error_strategy(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult | None:
        """根据 ErrorConfig 策略处理节点错误。

        优先级：node.error_config → graph.default_error_config → engine default。
        """
        config = ctx.current_node.error_config or getattr(
            ctx.graph, "default_error_config", None
        )

        if config is not None:
            retry_policy = config.retry_policy or self._config.default_retry_policy
            exhausted_strategy = config.exhausted_strategy
            fallback_label = config.fallback_label
            return self._apply_strategy(
                ctx, result, config.strategy,
                retry_policy, exhausted_strategy, fallback_label,
            )

        return self._apply_strategy(
            ctx, result, self._config.default_error_strategy,
            self._config.default_retry_policy,
            self._config.default_exhausted_strategy,
            "fallback",
        )

    def _apply_strategy(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
        strategy: ErrorStrategy,
        retry_policy: RetryPolicy,
        exhausted_strategy: ErrorStrategy | None,
        fallback_label: str,
    ) -> NodeResult | None:
        """统一的错误策略分派。"""
        node_id = ctx.current_node.node_id

        match strategy:
            case ErrorStrategy.FAIL_FAST:
                logger.error(
                    "节点 %s 执行失败 (FAIL_FAST): %s",
                    node_id, result.error,
                )
                return result

            case ErrorStrategy.RETRY:
                return self._handle_retry(ctx, result, retry_policy, exhausted_strategy)

            case ErrorStrategy.SKIP:
                logger.info(
                    "节点 %s 执行失败 (SKIP): %s",
                    node_id, result.error,
                )
                return None

            case ErrorStrategy.FALLBACK:
                return NodeResult.branch(fallback_label, success=False)

            case ErrorStrategy.IGNORE:
                logger.warning(
                    "节点 %s 执行失败 (IGNORE): %s",
                    node_id, result.error,
                )
                return NodeResult(success=True, cooldown=random.uniform(0.3, 0.8))

    def _handle_retry(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
        policy: RetryPolicy,
        exhausted_strategy: ErrorStrategy | None = None,
    ) -> NodeResult | None:
        """重试策略 — 使用指定的 RetryPolicy 退避 + exhausted_strategy。"""
        error = result.error or RuntimeError("unknown")

        if not policy.is_retryable(error):
            logger.warning(
                "节点 %s 错误不可重试: %s", ctx.current_node.node_id, error,
            )
            return self._apply_exhausted_strategy(result, exhausted_strategy)

        for attempt in range(policy.max_retries):
            delay = policy.calculate_delay(attempt)
            logger.info(
                "节点 %s 重试 (%d/%d)，延迟 %.1fs",
                ctx.current_node.node_id, attempt + 1, policy.max_retries, delay,
            )
            self._pause_aware_wait(ctx, delay)
            if ctx.is_stopping:
                return result
            retry_result = self._execute_pipeline(ctx)
            if isinstance(retry_result, ExecutionBlocker):
                break
            if retry_result is None or retry_result.success:
                return retry_result
            if (
                not retry_result.success
                and retry_result.error is not None
                and not policy.is_retryable(retry_result.error)
            ):
                break

        logger.error(
            "节点 %s 重试耗尽 (%d 次)",
            ctx.current_node.node_id, policy.max_retries,
        )
        return self._apply_exhausted_strategy(result, exhausted_strategy)

    def _apply_exhausted_strategy(
        self,
        result: NodeResult,
        exhausted_strategy: ErrorStrategy | None = None,
    ) -> NodeResult | None:
        """重试耗尽后按 exhausted_strategy 决定后续行为。"""
        strategy = exhausted_strategy or self._config.default_exhausted_strategy
        match strategy:
            case ErrorStrategy.SKIP:
                return None
            case ErrorStrategy.IGNORE:
                return NodeResult(success=True)
            case ErrorStrategy.FALLBACK:
                return NodeResult.branch("fallback", success=False)
            case _:
                return result

    # ---- 辅助方法 ----

    @staticmethod
    def _mark_branch_clean(
        graph: FlowGraph,
        tracker: DirtyTracker,
        root_id: str,
        generation: int,
    ) -> None:
        """将 root_id 及其所有下游节点标记为干净（惰性裁剪）。"""
        for nid in graph.get_reachable_nodes(root_id):
            tracker.mark_clean(nid, generation)

    @staticmethod
    def _pause_aware_wait(ctx: ExecutionContext, seconds: float) -> bool:
        return pause_aware_wait(ctx, seconds)

    def _validate_graph(self, graph: FlowGraph) -> list[str]:
        """验证图结构，返回错误列表。

        委托给 WorkflowValidator.validate_build()，提取 ERROR 级别问题。
        缓存 Validator 实例避免每次 run() 重复创建。
        """
        from src.core.engine.workflow_validator import (
            ValidationLevel,
            WorkflowValidator,
        )

        validator = self._validator_instance
        if validator is None:
            validator = WorkflowValidator()
            self._validator_instance = validator

        result = validator.validate_build(graph)
        errors: list[str] = []
        for issue in result.issues:
            if issue.level == ValidationLevel.ERROR:
                errors.append(issue.message)
            else:
                # 保留 WARNING 级别的日志行为
                logger.warning(t("engine.log.validation_warning", message=issue.message))
        return errors

    @staticmethod
    def get_action_type(node: FlowNode) -> str:
        """将 FlowNode 映射为 NodeRegistry 的 action_type 字符串。

        NodeType.ACTION → node.action.action_type.name
        其他（START/END/LOOP/CONDITION） → node_type.name
        """
        if node.node_type == NodeType.ACTION and node.action is not None:
            return node.action.action_type.name
        return node.node_type.name
