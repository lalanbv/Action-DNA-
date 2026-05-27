"""AddNodeCommand — 添加节点编辑命令。"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from src.core.step_types import BaseStep
from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowGraph, FlowNode, NodeType


@dataclass
class AddNodeCommand(EditCommand):
    """添加节点命令。撤销时从图中移除该节点。"""

    graph: FlowGraph
    node_type: NodeType
    x: int
    y: int
    action: BaseStep | None = None
    _node_id: str | None = None

    def execute(self) -> None:
        if self._node_id is None:
            self._node_id = FlowGraph.new_id("a")
        node = FlowNode(
            node_id=self._node_id,
            node_type=self.node_type,
            action=copy.deepcopy(self.action) if self.action else None,
            pos_x=self.x,
            pos_y=self.y,
        )
        self.graph.add_node(node)

    def undo(self) -> None:
        if self._node_id:
            self.graph.remove_node(self._node_id)

    @property
    def description(self) -> str:
        return f"添加节点 ({self.node_type.name})"

    @property
    def node_id(self) -> str:
        return self._node_id or ""
