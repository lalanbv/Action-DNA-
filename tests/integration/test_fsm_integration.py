"""FSM 集成测试 — 高频事件注入 + 延迟事件 + 多线程安全。

验收标准: FSM 不卡死。
测试场景:
- 大量事件快速注入
- 高频延迟事件处理
- 级联转换在高频下的稳定性
- 优先级竞争在并发下的一致性
- 全局中断在高频下的正确性
- 重置操作的原子性
"""

from __future__ import annotations

import threading
import time

import pytest

from src.core.engine.fsm_engine import (
    FSMEngine,
    GlobalTransition,
    Transition,
)


# ---- 辅助 ----


def make_linear_fsm(n: int) -> FSMEngine:
    """创建 n 个状态的线性 FSM: S0 → S1 → ... → Sn-1。"""
    transitions = [
        Transition(f"S{i}", f"S{i+1}", "next")
        for i in range(n - 1)
    ]
    return FSMEngine(transitions=transitions, initial_state="S0")


def make_cyclic_fsm() -> FSMEngine:
    """创建循环 FSM: A → B → C → A。"""
    return FSMEngine(
        transitions=[
            Transition("A", "B", "tick"),
            Transition("B", "C", "tick"),
            Transition("C", "A", "tick"),
        ],
        initial_state="A",
    )


# ---- 高频事件注入 ----


class TestHighFrequencyInjection:
    """快速注入大量事件，验证 FSM 不卡死、不崩溃。"""

    def test_rapid_injection_1000_transitions(self) -> None:
        """快速注入 1000 次有效转换（循环 FSM）。"""
        engine = make_cyclic_fsm()
        for _ in range(1000):
            result = engine.inject("tick")
            assert result is not None

        assert engine.transition_count == 1000

    def test_rapid_injection_mixed_events(self) -> None:
        """混合有效和无效事件。"""
        engine = make_cyclic_fsm()
        valid = 0
        for i in range(1000):
            result = engine.inject("tick" if i % 2 == 0 else "invalid")
            if result is not None:
                valid += 1

        assert engine.transition_count == valid

    def test_rapid_injection_with_no_match(self) -> None:
        """全部无效事件不应改变状态。"""
        engine = make_linear_fsm(5)
        for _ in range(10000):
            engine.inject("no_match")

        assert engine.current_state == "S0"
        assert engine.transition_count == 0

    def test_cyclic_fsm_high_frequency(self) -> None:
        """循环 FSM 在高频注入下状态正确循环。"""
        engine = make_cyclic_fsm()
        for i in range(3000):
            result = engine.inject("tick")
            assert result is not None

        expected_states = ["A", "B", "C"]
        assert engine.current_state == "A"
        assert engine.transition_count == 3000

    def test_injection_timing_under_load(self) -> None:
        """10000 次注入应在合理时间内完成（< 1s）。"""
        engine = make_cyclic_fsm()
        start = time.perf_counter()
        for _ in range(10000):
            engine.inject("tick")
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"10000 次注入耗时 {elapsed:.3f}s"


# ---- 高频延迟事件 ----


class TestHighFrequencyDelayedEvents:
    """大量延迟事件的处理性能和正确性。"""

    def test_many_immediate_delayed_events(self) -> None:
        """调度超过上限的延迟事件，验证容量限制。"""
        transitions = [
            Transition("A", "B", "ev"),
            Transition("B", "A", "ev"),
        ]
        engine = FSMEngine(transitions=transitions, initial_state="A")

        for _ in range(1000):
            engine.schedule_delayed("ev", delay_seconds=0.0)

        assert engine.pending_delayed_count == FSMEngine._MAX_DELAYED_EVENTS
        triggered = engine.process_delayed()

        assert len(triggered) == FSMEngine._MAX_DELAYED_EVENTS
        assert engine.pending_delayed_count == 0

    def test_delayed_event_schedule_and_cancel(self) -> None:
        """调度并取消延迟事件。"""
        engine = FSMEngine(initial_state="IDLE")
        for i in range(50):
            engine.schedule_delayed(f"ev_{i}", delay_seconds=1.0)

        assert engine.pending_delayed_count == 50
        cancelled = engine.cancel_delayed()
        assert cancelled == 50
        assert engine.pending_delayed_count == 0

    def test_mixed_ready_and_not_ready(self) -> None:
        """混合已到期和未到期的延迟事件。"""
        transitions = [
            Transition("A", "B", "ready"),
            Transition("B", "A", "ready"),
        ]
        engine = FSMEngine(transitions=transitions, initial_state="A")

        engine.schedule_delayed("ready", delay_seconds=0.0)
        engine.schedule_delayed("ready", delay_seconds=100.0)
        engine.schedule_delayed("ready", delay_seconds=0.0)
        engine.schedule_delayed("ready", delay_seconds=100.0)

        triggered = engine.process_delayed()
        assert len(triggered) == 2
        assert engine.pending_delayed_count == 2


# ---- 多线程安全 ----


class TestThreadSafety:
    """多线程并发注入事件。"""

    def test_concurrent_injections_no_crash(self) -> None:
        """多线程并发注入不应崩溃。"""
        engine = make_cyclic_fsm()
        errors: list[Exception] = []

        def inject_many():
            try:
                for _ in range(1000):
                    engine.inject("tick")
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=inject_many) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        assert not errors, f"线程异常: {errors}"
        assert engine.transition_count > 0

    def test_concurrent_schedule_and_process(self) -> None:
        """并发调度和处理延迟事件。"""
        transitions = [
            Transition("A", "B", "ev"),
            Transition("B", "A", "ev"),
        ]
        engine = FSMEngine(transitions=transitions, initial_state="A")
        errors: list[Exception] = []

        def scheduler():
            try:
                for _ in range(500):
                    engine.schedule_delayed("ev", delay_seconds=0.0)
            except Exception as e:
                errors.append(e)

        def processor():
            try:
                for _ in range(100):
                    engine.process_delayed()
                    time.sleep(0.001)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=scheduler)
        t2 = threading.Thread(target=processor)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        assert not errors, f"线程异常: {errors}"

    def test_concurrent_reset_during_injection(self) -> None:
        """并发重置和注入不应死锁。"""
        engine = make_cyclic_fsm()
        errors: list[Exception] = []
        stop_flag = threading.Event()

        def injector():
            try:
                while not stop_flag.is_set():
                    engine.inject("tick")
            except Exception as e:
                errors.append(e)

        def resetter():
            try:
                for _ in range(50):
                    engine.reset("A")
                    time.sleep(0.001)
                stop_flag.set()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=injector)
        t2 = threading.Thread(target=resetter)
        t1.start()
        t2.start()
        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        assert not errors, f"线程异常: {errors}"


# ---- 全局中断高频场景 ----


class TestGlobalInterruptUnderLoad:
    """全局转换在高频事件下的中断正确性。"""

    def test_global_interrupts_all_events(self) -> None:
        """全局中断应拦截所有匹配事件，无论当前状态。"""
        transitions = [
            Transition("IDLE", "RUNNING", "start"),
        ]
        global_t = GlobalTransition("interrupt", "HANDLER", priority=100)

        engine = FSMEngine(
            transitions=transitions,
            global_transitions=[global_t],
            initial_state="IDLE",
        )

        engine.inject("start")
        assert engine.current_state == "RUNNING"

        assert engine.inject("interrupt") == "HANDLER"
        assert engine.current_state == "HANDLER"

        engine.force_state("IDLE")
        engine.inject("start")
        assert engine.inject("interrupt") == "HANDLER"

    def test_high_priority_global_wins(self) -> None:
        """多个全局转换中高优先级胜出。"""
        gts = [
            GlobalTransition("ev", "LOW", priority=1),
            GlobalTransition("ev", "MID", priority=5),
            GlobalTransition("ev", "HIGH", priority=10),
        ]
        engine = FSMEngine(global_transitions=gts, initial_state="A")

        for _ in range(100):
            assert engine.inject("ev") == "HIGH"


# ---- 级联转换高频 ----


class TestCascadeUnderLoad:
    """级联转换在高频下的稳定性。"""

    def test_cascade_chain_completes(self) -> None:
        """长级联链（A→B→...→J）在每次 evaluate 后完整到达终点。"""
        states = [chr(ord("A") + i) for i in range(10)]
        transitions = [
            Transition(states[i], states[i + 1], "go")
            for i in range(len(states) - 1)
        ]
        engine = FSMEngine(transitions=transitions, initial_state="A")

        result = engine.evaluate("go")
        assert result == "J"

    def test_cascade_with_interrupt(self) -> None:
        """级联被全局中断截断。"""
        transitions = [
            Transition("A", "B", "go"),
            Transition("B", "C", "go"),
            Transition("C", "D", "go"),
        ]
        gt = GlobalTransition("go", "INTERCEPTED", priority=100)
        engine = FSMEngine(
            transitions=transitions,
            global_transitions=[gt],
            initial_state="A",
        )

        for _ in range(100):
            engine.force_state("A")
            result = engine.evaluate("go")
            assert result == "INTERCEPTED"
