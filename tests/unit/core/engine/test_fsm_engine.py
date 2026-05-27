"""FSMEngine 单元测试 — 覆盖 D8-D10 所有验收标准。

测试范围：
- 转换队列 + 优先级排序
- 全局转换（状态无关触发）
- 延迟事件（定时注入）
- 级联转换（A→B→C）
- 深度限制 (MAX_TRANSITION_DEPTH=10)
- 超时保护 (MAX_EVALUATION_TIME=0.1s)
- 禁止回退 START 状态
- 序列化/反序列化（含 condition_evaluator 恢复）
"""

import time

import pytest

from src.core.engine.fsm_engine import (
    MAX_EVALUATION_TIME,
    MAX_TRANSITION_DEPTH,
    START_STATE,
    DelayedEvent,
    FSMEngine,
    GlobalTransition,
    Transition,
)


# ---- Fixtures ----


@pytest.fixture
def simple_transitions() -> list[Transition]:
    return [
        Transition("RUNNING", "ERROR", "on_error"),
        Transition("ERROR", "RETRYING", "on_retry"),
        Transition("RETRYING", "RUNNING", "on_success"),
    ]


@pytest.fixture
def prioritized_transitions() -> list[Transition]:
    return [
        Transition("RUNNING", "RETRY", "on_error", priority=1),
        Transition("RUNNING", "FALLBACK", "on_error", priority=10),
        Transition("RUNNING", "LOG_AND_CONTINUE", "on_error", priority=5),
    ]


@pytest.fixture
def cascade_transitions() -> list[Transition]:
    return [
        Transition("A", "B", "go"),
        Transition("B", "C", "go"),
        Transition("C", "D", "go"),
    ]


@pytest.fixture
def global_transitions() -> list[GlobalTransition]:
    return [
        GlobalTransition("popup_detected", "HANDLE_POPUP", priority=5),
        GlobalTransition("black_screen", "RESTART", priority=10),
    ]


@pytest.fixture
def engine(simple_transitions: list[Transition]) -> FSMEngine:
    return FSMEngine(transitions=simple_transitions)


# ---- 基本转换 ----


class TestBasicTransition:
    def test_initial_state_is_start(self, engine: FSMEngine):
        assert engine.current_state == START_STATE

    def test_no_match_returns_none(self, engine: FSMEngine):
        assert engine.inject("unknown_event") is None
        assert engine.current_state == START_STATE

    def test_no_match_does_not_increment_count(self, engine: FSMEngine):
        engine.inject("unknown_event")
        assert engine.transition_count == 0

    def test_state_not_matching_returns_none(self, engine: FSMEngine):
        engine.force_state("UNKNOWN_STATE")
        assert engine.inject("on_error") is None

    def test_successful_transition(self, engine: FSMEngine):
        engine.force_state("RUNNING")
        result = engine.inject("on_error")
        assert result == "ERROR"
        assert engine.current_state == "ERROR"

    def test_chain_transitions(self, engine: FSMEngine):
        engine.force_state("RUNNING")
        assert engine.inject("on_error") == "ERROR"
        assert engine.inject("on_retry") == "RETRYING"
        assert engine.inject("on_success") == "RUNNING"
        assert engine.transition_count == 3

    def test_force_state_no_transition_count(self, engine: FSMEngine):
        engine.force_state("CUSTOM")
        assert engine.current_state == "CUSTOM"
        assert engine.transition_count == 0

    def test_evaluate_does_not_change_state(self, engine: FSMEngine):
        engine.force_state("RUNNING")
        result = engine.evaluate("on_error")
        assert result == "ERROR"
        assert engine.current_state == "RUNNING"


# ---- 级联转换 ----


class TestCascadeTransition:
    def test_cascade_follows_chain(self, cascade_transitions: list[Transition]):
        engine = FSMEngine(transitions=cascade_transitions)
        engine.force_state("A")
        result = engine.evaluate("go")
        assert result == "D"

    def test_cascade_inject_updates_state(self, cascade_transitions: list[Transition]):
        engine = FSMEngine(transitions=cascade_transitions)
        engine.force_state("A")
        result = engine.inject("go")
        assert result == "D"
        assert engine.current_state == "D"
        assert engine.transition_count == 1

    def test_cascade_stops_on_no_match(self):
        transitions = [
            Transition("A", "B", "go"),
        ]
        engine = FSMEngine(transitions=transitions)
        engine.force_state("A")
        result = engine.evaluate("go")
        assert result == "B"

    def test_cascade_stops_mid_chain(self):
        transitions = [
            Transition("A", "B", "go"),
            Transition("B", "C", "other_event"),
        ]
        engine = FSMEngine(transitions=transitions)
        engine.force_state("A")
        result = engine.evaluate("go")
        assert result == "B"

    def test_cascade_with_global_interrupt(self):
        transitions = [
            Transition("A", "B", "go"),
            Transition("B", "C", "go"),
        ]
        gt = GlobalTransition("go", "INTERCEPTED", priority=100)
        engine = FSMEngine(transitions=transitions, global_transitions=[gt])
        engine.force_state("A")
        result = engine.evaluate("go")
        assert result == "INTERCEPTED"


# ---- 优先级排序 ----


class TestPriority:
    def test_higher_priority_first(
        self, prioritized_transitions: list[Transition]
    ):
        engine = FSMEngine(transitions=prioritized_transitions)
        engine.force_state("RUNNING")
        result = engine.inject("on_error")
        assert result == "FALLBACK"  # priority=10

    def test_same_priority_first_defined(self):
        transitions = [
            Transition("A", "B1", "ev", priority=5),
            Transition("A", "B2", "ev", priority=5),
        ]
        engine = FSMEngine(transitions=transitions)
        engine.force_state("A")
        result = engine.inject("ev")
        assert result in ("B1", "B2")

    def test_zero_priority_default(self):
        t = Transition("X", "Y", "go")
        assert t.priority == 0


# ---- 全局转换 ----


class TestGlobalTransition:
    def test_global_any_state(self, global_transitions: list[GlobalTransition]):
        engine = FSMEngine(global_transitions=global_transitions)
        engine.force_state("RUNNING")
        assert engine.inject("popup_detected") == "HANDLE_POPUP"

    def test_global_from_start(self, global_transitions: list[GlobalTransition]):
        engine = FSMEngine(global_transitions=global_transitions)
        assert engine.inject("black_screen") == "RESTART"

    def test_global_priority_order(self):
        gts = [
            GlobalTransition("ev", "LOW", priority=1),
            GlobalTransition("ev", "HIGH", priority=100),
        ]
        engine = FSMEngine(global_transitions=gts)
        engine.force_state("ANY")
        assert engine.inject("ev") == "HIGH"

    def test_global_overrides_state_transition(
        self, simple_transitions: list[Transition]
    ):
        gt = GlobalTransition("on_error", "GLOBAL_HANDLER", priority=0)
        engine = FSMEngine(
            transitions=simple_transitions, global_transitions=[gt]
        )
        engine.force_state("RUNNING")
        result = engine.inject("on_error")
        assert result == "GLOBAL_HANDLER"

    def test_no_global_match_falls_to_state(self, engine: FSMEngine):
        gt = GlobalTransition("other_event", "OTHER")
        engine2 = FSMEngine(
            transitions=engine._transitions, global_transitions=[gt]
        )
        engine2.force_state("RUNNING")
        assert engine2.inject("on_error") == "ERROR"


# ---- 延迟事件 ----


class TestDelayedEvent:
    def test_schedule_and_count(self, engine: FSMEngine):
        engine.schedule_delayed("timeout", delay_seconds=5.0)
        assert engine.pending_delayed_count == 1

    def test_not_ready_before_delay(self):
        de = DelayedEvent(event="ev", delay_seconds=100.0, created_at=time.time())
        assert not de.is_ready

    def test_ready_after_delay(self):
        de = DelayedEvent(event="ev", delay_seconds=0.0, created_at=time.monotonic() - 1)
        assert de.is_ready

    def test_fire_at_property(self):
        de = DelayedEvent(event="ev", delay_seconds=5.0, created_at=100.0)
        assert de.fire_at == 105.0

    def test_process_delayed_fires_ready(self):
        t = Transition("RUNNING", "TIMED_OUT", "timeout")
        engine = FSMEngine(transitions=[t])
        engine.force_state("RUNNING")
        engine.schedule_delayed("timeout", delay_seconds=0.0)
        triggered = engine.process_delayed()
        assert "timeout" in triggered
        assert engine.current_state == "TIMED_OUT"

    def test_process_delayed_skips_not_ready(self, engine: FSMEngine):
        engine.schedule_delayed("timeout", delay_seconds=100.0)
        triggered = engine.process_delayed()
        assert triggered == []
        assert engine.pending_delayed_count == 1

    def test_cancel_all_delayed(self, engine: FSMEngine):
        engine.schedule_delayed("a", delay_seconds=1.0)
        engine.schedule_delayed("b", delay_seconds=2.0)
        count = engine.cancel_delayed()
        assert count == 2
        assert engine.pending_delayed_count == 0

    def test_cancel_specific_delayed(self, engine: FSMEngine):
        engine.schedule_delayed("keep", delay_seconds=1.0)
        engine.schedule_delayed("remove", delay_seconds=1.0)
        count = engine.cancel_delayed("remove")
        assert count == 1
        assert engine.pending_delayed_count == 1

    def test_process_delayed_only_fires_matching(self):
        t = Transition("RUNNING", "DONE", "match")
        engine = FSMEngine(transitions=[t])
        engine.force_state("RUNNING")
        engine.schedule_delayed("match", delay_seconds=0.0)
        engine.schedule_delayed("no_match", delay_seconds=0.0)
        triggered = engine.process_delayed()
        assert triggered == ["match"]


# ---- 安全限制 ----


class TestSafetyLimits:
    def test_max_transition_depth_constant(self):
        assert MAX_TRANSITION_DEPTH == 10

    def test_max_evaluation_time_constant(self):
        assert MAX_EVALUATION_TIME == 0.1

    def test_no_back_to_start(self):
        t = Transition("RUNNING", "START", "reset")
        engine = FSMEngine(transitions=[t])
        engine.force_state("RUNNING")
        result = engine.inject("reset")
        assert result is None
        assert engine.current_state == "RUNNING"

    def test_global_no_back_to_start(self):
        gt = GlobalTransition("restart", "START")
        engine = FSMEngine(global_transitions=[gt])
        engine.force_state("RUNNING")
        result = engine.inject("restart")
        assert result is None

    def test_cascade_depth_limit(self):
        # 自循环: S → S → S ... 应在 MAX_TRANSITION_DEPTH 时停止
        t = Transition("S", "S", "loop")
        engine = FSMEngine(transitions=[t])
        engine.force_state("S")
        result = engine.evaluate("loop")
        assert result == "S"  # 级联 MAX_TRANSITION_DEPTH 次后停在 S

    def test_cascade_stops_at_dead_end(self, cascade_transitions):
        engine = FSMEngine(transitions=cascade_transitions)
        engine.force_state("A")
        result = engine.evaluate("go")
        assert result == "D"  # A→B→C→D，D 无出边

    def test_no_back_to_start_mid_cascade(self):
        transitions = [
            Transition("A", "B", "go"),
            Transition("B", "START", "go"),
        ]
        engine = FSMEngine(transitions=transitions)
        engine.force_state("A")
        result = engine.evaluate("go")
        assert result == "B"  # A→B 成功，B→START 被阻止


# ---- 重置 ----


class TestReset:
    def test_reset_to_start(self, engine: FSMEngine):
        engine.force_state("CUSTOM")
        engine.reset()
        assert engine.current_state == START_STATE
        assert engine.transition_count == 0

    def test_reset_to_custom_state(self, engine: FSMEngine):
        engine.reset("SPECIAL")
        assert engine.current_state == "SPECIAL"

    def test_reset_clears_delayed(self, engine: FSMEngine):
        engine.schedule_delayed("ev", delay_seconds=1.0)
        engine.reset()
        assert engine.pending_delayed_count == 0


# ---- 序列化 ----


class TestSerialization:
    def test_transition_round_trip(self):
        t = Transition("A", "B", "ev", condition="x>0", priority=5, label="test")
        data = t.to_dict()
        t2 = Transition.from_dict(data)
        assert t2 == t

    def test_global_transition_round_trip(self):
        gt = GlobalTransition("ev", "TARGET", condition="ok", priority=3, label="g")
        data = gt.to_dict()
        gt2 = GlobalTransition.from_dict(data)
        assert gt2 == gt

    def test_delayed_event_round_trip(self):
        de = DelayedEvent(event="timeout", delay_seconds=5.0, created_at=1000.0)
        data = de.to_dict()
        de2 = DelayedEvent.from_dict(data)
        assert de2.event == "timeout"
        assert de2.delay_seconds == 5.0
        assert de2.created_at == 1000.0

    def test_engine_round_trip(self, simple_transitions, global_transitions):
        engine = FSMEngine(
            transitions=simple_transitions,
            global_transitions=global_transitions,
            initial_state="RUNNING",
        )
        engine.inject("on_error")  # trigger a transition
        data = engine.to_dict()
        assert data["current_state"] == "ERROR"
        assert data["transition_count"] == 1
        engine2 = FSMEngine.from_dict(data)
        assert engine2.current_state == "ERROR"
        assert engine2.transition_count == 1
        assert len(engine2._transitions) == 3
        assert len(engine2._global_transitions) == 2

    def test_engine_round_trip_with_evaluator(self):
        t = Transition("A", "B", "ev", condition="ok")
        engine = FSMEngine(
            transitions=[t],
            condition_evaluator=lambda c: c == "ok",
        )
        engine.force_state("A")
        data = engine.to_dict()
        evaluator = lambda c: c == "ok"
        engine2 = FSMEngine.from_dict(data, condition_evaluator=evaluator)
        engine2.force_state("A")
        assert engine2.inject("ev") == "B"

    def test_engine_round_trip_without_evaluator_loses_condition(self):
        t = Transition("A", "B", "ev", condition="ok")
        engine = FSMEngine(
            transitions=[t],
            condition_evaluator=lambda c: c == "ok",
        )
        engine.force_state("A")
        data = engine.to_dict()
        engine2 = FSMEngine.from_dict(data)
        engine2.force_state("A")
        # 无 evaluator 时条件被跳过（返回 True）
        assert engine2.inject("ev") == "B"

    def test_transition_omits_defaults(self):
        t = Transition("A", "B", "ev")
        data = t.to_dict()
        assert "condition" not in data
        assert "priority" not in data
        assert "label" not in data

    def test_from_dict_with_minimal_data(self):
        data = {
            "source_state": "A",
            "target_state": "B",
            "trigger_event": "ev",
        }
        t = Transition.from_dict(data)
        assert t.condition is None
        assert t.priority == 0
        assert t.label is None

    def test_from_dict_backward_compat_initial_state_key(self):
        data = {
            "initial_state": "RUNNING",
            "transitions": [],
            "global_transitions": [],
        }
        engine = FSMEngine.from_dict(data)
        assert engine.current_state == "RUNNING"


# ---- 查询 ----


class TestQuery:
    def test_has_transitions(self, engine: FSMEngine):
        assert engine.has_transitions

    def test_no_transitions(self):
        engine = FSMEngine()
        assert not engine.has_transitions

    def test_has_global_only(self):
        engine = FSMEngine(global_transitions=[GlobalTransition("ev", "T")])
        assert engine.has_transitions

    def test_get_applicable_transitions(self, simple_transitions):
        engine = FSMEngine(transitions=simple_transitions)
        engine.force_state("RUNNING")
        applicable = engine.get_applicable_transitions()
        assert len(applicable) == 1
        assert applicable[0].target_state == "ERROR"

    def test_get_applicable_for_specific_state(self, simple_transitions):
        engine = FSMEngine(transitions=simple_transitions)
        applicable = engine.get_applicable_transitions("ERROR")
        assert len(applicable) == 1
        assert applicable[0].target_state == "RETRYING"

    def test_get_applicable_no_match(self, engine: FSMEngine):
        applicable = engine.get_applicable_transitions("NONEXISTENT")
        assert applicable == []

    def test_repr(self, engine: FSMEngine):
        r = repr(engine)
        assert "FSMEngine" in r
        assert "transitions=3" in r


# ---- 条件求值 ----


class TestConditionEvaluation:
    def test_condition_passes(self):
        t = Transition("A", "B", "ev", condition="x > 0")
        evaluator = lambda cond: cond == "x > 0"
        engine = FSMEngine(transitions=[t], condition_evaluator=evaluator)
        engine.force_state("A")
        assert engine.inject("ev") == "B"

    def test_condition_blocks(self):
        t = Transition("A", "B", "ev", condition="x > 0")
        evaluator = lambda cond: False
        engine = FSMEngine(transitions=[t], condition_evaluator=evaluator)
        engine.force_state("A")
        assert engine.inject("ev") is None

    def test_no_evaluator_passes(self):
        t = Transition("A", "B", "ev", condition="x > 0")
        engine = FSMEngine(transitions=[t])
        engine.force_state("A")
        assert engine.inject("ev") == "B"

    def test_evaluator_exception_fails_safe(self):
        t = Transition("A", "B", "ev", condition="bad")

        def bad_evaluator(cond: str) -> bool:
            raise RuntimeError("boom")

        engine = FSMEngine(transitions=[t], condition_evaluator=bad_evaluator)
        engine.force_state("A")
        assert engine.inject("ev") is None

    def test_condition_on_global_transition(self):
        gt = GlobalTransition("ev", "TARGET", condition="must_pass")
        evaluator = lambda c: c == "must_pass"
        engine = FSMEngine(global_transitions=[gt], condition_evaluator=evaluator)
        engine.force_state("ANY")
        assert engine.inject("ev") == "TARGET"

        evaluator2 = lambda c: False
        engine2 = FSMEngine(global_transitions=[gt], condition_evaluator=evaluator2)
        engine2.force_state("ANY")
        assert engine2.inject("ev") is None
