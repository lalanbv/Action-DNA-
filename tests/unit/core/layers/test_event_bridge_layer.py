"""EventBridgeLayer 单元测试 — 验证事件发布时机和参数。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.layers.event_bridge_layer import EventBridgeLayer
from src.core.layers.layer import ErrorContext


@pytest.fixture
def publish_fn():
    return MagicMock()


@pytest.fixture
def layer(publish_fn):
    return EventBridgeLayer(publish_fn=publish_fn)


def _make_ctx(step_index=0, node_id="n1", *, is_action=True):
    """创建最小化 mock ExecutionContext。"""
    from src.core.flow import NodeType

    ctx = MagicMock()
    ctx.step_index = step_index
    node = MagicMock()
    node.node_id = node_id
    node.node_type = NodeType.ACTION if is_action else NodeType.END
    node.action = MagicMock() if is_action else None
    ctx.current_node = node
    return ctx


class TestEventBridgeLayerProperties:

    def test_name(self, layer):
        assert layer.name == "event_bridge"

    def test_priority(self, layer):
        assert layer.priority == -100


class TestOnGraphStart:

    def test_does_not_emit_started(self, layer, publish_fn):
        """started/finished 由 facade 统一发射，Layer 不重复。"""
        layer.on_graph_start(MagicMock())
        publish_fn.assert_not_called()


class TestOnGraphEnd:

    def test_does_not_emit_finished(self, layer, publish_fn):
        layer.on_graph_end(MagicMock())
        publish_fn.assert_not_called()


class TestOnNodeEnter:

    def test_publishes_step_changed(self, layer, publish_fn):
        ctx = _make_ctx(step_index=3, node_id="action_1")
        result = layer.on_node_enter(ctx)

        publish_fn.assert_called_once_with(
            "executor.step_changed",
            step_index=3,
            node_id="action_1",
        )
        assert result is ctx

    def test_calls_on_step_enter_callback(self, publish_fn):
        callback = MagicMock()
        layer = EventBridgeLayer(publish_fn=publish_fn, on_step_enter=callback)
        ctx = _make_ctx(step_index=5, node_id="n2")
        layer.on_node_enter(ctx)

        callback.assert_called_once_with(5, 0, "n2")

    def test_publishes_when_step_index_positive(self, layer, publish_fn):
        """step_index > 0（ACTION 节点）时发布事件。"""
        ctx = _make_ctx(step_index=1)
        layer.on_node_enter(ctx)
        publish_fn.assert_called_once_with(
            "executor.step_changed", step_index=1, node_id="n1",
        )

    def test_no_publish_when_not_action_node(self, layer, publish_fn):
        """非 ACTION 节点（如 END）不发布 step_changed。"""
        ctx = _make_ctx(step_index=0, is_action=False)
        layer.on_node_enter(ctx)
        publish_fn.assert_not_called()


class TestOnNodeError:

    def test_publishes_step_error(self, layer, publish_fn):
        ctx = _make_ctx(step_index=7)
        err_ctx = ErrorContext(error=RuntimeError("boom"))
        result = layer.on_node_error(ctx, err_ctx)

        publish_fn.assert_called_once_with("executor.step_error", step_index=7)
        assert result is err_ctx

    def test_returns_err_ctx_unchanged(self, layer):
        ctx = _make_ctx()
        err_ctx = ErrorContext(error=ValueError("x"))
        result = layer.on_node_error(ctx, err_ctx)
        assert result is err_ctx
