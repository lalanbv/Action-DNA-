"""AutoInsertCommand — 自动插入节点到连线上。"""

from __future__ import annotations

import logging

from src.core.editor.commands.add_edge_command import AddEdgeCommand
from src.core.editor.commands.composite_command import CompositeCommand
from src.core.editor.commands.remove_edge_command import RemoveEdgeCommand
from src.core.flow import FlowGraph

logger = logging.getLogger(__name__)


class AutoInsertCommand(CompositeCommand):
    """将节点插入到已有连线的两个节点之间。

    原始: A --[label]--> C
    插入 B 后: A --[label]--> B --[default]--> C

    撤销时恢复原始边，B 节点恢复无连接状态。
    """

    def __init__(self, graph: FlowGraph, edge_id: str, insert_node_id: str) -> None:
        old_edge = graph.get_edge(edge_id)
        if old_edge is None:
            raise ValueError(f"Edge {edge_id} not found")
        if insert_node_id not in graph.nodes:
            raise ValueError(f"Node {insert_node_id} not found")

        from_id = old_edge.from_node
        to_id = old_edge.to_node
        label = old_edge.label

        commands = [
            RemoveEdgeCommand(graph, edge_id),
            AddEdgeCommand(graph, from_id, insert_node_id, label),
            AddEdgeCommand(graph, insert_node_id, to_id, "default"),
        ]
        super().__init__(_commands=commands, _label=f"自动插入节点 {insert_node_id}")
