"""LoggingLayer 单元测试。"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

from src.core.debug.ring_buffer_log import LogEventType, RingBufferLog
from src.core.engine.node_result import NodeResult
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


class TestLoggingLayerRingLog:
    """ring_log 注入测试 — 结构化执行日志写入执行日志面板缓冲。

    锁定契约:
    - ring_log=None 时行为不变(不写、不崩)。
    - ring_log 注入后,各钩子写入正确事件类型,且原样返回 ctx/result(纯观察)。
    """

    def test_no_ring_log_does_not_write(self) -> None:
        layer = LoggingLayer(ring_log=None)
        ctx = _make_ctx()
        result = NodeResult.ok()
        # 各钩子不应抛,也不应有任何写入(无 ring_log)
        layer.on_graph_start(ctx)
        assert layer.on_node_enter(ctx) is ctx
        assert layer.on_node_exit(ctx, result) is result
        layer.on_graph_end(ctx)

    def test_graph_start_writes_execution_start(self) -> None:
        ring = RingBufferLog(capacity=10)
        layer = LoggingLayer(ring_log=ring)
        layer.on_graph_start(_make_ctx())
        entries = ring.get_by_type(LogEventType.EXECUTION_START)
        assert len(entries) == 1
        assert "test_graph" in entries[0].message

    def test_graph_end_writes_execution_end(self) -> None:
        ring = RingBufferLog(capacity=10)
        layer = LoggingLayer(ring_log=ring)
        ctx = _make_ctx()
        layer.on_graph_start(ctx)
        layer.on_node_enter(ctx)
        layer.on_graph_end(ctx)
        assert len(ring.get_by_type(LogEventType.EXECUTION_END)) == 1

    def test_node_enter_writes_node_enter_with_label(self) -> None:
        ring = RingBufferLog(capacity=10)
        layer = LoggingLayer(ring_log=ring)
        layer.on_node_enter(_make_ctx())
        entries = ring.get_by_type(LogEventType.NODE_ENTER)
        assert len(entries) == 1
        assert entries[0].node_id == "node_1"
        # _make_ctx 的 action_type 是 CLICK_IMAGE,应作为标签出现在消息里
        assert "CLICK_IMAGE" in entries[0].message

    def test_node_exit_success_writes_node_exit(self) -> None:
        ring = RingBufferLog(capacity=10)
        layer = LoggingLayer(ring_log=ring)
        result = NodeResult.ok(x=100, y=200)
        ret = layer.on_node_exit(_make_ctx(), result)
        assert ret is result  # 原样返回
        assert len(ring.get_by_type(LogEventType.NODE_EXIT)) == 1

    def test_node_exit_fail_writes_node_error(self) -> None:
        """软失败(descriptor 返回 fail,如模板未匹配)归 NODE_ERROR,进入错误过滤。"""
        ring = RingBufferLog(capacity=10)
        layer = LoggingLayer(ring_log=ring)
        result = NodeResult.fail("模板未匹配")
        layer.on_node_exit(_make_ctx(), result)
        assert len(ring.get_by_type(LogEventType.NODE_ERROR)) == 1
        # 失败不应同时写 NODE_EXIT 成功条目
        assert len(ring.get_by_type(LogEventType.NODE_EXIT)) == 0

    def test_node_error_writes_node_error(self) -> None:
        """硬失败(异常)走 on_node_error,写 NODE_ERROR。"""
        ring = RingBufferLog(capacity=10)
        layer = LoggingLayer(ring_log=ring)
        err_ctx = ErrorContext(error=ValueError("ocr 引擎不可用"))
        ret = layer.on_node_error(_make_ctx(), err_ctx)
        assert ret is err_ctx  # 原样返回
        errors = ring.get_by_type(LogEventType.NODE_ERROR)
        assert len(errors) == 1
        assert "CLICK_IMAGE" in errors[0].message

    def test_action_label_preferred_over_node_type(self) -> None:
        """节点带 action 时,优先用 action_type.name 作标签(node_type=ACTION 不应覆盖)。"""
        ring = RingBufferLog(capacity=10)
        layer = LoggingLayer(ring_log=ring)
        layer.on_node_enter(_make_ctx())
        msg = ring.get_by_type(LogEventType.NODE_ENTER)[0].message
        assert "CLICK_IMAGE" in msg
        assert "ACTION" not in msg
