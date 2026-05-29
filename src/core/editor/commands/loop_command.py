"""LoopChangedCommand — 循环模式变更命令，支持撤销/重做。"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowGraph, ensure_loop_edge, find_loop_edge, remove_loop_edge


@dataclass
class LoopChangedCommand(EditCommand):
    """循环模式变更命令。

    记录 loop / loop_count 的变更，以及 loop 边的增删。
    """

    graph: FlowGraph
    new_loop: bool
    new_loop_count: int
    _old_loop: bool = field(default=False, init=False, repr=False)
    _old_loop_count: int = field(default=0, init=False, repr=False)
    _old_edge_existed: bool = field(default=False, init=False, repr=False)

    def execute(self) -> None:
        self._old_loop = self.graph.loop
        self._old_loop_count = self.graph.loop_count
        self._old_edge_existed = find_loop_edge(self.graph) is not None

        self.graph.loop = self.new_loop
        self.graph.loop_count = self.new_loop_count
        if not self.new_loop:
            remove_loop_edge(self.graph)
        else:
            ensure_loop_edge(self.graph)

    def undo(self) -> None:
        self.graph.loop = self._old_loop
        self.graph.loop_count = self._old_loop_count
        # 恢复 loop 边状态
        loop_edge = find_loop_edge(self.graph)
        if self._old_edge_existed and loop_edge is None:
            ensure_loop_edge(self.graph)
        elif not self._old_edge_existed and loop_edge is not None:
            remove_loop_edge(self.graph)

    @property
    def description(self) -> str:
        return "修改循环模式"
