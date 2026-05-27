"""FailSafeLayer 单元测试。"""

from unittest.mock import MagicMock

import pytest

from src.core.fail_safe import FailSafeMonitor, FailSafeTriggered
from src.core.layers.failsafe_layer import FailSafeLayer


@pytest.fixture
def mock_input():
    inp = MagicMock()
    inp.get_mouse_position.return_value = (500, 500)
    return inp


@pytest.fixture
def mock_capture():
    cap = MagicMock()
    cap.get_screen_size.return_value = (1920, 1080)
    return cap


@pytest.fixture
def fail_safe():
    return FailSafeMonitor(enabled=True)


@pytest.fixture
def layer(fail_safe, mock_input, mock_capture):
    return FailSafeLayer(fail_safe, mock_input, mock_capture)


@pytest.fixture
def mock_ctx():
    return MagicMock()


class TestProperties:
    def test_name(self, layer):
        assert layer.name == "failsafe"

    def test_priority(self, layer):
        assert layer.priority == -400


class TestOnNodeEnter:
    def test_passes_through_when_safe(self, layer, mock_ctx):
        result = layer.on_node_enter(mock_ctx)
        assert result is mock_ctx

    def test_skips_when_disabled(self, mock_input, mock_capture, mock_ctx):
        fs = FailSafeMonitor(enabled=False)
        layer = FailSafeLayer(fs, mock_input, mock_capture)
        result = layer.on_node_enter(mock_ctx)
        assert result is mock_ctx
        mock_input.get_mouse_position.assert_not_called()

    def test_raises_on_corner(self, layer, mock_input, mock_ctx):
        mock_input.get_mouse_position.return_value = (0, 0)
        with pytest.raises(FailSafeTriggered):
            layer.on_node_enter(mock_ctx)

    def test_swallows_non_failsafe_exceptions(self, layer, mock_input, mock_ctx):
        mock_input.get_mouse_position.side_effect = OSError("no mouse")
        result = layer.on_node_enter(mock_ctx)
        assert result is mock_ctx
