"""CompositeCommand — 复合编辑命令（批量操作的原子撤销/重做）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from src.core.editor.commands.edit_command import EditCommand

logger = logging.getLogger(__name__)


@dataclass
class CompositeCommand(EditCommand):
    """复合命令。将多个子命令组合为一个原子操作，统一执行/撤销。

    execute() 按顺序执行所有子命令，undo() 按逆序撤销。
    """

    _commands: list[EditCommand] = field(default_factory=list)
    _label: str = ""

    def add(self, cmd: EditCommand) -> None:
        self._commands.append(cmd)

    def execute(self) -> None:
        for cmd in self._commands:
            cmd.execute()

    def undo(self) -> None:
        for cmd in reversed(self._commands):
            cmd.undo()

    @property
    def description(self) -> str:
        if self._label:
            return self._label
        count = len(self._commands)
        if count == 0:
            return "空复合命令"
        if count == 1:
            return self._commands[0].description
        return f"复合操作 ({count} 个子命令)"

    @property
    def commands(self) -> list[EditCommand]:
        return list(self._commands)
