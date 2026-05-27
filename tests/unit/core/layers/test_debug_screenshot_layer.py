"""DebugScreenshotLayer 单元测试 — 验证截图保存逻辑。"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from src.core.layers.debug_screenshot_layer import DebugScreenshotLayer
from src.core.layers.layer import ErrorContext
from src.core.flow import FlowNode, NodeType


def _make_action(image_path="test.png"):
    """创建 mock ActionStep with image_path."""
    action = MagicMock()
    action.image_path = image_path
    return action


def _make_ctx(node=None, step_index=0):
    ctx = MagicMock()
    ctx.step_index = step_index
    ctx.current_node = node
    return ctx


def _make_action_node(image_path="test.png"):
    node = MagicMock(spec=FlowNode)
    node.action = _make_action(image_path)
    node.node_id = "a1"
    return node


@pytest.fixture
def log_dir(tmp_path):
    return str(tmp_path / "logs")


@pytest.fixture
def capture():
    return MagicMock()


@pytest.fixture
def layer(capture, log_dir):
    return DebugScreenshotLayer(capture=capture, log_dir=log_dir)


class TestDebugScreenshotLayerProperties:

    def test_name(self, layer):
        assert layer.name == "debug_screenshot"

    def test_priority(self, layer):
        assert layer.priority == 50


class TestOnGraphStart:

    def test_resets_saved_nodes(self, layer):
        layer._saved_nodes.add("some_node")
        layer.on_graph_start(MagicMock())
        assert len(layer._saved_nodes) == 0


class TestOnNodeError:

    def test_skips_if_already_saved(self, layer):
        layer._saved_nodes.add("a1")
        ctx = _make_ctx(node=_make_action_node())
        err_ctx = ErrorContext(error=RuntimeError("boom"))
        result = layer.on_node_error(ctx, err_ctx)
        assert result is err_ctx

    def test_skips_if_no_node(self, layer):
        ctx = _make_ctx(node=None)
        err_ctx = ErrorContext(error=RuntimeError("boom"))
        result = layer.on_node_error(ctx, err_ctx)
        assert result is err_ctx

    def test_skips_if_no_action(self, layer):
        node = MagicMock(spec=FlowNode)
        node.action = None
        ctx = _make_ctx(node=node)
        err_ctx = ErrorContext(error=RuntimeError("boom"))
        result = layer.on_node_error(ctx, err_ctx)
        assert result is err_ctx

    def test_skips_if_no_image_path(self, layer):
        node = _make_action_node(image_path="")
        ctx = _make_ctx(node=node)
        err_ctx = ErrorContext(error=RuntimeError("boom"))
        result = layer.on_node_error(ctx, err_ctx)
        assert result is err_ctx
        assert len(layer._saved_nodes) == 0

    def test_skips_if_action_has_no_image_path_attr(self, layer):
        action = MagicMock(spec=[])
        node = MagicMock(spec=FlowNode)
        node.action = action
        node.node_id = "a1"
        ctx = _make_ctx(node=node)
        err_ctx = ErrorContext(error=RuntimeError("boom"))
        result = layer.on_node_error(ctx, err_ctx)
        assert result is err_ctx

    @patch("src.core.layers.debug_screenshot_layer.os.path.exists", return_value=False)
    def test_saves_screenshot_once(self, mock_exists, layer, capture, log_dir):
        import numpy as np

        screen = np.zeros((100, 100, 3), dtype=np.uint8)
        capture.grab_reuse.return_value = screen

        node = _make_action_node(image_path="/some/template.png")
        ctx = _make_ctx(node=node)

        with patch.dict("sys.modules", {"cv2": MagicMock(), "numpy": MagicMock()}):
            import sys
            mock_cv2 = sys.modules["cv2"]
            encoded = MagicMock()
            encoded.tofile = MagicMock()
            mock_cv2.imencode.return_value = (True, encoded)

            err_ctx = ErrorContext(error=RuntimeError("match failed"))
            result = layer.on_node_error(ctx, err_ctx)

        assert result is err_ctx
        assert "a1" in layer._saved_nodes
        capture.grab_reuse.assert_called_once()

    def test_second_error_skips_save(self, layer, capture, log_dir):
        layer._saved_nodes.add("a1")
        node = _make_action_node(image_path="/tpl.png")
        ctx = _make_ctx(node=node)
        layer.on_node_error(ctx, ErrorContext(error=RuntimeError("err1")))
        assert capture.grab_reuse.call_count == 0
