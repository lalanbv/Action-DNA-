"""TimingLayer 单元测试。"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from src.core.engine.execution_context import ExecutionContext

from src.core.layers.layer import ErrorContext
from src.core.layers.timing_layer import TimingLayer, TimingStats, TimingEntry
from tests._helpers import make_exec_ctx, make_test_graph


def _make_ctx() -> "ExecutionContext":
    graph, node = make_test_graph(name="test")
    return make_exec_ctx(graph, node)


class TestTimingStats:
    def test_defaults(self) -> None:
        s = TimingStats()
        assert s.call_count == 0
        assert s.avg_ms == 0.0
        assert s.success_rate == 0.0

    def test_avg_ms(self) -> None:
        s = TimingStats(call_count=2, total_ms=200.0)
        assert s.avg_ms == 100.0

    def test_success_rate(self) -> None:
        s = TimingStats(call_count=10, success_count=8, error_count=2)
        assert s.success_rate == 80.0


class TestTimingEntry:
    def test_elapsed_ms(self) -> None:
        e = TimingEntry(
            node_id="n1", node_type="CLICK_IMAGE",
            start_time=1.0, end_time=1.5,
        )
        assert e.elapsed_ms == 500.0


class TestTimingLayer:
    def test_name(self) -> None:
        assert TimingLayer().name == "timing"

    def test_priority(self) -> None:
        assert TimingLayer().priority == -50

    def test_graph_start_resets_state(self) -> None:
        layer = TimingLayer(report_on_exit=False)
        layer._timeline.append(TimingEntry("n1", "T", 0.0))
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        assert len(layer.timeline) == 0
        assert len(layer.stats) == 0

    def test_on_node_exit_tracks_timing(self) -> None:
        layer = TimingLayer(report_on_exit=False)
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        ctx = layer.on_node_enter(ctx)
        result = MagicMock()
        result.success = True
        layer.on_node_exit(ctx, result)

        assert len(layer.timeline) == 1
        entry = layer.timeline[0]
        assert entry.node_id == "node_1"
        assert entry.success is True
        assert entry.elapsed_ms >= 0

    def test_stats_aggregation(self) -> None:
        layer = TimingLayer(report_on_exit=False)
        ctx = _make_ctx()
        layer.on_graph_start(ctx)

        for _ in range(3):
            ctx = layer.on_node_enter(ctx)
            result = MagicMock()
            result.success = True
            layer.on_node_exit(ctx, result)

        assert "CLICK_IMAGE" in layer.stats
        stats = layer.stats["CLICK_IMAGE"]
        assert stats.call_count == 3
        assert stats.success_count == 3
        assert stats.error_count == 0

    def test_on_node_error_tracks_failure(self) -> None:
        layer = TimingLayer(report_on_exit=False)
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        ctx = layer.on_node_enter(ctx)

        err_ctx = ErrorContext(error=RuntimeError("fail"))
        ret = layer.on_node_error(ctx, err_ctx)
        assert ret is err_ctx
        assert len(layer.timeline) == 1
        assert layer.timeline[0].success is False
        assert "CLICK_IMAGE" in layer.stats
        assert layer.stats["CLICK_IMAGE"].error_count == 1

    def test_no_current_entry_on_exit(self) -> None:
        layer = TimingLayer(report_on_exit=False)
        ctx = _make_ctx()
        result = MagicMock()
        result.success = True
        returned = layer.on_node_exit(ctx, result)
        assert returned is result
        assert len(layer.timeline) == 0
