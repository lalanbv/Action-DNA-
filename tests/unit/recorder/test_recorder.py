"""MacroRecorder 单元测试 — 事件模型和录制器内部 API。"""

import pytest

from src.core.action import ActionType
from src.recorder.recorder import MacroRecorder, RecordedEvent


# ── RecordedEvent ──────────────────────────────────────────────


class TestRecordedEvent:
    def test_frozen(self):
        evt = RecordedEvent(event_type="mouse_move", x=100, y=200)
        with pytest.raises(AttributeError):
            evt.x = 300

    def test_is_mouse_event(self):
        assert RecordedEvent(event_type="mouse_move").is_mouse_event is True
        assert RecordedEvent(event_type="mouse_drag").is_mouse_event is True
        assert RecordedEvent(event_type="mouse_scroll").is_mouse_event is True
        assert RecordedEvent(event_type="key_down").is_mouse_event is False

    def test_is_key_event(self):
        assert RecordedEvent(event_type="key_down").is_key_event is True
        assert RecordedEvent(event_type="key_up").is_key_event is True
        assert RecordedEvent(event_type="mouse_move").is_key_event is False

    def test_scroll_delta_x_default(self):
        evt = RecordedEvent(event_type="mouse_scroll", scroll_delta=3)
        assert evt.scroll_delta_x == 0

    def test_scroll_delta_x_set(self):
        evt = RecordedEvent(event_type="mouse_scroll", scroll_delta=3, scroll_delta_x=5)
        assert evt.scroll_delta_x == 5


# ── MacroRecorder 生命周期 ────────────────────────────────────


class TestMacroRecorderLifecycle:
    def test_initial_state(self):
        r = MacroRecorder()
        assert r.is_recording is False
        assert r.event_count == 0

    def test_start_stop(self):
        r = MacroRecorder()
        r.start()
        assert r.is_recording is True
        events = r.stop()
        assert r.is_recording is False
        assert isinstance(events, list)

    def test_stop_without_events(self):
        r = MacroRecorder()
        r.start()
        events = r.stop()
        assert events == []

    def test_double_start(self):
        r = MacroRecorder()
        r.start()
        r.start()  # 应先 stop 再 start
        assert r.is_recording is True
        r.stop()


# ── 事件回调（直接调用内部方法，不启动捕获线程）──────────────


class TestOnMouseEvent:
    def test_recorded(self):
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_mouse_event("mouse_down", 100, 200, "left", 1.0, 0.0)
        assert r.event_count == 1

    def test_not_recording_ignored(self):
        r = MacroRecorder()
        r._is_recording = False
        r._on_mouse_event("mouse_down", 100, 200, "left", 1.0, 0.0)
        assert r.event_count == 0

    def test_dedup_close_move(self):
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_mouse_event("mouse_move", 100, 100, "", 1.0, 0.0)
        r._on_mouse_event("mouse_move", 100, 100, "", 1.0, 0.0)  # 距离 = 0，应去重
        assert r.event_count == 1

    def test_keep_distant_move(self):
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_mouse_event("mouse_move", 100, 100, "", 1.0, 0.0)
        r._on_mouse_event("mouse_move", 200, 200, "", 1.0, 0.0)  # 距离 > 5
        assert r.event_count == 2

    def test_never_dedup_click(self):
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_mouse_event("mouse_move", 100, 100, "", 1.0, 0.0)
        r._on_mouse_event("mouse_down", 101, 101, "left", 1.0, 0.0)  # 距离 < 5
        assert r.event_count == 2


class TestOnKeyEvent:
    def test_key_down_recorded(self):
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_key_event("key_down", "a", 1.0, 0.0)
        assert r.event_count == 1
        events = r.snapshot_events()
        assert events[0].key == "a"

    def test_repeat_key_now_recorded(self):
        """Phase 1 修复后：重复按键现在也被记录。"""
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_key_event("key_down", "a", 1.0, 0.0, is_repeat=False)
        r._on_key_event("key_down", "a", 1.1, 0.1, is_repeat=True)
        assert r.event_count == 2


class TestOnScrollEvent:
    def test_vertical_scroll(self):
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_scroll_event(100, 200, 3, 1.0, 0.0)
        events = r.snapshot_events()
        assert len(events) == 1
        assert events[0].scroll_delta == 3
        assert events[0].scroll_delta_x == 0

    def test_horizontal_scroll(self):
        """Phase 1 新增：水平滚动支持。"""
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_scroll_event(100, 200, 0, 1.0, 0.0, delta_x=5)
        events = r.snapshot_events()
        assert len(events) == 1
        assert events[0].scroll_delta_x == 5

    def test_diagonal_scroll(self):
        """同时垂直 + 水平滚动。"""
        r = MacroRecorder()
        r._is_recording = True
        r._last_event_time = 1.0
        r._on_scroll_event(100, 200, 3, 1.0, 0.0, delta_x=-2)
        events = r.snapshot_events()
        assert len(events) == 1
        assert events[0].scroll_delta == 3
        assert events[0].scroll_delta_x == -2
