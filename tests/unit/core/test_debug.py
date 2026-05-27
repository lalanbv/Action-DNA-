"""BreakpointManager 和 Debugger 单元测试。"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

from src.core.debug.breakpoint_manager import (
    Breakpoint,
    BreakpointManager,
    BreakpointType,
)
from src.core.debug.debugger import (
    DebugAction,
    Debugger,
    DebuggerState,
    VariableSnapshot,
)


# ---- BreakpointManager ----


class TestBreakpointManagerAdd:
    def test_add_line_breakpoint(self) -> None:
        mgr = BreakpointManager()
        bp = mgr.add_breakpoint("node_1")
        assert bp.node_id == "node_1"
        assert bp.bp_type == BreakpointType.LINE
        assert bp.enabled is True

    def test_add_conditional_breakpoint(self) -> None:
        mgr = BreakpointManager()
        bp = mgr.add_breakpoint(
            "node_1",
            bp_type=BreakpointType.CONDITIONAL,
            condition="hp < 50",
        )
        assert bp.bp_type == BreakpointType.CONDITIONAL
        assert bp.condition == "hp < 50"

    def test_add_log_breakpoint(self) -> None:
        mgr = BreakpointManager()
        bp = mgr.add_breakpoint(
            "node_1",
            bp_type=BreakpointType.LOG,
            log_message="passed node_1",
        )
        assert bp.bp_type == BreakpointType.LOG
        assert bp.log_message == "passed node_1"

    def test_add_replaces_existing(self) -> None:
        mgr = BreakpointManager()
        mgr.add_breakpoint("node_1")
        mgr.add_breakpoint("node_1", bp_type=BreakpointType.LOG)
        assert len(mgr.get_all()) == 1
        assert mgr.get_breakpoint("node_1").bp_type == BreakpointType.LOG


class TestBreakpointManagerRemove:
    def test_remove_existing(self) -> None:
        mgr = BreakpointManager()
        mgr.add_breakpoint("node_1")
        mgr.remove_breakpoint("node_1")
        assert mgr.get_breakpoint("node_1") is None

    def test_remove_nonexistent_no_error(self) -> None:
        mgr = BreakpointManager()
        mgr.remove_breakpoint("nonexistent")


class TestBreakpointManagerToggle:
    def test_toggle_adds(self) -> None:
        mgr = BreakpointManager()
        result = mgr.toggle_breakpoint("node_1")
        assert result is True
        assert mgr.has_breakpoint("node_1")

    def test_toggle_removes(self) -> None:
        mgr = BreakpointManager()
        mgr.toggle_breakpoint("node_1")
        result = mgr.toggle_breakpoint("node_1")
        assert result is False
        assert not mgr.has_breakpoint("node_1")


class TestBreakpointManagerHas:
    def test_has_enabled(self) -> None:
        mgr = BreakpointManager()
        mgr.add_breakpoint("node_1")
        assert mgr.has_breakpoint("node_1") is True

    def test_not_has_disabled(self) -> None:
        mgr = BreakpointManager()
        bp = mgr.add_breakpoint("node_1")
        bp.enabled = False
        assert mgr.has_breakpoint("node_1") is False

    def test_not_has_missing(self) -> None:
        mgr = BreakpointManager()
        assert mgr.has_breakpoint("node_1") is False


class TestBreakpointManagerGetAll:
    def test_returns_all(self) -> None:
        mgr = BreakpointManager()
        mgr.add_breakpoint("node_1")
        mgr.add_breakpoint("node_2")
        all_bps = mgr.get_all()
        assert len(all_bps) == 2

    def test_clear_all(self) -> None:
        mgr = BreakpointManager()
        mgr.add_breakpoint("node_1")
        mgr.add_breakpoint("node_2")
        mgr.clear_all()
        assert mgr.get_all() == []


# ---- Debugger ----


class TestDebuggerState:
    def test_initial_state_is_idle(self) -> None:
        dbg = Debugger()
        assert dbg.state == DebuggerState.IDLE

    def test_start_transitions_to_running(self) -> None:
        dbg = Debugger()
        dbg.start()
        assert dbg.state == DebuggerState.RUNNING

    def test_stop_transitions_to_idle(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.stop()
        assert dbg.state == DebuggerState.IDLE


class TestDebuggerBreakpoints:
    def test_breakpoints_property(self) -> None:
        dbg = Debugger()
        assert isinstance(dbg.breakpoints, BreakpointManager)

    def test_add_breakpoint_via_debugger(self) -> None:
        dbg = Debugger()
        dbg.breakpoints.add_breakpoint("node_1")
        assert dbg.breakpoints.has_breakpoint("node_1")


class TestDebuggerCallbacks:
    def test_state_change_callback(self) -> None:
        dbg = Debugger()
        cb = MagicMock()
        dbg.on_state_change(cb)
        dbg.start()
        cb.assert_called_once_with(DebuggerState.IDLE, DebuggerState.RUNNING)

    def test_breakpoint_hit_callback(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint("node_1")
        cb = MagicMock()
        dbg.on_breakpoint_hit(cb)

        def resume_after_delay():
            import time
            time.sleep(0.01)
            dbg.resume()

        t = threading.Thread(target=resume_after_delay, daemon=True)
        t.start()
        dbg.check_breakpoint("node_1")
        t.join(timeout=2)
        cb.assert_called_once_with("node_1")


class TestDebuggerCheckBreakpoint:
    def test_no_breakpoint_returns_none(self) -> None:
        dbg = Debugger()
        dbg.start()
        result = dbg.check_breakpoint("node_1")
        assert result is None

    def test_line_breakpoint_hits(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint("node_1")

        def resume_after_delay():
            import time
            time.sleep(0.01)
            dbg.resume()

        t = threading.Thread(target=resume_after_delay, daemon=True)
        t.start()
        action = dbg.check_breakpoint("node_1")
        t.join(timeout=2)
        assert action == DebugAction.CONTINUE

    def test_log_breakpoint_does_not_pause(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint(
            "node_1",
            bp_type=BreakpointType.LOG,
            log_message="test",
        )
        action = dbg.check_breakpoint("node_1")
        assert action is None
        assert dbg.state == DebuggerState.RUNNING

    def test_disabled_breakpoint_skipped(self) -> None:
        dbg = Debugger()
        dbg.start()
        bp = dbg.breakpoints.add_breakpoint("node_1")
        bp.enabled = False
        action = dbg.check_breakpoint("node_1")
        assert action is None

    def test_stepping_mode_pauses_on_any_node(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.step_over()

        def resume_after_delay():
            import time
            time.sleep(0.01)
            dbg.step_over()

        t = threading.Thread(target=resume_after_delay, daemon=True)
        t.start()
        action = dbg.check_breakpoint("node_no_bp")
        t.join(timeout=2)
        assert action == DebugAction.STEP_OVER

    def test_hit_count_increments(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint("node_1")

        for _ in range(3):
            def resume_after_delay():
                import time
                time.sleep(0.01)
                dbg.resume()

            t = threading.Thread(target=resume_after_delay, daemon=True)
            t.start()
            dbg.check_breakpoint("node_1")
            t.join(timeout=2)

        bp = dbg.breakpoints.get_breakpoint("node_1")
        assert bp.hit_count == 3


class TestDebuggerResumeActions:
    def test_step_over_action(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint("node_1")

        def step_over_delayed():
            import time
            time.sleep(0.01)
            dbg.step_over()

        t = threading.Thread(target=step_over_delayed, daemon=True)
        t.start()
        action = dbg.check_breakpoint("node_1")
        t.join(timeout=2)
        assert action == DebugAction.STEP_OVER

    def test_stop_action(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint("node_1")

        def stop_delayed():
            import time
            time.sleep(0.01)
            dbg.stop()

        t = threading.Thread(target=stop_delayed, daemon=True)
        t.start()
        action = dbg.check_breakpoint("node_1")
        t.join(timeout=2)
        assert action == DebugAction.STOP


class TestDebuggerVariables:
    def test_current_variables_empty_initially(self) -> None:
        dbg = Debugger()
        assert dbg.current_variables == []

    def test_current_node_id_none_initially(self) -> None:
        dbg = Debugger()
        assert dbg.current_node_id is None

    def test_call_stack_empty_initially(self) -> None:
        dbg = Debugger()
        assert dbg.call_stack == []

    def test_current_node_id_set_after_hit(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint("node_1")

        def resume_after_delay():
            import time
            time.sleep(0.01)
            dbg.resume()

        t = threading.Thread(target=resume_after_delay, daemon=True)
        t.start()
        dbg.check_breakpoint("node_1")
        t.join(timeout=2)
        assert dbg.current_node_id == "node_1"


class TestDebuggerEvaluateCondition:
    def test_condition_true(self) -> None:
        dbg = Debugger()
        ctx = MagicMock()
        ctx.flatten_variables = MagicMock(return_value={"hp": 30})
        dbg.start()
        dbg.breakpoints.add_breakpoint(
            "node_1",
            bp_type=BreakpointType.CONDITIONAL,
            condition="hp < 50",
        )

        def resume_after_delay():
            import time
            time.sleep(0.01)
            dbg.resume()

        t = threading.Thread(target=resume_after_delay, daemon=True)
        t.start()
        action = dbg.check_breakpoint("node_1", ctx)
        t.join(timeout=2)
        assert action == DebugAction.CONTINUE

    def test_condition_false_skips(self) -> None:
        dbg = Debugger()
        ctx = MagicMock()
        ctx.flatten_variables = MagicMock(return_value={"hp": 80})
        dbg.start()
        dbg.breakpoints.add_breakpoint(
            "node_1",
            bp_type=BreakpointType.CONDITIONAL,
            condition="hp < 50",
        )
        action = dbg.check_breakpoint("node_1", ctx)
        assert action is None

    def test_invalid_condition_skips(self) -> None:
        dbg = Debugger()
        dbg.start()
        dbg.breakpoints.add_breakpoint(
            "node_1",
            bp_type=BreakpointType.CONDITIONAL,
            condition="import os",
        )
        action = dbg.check_breakpoint("node_1")
        assert action is None


class TestDebuggerSnapshot:
    def test_snapshot_captures_variables(self) -> None:
        dbg = Debugger()
        ctx = MagicMock()
        ctx.flatten_variables = MagicMock(return_value={"hp": 100, "mp": 50})
        dbg.start()
        dbg.breakpoints.add_breakpoint("node_1")

        def resume_after_delay():
            import time
            time.sleep(0.01)
            dbg.resume()

        t = threading.Thread(target=resume_after_delay, daemon=True)
        t.start()
        dbg.check_breakpoint("node_1", ctx)
        t.join(timeout=2)

        vars_list = dbg.current_variables
        names = {v.name for v in vars_list}
        assert "hp" in names
        assert "mp" in names
