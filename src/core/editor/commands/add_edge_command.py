"""AddEdgeCommand — 添加连线编辑命令。"""

from __future__ import annotations

from dataclasses import dataclass

from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowEdge, FlowGraph


@dataclass
class AddEdgeCommand(EditCommand):
    """添加连线命令。撤销时移除该边。"""

    graph: FlowGraph
    source_id: str
    target_id: str
    label: str = "default"
    _edge_id: str | None = None

    def execute(self) -> None:
        if self._edge_id is None:
            self._edge_id = FlowGraph.new_id("e")
        edge = FlowEdge(
            edge_id=self._edge_id,
            from_node=self.source_id,
            to_node=self.target_id,
            label=self.label,
        )
        self.graph.add_edge(edge)

    def undo(self) -> None:
        if self._edge_id:
            self.graph.remove_edge(self._edge_id)

    @property
    def description(self) -> str:
        return f"添加连线 ({self.source_id} -> {self.target_id})"

    @property
    def edge_id(self) -> str:
        return self._edge_id or ""
