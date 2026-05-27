"""RemoveEdgeCommand — 删除连线编辑命令。"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field

from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowEdge, FlowGraph

logger = logging.getLogger(__name__)


@dataclass
class RemoveEdgeCommand(EditCommand):
    """删除连线命令。撤销时恢复该边。"""

    graph: FlowGraph
    edge_id: str
    _removed_edge: FlowEdge | None = field(default=None, init=False, repr=False)

    def execute(self) -> None:
        for e in self.graph.edges:
            if e.edge_id == self.edge_id:
                self._removed_edge = copy.deepcopy(e)
                break
        if self._removed_edge:
            self.graph.remove_edge(self.edge_id)

    def undo(self) -> None:
        if self._removed_edge:
            self.graph.add_edge(self._removed_edge)

    @property
    def description(self) -> str:
        return f"删除连线 ({self.edge_id})"
