"""LoggingLayer 单元测试。"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from src.core.layers.layer import ErrorContext
from src.core.layers.logging_layer import LoggingLayer


def _make_ctx(**overrides) -> MagicMock:
    ctx = MagicMock()
    node = MagicMock()
    node.node_id = "node_1"
    node.node_type = MagicMock()
    node.node_type.name = "ACTION"
    node.action = MagicMock()
    node.action.action_type = MagicMock()
    node.action.action_type.name = "CLICK_IMAGE"
    ctx.current_node = node

    graph = MagicMock()
    graph.name = "test_graph"
    graph.nodes = {"node_1": node}
    ctx.graph = graph
    ctx.step_index = 1

    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


class TestLoggingLayer:
    def test_name(self) -> None:
        assert LoggingLayer().name == "logging"

    def test_priority(self) -> None:
        assert LoggingLayer().priority == -100

    def test_on_graph_start_logs(self) -> None:
        layer = LoggingLayer()
        ctx = _make_ctx()
        with patch.object(logging.getLogger("src.core.layers.logging_layer"), "log") as mock_log:
            layer.on_graph_start(ctx)
            mock_log.assert_called_once()
            args = mock_log.call_args
            assert "图执行开始" in args[0][1]

    def test_on_graph_end_logs_elapsed(self) -> None:
        layer = LoggingLayer()
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        with patch.object(logging.getLogger("src.core.layers.logging_layer"), "log") as mock_log:
            layer.on_graph_end(ctx)
            mock_log.assert_called_once()
            assert "图执行结束" in mock_log.call_args[0][1]

    def test_on_node_enter_increments_count(self) -> None:
        layer = LoggingLayer()
        ctx = _make_ctx()
        assert layer._total_nodes == 0
        layer.on_node_enter(ctx)
        assert layer._total_nodes == 1

    def test_on_node_exit_success(self) -> None:
        layer = LoggingLayer()
        ctx = _make_ctx()
        result = MagicMock()
        result.success = True
        result.output_vars = {"key": "val"}
        with patch.object(logging.getLogger("src.core.layers.logging_layer"), "log"):
            returned = layer.on_node_exit(ctx, result)
        assert returned is result

    def test_on_node_exit_failure(self) -> None:
        layer = LoggingLayer()
        ctx = _make_ctx()
        result = MagicMock()
        result.success = False
        result.error = RuntimeError("boom")
        with patch.object(logging.getLogger("src.core.layers.logging_layer"), "log"):
            returned = layer.on_node_exit(ctx, result)
        assert returned is result

    def test_on_node_error_returns_err_ctx(self) -> None:
        layer = LoggingLayer()
        ctx = _make_ctx()
        err_ctx = ErrorContext(error=RuntimeError("fail"))
        with patch.object(logging.getLogger("src.core.layers.logging_layer"), "error"):
            ret = layer.on_node_error(ctx, err_ctx)
        assert ret is err_ctx
