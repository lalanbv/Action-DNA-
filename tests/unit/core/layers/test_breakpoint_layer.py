"""BreakpointLayer 单元测试。"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

from src.core.layers.breakpoint_layer import BreakpointLayer, StopExecution
from src.core.layers.layer import ErrorContext


def _make_ctx(**overrides) -> MagicMock:
    ctx = MagicMock()
    node = MagicMock()
    node.node_id = "node_1"
    ctx.current_node = node
    ctx.event_bus = None
    ctx.step_index = 1
    ctx.gen = 1

    for k, v in overrides.items():
        setattr(ctx, k, v)
    return ctx


def _make_stop_event_ctx() -> MagicMock:
    stop_event = threading.Event()
    ctx = _make_ctx()
    ctx.stop_event = stop_event
    return ctx, stop_event


class TestBreakpointLayer:
    def test_name(self) -> None:
        assert BreakpointLayer().name == "breakpoint"

    def test_priority(self) -> None:
        assert BreakpointLayer().priority == 50

    def test_debug_mode_valid(self) -> None:
        layer = BreakpointLayer()
        layer.debug_mode = "step_over"
        assert layer.debug_mode == "step_over"

    def test_debug_mode_invalid(self) -> None:
        layer = BreakpointLayer()
        try:
            layer.debug_mode = "invalid"
            assert False, "Should have raised ValueError"
        except ValueError:
            pass

    def test_graph_start_resets_hit_count(self) -> None:
        layer = BreakpointLayer()
        layer._hit_count["n1"] = 5
        layer._step_next = True
        layer.on_graph_start(_make_ctx())
        assert len(layer._hit_count) == 0
        assert layer._step_next is False

    def test_no_breakpoint_passes_through(self) -> None:
        layer = BreakpointLayer()
        ctx = _make_ctx()
        result = layer.on_node_enter(ctx)
        assert result is ctx

    def test_add_and_get_breakpoints(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("n1")
        layer.add_breakpoint("n2", condition="hit_count > 2", one_shot=True)
        bps = layer.get_breakpoints()
        assert set(bps) == {"n1", "n2"}

    def test_remove_breakpoint(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("n1")
        layer.remove_breakpoint("n1")
        assert layer.get_breakpoints() == []

    def test_clear_breakpoints(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("n1")
        layer.add_breakpoint("n2")
        layer.clear_breakpoints()
        assert layer.get_breakpoints() == []
        assert layer.get_hit_count("n1") == 0

    def test_breakpoint_hits_and_waits(self) -> None:
        layer = BreakpointLayer()
        layer._screenshot_on_hit = False
        layer.add_breakpoint("node_1")
        ctx = _make_ctx()

        def _resume():
            layer.resume("continue")

        timer = threading.Timer(0.1, _resume)
        timer.start()

        layer.on_node_enter(ctx)
        assert layer.get_hit_count("node_1") == 1
        timer.join()

    def test_one_shot_breakpoint_removed_after_hit(self) -> None:
        layer = BreakpointLayer()
        layer._screenshot_on_hit = False
        layer.add_breakpoint("node_1", one_shot=True)
        ctx = _make_ctx()

        def _resume():
            layer.resume("continue")

        timer = threading.Timer(0.1, _resume)
        timer.start()

        layer.on_node_enter(ctx)
        timer.join()
        assert "node_1" not in layer.get_breakpoints()

    def test_step_over_sets_step_next(self) -> None:
        layer = BreakpointLayer()
        layer.debug_mode = "step_over"
        ctx = _make_ctx()
        result = MagicMock()
        result.success = True
        layer.on_node_exit(ctx, result)
        assert layer._step_next is True

    def test_stop_mode_raises(self) -> None:
        layer = BreakpointLayer()
        layer._screenshot_on_hit = False
        layer.add_breakpoint("node_1")
        ctx = _make_ctx()

        def _stop():
            layer._debug_mode = "stop"
            layer._resume_event.set()

        timer = threading.Timer(0.1, _stop)
        timer.start()

        try:
            layer.on_node_enter(ctx)
            assert False, "Should have raised StopExecution"
        except StopExecution:
            pass
        timer.join()

    def test_on_node_error_returns_err_ctx(self) -> None:
        layer = BreakpointLayer()
        ctx = _make_ctx()
        err_ctx = ErrorContext(error=RuntimeError("fail"))
        ret = layer.on_node_error(ctx, err_ctx)
        assert ret is err_ctx

    def test_get_hit_count_default_zero(self) -> None:
        layer = BreakpointLayer()
        assert layer.get_hit_count("nonexistent") == 0

    def test_step_next_triggers_hit_and_wait(self) -> None:
        layer = BreakpointLayer()
        layer._screenshot_on_hit = False
        layer._step_next = True
        ctx = _make_ctx()

        def _resume():
            layer.resume("continue")

        timer = threading.Timer(0.1, _resume)
        timer.start()

        layer.on_node_enter(ctx)
        timer.join()
        assert layer._step_next is False

    def test_conditional_breakpoint_true(self) -> None:
        layer = BreakpointLayer()
        layer._screenshot_on_hit = False
        layer.add_breakpoint("node_1", condition="hit_count > 0")
        ctx = _make_ctx()

        def _resume():
            layer.resume("continue")

        timer = threading.Timer(0.1, _resume)
        timer.start()

        layer.on_node_enter(ctx)
        assert layer.get_hit_count("node_1") == 1
        timer.join()

    def test_conditional_breakpoint_false(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("node_1", condition="hit_count > 5")
        ctx = _make_ctx()
        result = layer.on_node_enter(ctx)
        assert result is ctx
        assert layer.get_hit_count("node_1") == 1

    def test_conditional_breakpoint_syntax_error(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("node_1", condition="if invalid syntax {{{")
        ctx = _make_ctx()
        result = layer.on_node_enter(ctx)
        assert result is ctx

    def test_conditional_breakpoint_disallowed_ast(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("node_1", condition="__import__('os').system('echo')")
        ctx = _make_ctx()
        result = layer.on_node_enter(ctx)
        assert result is ctx

    def test_conditional_breakpoint_eval_error(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("node_1", condition="undefined_var > 0")
        ctx = _make_ctx()
        result = layer.on_node_enter(ctx)
        assert result is ctx

    def test_conditional_breakpoint_with_step_index(self) -> None:
        layer = BreakpointLayer()
        layer.add_breakpoint("node_1", condition="step_index == 5")
        ctx = _make_ctx(step_index=1)
        result = layer.on_node_enter(ctx)
        assert result is ctx
        assert layer.get_hit_count("node_1") == 1

    def test_hit_and_wait_with_event_bus(self) -> None:
        layer = BreakpointLayer()
        layer._screenshot_on_hit = False
        bus = MagicMock()
        ctx = _make_ctx(event_bus=bus)
        layer.add_breakpoint("node_1")

        def _resume():
            layer.resume("continue")

        timer = threading.Timer(0.1, _resume)
        timer.start()

        layer.on_node_enter(ctx)
        bus.publish.assert_called_once()
        timer.join()

    def test_stop_event_triggers_stop_execution(self) -> None:
        layer = BreakpointLayer()
        layer._screenshot_on_hit = False
        ctx, stop_event = _make_stop_event_ctx()
        layer.add_breakpoint("node_1")

        def _stop():
            stop_event.set()

        timer = threading.Timer(0.6, _stop)
        timer.start()

        try:
            layer.on_node_enter(ctx)
            assert False, "Should have raised StopExecution"
        except StopExecution:
            pass
        timer.join()

    def test_save_debug_screenshot_handles_failure(self) -> None:
        layer = BreakpointLayer()
        ctx = _make_ctx()
        ctx.capture.grab.side_effect = RuntimeError("no capture")
        layer._save_debug_screenshot(ctx)

    def test_evaluate_condition_with_variables(self) -> None:
        layer = BreakpointLayer()
        ctx = _make_ctx()
        ctx.flatten_variables = MagicMock(return_value={"hp": 100})

        result = layer._evaluate_condition("hp > 50", ctx, 1)
        assert result is True
