"""RetryLayer 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.layers.layer import ErrorContext
from src.core.layers.retry_layer import RetryLayer


def _make_ctx(**overrides) -> MagicMock:
    ctx = MagicMock()
    node = MagicMock()
    node.node_id = "node_1"
    ctx.current_node = node
    ctx.event_bus = None
    ctx.step_index = 1

    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


class TestRetryLayer:
    def test_name(self) -> None:
        assert RetryLayer().name == "retry"

    def test_priority(self) -> None:
        assert RetryLayer().priority == 0

    def test_graph_start_resets_counts(self) -> None:
        layer = RetryLayer()
        layer._retry_counts["n1"] = 5
        layer._total_retries = 10
        layer.on_graph_start(_make_ctx())
        assert layer.total_retries == 0
        assert layer.get_retry_count("n1") == 0

    def test_on_node_enter_initializes_count(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        layer.on_node_enter(ctx)
        assert layer.get_retry_count("node_1") == 0

    def test_on_node_enter_preserves_existing_count(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        layer._retry_counts["node_1"] = 2
        layer.on_node_enter(ctx)
        assert layer.get_retry_count("node_1") == 2

    def test_on_node_exit_success_resets_count(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx()
        layer._retry_counts["node_1"] = 3
        result = MagicMock()
        result.success = True
        layer.on_node_exit(ctx, result)
        assert layer.get_retry_count("node_1") == 0

    def test_on_node_exit_failure_keeps_count(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx()
        layer._retry_counts["node_1"] = 2
        result = MagicMock()
        result.success = False
        layer.on_node_exit(ctx, result)
        assert layer.get_retry_count("node_1") == 2

    def test_on_node_error_increments_count(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        layer.on_node_enter(ctx)
        err_ctx = ErrorContext(error=RuntimeError("fail"))
        ret = layer.on_node_error(ctx, err_ctx)
        assert ret is err_ctx
        assert layer.get_retry_count("node_1") == 1
        assert layer.total_retries == 1

    def test_on_node_error_multiple_times(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        layer.on_node_enter(ctx)

        for i in range(3):
            layer.on_node_error(ctx, ErrorContext(error=RuntimeError("fail")))

        assert layer.get_retry_count("node_1") == 3
        assert layer.total_retries == 3

    def test_on_node_error_publishes_event(self) -> None:
        layer = RetryLayer()
        bus = MagicMock()
        ctx = _make_ctx(event_bus=bus)
        layer.on_graph_start(ctx)
        layer.on_node_enter(ctx)
        layer.on_node_error(ctx, ErrorContext(error=RuntimeError("fail")))
        bus.publish.assert_called_once()
        event = bus.publish.call_args[0][0]
        assert event.node_id == "node_1"
        assert event.attempt == 1

    def test_on_node_error_no_event_without_bus(self) -> None:
        layer = RetryLayer()
        ctx = _make_ctx(event_bus=None)
        layer.on_graph_start(ctx)
        layer.on_node_enter(ctx)
        layer.on_node_error(ctx, ErrorContext(error=RuntimeError("fail")))

    def test_reset_retry_count(self) -> None:
        layer = RetryLayer()
        layer._retry_counts["n1"] = 5
        layer.reset_retry_count("n1")
        assert layer.get_retry_count("n1") == 0
