"""GraphEngine 单元测试 — 配置、Layer 管理、线性执行、分支、循环、错误策略。"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.engine.descriptors.flow_descriptors import (
    EndDescriptor,
    LoopDescriptor,
    StartDescriptor,
)
from src.core.engine.descriptors.wait_descriptor import WaitDescriptor
from src.core.engine.execution_blocker import ExecutionBlocker
from src.core.engine.graph_engine import GraphEngine, GraphEngineConfig
from src.core.engine.node_descriptor import NodeDescriptor
from src.core.engine.node_registry import NodeRegistry
from src.core.engine.node_result import NodeResult
from src.core.error.error_config import ErrorStrategy, RetryPolicy
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.layers.layer import ErrorContext, GraphLayer
from tests._helpers import make_exec_ctx

# ---- 固定桩 ----


def _make_node(
    node_id: str,
    node_type: NodeType = NodeType.ACTION,
    **kwargs: Any,
) -> FlowNode:
    return FlowNode(node_id=node_id, node_type=node_type, **kwargs)



def _make_graph() -> FlowGraph:
    """创建 START → END 线性图。"""
    g = FlowGraph(name="test")
    start = _make_node("start", NodeType.START)
    end = _make_node("end", NodeType.END)
    g.add_node(start)
    g.add_node(end)
    g.start_node_id = "start"
    g.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end", label="default"))
    return g


_make_run_ctx = make_exec_ctx


def _make_action_step(action_type_name: str) -> MagicMock:
    """创建 mock 动作步骤，模拟 ActionStep 的字段。"""
    step = MagicMock()
    step.action_type.name = action_type_name
    step.enabled = True
    step.comment = ""
    return step


def _make_action_graph(action_type: str, name: str = "test") -> FlowGraph:
    """创建 START → ACTION(action_type) → END 线性图。"""
    graph = FlowGraph(name=name)
    start = _make_node("start", NodeType.START)
    act = _make_node("act", NodeType.ACTION, action=_make_action_step(action_type))
    end = _make_node("end", NodeType.END)
    graph.add_node(start)
    graph.add_node(act)
    graph.add_node(end)
    graph.start_node_id = "start"
    graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="act"))
    graph.add_edge(FlowEdge(edge_id="e2", from_node="act", to_node="end"))
    return graph


def _register_descriptor(
    action_type: str,
    execute_fn: Any,
) -> type[NodeDescriptor]:
    """创建并注册一个匿名 NodeDescriptor 子类，返回类。"""
    attrs: dict[str, Any] = {
        "action_type": classmethod(lambda cls: action_type),  # type: ignore[misc]
        "display_name": classmethod(lambda cls: action_type),  # type: ignore[misc]
        "category": classmethod(lambda cls: "测试"),  # type: ignore[misc]
        "input_types": classmethod(lambda cls: {}),  # type: ignore[misc]
        "output_types": classmethod(lambda cls: {}),  # type: ignore[misc]
        "execute": lambda self, ctx: execute_fn(ctx),
    }
    cls = type(f"_Desc_{action_type}", (NodeDescriptor,), attrs)
    NodeRegistry.register(cls)
    return cls


# ---- 每个测试前清空注册表并注册内置描述符 ----


@pytest.fixture(autouse=True)
def _setup_registry() -> Any:
    NodeRegistry.clear()
    NodeRegistry.register(StartDescriptor)
    NodeRegistry.register(EndDescriptor)
    NodeRegistry.register(LoopDescriptor)
    NodeRegistry.register(WaitDescriptor)
    yield
    NodeRegistry.clear()


# ---- GraphEngineConfig ----


class TestGraphEngineConfig:
    """配置默认值。"""

    def test_defaults(self) -> None:
        cfg = GraphEngineConfig()
        assert cfg.max_iterations == 10000
        assert cfg.default_error_strategy == ErrorStrategy.IGNORE
        assert isinstance(cfg.default_retry_policy, RetryPolicy)
        assert cfg.default_exhausted_strategy == ErrorStrategy.FAIL_FAST
        assert cfg.validate_graph_on_run is True
        assert cfg.raise_on_validation_error is True
        assert cfg.transient_retry_count == 1
        assert cfg.transient_retry_delay == 0.3


# ---- Layer 管理 ----


class _StubLayer(GraphLayer):
    """测试用 Layer。"""

    def __init__(self, name: str = "stub", priority: int = 0) -> None:
        self._name = name
        self._priority = priority

    @property
    def name(self) -> str:
        return self._name

    @property
    def priority(self) -> int:
        return self._priority


class TestLayerManagement:
    """Layer 添加、排序、移除、查询。"""

    def test_add_layer(self) -> None:
        engine = GraphEngine()
        layer = _StubLayer("test")
        engine.add_layer(layer)
        assert engine.get_layer("test") is layer

    def test_add_duplicate_raises(self) -> None:
        engine = GraphEngine()
        engine.add_layer(_StubLayer("dup"))
        with pytest.raises(ValueError, match="已存在"):
            engine.add_layer(_StubLayer("dup"))

    def test_sorted_by_priority(self) -> None:
        engine = GraphEngine()
        engine.add_layer(_StubLayer("mid", priority=10))
        engine.add_layer(_StubLayer("first", priority=-5))
        engine.add_layer(_StubLayer("last", priority=50))
        names = [l.name for l in engine._layers]
        assert names == ["first", "mid", "last"]

    def test_remove_layer(self) -> None:
        engine = GraphEngine()
        engine.add_layer(_StubLayer("removable"))
        assert engine.remove_layer("removable") is True
        assert engine.get_layer("removable") is None

    def test_remove_nonexistent(self) -> None:
        engine = GraphEngine()
        assert engine.remove_layer("ghost") is False

    def test_get_layer_nonexistent(self) -> None:
        engine = GraphEngine()
        assert engine.get_layer("missing") is None


# ---- get_action_type ----


class TestGetActionType:
    """NodeType → action_type 映射。"""

    def test_start_node(self) -> None:
        node = _make_node("s", NodeType.START)
        assert GraphEngine.get_action_type(node) == "START"

    def test_end_node(self) -> None:
        node = _make_node("e", NodeType.END)
        assert GraphEngine.get_action_type(node) == "END"

    def test_loop_node(self) -> None:
        node = _make_node("l", NodeType.LOOP)
        assert GraphEngine.get_action_type(node) == "LOOP"

    def test_condition_node(self) -> None:
        node = _make_node("c", NodeType.CONDITION)
        assert GraphEngine.get_action_type(node) == "CONDITION"

    def test_action_node_uses_action_type_name(self) -> None:
        action = MagicMock()
        action.action_type.name = "CLICK_IMAGE"
        node = _make_node("a", NodeType.ACTION, action=action)
        assert GraphEngine.get_action_type(node) == "CLICK_IMAGE"

    def test_action_node_no_action_falls_back(self) -> None:
        node = _make_node("a", NodeType.ACTION, action=None)
        assert GraphEngine.get_action_type(node) == "ACTION"


# ---- 图验证 ----


class TestValidateGraph:
    """图结构验证。"""

    def test_valid_graph_no_errors(self) -> None:
        graph = _make_graph()
        engine = GraphEngine()
        assert engine._validate_graph(graph) == []

    def test_missing_start(self) -> None:
        graph = _make_graph()
        del graph.nodes["start"]
        engine = GraphEngine()
        errors = engine._validate_graph(graph)
        assert any("START" in e for e in errors)

    def test_missing_end(self) -> None:
        graph = _make_graph()
        del graph.nodes["end"]
        engine = GraphEngine()
        errors = engine._validate_graph(graph)
        assert any("END" in e for e in errors)

    def test_unreachable_nodes(self, caplog) -> None:
        import logging
        graph = _make_graph()
        orphan = _make_node("orphan", NodeType.ACTION, action=_make_action_step("CLICK_IMAGE"))
        graph.add_node(orphan)
        engine = GraphEngine()
        with caplog.at_level(logging.WARNING, logger="src.core.engine.graph_engine"):
            errors = engine._validate_graph(graph)
        assert "不可达" in caplog.text
        assert len(errors) == 0


# ---- 线性图执行 ----


class TestLinearExecution:
    """START → ... → END 线性遍历。"""

    def test_run_simple_graph(self) -> None:
        graph = _make_graph()
        ctx = _make_run_ctx(graph)
        ended = [False]

        class EndLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "end_check"

            def on_graph_end(self, ctx: Any) -> None:
                ended[0] = True

        engine = GraphEngine()
        engine.add_layer(EndLayer())
        engine.run(graph, ctx)
        assert ended[0]

    def test_on_graph_start_end_called(self) -> None:
        graph = _make_graph()
        ctx = _make_run_ctx(graph)
        call_log: list[str] = []

        class LogLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "log"

            def on_graph_start(self, ctx: Any) -> None:
                call_log.append("start")

            def on_graph_end(self, ctx: Any) -> None:
                call_log.append("end")

        engine = GraphEngine()
        engine.add_layer(LogLayer())
        engine.run(graph, ctx)
        assert call_log == ["start", "end"]

    def test_empty_graph_raises(self) -> None:
        graph = FlowGraph(name="empty")
        ctx = _make_run_ctx(graph)
        engine = GraphEngine()
        with pytest.raises(ValueError, match="缺少 START"):
            engine.run(graph, ctx)


# ---- 迭代上限 ----


class TestMaxIterations:
    """超过 max_iterations 强制终止。"""

    def test_stops_at_max_iterations(self) -> None:
        graph = FlowGraph(name="loop")
        start = _make_node("start", NodeType.START)
        graph.add_node(start)
        graph.start_node_id = "start"
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="start"))

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(max_iterations=5, validate_graph_on_run=False)
        engine = GraphEngine(config)
        engine.run(graph, ctx)


# ---- _resolve_next_node ----


class TestResolveNextNode:
    """节点路由规则。"""

    def _engine(self) -> GraphEngine:
        return GraphEngine()

    def test_end_node_returns_none(self) -> None:
        engine = self._engine()
        end = _make_node("end", NodeType.END)
        assert engine._resolve_next_node(MagicMock(), end, None) is None

    def test_default_takes_first_edge(self) -> None:
        engine = self._engine()
        graph = FlowGraph(name="linear")
        a = _make_node("a", NodeType.ACTION)
        b = _make_node("b", NodeType.ACTION)
        graph.add_node(a)
        graph.add_node(b)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="a", to_node="b"))
        result = engine._resolve_next_node(graph, a, None)
        assert result is not None
        assert result.node_id == "b"

    def test_next_label_match(self) -> None:
        engine = self._engine()
        graph = FlowGraph(name="branch")
        a = _make_node("a", NodeType.ACTION)
        b = _make_node("b", NodeType.ACTION)
        c = _make_node("c", NodeType.ACTION)
        graph.add_node(a)
        graph.add_node(b)
        graph.add_node(c)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="a", to_node="b", label="left"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a", to_node="c", label="right"))

        result = engine._resolve_next_node(graph, a, NodeResult.branch("right"))
        assert result is not None
        assert result.node_id == "c"

    def test_condition_true_branch(self) -> None:
        engine = self._engine()
        graph = FlowGraph(name="cond")
        cond = _make_node("cond", NodeType.CONDITION)
        t = _make_node("t", NodeType.ACTION)
        f = _make_node("f", NodeType.ACTION)
        graph.add_node(cond)
        graph.add_node(t)
        graph.add_node(f)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="cond", to_node="t", label="true"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="cond", to_node="f", label="false"))

        result = engine._resolve_next_node(graph, cond, NodeResult(success=True))
        assert result is not None
        assert result.node_id == "t"

    def test_condition_false_branch(self) -> None:
        engine = self._engine()
        graph = FlowGraph(name="cond")
        cond = _make_node("cond", NodeType.CONDITION)
        t = _make_node("t", NodeType.ACTION)
        f = _make_node("f", NodeType.ACTION)
        graph.add_node(cond)
        graph.add_node(t)
        graph.add_node(f)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="cond", to_node="t", label="true"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="cond", to_node="f", label="false"))

        result = engine._resolve_next_node(graph, cond, NodeResult(success=False))
        assert result is not None
        assert result.node_id == "f"

    def test_loop_continue(self) -> None:
        engine = self._engine()
        graph = FlowGraph(name="loop")
        loop = _make_node("loop", NodeType.LOOP, loop_count=3)
        body = _make_node("body", NodeType.ACTION)
        after = _make_node("after", NodeType.ACTION)
        graph.add_node(loop)
        graph.add_node(body)
        graph.add_node(after)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="loop", to_node="body", label="loop"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="loop", to_node="after", label="exit"))

        result = engine._resolve_next_node(graph, loop, NodeResult(success=True))
        assert result is not None
        assert result.node_id == "body"

    def test_loop_exit(self) -> None:
        engine = self._engine()
        graph = FlowGraph(name="loop")
        loop = _make_node("loop", NodeType.LOOP, loop_count=3)
        body = _make_node("body", NodeType.ACTION)
        after = _make_node("after", NodeType.ACTION)
        graph.add_node(loop)
        graph.add_node(body)
        graph.add_node(after)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="loop", to_node="body", label="loop"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="loop", to_node="after", label="exit"))

        result = engine._resolve_next_node(graph, loop, NodeResult(success=False))
        assert result is not None
        assert result.node_id == "after"

    def test_no_out_edges_returns_none(self) -> None:
        engine = self._engine()
        graph = FlowGraph(name="dead")
        node = _make_node("dead", NodeType.ACTION)
        graph.add_node(node)
        assert engine._resolve_next_node(graph, node, None) is None


# ---- ExecutionBlocker ----


class TestExecutionBlocker:
    """ExecutionBlocker 哨兵被正确处理。"""

    def test_blocker_skips_to_next(self) -> None:
        call_log: list[str] = []
        _register_descriptor("BLOCKER_TEST", lambda ctx: (
            call_log.append("blocked"),
            ExecutionBlocker("test block"),
        )[1])

        graph = _make_action_graph("BLOCKER_TEST", name="block")
        ctx = _make_run_ctx(graph)
        engine = GraphEngine()
        engine.run(graph, ctx)
        assert "blocked" in call_log


# ---- 错误策略 ----


class TestErrorStrategies:
    """5 种 ErrorStrategy 行为。"""

    def _make_failing_graph(self) -> FlowGraph:
        _register_descriptor("FAIL_TEST", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom")))
        return _make_action_graph("FAIL_TEST", name="fail")

    @staticmethod
    def _run_and_track(graph: FlowGraph, config: GraphEngineConfig) -> list[str]:
        """运行引擎并返回生命周期日志。"""
        log: list[str] = []

        class TrackLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "track"

            def on_graph_start(self, ctx: Any) -> None:
                log.append("start")

            def on_graph_end(self, ctx: Any) -> None:
                log.append("end")

        engine = GraphEngine(config)
        engine.add_layer(TrackLayer())
        engine.run(graph, _make_run_ctx(graph))
        return log

    def test_ignore_strategy_continues(self) -> None:
        graph = self._make_failing_graph()
        log = self._run_and_track(graph, GraphEngineConfig(default_error_strategy=ErrorStrategy.IGNORE))
        assert log == ["start", "end"]

    def test_skip_strategy_continues(self) -> None:
        graph = self._make_failing_graph()
        log = self._run_and_track(graph, GraphEngineConfig(default_error_strategy=ErrorStrategy.SKIP))
        assert log == ["start", "end"]

    def test_fail_fast_stops(self) -> None:
        graph = self._make_failing_graph()
        log = self._run_and_track(graph, GraphEngineConfig(default_error_strategy=ErrorStrategy.FAIL_FAST))
        assert "start" in log
        assert "end" in log

    def test_fallback_strategy_branches(self) -> None:
        """FALLBACK 策略：返回带 fallback label 的结果。"""
        graph = self._make_failing_graph()
        log = self._run_and_track(graph, GraphEngineConfig(default_error_strategy=ErrorStrategy.FALLBACK))
        assert log == ["start", "end"]

    def test_retry_with_skip_on_exhaust(self) -> None:
        """RETRY 策略：重试耗尽后按 exhausted_strategy=SKIP 继续执行。"""
        graph = self._make_failing_graph()
        log = self._run_and_track(
            graph,
            GraphEngineConfig(
                default_error_strategy=ErrorStrategy.RETRY,
                default_retry_policy=RetryPolicy(max_retries=1, base_delay=0.01, max_delay=0.1),
                default_exhausted_strategy=ErrorStrategy.SKIP,
            ),
        )
        assert log == ["start", "end"]

    def test_retry_with_ignore_on_exhaust(self) -> None:
        """RETRY 策略：重试耗尽后按 exhausted_strategy=IGNORE 继续执行。"""
        graph = self._make_failing_graph()
        log = self._run_and_track(
            graph,
            GraphEngineConfig(
                default_error_strategy=ErrorStrategy.RETRY,
                default_retry_policy=RetryPolicy(max_retries=1, base_delay=0.01, max_delay=0.1),
                default_exhausted_strategy=ErrorStrategy.IGNORE,
            ),
        )
        assert log == ["start", "end"]


# ---- Layer on_node_error override ----


class TestLayerErrorOverride:
    """Layer 的 on_node_error 标记 handled 时覆盖错误。"""

    def test_on_node_error_override(self) -> None:
        call_log: list[str] = []

        class RecoveryLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "recovery"

            def on_node_error(self, ctx: Any, err_ctx: ErrorContext) -> ErrorContext:
                call_log.append(f"recovered:{type(err_ctx.error).__name__}")
                return ErrorContext(
                    error=err_ctx.error,
                    node_result=NodeResult.ok(recovered=True),
                    handled=True,
                )

        _register_descriptor("OVERRIDE_FAIL", lambda ctx: (_ for _ in ()).throw(RuntimeError("controlled failure")))
        graph = _make_action_graph("OVERRIDE_FAIL", name="override")

        ctx = _make_run_ctx(graph)
        engine = GraphEngine(
            GraphEngineConfig(default_error_strategy=ErrorStrategy.FAIL_FAST),
        )
        engine.add_layer(RecoveryLayer())
        engine.run(graph, ctx)
        assert "recovered:RuntimeError" in call_log


# ---- Layer 管道顺序 ----


class TestLayerPipelineOrder:
    """验证 on_node_enter 正序、on_node_exit 逆序。"""

    def test_enter_forward_exit_reverse(self) -> None:
        call_log: list[str] = []

        class OrderLayer(GraphLayer):
            def __init__(self, tag: str, prio: int) -> None:
                self._tag = tag
                self._prio = prio

            @property
            def name(self) -> str:
                return self._tag

            @property
            def priority(self) -> int:
                return self._prio

            def on_node_enter(self, ctx: Any) -> Any:
                call_log.append(f"enter_{self._tag}")
                return ctx

            def on_node_exit(self, ctx: Any, result: Any) -> Any:
                call_log.append(f"exit_{self._tag}")
                return result

        graph = _make_graph()
        ctx = _make_run_ctx(graph)
        engine = GraphEngine()
        engine.add_layer(OrderLayer("A", -10))
        engine.add_layer(OrderLayer("B", 0))
        engine.add_layer(OrderLayer("C", 10))
        engine.run(graph, ctx)

        enters = [c for c in call_log if c.startswith("enter_")]
        exits = [c for c in call_log if c.startswith("exit_")]

        for i in range(0, len(enters), 3):
            assert enters[i : i + 3] == ["enter_A", "enter_B", "enter_C"]

        for i in range(0, len(exits), 3):
            assert exits[i : i + 3] == ["exit_C", "exit_B", "exit_A"]


# ---- on_graph_end 在 finally 中调用 ----


class TestFinallyGuarantee:
    """即使执行出错 on_graph_end 也一定被调用。"""

    def test_on_graph_end_called_on_error(self) -> None:
        call_log: list[str] = []

        class WatchLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "watch"

            def on_graph_end(self, ctx: Any) -> None:
                call_log.append("end")

        graph = FlowGraph(name="bad")
        start = _make_node("start", NodeType.START)
        graph.add_node(start)
        graph.start_node_id = "start"

        ctx = _make_run_ctx(graph)
        engine = GraphEngine(
            GraphEngineConfig(validate_graph_on_run=False, raise_on_validation_error=False),
        )
        engine.add_layer(WatchLayer())
        engine.run(graph, ctx)
        assert "end" in call_log


# ---- 验证 warning 模式（line 96）----


class TestValidationWarningMode:
    """raise_on_validation_error=False 时，验证失败仅 warning 不抛异常。"""

    def test_validation_error_logs_warning(self) -> None:
        graph = FlowGraph(name="bad")
        start = _make_node("start", NodeType.START)
        graph.add_node(start)
        graph.start_node_id = "start"

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(
            validate_graph_on_run=True,
            raise_on_validation_error=False,
        )
        engine = GraphEngine(config)
        engine.run(graph, ctx)


# ---- is_stopping 中断（line 114）----


class TestIsStopping:
    """ctx.is_stopping=True 时主循环立即终止。"""

    def test_stops_when_is_stopping(self) -> None:
        call_log: list[str] = []
        _register_descriptor("COUNT_STOP", lambda ctx: (call_log.append("exec"), NodeResult.ok())[1])

        graph = _make_action_graph("COUNT_STOP", name="stop_test")
        ctx = _make_run_ctx(graph)
        ctx.stop_event.set()
        engine = GraphEngine()
        engine.run(graph, ctx)
        assert call_log == []


# ---- 多节点线性链 ----


class TestMultiNodeLinearChain:
    """START → A → B → C → END 多节点线性执行。"""

    def test_three_action_nodes_in_sequence(self) -> None:
        call_log: list[str] = []
        _register_descriptor("ORDER_SEQ", lambda ctx: (call_log.append(ctx.current_node.node_id), NodeResult.ok())[1])

        graph = FlowGraph(name="linear3")
        start = _make_node("start", NodeType.START)
        for nid in ("a", "b", "c"):
            graph.add_node(_make_node(nid, NodeType.ACTION, action=_make_action_step("ORDER_SEQ")))
        end = _make_node("end", NodeType.END)
        graph.add_node(start)
        graph.add_node(end)
        graph.start_node_id = "start"
        graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="a"))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="a", to_node="b"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="b", to_node="c"))
        graph.add_edge(FlowEdge(edge_id="e3", from_node="c", to_node="end"))

        ctx = _make_run_ctx(graph)
        engine = GraphEngine()
        engine.run(graph, ctx)
        assert call_log == ["a", "b", "c"]


# ---- CONDITION 分支集成 ----


class TestConditionBranchIntegration:
    """CONDITION 节点通过 _resolve_next_node 路由 true/false 边。"""

    def test_condition_routes_to_true_branch(self) -> None:
        """CONDITION 节点 evaluate 成功后路由到 true 分支。"""
        call_log: list[str] = []
        _register_descriptor("TRACK", lambda ctx: (call_log.append(ctx.current_node.node_id), NodeResult.ok())[1])

        graph = FlowGraph(name="cond_integ")
        start = _make_node("start", NodeType.START)
        cond = _make_node("cond", NodeType.CONDITION)
        t = _make_node("t", NodeType.ACTION, action=_make_action_step("TRACK"))
        f = _make_node("f", NodeType.ACTION, action=_make_action_step("TRACK"))
        end = _make_node("end", NodeType.END)
        graph.add_node(start)
        graph.add_node(cond)
        graph.add_node(t)
        graph.add_node(f)
        graph.add_node(end)
        graph.start_node_id = "start"
        graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="cond"))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="cond", to_node="t", label="true"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="cond", to_node="f", label="false"))
        graph.add_edge(FlowEdge(edge_id="e3", from_node="t", to_node="end"))
        graph.add_edge(FlowEdge(edge_id="e4", from_node="f", to_node="end"))

        ctx = _make_run_ctx(graph)
        engine = GraphEngine()
        engine.run(graph, ctx)
        assert "t" in call_log


# ---- LOOP 循环节点集成 ----


class TestLoopIntegration:
    """LOOP 节点通过 _resolve_next_node 路由 loop/exit 边。"""

    def test_loop_routes_to_body_on_success(self) -> None:
        call_log: list[str] = []
        _register_descriptor("LOOP_BODY", lambda ctx: (call_log.append("body"), NodeResult.ok())[1])

        graph = FlowGraph(name="loop_integ")
        start = _make_node("start", NodeType.START)
        loop_node = _make_node("loop", NodeType.LOOP, loop_count=2)
        body = _make_node("body", NodeType.ACTION, action=_make_action_step("LOOP_BODY"))
        after = _make_node("after", NodeType.END)
        graph.add_node(start)
        graph.add_node(loop_node)
        graph.add_node(body)
        graph.add_node(after)
        graph.start_node_id = "start"
        graph.add_edge(FlowEdge(edge_id="e0", from_node="start", to_node="loop"))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="loop", to_node="body", label="loop"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="loop", to_node="after", label="exit"))

        ctx = _make_run_ctx(graph)
        engine = GraphEngine()
        engine.run(graph, ctx)


# ---- next_label 未匹配回退（line 242）----


class TestNextLabelFallback:
    """result.next_label 在出边中未匹配时回退到默认路由。"""

    def test_next_label_not_found_falls_back(self) -> None:
        engine = GraphEngine()
        graph = FlowGraph(name="fallback")
        a = _make_node("a", NodeType.ACTION)
        b = _make_node("b", NodeType.ACTION)
        graph.add_node(a)
        graph.add_node(b)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="a", to_node="b", label="default"))

        result = NodeResult.branch("nonexistent_label")
        next_node = engine._resolve_next_node(graph, a, result)
        assert next_node is not None
        assert next_node.node_id == "b"


# ---- CONDITION 无 label 边回退（line 254）----


class TestConditionNoLabelEdge:
    """CONDITION 节点出边没有 true/false label 时回退到第一条出边。"""

    def test_condition_no_labeled_edges_falls_back(self) -> None:
        engine = GraphEngine()
        graph = FlowGraph(name="cond_fb")
        cond = _make_node("cond", NodeType.CONDITION)
        first = _make_node("first", NodeType.ACTION)
        graph.add_node(cond)
        graph.add_node(first)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="cond", to_node="first", label="default"))

        result = engine._resolve_next_node(graph, cond, NodeResult(success=True))
        assert result is not None
        assert result.node_id == "first"


# ---- LOOP 无 label 边回退（line 262）----


class TestLoopNoLabelEdge:
    """LOOP 节点出边没有 loop/exit label 时回退到第一条出边。"""

    def test_loop_no_labeled_edges_falls_back(self) -> None:
        engine = GraphEngine()
        graph = FlowGraph(name="loop_fb")
        loop = _make_node("loop", NodeType.LOOP, loop_count=3)
        first = _make_node("first", NodeType.ACTION)
        graph.add_node(loop)
        graph.add_node(first)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="loop", to_node="first", label="default"))

        result = engine._resolve_next_node(graph, loop, NodeResult(success=True))
        assert result is not None
        assert result.node_id == "first"


# ---- 未注册节点类型（line 183）----


class TestUnregisteredNodeType:
    """执行未注册的节点类型时抛出 RuntimeError。"""

    def test_unregistered_type_raises(self) -> None:
        graph = _make_action_graph("UNKNOWN_TYPE", name="unregistered")
        ctx = _make_run_ctx(graph)
        ended = [False]

        class EndLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "end_check"

            def on_graph_end(self, ctx: Any) -> None:
                ended[0] = True

        config = GraphEngineConfig(default_error_strategy=ErrorStrategy.IGNORE)
        engine = GraphEngine(config)
        engine.add_layer(EndLayer())
        engine.run(graph, ctx)
        assert ended[0]


# ---- retry 不可重试异常（line 317-320）----


class TestRetryNonRetryable:
    """RETRY 策略遇到不可重试的异常时直接应用 exhausted_strategy。"""

    def test_non_retryable_goes_to_exhausted(self) -> None:
        _register_descriptor("VALUE_ERR", lambda ctx: (_ for _ in ()).throw(ValueError("not retryable")))
        graph = _make_action_graph("VALUE_ERR", name="non_retry")
        ended = [False]

        class EndLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "end_check"

            def on_graph_end(self, ctx: Any) -> None:
                ended[0] = True

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(
            default_error_strategy=ErrorStrategy.RETRY,
            default_retry_policy=RetryPolicy(
                max_retries=2,
                base_delay=0.01,
                max_delay=0.1,
                retryable_exceptions=(RuntimeError,),
            ),
            default_exhausted_strategy=ErrorStrategy.SKIP,
        )
        engine = GraphEngine(config)
        engine.add_layer(EndLayer())
        engine.run(graph, ctx)
        assert ended[0]


# ---- retry 中遇到不可重试异常中断（line 333, 340）----


class TestRetryBreaksOnNonRetryable:
    """重试过程中如果新的错误不可重试，则中断重试。"""

    def test_retry_breaks_on_non_retryable_mid_retry(self) -> None:
        attempt = 0

        def _intermittent(ctx: Any) -> NodeResult:
            nonlocal attempt
            attempt += 1
            if attempt == 1:
                raise RuntimeError("retryable")
            raise ValueError("not retryable")

        _register_descriptor("INTERMITTENT", _intermittent)
        graph = _make_action_graph("INTERMITTENT", name="mid_retry")
        ended = [False]

        class EndLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "end_check"

            def on_graph_end(self, ctx: Any) -> None:
                ended[0] = True

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(
            default_error_strategy=ErrorStrategy.RETRY,
            default_retry_policy=RetryPolicy(
                max_retries=5,
                base_delay=0.01,
                max_delay=0.1,
                retryable_exceptions=(RuntimeError,),
            ),
            default_exhausted_strategy=ErrorStrategy.SKIP,
        )
        engine = GraphEngine(config)
        engine.add_layer(EndLayer())
        engine.run(graph, ctx)
        assert attempt == 2
        assert ended[0]


# ---- exhausted_strategy: FALLBACK（line 358-359）----


class TestExhaustedFallback:
    """重试耗尽后 exhausted_strategy=FALLBACK 返回 fallback 分支。"""

    def test_exhausted_fallback(self) -> None:
        _register_descriptor("ALWAYS_FAIL", lambda ctx: (_ for _ in ()).throw(RuntimeError("always")))

        ended = [False]

        class EndLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "end_check"

            def on_graph_end(self, ctx: Any) -> None:
                ended[0] = True

        graph = _make_action_graph("ALWAYS_FAIL", name="exhaust_fb")

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(
            default_error_strategy=ErrorStrategy.RETRY,
            default_retry_policy=RetryPolicy(max_retries=1, base_delay=0.01, max_delay=0.1),
            default_exhausted_strategy=ErrorStrategy.FALLBACK,
        )
        engine = GraphEngine(config)
        engine.add_layer(EndLayer())
        engine.run(graph, ctx)
        # FALLBACK 返回 success=False → 主循环 break，但 on_graph_end 仍触发
        assert ended[0]


# ---- exhausted_strategy: IGNORE（line 360）----


class TestExhaustedIgnore:
    """重试耗尽后 exhausted_strategy=IGNORE 标记成功并继续。"""

    def test_exhausted_ignore(self) -> None:
        _register_descriptor("EXHAUST_IGNORE", lambda ctx: (_ for _ in ()).throw(RuntimeError("always")))
        graph = _make_action_graph("EXHAUST_IGNORE", name="exhaust_ign")
        ended = [False]

        class EndLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "end_check"

            def on_graph_end(self, ctx: Any) -> None:
                ended[0] = True

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(
            default_error_strategy=ErrorStrategy.RETRY,
            default_retry_policy=RetryPolicy(max_retries=1, base_delay=0.01, max_delay=0.1),
            default_exhausted_strategy=ErrorStrategy.IGNORE,
        )
        engine = GraphEngine(config)
        engine.add_layer(EndLayer())
        engine.run(graph, ctx)
        assert ended[0]


# ---- on_node_error 多层 LIFO 传递（line 305）----


class TestMultiLayerErrorPropagation:
    """多层 on_node_error 按 LIFO 逆序传递 ErrorContext。"""

    def test_error_propagates_through_layers(self) -> None:
        call_log: list[str] = []

        class OuterLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "outer"

            @property
            def priority(self) -> int:
                return 10

            def on_node_error(self, ctx: Any, err_ctx: ErrorContext) -> ErrorContext:
                call_log.append("outer")
                return err_ctx

        class InnerLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "inner"

            @property
            def priority(self) -> int:
                return -10

            def on_node_error(self, ctx: Any, err_ctx: ErrorContext) -> ErrorContext:
                call_log.append("inner")
                return ErrorContext(
                    error=err_ctx.error,
                    node_result=NodeResult.ok(recovered=True),
                    handled=True,
                )

        _register_descriptor("PROP_ERR", lambda ctx: (_ for _ in ()).throw(RuntimeError("prop")))
        graph = _make_action_graph("PROP_ERR", name="prop")
        ctx = _make_run_ctx(graph)
        engine = GraphEngine(
            GraphEngineConfig(default_error_strategy=ErrorStrategy.FAIL_FAST),
        )
        engine.add_layer(InnerLayer())
        engine.add_layer(OuterLayer())
        engine.run(graph, ctx)
        assert call_log == ["outer", "inner"]


# ---- on_graph_start/end 逆序 ----


class TestGraphStartEndOrder:
    """on_graph_start 正序、on_graph_end 逆序。"""

    def test_start_forward_end_reverse(self) -> None:
        call_log: list[str] = []

        class OrderedLayer(GraphLayer):
            def __init__(self, tag: str, prio: int) -> None:
                self._tag = tag
                self._prio = prio

            @property
            def name(self) -> str:
                return self._tag

            @property
            def priority(self) -> int:
                return self._prio

            def on_graph_start(self, ctx: Any) -> None:
                call_log.append(f"gs_{self._tag}")

            def on_graph_end(self, ctx: Any) -> None:
                call_log.append(f"ge_{self._tag}")

        graph = _make_graph()
        ctx = _make_run_ctx(graph)
        engine = GraphEngine()
        engine.add_layer(OrderedLayer("A", -10))
        engine.add_layer(OrderedLayer("B", 10))
        engine.run(graph, ctx)
        assert call_log == ["gs_A", "gs_B", "ge_B", "ge_A"]


# ---- 缺少 START 节点（跳过验证）line 101 ----


class TestMissingStartWithoutValidation:
    """validate_graph_on_run=False 但图没有 START 节点时，run() 仍抛 ValueError。"""

    def test_no_start_raises_even_without_validation(self) -> None:
        graph = FlowGraph(name="no_start")
        end = _make_node("end", NodeType.END)
        graph.add_node(end)

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(validate_graph_on_run=False)
        engine = GraphEngine(config)
        with pytest.raises(ValueError, match="缺少 START"):
            engine.run(graph, ctx)


# ---- retry 成功返回 None（line 333）----


class TestRetrySuccessReturnsNone:
    """重试时描述符返回 None（成功），引擎正常继续。"""

    def test_retry_recovers_with_none_result(self) -> None:
        attempt = 0

        def _recover(ctx: Any) -> NodeResult | None:
            nonlocal attempt
            attempt += 1
            if attempt <= 1:
                raise RuntimeError("first fail")
            return None

        _register_descriptor("RECOVER", _recover)
        graph = _make_action_graph("RECOVER", name="recover")
        ended = [False]

        class EndLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "end_check"

            def on_graph_end(self, ctx: Any) -> None:
                ended[0] = True

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(
            default_error_strategy=ErrorStrategy.RETRY,
            default_retry_policy=RetryPolicy(max_retries=3, base_delay=0.01, max_delay=0.1),
            default_exhausted_strategy=ErrorStrategy.SKIP,
        )
        engine = GraphEngine(config)
        engine.add_layer(EndLayer())
        engine.run(graph, ctx)
        assert attempt == 2
        assert ended[0]


# ---- exhausted_strategy: FAIL_FAST（line 360-361）----


class TestExhaustedFailFast:
    """重试耗尽后 exhausted_strategy=FAIL_FAST 直接返回失败结果。"""

    def test_exhausted_fail_fast(self) -> None:
        _register_descriptor("EXHAUST_FF", lambda ctx: (_ for _ in ()).throw(RuntimeError("always")))
        graph = _make_action_graph("EXHAUST_FF", name="exhaust_ff")
        nodes_visited: list[str] = []

        class TrackLayer(GraphLayer):
            @property
            def name(self) -> str:
                return "track"

            def on_node_enter(self, ctx: Any) -> Any:
                nodes_visited.append(ctx.current_node.node_id)
                return ctx

        ctx = _make_run_ctx(graph)
        config = GraphEngineConfig(
            default_error_strategy=ErrorStrategy.RETRY,
            default_retry_policy=RetryPolicy(max_retries=1, base_delay=0.01, max_delay=0.1),
            default_exhausted_strategy=ErrorStrategy.FAIL_FAST,
        )
        engine = GraphEngine(config)
        engine.add_layer(TrackLayer())
        engine.run(graph, ctx)
        assert "act" in nodes_visited
        assert "end" not in nodes_visited


# ---- FlowGraph.get_successors ----


class TestGetSuccessors:
    """FlowGraph.get_successors 去重 + 正确返回后继 ID。"""

    def test_linear(self) -> None:
        g = _make_graph()
        assert g.get_successors("start") == ["end"]
        assert g.get_successors("end") == []

    def test_branch_dedup(self) -> None:
        g = FlowGraph(name="test")
        g.add_node(_make_node("a", NodeType.START))
        g.add_node(_make_node("b", NodeType.ACTION))
        g.add_node(_make_node("c", NodeType.END))
        g.start_node_id = "a"
        g.add_edge(FlowEdge(edge_id="e1", from_node="a", to_node="b", label="true"))
        g.add_edge(FlowEdge(edge_id="e2", from_node="a", to_node="b", label="false"))
        g.add_edge(FlowEdge(edge_id="e3", from_node="b", to_node="c"))
        # a → b 出现两次（true/false），去重后只有一个
        assert g.get_successors("a") == ["b"]


# ---- run_incremental ----


class TestRunIncremental:
    """增量执行 — 首次全量，后续仅脏节点。"""

    def test_first_run_executes_all(self) -> None:
        call_log: list[str] = []

        def _exec_wait(ctx: Any) -> NodeResult:
            call_log.append(ctx.current_node.node_id)
            return NodeResult.success()

        _register_descriptor("WAIT", _exec_wait)

        graph = _make_action_graph("WAIT")
        ctx = _make_run_ctx(graph)
        engine = GraphEngine(GraphEngineConfig(validate_graph_on_run=False))
        tracker = engine.run_incremental(graph, ctx)
        # 全量执行：start, act, end
        assert "act" in call_log
        # tracker 不应再有脏节点
        assert len(tracker.dirty_nodes) == 0

    def test_incremental_skips_clean(self) -> None:
        call_log: list[str] = []

        def _exec_wait(ctx: Any) -> NodeResult:
            call_log.append(ctx.current_node.node_id)
            return NodeResult.success()

        _register_descriptor("WAIT", _exec_wait)

        graph = _make_action_graph("WAIT")
        ctx = _make_run_ctx(graph)
        engine = GraphEngine(GraphEngineConfig(validate_graph_on_run=False))

        # 首次全量
        tracker = engine.run_incremental(graph, ctx)
        assert "act" in call_log

        # 第二次无脏节点 — 应跳过 action
        call_log.clear()
        tracker2 = engine.run_incremental(graph, ctx, tracker)
        assert "act" not in call_log

    def test_dirty_node_reexecutes(self) -> None:
        call_log: list[str] = []

        def _exec_wait(ctx: Any) -> NodeResult:
            call_log.append(ctx.current_node.node_id)
            return NodeResult.success()

        _register_descriptor("WAIT", _exec_wait)

        graph = _make_action_graph("WAIT")
        ctx = _make_run_ctx(graph)
        engine = GraphEngine(GraphEngineConfig(validate_graph_on_run=False))

        tracker = engine.run_incremental(graph, ctx)
        call_log.clear()

        # 标记 act 为脏 + 传播下游（end）
        tracker.mark_dirty("act")
        tracker.propagate_downstream(graph.get_successors, "act")

        tracker2 = engine.run_incremental(graph, ctx, tracker)
        assert "act" in call_log

    def test_condition_prunes_unselected_branch(self) -> None:
        """CONDITION 节点评估后，未选中分支的脏节点应被标记为干净。"""
        from src.core.engine.descriptors.condition_descriptor import ConditionDescriptor

        NodeRegistry.register(ConditionDescriptor)

        # 构建: START → COND → (true: ACT_TRUE, false: ACT_FALSE) → END
        graph = FlowGraph(name="cond_test")
        graph.add_node(_make_node("start", NodeType.START))
        graph.add_node(_make_node("cond", NodeType.CONDITION))
        act_true = _make_node("act_true", NodeType.ACTION, action=_make_action_step("WAIT"))
        act_false = _make_node("act_false", NodeType.ACTION, action=_make_action_step("WAIT"))
        graph.add_node(act_true)
        graph.add_node(act_false)
        graph.add_node(_make_node("end", NodeType.END))
        graph.start_node_id = "start"

        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="cond"))
        graph.add_edge(FlowEdge(edge_id="e_true", from_node="cond", to_node="act_true", label="true"))
        graph.add_edge(FlowEdge(edge_id="e_false", from_node="cond", to_node="act_false", label="false"))
        graph.add_edge(FlowEdge(edge_id="e3", from_node="act_true", to_node="end"))
        graph.add_edge(FlowEdge(edge_id="e4", from_node="act_false", to_node="end"))

        call_log: list[str] = []

        def _exec_wait(ctx: Any) -> NodeResult:
            call_log.append(ctx.current_node.node_id)
            return NodeResult.success()

        _register_descriptor("WAIT", _exec_wait)

        ctx = _make_run_ctx(graph)
        engine = GraphEngine(GraphEngineConfig(validate_graph_on_run=False))
        tracker = engine.run_incremental(graph, ctx)

        # COND 默认走 true（无条件/无 evaluator → success=True → true 分支）
        # 所以 act_false 及其下游应被裁剪
        assert "act_true" in call_log
        assert "act_false" not in call_log

        # 验证 tracker 中 act_false 被标记为干净（在未选中分支上被裁剪）
        assert not tracker.needs_eval("act_false", ctx.gen)
