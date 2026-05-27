"""RemoveNodeCommand — 删除节点编辑命令。"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowEdge, FlowGraph, FlowNode

logger = logging.getLogger(__name__)


@dataclass
class RemoveNodeCommand(EditCommand):
    """删除节点命令。记录被删除节点的完整信息和关联的边，撤销时恢复。"""

    graph: FlowGraph
    node_id: str
    _removed_node: FlowNode | None = field(default=None, init=False, repr=False)
    _removed_edges: list[FlowEdge] = field(default_factory=list, init=False, repr=False)

    def execute(self) -> None:
        node = self.graph.get_node(self.node_id)
        if node is None:
            return
        self._removed_node = copy.deepcopy(node)
        self._removed_edges = [
            copy.deepcopy(e) for e in self.graph.edges
            if e.from_node == self.node_id or e.to_node == self.node_id
        ]
        self.graph.remove_node(self.node_id)

    def undo(self) -> None:
        if self._removed_node:
            self.graph.add_node(self._removed_node)
        for edge in self._removed_edges:
            self.graph.add_edge(edge)

    @property
    def description(self) -> str:
        return f"删除节点 ({self.node_id})"
