"""ReconnectEdgeCommand — 重连连线端点编辑命令。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowGraph

logger = logging.getLogger(__name__)


@dataclass
class ReconnectEdgeCommand(EditCommand):
    """重连边的一端（源端或目标端）。

    撤销时恢复原始连接。
    """

    graph: FlowGraph
    edge_id: str
    side: str  # "source" | "target"
    new_node_id: str
    new_port: str
    _old_node_id: str = field(default="", init=False, repr=False)
    _old_port: str = field(default="", init=False, repr=False)

    def __post_init__(self) -> None:
        edge = self.graph.get_edge(self.edge_id)
        if edge is None:
            raise ValueError(f"Edge {self.edge_id} not found")
        if self.side == "source":
            self._old_node_id = edge.from_node
            self._old_port = edge.label
        elif self.side == "target":
            self._old_node_id = edge.to_node
            self._old_port = "in"
        else:
            raise ValueError(f"Invalid side: {self.side!r}")

    def execute(self) -> None:
        self.graph.reconnect_edge(
            self.edge_id, self.side, self.new_node_id, self.new_port
        )

    def undo(self) -> None:
        self.graph.reconnect_edge(
            self.edge_id, self.side, self._old_node_id, self._old_port
        )

    @property
    def description(self) -> str:
        return f"重连连线 ({self.edge_id} {self.side})"
