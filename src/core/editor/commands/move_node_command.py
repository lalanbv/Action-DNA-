"""MoveNodeCommand — 移动节点编辑命令。"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowGraph

logger = logging.getLogger(__name__)


@dataclass
class MoveNodeCommand(EditCommand):
    """移动节点命令。支持合并：连续拖拽同一节点合并为一个命令。"""

    graph: FlowGraph
    node_id: str
    new_x: int
    new_y: int
    _old_x: int = 0
    _old_y: int = 0

    def execute(self) -> None:
        node = self.graph.get_node(self.node_id)
        if node:
            self._old_x, self._old_y = node.pos_x, node.pos_y
            node.pos_x = self.new_x
            node.pos_y = self.new_y

    def undo(self) -> None:
        node = self.graph.get_node(self.node_id)
        if node:
            node.pos_x = self._old_x
            node.pos_y = self._old_y

    @property
    def description(self) -> str:
        return f"移动节点 ({self.node_id})"

    @property
    def can_merge(self) -> bool:
        return True

    def merge(self, other: EditCommand) -> bool:
        if not isinstance(other, MoveNodeCommand):
            return False
        if other.node_id != self.node_id:
            return False
        self.new_x = other.new_x
        self.new_y = other.new_y
        node = self.graph.get_node(self.node_id)
        if node:
            node.pos_x = self.new_x
            node.pos_y = self.new_y
        return True
