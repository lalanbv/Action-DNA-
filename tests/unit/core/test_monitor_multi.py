"""Monitor 多模板(触发图 + 处理图)测试(mock matcher.find_any)。"""

import threading
from unittest.mock import MagicMock

from src.core.action import FoundAction, MatchStrategy, ThresholdMode
from src.core.monitor import BackgroundMonitor, MonitorConfig
from src.core.vision.capture import MultiMatchResult


def _monitor(alt_trigger=None, alt_handler=None, strategy=MatchStrategy.ADAPTIVE,
             mode=ThresholdMode.GLOBAL, threshold=0.8):
    """构造带多模板字段的 MonitorConfig(触发图 + 处理图各加备用图)。"""
    return MonitorConfig(
        name="m1", enabled=True,
        image_path="trigger.png", threshold=threshold, check_interval=1.0,
        handler_action=FoundAction.LEFT_CLICK, handler_image_path="handler.png",
        priority=0, max_consecutive=3, cooldown=2.0,
        alt_image_paths=alt_trigger or [],
        alt_thresholds=[None] * len(alt_trigger or []),
        alt_handler_image_paths=alt_handler or [],
        alt_handler_thresholds=[None] * len(alt_handler or []),
        match_strategy=strategy, threshold_mode=mode,
    )


def _make_monitor(config, find_any_results):
    """构造 BackgroundMonitor;frame_provider=None 走 capture.grab();matcher.find_any 按序返回。"""
    mon = BackgroundMonitor.__new__(BackgroundMonitor)
    mon._config = config
    mon._capture = MagicMock()
    mon._capture.grab.return_value = MagicMock(name="screen")
    mon._capture.to_logical_rect.side_effect = lambda r: r
    mon._matcher = MagicMock()
    mon._matcher.find_any.side_effect = find_any_results
    mon._input = MagicMock()
    # _handle 内 `ax, ay = self._input.move_to(...)` 需返回 2 元组
    mon._input.move_to.return_value = (0, 0)
    mon._stop_event = threading.Event()
    mon._pause_event = threading.Event()
    mon._event_bus = None
    mon._frame_provider = None
    mon._state_callback = None
    mon._handler_enter = None
    mon._handler_exit = None
    mon._thread = None
    mon._last_trigger_time = 0.0
    mon._consecutive_count = 0
    mon._trigger_count = 0
    mon._error_count = 0
    mon._last_error = ""
    mon._last_check_time = 0.0
    mon._status = "running"
    mon._state_lock = threading.Lock()
    return mon


def test_monitor_config_has_multi_template_fields():
    """MonitorConfig dataclass 默认携带多模板字段(向后兼容)。"""
    m = MonitorConfig(name="m")
    assert m.alt_image_paths == []
    assert m.alt_thresholds == []
    assert m.alt_handler_image_paths == []
    assert m.alt_handler_thresholds == []
    assert m.match_strategy == MatchStrategy.ADAPTIVE
    assert m.threshold_mode == ThresholdMode.GLOBAL


def test_trigger_primary_miss_alt_hit_triggers_handler():
    """触发图主图 miss + 备用图 hit → 应触发处理(调用 input)。"""
    trig = MultiMatchResult(path="alt_t.png", rect=(10, 20, 30, 30), confidence=0.9, strategy_used="early_exit")
    hdl = MultiMatchResult(path="handler.png", rect=(40, 50, 5, 5), confidence=0.95, strategy_used="early_exit")
    config = _monitor(alt_trigger=["alt_t.png"])
    mon = _make_monitor(config, [trig, hdl])
    mon._check()
    assert mon._trigger_count == 1
    assert mon._input.left_click.called


def test_trigger_all_miss_no_handler():
    """触发图全部未命中 → 不触发处理。"""
    config = _monitor(alt_trigger=["alt_t.png"])
    mon = _make_monitor(config, [None])
    mon._check()
    assert mon._trigger_count == 0
    assert not mon._input.left_click.called


def test_trigger_uses_find_any_with_resolved_paths():
    """触发图 find_any 收到主图 + 备用图,strategy 来自 config。"""
    trig = MultiMatchResult(path="trigger.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    config = _monitor(alt_trigger=["alt_t.png"], strategy=MatchStrategy.BEST_CONFIDENCE)
    mon = _make_monitor(config, [trig, None])
    mon._check()
    first_call = mon._matcher.find_any.call_args_list[0]
    paths = first_call.kwargs.get("template_paths") or first_call.args[1]
    assert "trigger.png" in paths and "alt_t.png" in paths
    assert first_call.kwargs.get("strategy") == MatchStrategy.BEST_CONFIDENCE


def test_handler_multitemplate_resolved():
    """处理图多模板:find_any 第二次调用收 handler 主图 + 备用图。"""
    trig = MultiMatchResult(path="trigger.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    hdl = MultiMatchResult(path="alt_h.png", rect=(40, 50, 5, 5), confidence=0.9, strategy_used="early_exit")
    config = _monitor(alt_handler=["alt_h.png"])
    mon = _make_monitor(config, [trig, hdl])
    mon._check()
    assert mon._matcher.find_any.call_count == 2
    second = mon._matcher.find_any.call_args_list[1]
    paths = second.kwargs.get("template_paths") or second.args[1]
    assert "handler.png" in paths and "alt_h.png" in paths
