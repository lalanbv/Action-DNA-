"""变量系统集成测试 — VariablePool + EventBus + builtins 联动。

参考: 13_风险与验证策略.md §5.3
覆盖: 变更事件桥接、执行生命周期模拟、计数器联动、
      快照与审计一致性、作用域隔离、内置变量 + 模板解析。
"""

import threading
import time

import pytest

from src.core.events.bus import TypedEventBus
from src.core.events.events import (
    ExecutionStartedEvent,
    ExecutionCompletedEvent,
    NodeStartedEvent,
    NodeCompletedEvent,
    NodeFailedEvent,
    VariableChangedEvent,
)
from src.core.variables.builtins import (
    increment_counter,
    get_counter,
    reset_counter,
)
from src.core.variables.pool import VariablePool
from src.core.variables.scope import VariableScope
from src.core.variables.types import VariableType


# ---- fixtures ----


@pytest.fixture
def pool() -> VariablePool:
    return VariablePool()


@pytest.fixture
def bus() -> TypedEventBus:
    return TypedEventBus()


@pytest.fixture
def bridge(pool: VariablePool, bus: TypedEventBus):
    """将 pool 的 on_change 回调桥接到 bus，发布 VariableChangedEvent。"""

    def _on_change(name: str, old_value, new_value, scope: VariableScope):
        bus.publish(VariableChangedEvent(
            var_name=name,
            old_value=old_value,
            new_value=new_value,
            scope=scope,
        ))

    pool.on_change(_on_change)
    return _on_change


@pytest.fixture
def collected_events(bus: TypedEventBus):
    """收集总线上所有 VariableChangedEvent。"""
    events: list[VariableChangedEvent] = []

    def _handler(event: VariableChangedEvent):
        events.append(event)

    bus.subscribe(VariableChangedEvent, _handler)
    return events


# ---- 1. 变更事件桥接 ----


class TestChangeEventBridge:
    """VariablePool.on_change → EventBus.publish(VariableChangedEvent)。"""

    def test_set_publishes_change_event(self, pool, bus, bridge, collected_events):
        pool.declare("x", VariableType.INT, initial_value=0)
        pool.set("x", 42)

        assert len(collected_events) == 1
        evt = collected_events[0]
        assert evt.var_name == "x"
        assert evt.old_value == 0
        assert evt.new_value == 42

    def test_multiple_sets_produce_multiple_events(self, pool, bus, bridge, collected_events):
        pool.declare("count", VariableType.INT, initial_value=0)
        for i in range(1, 6):
            pool.set("count", i)

        assert len(collected_events) == 5
        assert [e.new_value for e in collected_events] == [1, 2, 3, 4, 5]

    def test_declare_does_not_publish_event(self, pool, bus, bridge, collected_events):
        pool.declare("y", VariableType.STR, initial_value="hello")
        assert len(collected_events) == 0

    def test_type_mismatch_no_event(self, pool, bus, bridge, collected_events):
        pool.declare("z", VariableType.INT, initial_value=1)
        with pytest.raises(TypeError):
            pool.set("z", "bad")
        assert len(collected_events) == 0

    def test_event_scope_reflects_variable_scope(self, pool, bus, bridge, collected_events):
        pool.declare("node_var", VariableType.INT, VariableScope.NODE, initial_value=0)
        pool.set("node_var", 10, VariableScope.NODE)

        assert len(collected_events) == 1
        assert collected_events[0].scope == VariableScope.NODE


# ---- 2. EventBus 订阅者反向更新 VariablePool ----


class TestEventSubscriberUpdatesPool:
    """EventBus 订阅者接收事件后更新 VariablePool。"""

    def test_node_completed_updates_pool(self, pool, bus):
        def _on_node_completed(event: NodeCompletedEvent):
            for k, v in event.output_vars.items():
                pool.set(k, v)

        bus.subscribe(NodeCompletedEvent, _on_node_completed)

        bus.publish(NodeCompletedEvent(
            node_id="click_1",
            node_type="click_image",
            success=True,
            elapsed_ms=12.5,
            output_vars={"last_match": (320, 480), "confidence": 0.95},
        ))

        assert pool.get("last_match") == (320, 480)
        assert pool.get("confidence") == 0.95

    def test_execution_completed_updates_loop_count(self, pool, bus):
        bus.subscribe(ExecutionCompletedEvent, lambda e: pool.set("total_steps", e.total_steps))

        bus.publish(ExecutionCompletedEvent(
            graph_id="g1",
            total_steps=42,
            elapsed_seconds=5.3,
            success=True,
        ))

        assert pool.get("total_steps") == 42


# ---- 3. 执行生命周期模拟 ----


class TestExecutionLifecycle:
    """模拟一次完整执行: scope push/pop + 事件发布 + 变量生命周期。"""

    def test_full_lifecycle_variable_visibility(self, pool, bus, bridge, collected_events):
        pool.push_scope(VariableScope.STEP)
        pool.declare("loop_count", VariableType.INT, VariableScope.STEP, initial_value=0)

        pool.push_scope(VariableScope.NODE)
        pool.declare("temp_pos", VariableType.COORD, VariableScope.NODE, initial_value=(0, 0))

        pool.set("temp_pos", (100, 200), VariableScope.NODE)
        pool.set("loop_count", 1, VariableScope.STEP)

        pool.declare("global_flag", VariableType.BOOL, initial_value=False)
        pool.set("global_flag", True)

        pool.pop_scope(VariableScope.NODE)
        assert not pool.has("temp_pos", VariableScope.NODE)
        assert pool.has("loop_count", VariableScope.STEP)
        assert pool.has("global_flag")

        pool.pop_scope(VariableScope.STEP)
        assert not pool.has("loop_count", VariableScope.STEP)
        assert pool.has("global_flag")

        assert len(collected_events) == 3

    def test_lifecycle_event_order(self, pool, bus):
        log: list[str] = []

        bus.subscribe(ExecutionStartedEvent, lambda e: log.append(f"started:{e.node_count}"))
        bus.subscribe(NodeStartedEvent, lambda e: log.append(f"node_start:{e.node_id}"))
        bus.subscribe(NodeCompletedEvent, lambda e: log.append(f"node_done:{e.node_id}"))
        bus.subscribe(ExecutionCompletedEvent, lambda e: log.append(f"completed:{e.total_steps}"))

        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=3))
        for nid in ["n1", "n2", "n3"]:
            bus.publish(NodeStartedEvent(node_id=nid, node_type="wait", step_index=0))
            bus.publish(NodeCompletedEvent(
                node_id=nid, node_type="wait", success=True, elapsed_ms=1.0,
            ))
        bus.publish(ExecutionCompletedEvent(
            graph_id="g1", total_steps=3, elapsed_seconds=0.01, success=True,
        ))

        assert log == [
            "started:3",
            "node_start:n1", "node_done:n1",
            "node_start:n2", "node_done:n2",
            "node_start:n3", "node_done:n3",
            "completed:3",
        ]


# ---- 4. 计数器 + EventBus 联动 ----


class TestCounterEventIntegration:
    """计数器操作触发 EventBus 事件。"""

    def test_increment_publishes_event(self, pool, bus, bridge, collected_events):
        increment_counter(pool, "loops")
        assert len(collected_events) == 0  # first increment uses declare()

        increment_counter(pool, "loops")
        assert len(collected_events) == 1
        assert collected_events[0].var_name == "counter.loops"
        assert collected_events[0].new_value == 2

    def test_multiple_increments_event_sequence(self, pool, bus, bridge, collected_events):
        increment_counter(pool, "loops")  # declare, no event
        increment_counter(pool, "loops")  # set: 1→2
        increment_counter(pool, "loops")  # set: 2→3

        values = [e.new_value for e in collected_events]
        assert values == [2, 3]

    def test_reset_counter_publishes_event(self, pool, bus, bridge, collected_events):
        increment_counter(pool, "loops")
        collected_events.clear()
        reset_counter(pool, "loops")
        assert len(collected_events) == 1
        assert collected_events[0].new_value == 0

    def test_multiple_counter_events_interleaved(self, pool, bus, bridge, collected_events):
        increment_counter(pool, "c1") # declare, no event
        increment_counter(pool, "c1") # set counter: 1→2, event
        increment_counter(pool, "c1") # set counter: 2→3, event

        names = [e.var_name for e in collected_events]
        assert names == ["counter.c1", "counter.c1"]
        assert collected_events[1].new_value == 3


# ---- 6. 快照与审计一致性 ----


class TestSnapshotAuditConsistency:
    """快照内容与 EventBus 审计日志应一致。"""

    def test_snapshot_matches_final_state(self, pool, bus, bridge):
        pool.declare("a", VariableType.INT, initial_value=1)
        pool.declare("b", VariableType.STR, initial_value="x")
        pool.set("a", 10)
        pool.set("b", "y")

        snap = pool.snapshot()
        assert snap["global"]["a"] == 10
        assert snap["global"]["b"] == "y"

    def test_audit_log_captures_publish_order(self, pool, bus, bridge):
        bus.enable_audit(True)
        pool.declare("x", VariableType.INT, initial_value=0)
        pool.set("x", 1)
        pool.set("x", 2)

        log = bus.get_audit_log()
        assert len(log) == 2
        assert log[0][1] == "VariableChangedEvent"
        assert log[1][1] == "VariableChangedEvent"

    def test_snapshot_after_scope_lifecycle(self, pool):
        pool.push_scope(VariableScope.NODE)
        pool.declare("local", VariableType.INT, VariableScope.NODE, initial_value=5)
        pool.set("local", 99, VariableScope.NODE)

        snap = pool.snapshot()
        assert snap["node"]["local"] == 99

        pool.pop_scope(VariableScope.NODE)
        snap_after = pool.snapshot()
        assert "local" not in snap_after["node"]

    def test_snapshot_isolation(self, pool):
        pool.declare("items", VariableType.LIST, initial_value=[1, 2, 3])
        snap = pool.snapshot()
        snap["global"]["items"].append(4)
        assert pool.get("items") == [1, 2, 3]


# ---- 7. 内置变量 + 模板 + 事件 ----


class TestBuiltinTemplateIntegration:
    """内置变量、模板解析与事件桥接集成。"""

    def test_builtin_sys_time_in_template(self, pool):
        result = pool.resolve_template("时间: {{sys.time}}")
        assert result.startswith("时间: ")
        time_part = result.split(": ", 1)[1]
        assert len(time_part) == 8  # HH:MM:SS

    def test_builtin_exec_defaults(self, pool):
        assert pool.get("exec.loop_count") == 0
        assert pool.get("exec.step_count") == 0
        assert pool.get("exec.step_index") == 0

    def test_runtime_resolvers_in_template(self, pool):
        pool.set_runtime_resolvers(
            mouse_x_fn=lambda: 500,
            mouse_y_fn=lambda: 300,
            screen_w_fn=lambda: 1920,
            screen_h_fn=lambda: 1080,
        )
        result = pool.resolve_template("({{sys.mouse_x}}, {{sys.mouse_y}}) on {{sys.screen_w}}x{{sys.screen_h}}")
        assert result == "(500, 300) on 1920x1080"

    def test_builtin_with_region(self, pool):
        pool.set_runtime_resolvers(
            mouse_x_fn=lambda: 0,
            mouse_y_fn=lambda: 0,
            screen_w_fn=lambda: 1920,
            screen_h_fn=lambda: 1080,
            region_fn=lambda: (100, 200, 800, 600),
        )
        assert pool.get("region.x") == 100
        assert pool.get("region.y") == 200
        assert pool.get("region.w") == 800
        assert pool.get("region.h") == 600

    def test_event_handler_reads_builtins(self, pool, bus):
        pool.set_runtime_resolvers(
            mouse_x_fn=lambda: 960,
            mouse_y_fn=lambda: 540,
            screen_w_fn=lambda: 1920,
            screen_h_fn=lambda: 1080,
        )

        captured: list[str] = []

        def _on_exec_started(event: ExecutionStartedEvent):
            captured.append(pool.resolve_template(
                "开始执行，鼠标: ({{sys.mouse_x}}, {{sys.mouse_y}})"
            ))

        bus.subscribe(ExecutionStartedEvent, _on_exec_started)
        bus.publish(ExecutionStartedEvent(graph_id="g1", node_count=1))

        assert captured == ["开始执行，鼠标: (960, 540)"]


# ---- 8. 作用域隔离与事件 ----


class TestScopeIsolationWithEvents:
    """作用域隔离 + EventBus 变更事件。"""

    def test_same_name_different_scopes(self, pool, bus, bridge, collected_events):
        pool.declare("val", VariableType.INT, VariableScope.GLOBAL, initial_value=1)
        pool.declare("val", VariableType.INT, VariableScope.NODE, initial_value=10)
        pool.set("val", 100, VariableScope.GLOBAL)
        pool.set("val", 200, VariableScope.NODE)

        assert pool.get("val") == 200
        assert pool.get("val", VariableScope.GLOBAL) == 100

        assert len(collected_events) == 2

    def test_pop_scope_does_not_publish_events(self, pool, bus, bridge, collected_events):
        pool.push_scope(VariableScope.NODE)
        pool.declare("temp", VariableType.INT, VariableScope.NODE, initial_value=5)
        pool.set("temp", 10, VariableScope.NODE)
        assert len(collected_events) == 1

        pool.pop_scope(VariableScope.NODE)
        assert len(collected_events) == 1

    def test_from_snapshot_does_not_publish_events(self, pool, bus, bridge, collected_events):
        pool.declare("a", VariableType.INT, initial_value=0)

        snap = {"global": {"a": 99}, "node": {}, "step": {}}
        pool.from_snapshot(snap)

        assert pool.get("a") == 99
        assert len(collected_events) == 0  # from_snapshot bypasses set(), no events


# ---- 9. 线程安全集成 ----


class TestThreadSafetyIntegration:
    """多线程并发修改变量 + 发布事件。"""

    def test_concurrent_increments(self, pool, bus, bridge):
        n_threads = 5
        n_increments = 20
        barrier = threading.Barrier(n_threads)

        def _worker():
            barrier.wait()
            for _ in range(n_increments):
                increment_counter(pool, "shared")

        threads = [threading.Thread(target=_worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final = get_counter(pool, "shared")
        assert final == n_threads * n_increments

    def test_concurrent_events_and_reads(self, pool, bus, bridge):
        pool.declare("x", VariableType.INT, initial_value=0)
        errors: list[Exception] = []

        def _writer():
            try:
                for i in range(50):
                    pool.set("x", i)
            except Exception as e:
                errors.append(e)

        def _reader():
            try:
                for _ in range(50):
                    pool.get("x")
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_writer),
            threading.Thread(target=_reader),
            threading.Thread(target=_reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors


# ---- 10. 错误场景集成 ----


class TestErrorScenarios:
    """错误场景下两个模块的协作。"""

    def test_failed_node_does_not_corrupt_pool(self, pool, bus):
        pool.declare("result", VariableType.STR, initial_value="pending")

        def _on_failed(event: NodeFailedEvent):
            pool.set("result", f"failed:{event.node_id}")

        bus.subscribe(NodeFailedEvent, _on_failed)

        bus.publish(NodeFailedEvent(
            node_id="n1",
            node_type="click_image",
            error=RuntimeError("template not found"),
            error_config="RETRY",
            retry_count=3,
        ))

        assert pool.get("result") == "failed:n1"

    def test_error_in_subscriber_does_not_block_others(self, pool, bus):
        second_called = False

        def _bad_handler(event: NodeCompletedEvent):
            raise ValueError("boom")

        def _good_handler(event: NodeCompletedEvent):
            nonlocal second_called
            second_called = True

        bus.subscribe(NodeCompletedEvent, _bad_handler)
        bus.subscribe(NodeCompletedEvent, _good_handler)

        bus.publish(NodeCompletedEvent(
            node_id="n1", node_type="wait", success=True, elapsed_ms=1.0,
        ))

        assert second_called
