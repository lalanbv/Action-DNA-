"""Layer 管道集成测试。

验证：
- create_default_layers 返回正确顺序
- 层管道按 priority 排序执行
- 每层钩子开销 < 0.1ms
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_result import NodeResult

from src.core.layers import (
    BreakpointLayer,
    LoggingLayer,
    RetryLayer,
    TimingLayer,
    create_default_layers,
)
from src.core.layers.layer import GraphLayer
from tests._helpers import make_exec_ctx, make_test_graph


def _make_ctx() -> ExecutionContext:
    graph, node = make_test_graph()
    return make_exec_ctx(graph, node, gen=1)


class TestCreateDefaultLayers:
    def test_returns_four_layers(self) -> None:
        layers = create_default_layers()
        assert len(layers) == 4

    def test_layer_types(self) -> None:
        layers = create_default_layers()
        assert isinstance(layers[0], LoggingLayer)
        assert isinstance(layers[1], TimingLayer)
        assert isinstance(layers[2], RetryLayer)
        assert isinstance(layers[3], BreakpointLayer)

    def test_priority_order(self) -> None:
        layers = create_default_layers()
        priorities = [l.priority for l in layers]
        assert priorities == sorted(priorities)

    def test_names(self) -> None:
        layers = create_default_layers()
        names = [l.name for l in layers]
        assert names == ["logging", "timing", "retry", "breakpoint"]


class TestPipelineExecution:
    """模拟 GraphEngine 的层管道执行顺序。"""

    @staticmethod
    def _run_pipeline(
        layers: list[GraphLayer],
        ctx: ExecutionContext,
        result: NodeResult | None = None,
    ) -> None:
        sorted_layers = sorted(layers, key=lambda l: l.priority)

        for layer in sorted_layers:
            layer.on_graph_start(ctx)

        for layer in sorted_layers:
            ctx = layer.on_node_enter(ctx)

        if result is not None:
            for layer in reversed(sorted_layers):
                result = layer.on_node_exit(ctx, result)

        for layer in reversed(sorted_layers):
            layer.on_graph_end(ctx)

    def test_pipeline_runs_without_error(self) -> None:
        layers = create_default_layers()
        ctx = _make_ctx()
        self._run_pipeline(layers, ctx, NodeResult.ok())

    def test_pipeline_timing_layer_records(self) -> None:
        layers = create_default_layers()
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        ctx = _make_ctx()
        self._run_pipeline(layers, ctx, NodeResult.ok())

        assert len(timing.timeline) == 1
        assert timing.timeline[0].success is True

    def test_pipeline_retry_layer_tracks(self) -> None:
        layers = create_default_layers()
        retry = next(l for l in layers if isinstance(l, RetryLayer))

        ctx = _make_ctx()
        self._run_pipeline(layers, ctx, NodeResult.ok())

        assert retry.get_retry_count("node_1") == 0

    def test_pipeline_logging_increments_nodes(self) -> None:
        layers = create_default_layers()
        logging_layer = next(l for l in layers if isinstance(l, LoggingLayer))

        ctx = _make_ctx()
        self._run_pipeline(layers, ctx, NodeResult.ok())

        assert logging_layer._total_nodes == 1


class TestLayerPerformance:
    """每层钩子执行时间应 < 0.1ms。"""

    def test_logging_layer_performance(self) -> None:
        layer = LoggingLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)

        start = time.perf_counter()
        cur = ctx
        for _ in range(100):
            cur = layer.on_node_enter(cur)
        elapsed = (time.perf_counter() - start) / 100 * 1000  # ms
        assert elapsed < 0.1, f"LoggingLayer.on_node_enter: {elapsed:.3f}ms"

    def test_timing_layer_performance(self) -> None:
        layer = TimingLayer(report_on_exit=False)
        ctx = _make_ctx()
        layer.on_graph_start(ctx)

        start = time.perf_counter()
        cur = ctx
        for _ in range(100):
            cur = layer.on_node_enter(cur)
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed < 0.1, f"TimingLayer.on_node_enter: {elapsed:.3f}ms"

    def test_retry_layer_performance(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)

        start = time.perf_counter()
        cur = ctx
        for _ in range(100):
            cur = layer.on_node_enter(cur)
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed < 0.1, f"RetryLayer.on_node_enter: {elapsed:.3f}ms"

    def test_breakpoint_layer_performance(self) -> None:
        layer = BreakpointLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)

        start = time.perf_counter()
        cur = ctx
        for _ in range(100):
            cur = layer.on_node_enter(cur)
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed < 0.1, f"BreakpointLayer.on_node_enter: {elapsed:.3f}ms"

    def test_full_pipeline_performance(self) -> None:
        layers = create_default_layers()
        timing = next(l for l in layers if isinstance(l, TimingLayer))
        timing._report_on_exit = False

        ctx = _make_ctx()
        result = NodeResult.ok()
        sorted_layers = sorted(layers, key=lambda l: l.priority)

        for layer in sorted_layers:
            layer.on_graph_start(ctx)

        start = time.perf_counter()
        cur = ctx
        for _ in range(100):
            for layer in sorted_layers:
                cur = layer.on_node_enter(cur)
            for layer in reversed(sorted_layers):
                result = layer.on_node_exit(cur, result)
        elapsed = (time.perf_counter() - start) / 100 * 1000
        assert elapsed < 1.0, f"Full pipeline per iteration: {elapsed:.3f}ms"
