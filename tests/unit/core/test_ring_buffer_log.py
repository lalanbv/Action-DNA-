"""RingBufferLog 单元测试。"""

from __future__ import annotations

import json
import time
from unittest.mock import MagicMock

import pytest

from src.core.debug.ring_buffer_log import LogEntry, LogEventType, RingBufferLog


class TestLogEntry:
    def test_frozen(self) -> None:
        entry = LogEntry(
            timestamp=1000.0,
            node_id="n1",
            event_type=LogEventType.NODE_ENTER,
            message="test",
        )
        with pytest.raises(AttributeError):
            entry.message = "changed"  # type: ignore[misc]

    def test_time_str(self) -> None:
        entry = LogEntry(
            timestamp=1000.0,
            node_id="",
            event_type=LogEventType.CUSTOM,
            message="",
        )
        assert isinstance(entry.time_str, str)
        assert len(entry.time_str) > 0

    def test_data_default_none(self) -> None:
        entry = LogEntry(
            timestamp=0.0,
            node_id="",
            event_type=LogEventType.CUSTOM,
            message="",
        )
        assert entry.data is None


class TestRingBufferLogAppend:
    def test_append_returns_entry(self) -> None:
        log = RingBufferLog()
        entry = log.append(
            node_id="n1",
            event_type=LogEventType.NODE_ENTER,
            message="entered",
        )
        assert entry.node_id == "n1"
        assert entry.event_type == LogEventType.NODE_ENTER
        assert entry.message == "entered"

    def test_count_increments(self) -> None:
        log = RingBufferLog()
        log.append()
        log.append()
        assert log.count == 2

    def test_capacity_property(self) -> None:
        log = RingBufferLog(capacity=500)
        assert log.capacity == 500

    def test_auto_evicts_oldest(self) -> None:
        log = RingBufferLog(capacity=3)
        log.append(node_id="a")
        log.append(node_id="b")
        log.append(node_id="c")
        log.append(node_id="d")
        assert log.count == 3
        entries = log.get_all()
        assert [e.node_id for e in entries] == ["b", "c", "d"]


class TestRingBufferLogRead:
    def test_get_recent(self) -> None:
        log = RingBufferLog()
        for i in range(10):
            log.append(node_id=f"n{i}")
        recent = log.get_recent(3)
        assert len(recent) == 3
        assert [e.node_id for e in recent] == ["n7", "n8", "n9"]

    def test_get_recent_more_than_count(self) -> None:
        log = RingBufferLog()
        log.append(node_id="a")
        recent = log.get_recent(10)
        assert len(recent) == 1

    def test_get_all(self) -> None:
        log = RingBufferLog()
        log.append(node_id="a")
        log.append(node_id="b")
        all_entries = log.get_all()
        assert len(all_entries) == 2
        assert all_entries[0].node_id == "a"

    def test_get_by_node(self) -> None:
        log = RingBufferLog()
        log.append(node_id="n1", event_type=LogEventType.NODE_ENTER)
        log.append(node_id="n2", event_type=LogEventType.NODE_EXIT)
        log.append(node_id="n1", event_type=LogEventType.NODE_EXIT)
        result = log.get_by_node("n1")
        assert len(result) == 2
        assert all(e.node_id == "n1" for e in result)

    def test_get_by_type(self) -> None:
        log = RingBufferLog()
        log.append(event_type=LogEventType.NODE_ENTER)
        log.append(event_type=LogEventType.NODE_ERROR)
        log.append(event_type=LogEventType.NODE_ENTER)
        result = log.get_by_type(LogEventType.NODE_ENTER)
        assert len(result) == 2

    def test_get_by_time_range(self) -> None:
        log = RingBufferLog()
        e1 = log.append(message="first")
        e2 = log.append(message="second")
        e3 = log.append(message="third")

        # Full range should include all
        result_all = log.get_by_time_range(e1.timestamp)
        assert len(result_all) == 3

        # Range before all entries should return empty
        result_before = log.get_by_time_range(0.0, e1.timestamp - 1.0)
        assert len(result_before) == 0


class TestRingBufferLogStats:
    def test_get_error_count(self) -> None:
        log = RingBufferLog()
        log.append(event_type=LogEventType.NODE_ENTER)
        log.append(event_type=LogEventType.NODE_ERROR)
        log.append(event_type=LogEventType.NODE_ERROR)
        assert log.get_error_count() == 2

    def test_get_error_count_zero(self) -> None:
        log = RingBufferLog()
        assert log.get_error_count() == 0


class TestRingBufferLogCallback:
    def test_on_append_callback(self) -> None:
        log = RingBufferLog()
        cb = MagicMock()
        log.on_append(cb)
        entry = log.append(node_id="n1")
        cb.assert_called_once_with(entry)

    def test_callback_exception_does_not_break(self) -> None:
        log = RingBufferLog()
        log.on_append(lambda e: 1 / 0)
        log.append()  # should not raise


class TestRingBufferLogExport:
    def test_export_to_file(self, tmp_path) -> None:
        log = RingBufferLog()
        log.append(
            node_id="n1",
            event_type=LogEventType.NODE_ENTER,
            message="test entry",
            data={"key": "value"},
        )
        filepath = str(tmp_path / "log.json")
        log.export_to_file(filepath)

        with open(filepath) as f:
            data = json.load(f)
        assert len(data) == 1
        assert data[0]["node_id"] == "n1"
        assert data[0]["event_type"] == "node_enter"
        assert data[0]["message"] == "test entry"
        assert data[0]["data"] == {"key": "value"}

    def test_export_empty(self, tmp_path) -> None:
        log = RingBufferLog()
        filepath = str(tmp_path / "empty.json")
        log.export_to_file(filepath)

        with open(filepath) as f:
            data = json.load(f)
        assert data == []


class TestRingBufferLogClear:
    def test_clear(self) -> None:
        log = RingBufferLog()
        log.append()
        log.append()
        log.clear()
        assert log.count == 0

    def test_clear_empty_no_error(self) -> None:
        log = RingBufferLog()
        log.clear()
        assert log.count == 0


class TestRingBufferLogThreadSafety:
    def test_concurrent_appends(self) -> None:
        import threading

        log = RingBufferLog(capacity=1000)

        def append_many():
            for i in range(100):
                log.append(node_id=f"n{i}")

        threads = [threading.Thread(target=append_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert log.count == 500
