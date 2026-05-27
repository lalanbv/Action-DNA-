"""ActionExecutor Facade 单元测试 — 验证委托给 GraphEngine 的行为。"""

from __future__ import annotations

import threading
from typing import Any
from unittest.mock import MagicMock, patch

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.action_executor import ActionExecutor
from src.core.engine.execution_context import ExecutionContext
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType, chain_to_flow


def _make_graph() -> FlowGraph:
    """创建 START → END 线性图。"""
    g = FlowGraph(name="test")
    g.add_node(FlowNode(node_id="start", node_type=NodeType.START))
    g.add_node(FlowNode(node_id="end", node_type=NodeType.END))
    g.start_node_id = "start"
    g.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))
    return g


def _make_executor() -> ActionExecutor:
    """创建 mock 依赖的 ActionExecutor。"""
    capture = MagicMock()
    matcher = MagicMock()
    input_ctrl = MagicMock()
    return ActionExecutor(capture, matcher, input_ctrl)


class TestFacadeInit:
    """验证 Facade 初始化。"""

    def test_creates_graph_engine(self) -> None:
        ex = _make_executor()
        assert ex._graph_engine is not None

    def test_creates_layers(self) -> None:
        ex = _make_executor()
        assert ex._pause_layer is not None
        assert ex._event_bridge is not None
        assert ex._debug_layer is not None

    def test_initial_state(self) -> None:
        ex = _make_executor()
        assert not ex.is_running
        assert not ex.is_paused
        assert ex.current_step_index == -1
        assert ex.loop_iteration == 0


class TestFacadeStart:
    """验证 start() 构建 ExecutionContext 并委托 GraphEngine。"""

    def test_start_with_flow_graph(self) -> None:
        ex = _make_executor()
        graph = _make_graph()

        with patch.object(threading, "Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            ex.start(graph)

        assert ex.is_running
        mock_thread.assert_called_once()
        call_kwargs = mock_thread.call_args
        assert call_kwargs[1]["daemon"] is True

    def test_start_with_converted_chain(self) -> None:
        ex = _make_executor()
        steps = [STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01)]
        graph = chain_to_flow("test", steps, loop=False)

        with patch.object(threading, "Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            ex.start(graph)

        assert ex.is_running

    def test_start_sets_stop_event_cleared(self) -> None:
        ex = _make_executor()
        ex._stop_event.set()

        with patch.object(threading, "Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            ex.start(_make_graph())

        assert not ex._stop_event.is_set()

    def test_start_increments_gen(self) -> None:
        ex = _make_executor()
        old_gen = ex._gen

        with patch.object(threading, "Thread") as mock_thread:
            mock_thread.return_value.start = MagicMock()
            ex.start(_make_graph())

        assert ex._gen == old_gen + 1


class TestFacadeControl:
    """验证 stop/pause/resume 行为。"""

    def test_stop_sets_stop_event(self) -> None:
        ex = _make_executor()
        ex._stop_event.clear()
        ex.stop()
        assert ex._stop_event.is_set()

    def test_stop_clears_running(self) -> None:
        ex = _make_executor()
        with ex._lock:
            ex._running = True
        ex.stop()
        assert not ex.is_running

    def test_pause_sets_pause_event(self) -> None:
        ex = _make_executor()
        ex.pause()
        assert ex.is_paused

    def test_resume_clears_pause_event(self) -> None:
        ex = _make_executor()
        ex.pause()
        assert ex.is_paused
        ex.resume()
        assert not ex.is_paused


class TestBuildContext:
    """验证 _build_context 构建正确的 ExecutionContext。"""

    def test_builds_immutable_context(self) -> None:
        ex = _make_executor()
        graph = _make_graph()
        ctx = ex._build_context(graph, gen=1)

        assert isinstance(ctx, ExecutionContext)
        assert ctx.gen == 1
        assert ctx.graph is graph
        assert ctx.capture is ex.capture
        assert ctx.matcher is ex.matcher
        assert ctx.input_ctrl is ex.input
        assert ctx.step_index == 0

    def test_context_contains_executor_in_extra(self) -> None:
        ex = _make_executor()
        graph = _make_graph()
        ctx = ex._build_context(graph, gen=1)

        assert ctx.extra.get("_executor") is ex

    def test_context_start_node(self) -> None:
        ex = _make_executor()
        graph = _make_graph()
        ctx = ex._build_context(graph, gen=1)

        assert ctx.current_node.node_type == NodeType.START


class TestRunWithEngine:
    """验证 _run_with_engine 外层循环。"""

    def test_single_pass_no_loop(self) -> None:
        """graph.loop=False 时只执行一轮。"""
        ex = _make_executor()
        graph = _make_graph()
        graph.loop = False

        run_count = 0
        original_run = ex._graph_engine.run

        def counting_run(g: FlowGraph, ctx: ExecutionContext) -> None:
            nonlocal run_count
            run_count += 1
            # 模拟正常执行完所有节点
            original_run(g, ctx)

        ex._graph_engine.run = counting_run
        ex._run_with_engine(graph, gen=ex._gen)

        assert run_count == 1

    def test_stops_on_stop_event(self) -> None:
        """stop_event 被设置时中断外层循环。"""
        ex = _make_executor()
        graph = _make_graph()
        graph.loop = True

        ex._stop_event.set()
        ex._run_with_engine(graph, gen=ex._gen)

        assert ex.loop_iteration == 0

    def test_stops_at_loop_count(self) -> None:
        """达到 loop_count 上限时停止。"""
        ex = _make_executor()
        graph = _make_graph()
        graph.loop = True
        graph.loop_count = 3

        call_count = 0

        def counting_run(g: FlowGraph, ctx: ExecutionContext) -> None:
            nonlocal call_count
            call_count += 1

        ex._graph_engine.run = counting_run
        ex._run_with_engine(graph, gen=ex._gen)

        assert call_count == 3


class TestEventEmission:
    """验证事件发射桥接。"""

    def test_emit_with_scheduler(self) -> None:
        events: list[str] = []
        scheduler_calls: list[tuple] = []

        def mock_schedule(delay: int, fn: Any) -> None:
            scheduler_calls.append((delay, fn))
            fn()

        ex = _make_executor()
        ex.set_main_scheduler(mock_schedule)

        bus = MagicMock()
        ex._event_bus = bus

        ex._emit("test.event", data=42)

        assert len(scheduler_calls) == 1
        bus.emit.assert_called_once_with("test.event", data=42)

    def test_emit_without_scheduler(self) -> None:
        bus = MagicMock()
        ex = _make_executor()
        ex._event_bus = bus

        ex._emit("test.event")

        bus.emit.assert_called_once_with("test.event")


class TestEnsureStopped:
    """验证线程安全停止。"""

    def test_waits_for_thread_exit(self) -> None:
        ex = _make_executor()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        ex._thread = mock_thread

        ex._ensure_stopped()

        mock_thread.join.assert_called_once_with(timeout=5.0)
        assert ex._thread is None

    def test_sets_stop_event_if_alive(self) -> None:
        ex = _make_executor()
        mock_thread = MagicMock()
        mock_thread.is_alive.return_value = True
        ex._thread = mock_thread

        ex._ensure_stopped()

        assert ex._stop_event.is_set()
        mock_thread.join.assert_called_once_with(timeout=5.0)


class TestAlive:
    """验证 _alive 代际检查。"""

    def test_alive_when_gen_matches_and_not_stopped(self) -> None:
        ex = _make_executor()
        ex._stop_event.clear()
        assert ex._alive(gen=ex._gen) is True

    def test_not_alive_when_stopped(self) -> None:
        ex = _make_executor()
        ex._stop_event.set()
        assert ex._alive(gen=ex._gen) is False

    def test_not_alive_when_gen_mismatch(self) -> None:
        ex = _make_executor()
        ex._stop_event.clear()
        assert ex._alive(gen=ex._gen + 1) is False
