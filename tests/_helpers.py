"""Test helpers shared across test directories."""

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from src.core.step_types import BaseStep

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.flow import FlowGraph, FlowNode


@dataclass
class ActionChain:
    """轻量动作链容器，供测试 fixture 使用。

    替代已移除的 src.core.action.ActionChain。
    """
    name: str = ""
    steps: list[BaseStep] = field(default_factory=list)
    loop: bool = True
    loop_count: int = 0


def make_exec_ctx(
    graph: FlowGraph,
    node: FlowNode | None = None,
    *,
    gen: int = 0,
    step_index: int = 0,
) -> ExecutionContext:
    """创建用于测试的真实 ExecutionContext。

    外部依赖（capture/matcher/input_ctrl）使用 MagicMock。
    """
    from src.core.engine.execution_context import ExecutionContext
    from src.core.variables.pool import VariablePool

    return ExecutionContext(
        graph=graph,
        current_node=node or graph.find_by_type("START"),
        variables=VariablePool(),
        capture=MagicMock(),
        matcher=MagicMock(),
        input_ctrl=MagicMock(),
        gen=gen,
        stop_event=threading.Event(),
        pause_event=threading.Event(),
        step_index=step_index,
    )


def make_test_graph(
    name: str = "test_graph",
    *,
    action_type_name: str = "CLICK_IMAGE",
) -> tuple[FlowGraph, FlowNode]:
    """构建标准三节点测试图（start → action → end），返回 (graph, action_node)。"""
    from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType

    action = MagicMock()
    action.action_type.name = action_type_name
    node = FlowNode(node_id="node_1", node_type=NodeType.ACTION, action=action)
    graph = FlowGraph(name=name)
    graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
    graph.add_node(node)
    graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
    graph.start_node_id = "start"
    graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="node_1"))
    graph.add_edge(FlowEdge(edge_id="e2", from_node="node_1", to_node="end"))
    return graph, node
