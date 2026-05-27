"""单元测试 — WorkflowValidator 三阶段验证。

参考: 03_核心引擎设计.md §10, 12_开发计划与时间安排.md §9.2
覆盖: 构建时验证 (D12)、连接验证 (D13)、运行时验证 (D14)。
"""

import threading
from unittest.mock import MagicMock

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType, chain_to_flow
from src.core.engine.workflow_validator import (
    ValidationIssue,
    ValidationLevel,
    ValidationResult,
    WorkflowValidator,
)

import src.core.engine.descriptors as _builtin_descriptors  # noqa: F401


# ============================================================
# helpers
# ============================================================


def _valid_graph(name: str = "valid") -> FlowGraph:
    """创建一个合法的线性图: START → WAIT → END"""
    return chain_to_flow(name, [
        STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
    ])


def _error_ids(result: ValidationResult) -> list[str]:
    return [i.node_id or i.edge_id or "" for i in result.errors]


def _warning_messages(result: ValidationResult) -> list[str]:
    return [i.message for i in result.warnings]


# ============================================================
# D12: 构建时验证
# ============================================================


class TestValidateBuild:
    """阶段 1 — 图结构完整性验证。"""

    def test_valid_graph_passes(self):
        """合法线性图通过验证。"""
        graph = _valid_graph()
        result = WorkflowValidator().validate_build(graph)
        assert result.is_valid

    def test_missing_start_node(self):
        """缺少 START 节点报 ERROR。"""
        graph = FlowGraph(name="no_start", start_node_id="end")
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        result = WorkflowValidator().validate_build(graph)
        assert not result.is_valid
        assert any("START" in e.message for e in result.errors)

    def test_missing_end_node(self):
        """缺少 END 节点报 ERROR。"""
        graph = FlowGraph(name="no_end", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        result = WorkflowValidator().validate_build(graph)
        assert not result.is_valid
        assert any("END" in e.message for e in result.errors)

    def test_multiple_start_nodes(self):
        """多个 START 节点报 ERROR。"""
        graph = FlowGraph(name="multi_start", start_node_id="start1")
        graph.add_node(FlowNode(node_id="start1", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="start2", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        result = WorkflowValidator().validate_build(graph)
        assert not result.is_valid
        assert any("多个 START" in e.message for e in result.errors)

    def test_unreachable_action_node(self):
        """不可达的 ACTION 节点报 WARNING。"""
        graph = FlowGraph(name="unreachable", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_node(FlowNode(
            node_id="orphan",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))
        result = WorkflowValidator().validate_build(graph)
        assert any("不可达" in w for w in _warning_messages(result))

    def test_unreachable_end_node(self):
        """不可达的 END 节点报 ERROR。"""
        graph = FlowGraph(name="unreachable_end", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="wait",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="wait"))
        result = WorkflowValidator().validate_build(graph)
        assert any("END" in e.message and "不可达" in e.message for e in result.errors)

    def test_action_node_without_action_config(self):
        """ACTION 节点缺少 action 配置报 ERROR。"""
        graph = FlowGraph(name="no_action", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="broken", node_type=NodeType.ACTION))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="broken"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="broken", to_node="end"))
        result = WorkflowValidator().validate_build(graph)
        assert not result.is_valid
        assert any("action 配置" in e.message for e in result.errors)

    def test_chain_to_flow_always_valid(self):
        """chain_to_flow 生成的图始终通过构建时验证。"""
        graph = chain_to_flow("chain_valid", [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.5),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
            STEP_CLASSES[ActionType.PRESS_KEY](key="enter"),
        ])
        result = WorkflowValidator().validate_build(graph)
        assert result.is_valid


# ============================================================
# D13: 连接验证
# ============================================================


class TestValidateConnections:
    """阶段 2 — 边完整性验证。"""

    def test_valid_graph_passes(self):
        """合法图通过连接验证。"""
        graph = _valid_graph()
        result = WorkflowValidator().validate_connections(graph)
        assert result.is_valid

    def test_dangling_from_node(self):
        """边的 from_node 不存在报 ERROR。"""
        graph = FlowGraph(name="dangling_from", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="ghost", to_node="end"))
        result = WorkflowValidator().validate_connections(graph)
        assert not result.is_valid
        assert any("from_node" in e.message for e in result.errors)

    def test_dangling_to_node(self):
        """边的 to_node 不存在报 ERROR。"""
        graph = FlowGraph(name="dangling_to", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="ghost"))
        result = WorkflowValidator().validate_connections(graph)
        assert not result.is_valid
        assert any("to_node" in e.message for e in result.errors)

    def test_self_loop_edge(self):
        """自环边报 ERROR。"""
        graph = FlowGraph(name="self_loop", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="wait",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="wait"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="wait", to_node="wait"))
        graph.add_edge(FlowEdge(edge_id="e3", from_node="wait", to_node="end"))
        result = WorkflowValidator().validate_connections(graph)
        assert any("自环" in e.message for e in result.errors)

    def test_duplicate_edge_warning(self):
        """重复边报 WARNING。"""
        graph = FlowGraph(name="dup_edge", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="start", to_node="end"))
        result = WorkflowValidator().validate_connections(graph)
        assert any("重复边" in w for w in _warning_messages(result))

    def test_end_node_with_outgoing_edge_warning(self):
        """END 节点有出边报 WARNING。"""
        graph = FlowGraph(name="end_out", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_node(FlowNode(
            node_id="wait",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="end", to_node="wait"))
        result = WorkflowValidator().validate_connections(graph)
        assert any("END" in w and "出边" in w for w in _warning_messages(result))

    def test_start_node_with_incoming_edge_warning(self):
        """START 节点有入边报 WARNING。"""
        graph = FlowGraph(name="start_in", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="wait",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="wait", to_node="start"))
        result = WorkflowValidator().validate_connections(graph)
        assert any("START" in w and "入边" in w for w in _warning_messages(result))

    def test_node_without_outgoing_warning(self):
        """非终止节点没有出边报 WARNING。"""
        graph = FlowGraph(name="no_out", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="dead_end",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="dead_end"))
        result = WorkflowValidator().validate_connections(graph)
        assert any("没有出边" in w for w in _warning_messages(result))

    def test_unregistered_action_type(self):
        """未注册的动作类型报 ERROR。"""
        graph = FlowGraph(name="bad_type", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="action1",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="action1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="action1", to_node="end"))

        from src.core.engine.node_registry import NodeRegistry
        NodeRegistry.clear()
        result = WorkflowValidator().validate_connections(graph)
        assert not result.is_valid
        assert any("未注册" in e.message for e in result.errors)

    def test_chain_to_flow_connections_valid(self):
        """chain_to_flow 生成的图通过连接验证。"""
        graph = chain_to_flow("chain_conn", [
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=50, pos_y=60),
        ])
        result = WorkflowValidator().validate_connections(graph)
        assert result.is_valid


# ============================================================
# D14: 运行时验证
# ============================================================


class TestValidateRuntime:
    """阶段 3 — 执行前验证。"""

    def _make_ctx(self, graph, **overrides):
        """创建 ExecutionContext，默认提供完整的 mock 依赖。"""
        from src.core.engine.execution_context import ExecutionContext
        from src.core.variables.pool import VariablePool

        start = graph.find_by_type("START")
        defaults = dict(
            graph=graph,
            current_node=start,
            variables=VariablePool(),
            capture=MagicMock(),
            matcher=MagicMock(),
            input_ctrl=MagicMock(),
            gen=0,
            stop_event=threading.Event(),
            pause_event=threading.Event(),
        )
        defaults.update(overrides)
        return ExecutionContext(**defaults)

    def test_valid_runtime_passes(self):
        """完整上下文通过运行时验证。"""
        graph = _valid_graph()
        ctx = self._make_ctx(graph)
        result = WorkflowValidator().validate_runtime(graph, ctx)
        assert result.is_valid

    def test_missing_stop_event(self):
        """缺少 stop_event 报 ERROR。"""
        graph = _valid_graph()
        ctx = self._make_ctx(graph, stop_event=None)
        result = WorkflowValidator().validate_runtime(graph, ctx)
        assert not result.is_valid
        assert any("stop_event" in e.message for e in result.errors)

    def test_missing_pause_event_warning(self):
        """缺少 pause_event 报 WARNING（不阻断执行）。"""
        graph = _valid_graph()
        ctx = self._make_ctx(graph, pause_event=None)
        result = WorkflowValidator().validate_runtime(graph, ctx)
        assert result.is_valid
        assert any("pause_event" in w for w in _warning_messages(result))

    def test_missing_capture(self):
        """缺少 capture 报 ERROR。"""
        graph = _valid_graph()
        ctx = self._make_ctx(graph, capture=None)
        result = WorkflowValidator().validate_runtime(graph, ctx)
        assert not result.is_valid
        assert any("capture" in e.message for e in result.errors)

    def test_missing_input_ctrl(self):
        """缺少 input_ctrl 报 ERROR。"""
        graph = _valid_graph()
        ctx = self._make_ctx(graph, input_ctrl=None)
        result = WorkflowValidator().validate_runtime(graph, ctx)
        assert not result.is_valid
        assert any("input_ctrl" in e.message for e in result.errors)

    def test_includes_build_and_connection_checks(self):
        """运行时验证包含构建时和连接时检查。"""
        graph = FlowGraph(name="empty", start_node_id="x")
        ctx = self._make_ctx(graph, current_node=None)
        result = WorkflowValidator().validate_runtime(graph, ctx)
        assert not result.is_valid
        assert any("START" in e.message for e in result.errors)
        assert any("END" in e.message for e in result.errors)


# ============================================================
# ValidationResult 辅助方法
# ============================================================


class TestValidationResult:
    """ValidationResult 辅助方法测试。"""

    def test_is_valid_when_no_errors(self):
        """无 ERROR 时 is_valid 为 True。"""
        r = ValidationResult(issues=[
            ValidationIssue(level=ValidationLevel.WARNING, message="w"),
        ])
        assert r.is_valid

    def test_is_invalid_when_has_errors(self):
        """有 ERROR 时 is_valid 为 False。"""
        r = ValidationResult(issues=[
            ValidationIssue(level=ValidationLevel.ERROR, message="e"),
        ])
        assert not r.is_valid

    def test_merge_combines_issues(self):
        """merge 合并两个结果的 issues。"""
        r1 = ValidationResult(issues=[
            ValidationIssue(level=ValidationLevel.ERROR, message="e1"),
        ])
        r2 = ValidationResult(issues=[
            ValidationIssue(level=ValidationLevel.WARNING, message="w1"),
        ])
        merged = r1.merge(r2)
        assert len(merged.issues) == 2
        assert len(merged.errors) == 1
        assert len(merged.warnings) == 1
        assert len(r1.issues) == 1  # original unchanged

    def test_empty_result_is_valid(self):
        """空结果 is_valid。"""
        assert ValidationResult().is_valid


# ============================================================
# validate_all 便捷方法
# ============================================================


class TestValidateAll:
    """validate_all 便捷方法测试。"""

    def test_valid_graph_passes(self):
        """合法图通过所有静态验证。"""
        graph = _valid_graph()
        result = WorkflowValidator().validate_all(graph)
        assert result.is_valid

    def test_catches_build_and_connection_errors(self):
        """同时捕获构建时和连接时错误。"""
        graph = FlowGraph(name="bad", start_node_id="start")
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="ghost", to_node="start"))
        result = WorkflowValidator().validate_all(graph)
        assert not result.is_valid
        assert any("END" in e.message for e in result.errors)
        assert any("from_node" in e.message for e in result.errors)
