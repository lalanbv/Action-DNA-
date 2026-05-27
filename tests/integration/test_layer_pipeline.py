"""Layer 管道集成测试 — 4 层管道顺序执行 + 错误传播。

验证：
- create_default_layers 返回 4 层且按 priority 排序
- on_node_enter 按 priority 升序执行
- on_node_exit / on_node_error 按 priority 降序（LIFO）执行
- 错误在层间正确传播
- 完整管道端到端无异常
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_result import NodeResult

from src.core.layers import (
    BreakpointLayer,
    LoggingLayer,
    RetryLayer,
    TimingLayer,
    create_default_layers,
)
from src.core.layers.layer import ErrorContext, GraphLayer
from src.core.layers.pause_layer import PauseLayer
from src.core.layers.event_bridge_layer import EventBridgeLayer
from tests._helpers import make_exec_ctx, make_test_graph


def _make_ctx() -> ExecutionContext:
    graph, node = make_test_graph()
    return make_exec_ctx(graph, node, gen=1, step_index=1)


def _run_full_pipeline(
    layers: list[GraphLayer],
    ctx: ExecutionContext,
    *,
    success: bool = True,
    error: Exception | None = None,
) -> list[str]:
    """模拟 GraphEngine 的完整层管道执行，返回执行顺序追踪。"""
    sorted_layers = sorted(layers, key=lambda l: l.priority)
    order: list[str] = []

    for layer in sorted_layers:
        layer.on_graph_start(ctx)
        order.append(f"graph_start:{layer.name}")

    for layer in sorted_layers:
        ctx = layer.on_node_enter(ctx)
        order.append(f"node_enter:{layer.name}")

    if error is not None:
        err_ctx = ErrorContext(error=error)
        for layer in reversed(sorted_layers):
            err_ctx = layer.on_node_error(ctx, err_ctx)
            order.append(f"node_error:{layer.name}")
    elif success:
        result = NodeResult.ok()
        for layer in reversed(sorted_layers):
            result = layer.on_node_exit(ctx, result)
            order.append(f"node_exit:{layer.name}")

    for layer in reversed(sorted_layers):
        layer.on_graph_end(ctx)
        order.append(f"graph_end:{layer.name}")

    return order


class TestFourLayerPipeline:
    """4 层管道：LoggingLayer → TimingLayer → RetryLayer → BreakpointLayer。"""

    def test_default_layers_count(self) -> None:
        assert len(create_default_layers()) == 4

    def test_pipeline_success_path(self) -> None:
        """成功路径：graph_start → node_enter(4) → node_exit(4) → graph_end(4)。"""
        layers = create_default_layers()
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        ctx = _make_ctx()
        order = _run_full_pipeline(layers, ctx, success=True)

        # 4 graph_start + 4 node_enter + 4 node_exit + 4 graph_end
        assert len(order) == 16

        # 验证 node_enter 按正序
        enter_names = [o.split(":")[1] for o in order if o.startswith("node_enter:")]
        assert enter_names == ["logging", "timing", "retry", "breakpoint"]

        # 验证 node_exit 按 LIFO 逆序
        exit_names = [o.split(":")[1] for o in order if o.startswith("node_exit:")]
        assert exit_names == ["breakpoint", "retry", "timing", "logging"]

        # 验证 graph_end 按 LIFO 逆序
        end_names = [o.split(":")[1] for o in order if o.startswith("graph_end:")]
        assert end_names == ["breakpoint", "retry", "timing", "logging"]

    def test_pipeline_error_path(self) -> None:
        """错误路径：graph_start → node_enter(4) → node_error(4) → graph_end(4)。"""
        layers = create_default_layers()
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        ctx = _make_ctx()
        order = _run_full_pipeline(layers, ctx, error=RuntimeError("test error"))

        # 4 graph_start + 4 node_enter + 4 node_error + 4 graph_end
        assert len(order) == 16

        # 验证 node_error 按 LIFO 逆序
        error_names = [o.split(":")[1] for o in order if o.startswith("node_error:")]
        assert error_names == ["breakpoint", "retry", "timing", "logging"]

    def test_logging_layer_tracks_node_count(self) -> None:
        """LoggingLayer 应追踪已执行节点数。"""
        layers = create_default_layers()
        logging_layer = next(l for l in layers if isinstance(l, LoggingLayer))
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        ctx = _make_ctx()
        _run_full_pipeline(layers, ctx, success=True)
        assert logging_layer._total_nodes == 1

    def test_timing_layer_records_success(self) -> None:
        """TimingLayer 应记录成功执行的时间。"""
        layers = create_default_layers()
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        ctx = _make_ctx()
        _run_full_pipeline(layers, ctx, success=True)
        assert len(timing.timeline) == 1
        assert timing.timeline[0].success is True

    def test_retry_layer_zero_count_on_success(self) -> None:
        """RetryLayer 成功后重试计数应为 0。"""
        layers = create_default_layers()
        retry = next(l for l in layers if isinstance(l, RetryLayer))

        ctx = _make_ctx()
        _run_full_pipeline(layers, ctx, success=True)
        assert retry.get_retry_count("node_1") == 0

    def test_retry_layer_increments_on_error(self) -> None:
        """RetryLayer 错误后重试计数应增加。"""
        layers = create_default_layers()
        retry = next(l for l in layers if isinstance(l, RetryLayer))
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        ctx = _make_ctx()
        _run_full_pipeline(layers, ctx, error=RuntimeError("retry me"))
        assert retry.get_retry_count("node_1") == 1

    def test_pipeline_multiple_nodes(self) -> None:
        """多节点管道：每个节点独立追踪。"""
        layers = create_default_layers()
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        sorted_layers = sorted(layers, key=lambda l: l.priority)
        for layer in sorted_layers:
            layer.on_graph_start(_make_ctx())

        for i in range(3):
            ctx = _make_ctx()
            ctx.current_node.node_id = f"node_{i}"
            for layer in sorted_layers:
                ctx = layer.on_node_enter(ctx)
            result = NodeResult.ok()
            for layer in reversed(sorted_layers):
                result = layer.on_node_exit(ctx, result)

        for layer in reversed(sorted_layers):
            layer.on_graph_end(_make_ctx())

        assert len(timing.timeline) == 3

    def test_priority_ordering_ascending_enter(self) -> None:
        """自定义层验证 on_node_enter 按 priority 升序执行。"""
        call_order: list[str] = []

        class LayerA(GraphLayer):
            @property
            def name(self) -> str:
                return "A"
            @property
            def priority(self) -> int:
                return 10
            def on_node_enter(self, ctx):
                call_order.append("A")
                return ctx

        class LayerB(GraphLayer):
            @property
            def name(self) -> str:
                return "B"
            @property
            def priority(self) -> int:
                return -10
            def on_node_enter(self, ctx):
                call_order.append("B")
                return ctx

        class LayerC(GraphLayer):
            @property
            def name(self) -> str:
                return "C"
            @property
            def priority(self) -> int:
                return 0
            def on_node_enter(self, ctx):
                call_order.append("C")
                return ctx

        layers = [LayerA(), LayerB(), LayerC()]
        sorted_layers = sorted(layers, key=lambda l: l.priority)
        ctx = _make_ctx()
        for layer in sorted_layers:
            ctx = layer.on_node_enter(ctx)

        assert call_order == ["B", "C", "A"]


class TestLayerPipelineWithErrorPropagation:
    """错误在层间传播的集成测试。"""

    def test_error_propagated_through_all_layers(self) -> None:
        """on_node_error 应按 LIFO 逆序传播，每层都有机会处理。"""
        handled: list[str] = []

        class HandlerLayer(GraphLayer):
            def __init__(self, n: str, pri: int) -> None:
                self._name = n
                self._pri = pri
            @property
            def name(self) -> str:
                return self._name
            @property
            def priority(self) -> int:
                return self._pri
            def on_node_error(self, ctx, err_ctx):
                handled.append(self._name)
                return err_ctx

        layers = [
            HandlerLayer("outer", -50),
            HandlerLayer("middle", 0),
            HandlerLayer("inner", 50),
        ]
        sorted_layers = sorted(layers, key=lambda l: l.priority)
        ctx = _make_ctx()

        err_ctx = ErrorContext(error=RuntimeError("boom"))
        for layer in reversed(sorted_layers):
            err_ctx = layer.on_node_error(ctx, err_ctx)

        assert handled == ["inner", "middle", "outer"]

    def test_error_handler_marks_handled(self) -> None:
        """LIFO 中层可以将 err_ctx 标记为已处理。"""
        class ConsumingLayer(GraphLayer):
            def __init__(self, pri: int) -> None:
                self._pri = pri
            @property
            def name(self) -> str:
                return "consumer"
            @property
            def priority(self) -> int:
                return self._pri
            def on_node_error(self, ctx, err_ctx):
                return ErrorContext(
                    error=err_ctx.error,
                    node_result=NodeResult.fail(err_ctx.error),
                    handled=True,
                )

        layers = [ConsumingLayer(0)]
        sorted_layers = sorted(layers, key=lambda l: l.priority)
        ctx = _make_ctx()

        err_ctx = ErrorContext(error=RuntimeError("handled"))
        for layer in reversed(sorted_layers):
            err_ctx = layer.on_node_error(ctx, err_ctx)
            if err_ctx.handled:
                break

        assert err_ctx.handled is True
        assert err_ctx.node_result is not None
        assert err_ctx.node_result.success is False


class TestExtendedPipeline:
    """扩展管道：默认 4 层 + PauseLayer + EventBridgeLayer。"""

    def test_six_layer_pipeline(self) -> None:
        """6 层管道：Pause → EventBridge → Logging → Timing → Retry → Breakpoint。"""
        published: list[str] = []

        def mock_publish(event_name: str, **kwargs):
            published.append(event_name)

        layers: list[GraphLayer] = [
            PauseLayer(),
            EventBridgeLayer(publish_fn=mock_publish),
            *create_default_layers(),
        ]

        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        sorted_layers = sorted(layers, key=lambda l: l.priority)
        ctx = _make_ctx()

        for layer in sorted_layers:
            layer.on_graph_start(ctx)

        for layer in sorted_layers:
            ctx = layer.on_node_enter(ctx)

        result = NodeResult.ok()
        for layer in reversed(sorted_layers):
            result = layer.on_node_exit(ctx, result)

        for layer in reversed(sorted_layers):
            layer.on_graph_end(ctx)

        assert len(published) > 0
        assert "executor.step_changed" in published

    def test_pause_layer_blocks_when_paused(self) -> None:
        """PauseLayer 在暂停时应阻塞 on_node_enter。"""
        pause = PauseLayer()
        ctx = _make_ctx()
        ctx.pause_event.set()

        def unpause():
            time.sleep(0.2)
            ctx.pause_event.clear()

        t = threading.Thread(target=unpause, daemon=True)
        t.start()
        start = time.time()
        pause.on_node_enter(ctx)
        elapsed = time.time() - start
        t.join()

        assert elapsed >= 0.15
