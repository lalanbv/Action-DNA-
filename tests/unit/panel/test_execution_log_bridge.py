"""ExecutionLogBridge 单元测试 — EventBus 执行事件 → RingBufferLog 翻译。

锁定契约: 桥接器把 ActionExecutor 经 EventBus 发布的生命周期事件
(启动/停止/暂停/恢复/结束/安全停止/轮次)翻译成结构化执行日志条目,
写入共享 RingBufferLog,供执行日志面板显示。destroy() 后不再接收事件。
"""

from __future__ import annotations

from src.core.debug.ring_buffer_log import LogEventType, RingBufferLog
from src.core.events.bus import TypedEventBus
from src.core.events.event_names import EventName
from src.panel.components.execution_log_bridge import ExecutionLogBridge


def _make_bridge():
    """构造 (bus, ring, bridge) 三元组,供各用例复用。"""
    bus = TypedEventBus()
    ring = RingBufferLog(capacity=50)
    bridge = ExecutionLogBridge(bus, ring)
    return bus, ring, bridge


class TestExecutionLogBridge:
    def test_started_writes_execution_start(self) -> None:
        bus, ring, _ = _make_bridge()
        bus.emit(EventName.EXECUTOR_STARTED)
        entries = ring.get_by_type(LogEventType.EXECUTION_START)
        assert len(entries) == 1
        # zh "执行已启动" / en "Execution started"
        assert "启动" in entries[0].message or "start" in entries[0].message.lower()

    def test_finished_writes_execution_end_with_rounds(self) -> None:
        bus, ring, _ = _make_bridge()
        bus.emit(EventName.EXECUTOR_FINISHED, rounds=3)
        ends = ring.get_by_type(LogEventType.EXECUTION_END)
        assert len(ends) == 1
        assert "3" in ends[0].message  # "共 3 轮" / "3 round(s)"

    def test_finished_without_rounds_does_not_crash(self) -> None:
        """executor 未来若不发 rounds,桥接器以 0 兜底,不得抛。"""
        bus, ring, _ = _make_bridge()
        bus.emit(EventName.EXECUTOR_FINISHED)
        assert len(ring.get_by_type(LogEventType.EXECUTION_END)) == 1

    def test_paused_resumed_stopped_write_custom(self) -> None:
        bus, ring, _ = _make_bridge()
        bus.emit(EventName.EXECUTOR_PAUSED)
        bus.emit(EventName.EXECUTOR_RESUMED)
        bus.emit(EventName.EXECUTOR_STOPPED)
        customs = ring.get_by_type(LogEventType.CUSTOM)
        assert len(customs) == 3

    def test_failsafe_writes_node_error(self) -> None:
        bus, ring, _ = _make_bridge()
        bus.emit(EventName.EXECUTOR_FAILSAFE)
        assert len(ring.get_by_type(LogEventType.NODE_ERROR)) == 1

    def test_round_started_uses_one_based_index(self) -> None:
        """executor iteration=1 表示第 2 轮,面板展示 1-based。"""
        bus, ring, _ = _make_bridge()
        bus.emit(EventName.EXECUTOR_ROUND_STARTED, iteration=1)
        customs = ring.get_by_type(LogEventType.CUSTOM)
        assert len(customs) == 1
        assert "2" in customs[0].message  # "第 2 轮" / "Round 2"

    def test_destroy_unsubscribes(self) -> None:
        """destroy 后,EventBus 事件不再写入 ring_log。"""
        bus, ring, bridge = _make_bridge()
        bridge.destroy()
        bus.emit(EventName.EXECUTOR_STARTED)
        assert ring.count == 0

    def test_full_lifecycle_smoke(self) -> None:
        """端到端冒烟: 完整生命周期事件序列全部被翻译。"""
        bus, ring, bridge = _make_bridge()
        bus.emit(EventName.EXECUTOR_STARTED)
        bus.emit(EventName.EXECUTOR_ROUND_STARTED, iteration=1)
        bus.emit(EventName.EXECUTOR_PAUSED)
        bus.emit(EventName.EXECUTOR_RESUMED)
        bus.emit(EventName.EXECUTOR_FAILSAFE)
        bus.emit(EventName.EXECUTOR_STOPPED)
        bus.emit(EventName.EXECUTOR_FINISHED, rounds=2)
        bridge.destroy()
        # 7 个事件各翻译一条
        assert ring.count == 7
        assert len(ring.get_by_type(LogEventType.EXECUTION_START)) == 1
        assert len(ring.get_by_type(LogEventType.EXECUTION_END)) == 1
        assert len(ring.get_by_type(LogEventType.NODE_ERROR)) == 1  # failsafe
        assert len(ring.get_by_type(LogEventType.CUSTOM)) == 4  # round/paused/resumed/stopped
