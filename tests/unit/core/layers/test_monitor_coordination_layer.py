"""MonitorCoordinationLayer 单元测试。"""

import time
import threading
from unittest.mock import MagicMock

import pytest

from src.core.layers.monitor_coordination_layer import MonitorCoordinationLayer


@pytest.fixture
def mock_ctx():
    ctx = MagicMock()
    ctx.is_paused = False
    ctx.is_stopping = False
    return ctx


@pytest.fixture
def mock_manager():
    manager = MagicMock()
    manager.is_handler_active = False
    return manager


@pytest.fixture
def layer(mock_manager):
    return MonitorCoordinationLayer(mock_manager)


class TestProperties:
    def test_name(self, layer):
        assert layer.name == "monitor_coordination"

    def test_priority(self, layer):
        assert layer.priority == -300


class TestOnNodeEnter:
    def test_passes_through_when_no_handler(self, layer, mock_manager, mock_ctx):
        mock_manager.is_handler_active = False
        result = layer.on_node_enter(mock_ctx)
        assert result is mock_ctx

    def test_passes_through_when_no_manager(self, mock_ctx):
        layer = MonitorCoordinationLayer(None)
        result = layer.on_node_enter(mock_ctx)
        assert result is mock_ctx

    def test_waits_for_handler_to_complete(self, layer, mock_manager, mock_ctx):
        mock_manager.is_handler_active = True

        def deactivate_after_delay():
            time.sleep(0.05)
            mock_manager.is_handler_active = False

        t = threading.Thread(target=deactivate_after_delay)
        t.start()

        result = layer.on_node_enter(mock_ctx)
        assert result is mock_ctx
        t.join()
