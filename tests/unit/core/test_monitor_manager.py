"""MonitorManager 单元测试。"""

import threading
import time
from unittest.mock import MagicMock

import pytest

from src.core.events.bus import TypedEventBus
from src.core.monitor import MonitorConfig
from src.core.monitor_manager import MonitorManager, MonitorState


@pytest.fixture
def mock_capture():
    c = MagicMock()
    c.grab.return_value = MagicMock()
    c.to_logical_rect.side_effect = lambda r: r
    return c


@pytest.fixture
def mock_matcher():
    m = MagicMock()
    m.find.return_value = None
    # 多模板改用 find_any;默认"未命中"以保持单模板等价语义
    m.find_any.return_value = None
    return m


@pytest.fixture
def mock_input():
    return MagicMock()


@pytest.fixture
def typed_bus():
    return TypedEventBus()


@pytest.fixture
def manager(mock_capture, mock_matcher, mock_input, typed_bus):
    return MonitorManager(
        capture=mock_capture,
        matcher=mock_matcher,
        input_ctrl=mock_input,
        event_bus=typed_bus,
    )


@pytest.fixture
def sample_config():
    return MonitorConfig(
        name="test_monitor",
        image_path="test.png",
        threshold=0.8,
        check_interval=0.01,
    )


class TestRegister:
    def test_returns_id(self, manager, sample_config):
        mid = manager.register(sample_config)
        assert isinstance(mid, str)
        assert len(mid) > 0

    def test_creates_idle_state(self, manager, sample_config):
        mid = manager.register(sample_config)
        state = manager.get_state(mid)
        assert state.status == "idle"
        assert state.trigger_count == 0
        assert state.config_name == "test_monitor"

    def test_monitor_count_increases(self, manager, sample_config):
        manager.register(sample_config)
        assert manager.monitor_count == 1
        manager.register(MonitorConfig(name="m2", image_path="m2.png"))
        assert manager.monitor_count == 2


class TestUnregister:
    def test_removes_monitor(self, manager, sample_config):
        mid = manager.register(sample_config)
        manager.unregister(mid)
        assert manager.monitor_count == 0

    def test_raises_on_running_monitor(self, manager, sample_config):
        mid = manager.register(sample_config)
        manager.start_all()
        with pytest.raises(RuntimeError, match="Cannot unregister running"):
            manager.unregister(mid)
        manager.stop_all()


class TestLifecycle:
    def test_start_all_sets_running(self, manager, sample_config):
        manager.register(sample_config)
        manager.start_all()
        assert manager.is_running

    def test_stop_all_sets_not_running(self, manager, sample_config):
        manager.register(sample_config)
        manager.start_all()
        manager.stop_all()
        assert not manager.is_running

    def test_start_all_sets_state_running(self, manager, sample_config):
        mid = manager.register(sample_config)
        manager.start_all()
        state = manager.get_state(mid)
        assert state.status == "running"
        manager.stop_all()

    def test_stop_all_sets_state_idle(self, manager, sample_config):
        mid = manager.register(sample_config)
        manager.start_all()
        manager.stop_all()
        state = manager.get_state(mid)
        assert state.status == "idle"

    def test_pause_all_sets_paused(self, manager, sample_config):
        mid = manager.register(sample_config)
        manager.start_all()
        manager.pause_all()
        state = manager.get_state(mid)
        assert state.status == "paused"
        manager.stop_all()

    def test_resume_all_sets_running(self, manager, sample_config):
        mid = manager.register(sample_config)
        manager.start_all()
        manager.pause_all()
        manager.resume_all()
        state = manager.get_state(mid)
        assert state.status == "running"
        manager.stop_all()

    def test_disabled_config_not_started(self, manager):
        cfg = MonitorConfig(name="disabled", image_path="x.png", enabled=False)
        mid = manager.register(cfg)
        manager.start_all()
        state = manager.get_state(mid)
        assert state.status == "idle"
        manager.stop_all()


class TestHandlerActive:
    def test_initially_not_active(self, manager):
        assert not manager.is_handler_active

    def test_handler_enter_makes_active(self, manager):
        manager._on_handler_enter()
        assert manager.is_handler_active

    def test_handler_exit_clears_active(self, manager):
        manager._on_handler_enter()
        manager._on_handler_exit()
        assert not manager.is_handler_active

    def test_nested_handlers(self, manager):
        manager._on_handler_enter()
        manager._on_handler_enter()
        manager._on_handler_exit()
        assert manager.is_handler_active
        manager._on_handler_exit()
        assert not manager.is_handler_active


class TestStateQueries:
    def test_get_all_states(self, manager):
        manager.register(MonitorConfig(name="a", image_path="a.png"))
        manager.register(MonitorConfig(name="b", image_path="b.png"))
        states = manager.get_all_states()
        assert len(states) == 2

    def test_get_state_unknown_raises(self, manager):
        with pytest.raises(KeyError, match="Unknown monitor"):
            manager.get_state("nonexistent")

    def test_get_config(self, manager, sample_config):
        mid = manager.register(sample_config)
        cfg = manager.get_config(mid)
        assert cfg.name == "test_monitor"

    def test_get_all_configs(self, manager):
        manager.register(MonitorConfig(name="a", image_path="a.png"))
        manager.register(MonitorConfig(name="b", image_path="b.png"))
        configs = manager.get_all_configs()
        assert len(configs) == 2


class TestMonitorStateProperties:
    def test_has_ever_triggered_false_initially(self):
        state = MonitorState(
            monitor_id="m1", config_name="test", status="idle",
            trigger_count=0, last_trigger_time=0.0, consecutive_count=0,
            error_count=0, last_error="", last_check_time=0.0,
        )
        assert not state.has_ever_triggered

    def test_has_ever_triggered_true_after_trigger(self):
        state = MonitorState(
            monitor_id="m1", config_name="test", status="idle",
            trigger_count=1, last_trigger_time=100.0, consecutive_count=0,
            error_count=0, last_error="", last_check_time=0.0,
        )
        assert state.has_ever_triggered

    def test_frozen(self):
        state = MonitorState(
            monitor_id="m1", config_name="test", status="idle",
            trigger_count=0, last_trigger_time=0.0, consecutive_count=0,
            error_count=0, last_error="", last_check_time=0.0,
        )
        with pytest.raises(AttributeError):
            state.status = "running"


class TestEventPublishing:
    def test_publishes_state_change_on_start(self, manager, sample_config, typed_bus):
        events = []
        from src.core.events.events import MonitorStateChangedEvent
        typed_bus.subscribe(MonitorStateChangedEvent, lambda e: events.append(e))

        manager.register(sample_config)
        manager.start_all()
        manager.stop_all()

        assert len(events) >= 1
        assert events[0].new_status == "running"
