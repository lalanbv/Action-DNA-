"""RecordBridge 测试 — 录制到动作链的桥接器。

验证 start_recording / stop_and_convert / convert_events / 属性访问。
MacroRecorder 和 EventMerger 通过 mock 隔离。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.descriptors.record_descriptor import RecordBridge
from src.recorder.recorder import RecordedEvent


def _make_event(event_type: str = "mouse_down", **kwargs) -> RecordedEvent:
    """构建测试用 RecordedEvent。"""
    defaults = {
        "event_type": event_type,
        "x": 100,
        "y": 200,
        "timestamp": 1.0,
        "delta_time": 0.1,
    }
    defaults.update(kwargs)
    return RecordedEvent(**defaults)


class TestRecordBridgeInit:

    def test_default_init(self) -> None:
        bridge = RecordBridge()
        assert bridge.is_recording is False
        assert bridge.event_count == 0
        assert bridge.duration == 0.0

    def test_init_with_region(self) -> None:
        bridge = RecordBridge(region=(10, 20, 800, 600))
        assert bridge.is_recording is False


class TestStartRecording:

    @patch("src.core.engine.descriptors.record_descriptor.MacroRecorder")
    @patch("src.core.engine.descriptors.record_descriptor.EventMerger")
    def test_start_sets_recording(self, mock_merger_cls, mock_recorder_cls) -> None:
        mock_recorder = MagicMock()
        mock_recorder.is_recording = True
        mock_recorder_cls.return_value = mock_recorder

        bridge = RecordBridge()
        bridge.start_recording()

        mock_recorder.start.assert_called_once()
        assert bridge.is_recording is True


class TestStopAndConvert:

    @patch("src.core.engine.descriptors.record_descriptor.MacroRecorder")
    @patch("src.core.engine.descriptors.record_descriptor.EventMerger")
    def test_stop_returns_steps(self, mock_merger_cls, mock_recorder_cls) -> None:
        events = [_make_event(), _make_event(event_type="key_down", key="a")]
        steps = [STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200)]

        mock_recorder = MagicMock()
        mock_recorder.stop.return_value = events
        mock_recorder_cls.return_value = mock_recorder

        mock_merger = MagicMock()
        mock_merger.merge.return_value = steps
        mock_merger_cls.return_value = mock_merger

        bridge = RecordBridge()
        result = bridge.stop_and_convert()

        mock_recorder.stop.assert_called_once()
        mock_merger.merge.assert_called_once_with(events)
        assert result == steps

    @patch("src.core.engine.descriptors.record_descriptor.MacroRecorder")
    @patch("src.core.engine.descriptors.record_descriptor.EventMerger")
    def test_stop_empty_events(self, mock_merger_cls, mock_recorder_cls) -> None:
        mock_recorder = MagicMock()
        mock_recorder.stop.return_value = []
        mock_recorder_cls.return_value = mock_recorder

        mock_merger = MagicMock()
        mock_merger.merge.return_value = []
        mock_merger_cls.return_value = mock_merger

        bridge = RecordBridge()
        result = bridge.stop_and_convert()

        assert result == []


class TestConvertEvents:

    @patch("src.core.engine.descriptors.record_descriptor.MacroRecorder")
    @patch("src.core.engine.descriptors.record_descriptor.EventMerger")
    def test_convert_without_recording(self, mock_merger_cls, mock_recorder_cls) -> None:
        events = [_make_event()]
        steps = [STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200)]

        mock_merger = MagicMock()
        mock_merger.merge.return_value = steps
        mock_merger_cls.return_value = mock_merger

        bridge = RecordBridge()
        result = bridge.convert_events(events)

        mock_merger.merge.assert_called_once_with(events)
        assert result == steps


class TestProperties:

    @patch("src.core.engine.descriptors.record_descriptor.MacroRecorder")
    @patch("src.core.engine.descriptors.record_descriptor.EventMerger")
    def test_event_count_delegates(self, mock_merger_cls, mock_recorder_cls) -> None:
        mock_recorder = MagicMock()
        mock_recorder.event_count = 5
        mock_recorder_cls.return_value = mock_recorder

        bridge = RecordBridge()
        assert bridge.event_count == 5

    @patch("src.core.engine.descriptors.record_descriptor.MacroRecorder")
    @patch("src.core.engine.descriptors.record_descriptor.EventMerger")
    def test_duration_delegates(self, mock_merger_cls, mock_recorder_cls) -> None:
        mock_recorder = MagicMock()
        mock_recorder.duration = 3.5
        mock_recorder_cls.return_value = mock_recorder

        bridge = RecordBridge()
        assert bridge.duration == 3.5

    @patch("src.core.engine.descriptors.record_descriptor.MacroRecorder")
    @patch("src.core.engine.descriptors.record_descriptor.EventMerger")
    def test_is_recording_delegates(self, mock_merger_cls, mock_recorder_cls) -> None:
        mock_recorder = MagicMock()
        mock_recorder.is_recording = True
        mock_recorder_cls.return_value = mock_recorder

        bridge = RecordBridge()
        assert bridge.is_recording is True
