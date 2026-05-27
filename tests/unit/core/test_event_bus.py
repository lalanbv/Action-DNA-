"""TypedEventBus 测试 — 类型化发布/订阅、错误隔离、审计日志。"""

import threading
import time

import pytest

from src.core.events.bus import TypedEventBus
from src.core.events.events import (
    BaseEvent,
    ExecutionStartedEvent,
    NodeStartedEvent,
    NodeCompletedEvent,
    StepHighlightEvent,
    ExecutorStateChangedEvent,
    NodeFailedEvent,
)


# ============================================================
# 订阅与发布
# ============================================================


class TestSubscribePublish:
    """基本的订阅/发布功能。"""

    def test_publish_calls_subscriber(self):
        bus = TypedEventBus()
        received = []

        def handler(event: ExecutionStartedEvent):
            received.append(event)

        bus.subscribe(ExecutionStartedEvent, handler)
        event = ExecutionStartedEvent(graph_id="g1", node_count=3)
        bus.publish(event)

        assert len(received) == 1
        assert received[0] is event

    def test_multiple_subscribers(self):
        bus = TypedEventBus()
        results = {"a": [], "b": []}

        bus.subscribe(NodeStartedEvent, lambda e: results["a"].append(e))
        bus.subscribe(NodeStartedEvent, lambda e: results["b"].append(e))

        event = NodeStartedEvent(node_id="n1", node_type="CLICK_IMAGE", step_index=0)
        bus.publish(event)

        assert len(results["a"]) == 1
        assert len(results["b"]) == 1

    def test_no_subscriber_no_error(self):
        bus = TypedEventBus()
        event = ExecutionStartedEvent(graph_id="g1", node_count=1)
        bus.publish(event)  # 不应抛异常

    def test_subscriber_receives_correct_event_type_only(self):
        bus = TypedEventBus()
        started_events = []

        bus.subscribe(ExecutionStartedEvent, lambda e: started_events.append(e))

        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        bus.publish(NodeStartedEvent(node_id="n1", node_type="WAIT", step_index=0))

        assert len(started_events) == 1
        assert started_events[0].graph_id == "g1"

    def test_event_has_timestamp(self):
        bus = TypedEventBus()
        received = []
        bus.subscribe(ExecutionStartedEvent, lambda e: received.append(e))

        before = time.time()
        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        after = time.time()

        assert before <= received[0].timestamp <= after


# ============================================================
# 取消订阅
# ============================================================


class TestUnsubscribe:
    """取消订阅功能。"""

    def test_unsubscribe_stops_receiving(self):
        bus = TypedEventBus()
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(ExecutionStartedEvent, handler)
        bus.unsubscribe(ExecutionStartedEvent, handler)

        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        assert len(received) == 0

    def test_unsubscribe_nonexistent_no_error(self):
        bus = TypedEventBus()
        bus.unsubscribe(ExecutionStartedEvent, lambda e: None)

    def test_unsubscribe_one_of_many(self):
        bus = TypedEventBus()
        results = {"a": [], "b": []}

        handler_a = lambda e: results["a"].append(e)
        handler_b = lambda e: results["b"].append(e)

        bus.subscribe(NodeStartedEvent, handler_a)
        bus.subscribe(NodeStartedEvent, handler_b)
        bus.unsubscribe(NodeStartedEvent, handler_a)

        bus.publish(NodeStartedEvent(node_id="n1", node_type="WAIT", step_index=0))
        assert len(results["a"]) == 0
        assert len(results["b"]) == 1

    def test_unsubscribe_all_removes_type_key(self):
        bus = TypedEventBus()
        handler = lambda e: None
        bus.subscribe(ExecutionStartedEvent, handler)
        bus.unsubscribe(ExecutionStartedEvent, handler)
        assert bus.subscriber_count(ExecutionStartedEvent) == 0


# ============================================================
# 防重复订阅
# ============================================================


class TestNoDuplicateSubscription:
    """同一个 handler 不会被重复订阅。"""

    def test_duplicate_subscribe_ignored(self):
        bus = TypedEventBus()
        received = []

        handler = lambda e: received.append(e)
        bus.subscribe(ExecutionStartedEvent, handler)
        bus.subscribe(ExecutionStartedEvent, handler)  # 重复

        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        assert len(received) == 1

    def test_subscriber_count_after_duplicate(self):
        bus = TypedEventBus()
        handler = lambda e: None
        bus.subscribe(ExecutionStartedEvent, handler)
        bus.subscribe(ExecutionStartedEvent, handler)
        assert bus.subscriber_count(ExecutionStartedEvent) == 1


# ============================================================
# 错误隔离
# ============================================================


class TestErrorIsolation:
    """一个订阅者抛异常不影响其他订阅者。"""

    def test_error_does_not_stop_other_subscribers(self):
        bus = TypedEventBus()
        results = {"before": [], "after": []}

        def bad_handler(e):
            raise RuntimeError("boom")

        bus.subscribe(NodeStartedEvent, lambda e: results["before"].append(e))
        bus.subscribe(NodeStartedEvent, bad_handler)
        bus.subscribe(NodeStartedEvent, lambda e: results["after"].append(e))

        event = NodeStartedEvent(node_id="n1", node_type="WAIT", step_index=0)
        bus.publish(event)

        assert len(results["before"]) == 1
        assert len(results["after"]) == 1

    def test_all_subscribers_called_despite_error(self):
        bus = TypedEventBus()
        results = {"a": [], "b": []}

        def handler_a(e):
            results["a"].append(e)

        def error_handler(e):
            raise ValueError("test error")

        def handler_b(e):
            results["b"].append(e)

        bus.subscribe(ExecutionStartedEvent, handler_a)
        bus.subscribe(ExecutionStartedEvent, error_handler)
        bus.subscribe(ExecutionStartedEvent, handler_b)

        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        assert len(results["a"]) == 1
        assert len(results["b"]) == 1


# ============================================================
# 事件不可变性
# ============================================================


class TestEventImmutability:
    """事件 dataclass 应为 frozen，不可修改。"""

    def test_event_frozen(self):
        event = ExecutionStartedEvent(graph_id="g1", node_count=1)
        with pytest.raises(AttributeError):
            event.graph_id = "modified"  # type: ignore[misc]

    def test_base_event_frozen(self):
        event = NodeStartedEvent(node_id="n1", node_type="WAIT", step_index=0)
        with pytest.raises(AttributeError):
            event.node_id = "modified"  # type: ignore[misc]


# ============================================================
# 线程安全
# ============================================================


class TestThreadSafety:
    """多线程并发 publish/subscribe 安全。"""

    def test_concurrent_publish(self):
        bus = TypedEventBus()
        received = []
        lock = threading.Lock()

        def handler(event):
            with lock:
                received.append(event)

        bus.subscribe(ExecutionStartedEvent, handler)

        def publish_many():
            for i in range(50):
                bus.publish(ExecutionStartedEvent(graph_id=f"g{i}", node_count=i))

        threads = [threading.Thread(target=publish_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(received) == 200

    def test_concurrent_subscribe_unsubscribe(self):
        bus = TypedEventBus()

        def subscribe_many():
            for i in range(50):
                bus.subscribe(ExecutionStartedEvent, lambda e, _i=i: None)

        threads = [threading.Thread(target=subscribe_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert bus.subscriber_count(ExecutionStartedEvent) == 200

    def test_concurrent_publish_and_drain(self):
        """工作线程 publish UI 事件，主线程 drain 不崩溃。"""
        bus = TypedEventBus()
        received = []
        lock = threading.Lock()

        bus.subscribe_ui(ExecutionStartedEvent, lambda e: None)

        def publish_many():
            for i in range(50):
                bus.publish(ExecutionStartedEvent(graph_id=f"g{i}", node_count=i))

        t = threading.Thread(target=publish_many)
        t.start()
        # Simulate main thread draining
        for _ in range(10):
            bus.drain_ui_events()
        t.join()
        bus.drain_ui_events()  # drain remaining


# ============================================================
# 审计日志
# ============================================================


class TestAuditLog:
    """事件审计日志功能。"""

    def test_audit_disabled_by_default(self):
        bus = TypedEventBus()
        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        assert bus.get_audit_log() == []

    def test_enable_audit_records_events(self):
        bus = TypedEventBus()
        bus.enable_audit(True)

        event = ExecutionStartedEvent(graph_id="g1", node_count=1)
        bus.publish(event)

        log = bus.get_audit_log()
        assert len(log) == 1
        assert log[0][1] == "ExecutionStartedEvent"
        assert log[0][2] is event

    def test_audit_timestamp_order(self):
        bus = TypedEventBus()
        bus.enable_audit(True)

        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        bus.publish(NodeStartedEvent(node_id="n1", node_type="WAIT", step_index=0))

        log = bus.get_audit_log()
        assert len(log) == 2
        assert log[0][0] <= log[1][0]

    def test_disable_audit_clears_log(self):
        bus = TypedEventBus()
        bus.enable_audit(True)
        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        bus.enable_audit(False)
        assert bus.get_audit_log() == []

    def test_audit_returns_copy(self):
        bus = TypedEventBus()
        bus.enable_audit(True)
        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))

        log1 = bus.get_audit_log()
        log2 = bus.get_audit_log()
        assert log1 is not log2

    def test_audit_records_without_subscribers(self):
        bus = TypedEventBus()
        bus.enable_audit(True)
        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        assert len(bus.get_audit_log()) == 1

    def test_audit_records_ui_events(self):
        bus = TypedEventBus()
        bus.enable_audit(True)
        bus.subscribe_ui(StepHighlightEvent, lambda e: None)
        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))
        assert len(bus.get_audit_log()) == 1


# ============================================================
# clear / count
# ============================================================


class TestManagement:
    """订阅管理功能。"""

    def test_clear_subscriptions(self):
        bus = TypedEventBus()
        bus.subscribe(ExecutionStartedEvent, lambda e: None)
        bus.subscribe(NodeStartedEvent, lambda e: None)
        bus.clear_subscriptions()
        assert bus.subscriber_count() == 0

    def test_subscriber_count_total(self):
        bus = TypedEventBus()
        bus.subscribe(ExecutionStartedEvent, lambda e: None)
        bus.subscribe(NodeStartedEvent, lambda e: None)
        bus.subscribe(NodeStartedEvent, lambda e: None)
        assert bus.subscriber_count() == 3

    def test_subscriber_count_by_type(self):
        bus = TypedEventBus()
        bus.subscribe(ExecutionStartedEvent, lambda e: None)
        bus.subscribe(NodeStartedEvent, lambda e: None)
        bus.subscribe(NodeStartedEvent, lambda e: None)
        assert bus.subscriber_count(NodeStartedEvent) == 2
        assert bus.subscriber_count(ExecutionStartedEvent) == 1

    def test_subscriber_count_no_subscribers(self):
        bus = TypedEventBus()
        assert bus.subscriber_count() == 0
        assert bus.subscriber_count(ExecutionStartedEvent) == 0

    def test_clear_also_clears_audit(self):
        bus = TypedEventBus()
        bus.enable_audit(True)
        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))
        assert len(bus.get_audit_log()) == 1
        bus.clear_subscriptions()
        assert bus.get_audit_log() == []


# ============================================================
# UI 线程桥接
# ============================================================


class TestUIThreadBridge:
    """subscribe_ui + drain_ui_events 线程安全桥接。"""

    def test_ui_handler_not_called_directly(self):
        bus = TypedEventBus()
        called = []

        bus.subscribe_ui(StepHighlightEvent, lambda e: called.append(e))
        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))

        assert len(called) == 0

    def test_drain_executes_queued_handlers(self):
        bus = TypedEventBus()
        received = []

        bus.subscribe_ui(StepHighlightEvent, lambda e: received.append(e))
        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))
        bus.publish(StepHighlightEvent(node_id="n2", is_active=False))

        count = bus.drain_ui_events()
        assert count == 2
        assert len(received) == 2
        assert received[0].node_id == "n1"
        assert received[1].node_id == "n2"

    def test_drain_returns_zero_when_empty(self):
        bus = TypedEventBus()
        assert bus.drain_ui_events() == 0

    def test_mixed_ui_and_non_ui_handlers(self):
        bus = TypedEventBus()
        non_ui = []
        ui = []

        bus.subscribe(StepHighlightEvent, lambda e: non_ui.append(e))
        bus.subscribe_ui(StepHighlightEvent, lambda e: ui.append(e))

        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))

        assert len(non_ui) == 1
        assert len(ui) == 0

        bus.drain_ui_events()
        assert len(ui) == 1

    def test_ui_handler_error_isolation_in_drain(self):
        bus = TypedEventBus()
        results = []

        def bad_handler(e):
            raise RuntimeError("ui boom")

        bus.subscribe_ui(StepHighlightEvent, bad_handler)
        bus.subscribe_ui(StepHighlightEvent, lambda e: results.append(e))

        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))
        count = bus.drain_ui_events()

        assert count == 2
        assert len(results) == 1

    def test_unsubscribe_removes_ui_handler(self):
        bus = TypedEventBus()
        received = []

        handler = lambda e: received.append(e)
        bus.subscribe_ui(StepHighlightEvent, handler)
        bus.unsubscribe(StepHighlightEvent, handler)

        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))
        bus.drain_ui_events()

        assert len(received) == 0

    def test_subscribe_ui_no_duplicate(self):
        bus = TypedEventBus()
        received = []

        handler = lambda e: received.append(e)
        bus.subscribe_ui(StepHighlightEvent, handler)
        bus.subscribe_ui(StepHighlightEvent, handler)

        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))
        bus.drain_ui_events()

        assert len(received) == 1

    def test_drain_clears_queue(self):
        bus = TypedEventBus()
        received = []

        bus.subscribe_ui(StepHighlightEvent, lambda e: received.append(e))
        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))

        bus.drain_ui_events()
        bus.drain_ui_events()

        assert len(received) == 1

    def test_ui_events_from_worker_thread(self):
        bus = TypedEventBus()
        received = []
        lock = threading.Lock()

        def handler(event):
            with lock:
                received.append(event)

        bus.subscribe_ui(ExecutionStartedEvent, handler)

        def worker():
            for i in range(20):
                bus.publish(ExecutionStartedEvent(graph_id=f"g{i}", node_count=i))

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        count = bus.drain_ui_events()
        assert count == 20
        assert len(received) == 20

    def test_clear_subscriptions_clears_ui_state(self):
        bus = TypedEventBus()
        bus.subscribe_ui(StepHighlightEvent, lambda e: None)
        bus.publish(StepHighlightEvent(node_id="n1", is_active=True))
        bus.clear_subscriptions()
        assert bus.drain_ui_events() == 0
