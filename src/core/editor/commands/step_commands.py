"""step_commands — 录制页面步骤编辑命令（Command 模式）。

为 RecordPage 的步骤操作提供撤销/重做支持。
命令不持有 UI 引用，仅操作 steps 列表（通过 getter/setter 回调）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from src.core.editor.commands.edit_command import EditCommand
from src.core.step_types import BaseStep

GetSteps = Callable[[], list[BaseStep]]
SetSteps = Callable[[list[BaseStep]], None]


@dataclass
class DeleteStepsCommand(EditCommand):
    """删除一个或多个步骤（支持批量删除的原子撤销/重做）。"""

    _get_steps: GetSteps
    _set_steps: SetSteps
    _indices: list[int] = field(default_factory=list)
    _removed: list[tuple[int, BaseStep]] = field(default_factory=list, init=False, repr=False)

    def execute(self) -> None:
        steps = list(self._get_steps())
        self._removed = [(i, steps[i]) for i in sorted(self._indices) if i < len(steps)]
        remaining = [s for idx, s in enumerate(steps) if idx not in set(self._indices)]
        self._set_steps(remaining)

    def undo(self) -> None:
        steps = list(self._get_steps())
        for idx, step in self._removed:
            steps.insert(idx, step)
        self._set_steps(steps)

    @property
    def description(self) -> str:
        count = len(self._indices)
        return f"删除 {count} 个步骤" if count > 1 else "删除步骤"


@dataclass
class MoveStepCommand(EditCommand):
    """移动步骤（上移/下移）。"""

    _get_steps: GetSteps
    _set_steps: SetSteps
    _from_index: int = 0
    _to_index: int = 0

    def execute(self) -> None:
        steps = list(self._get_steps())
        if self._from_index >= len(steps) or self._to_index >= len(steps):
            return
        steps[self._from_index], steps[self._to_index] = (
            steps[self._to_index],
            steps[self._from_index],
        )
        self._set_steps(steps)

    def undo(self) -> None:
        self.execute()

    @property
    def description(self) -> str:
        direction = "上移" if self._to_index < self._from_index else "下移"
        return f"{direction}步骤 #{self._from_index + 1}"


@dataclass
class DuplicateStepCommand(EditCommand):
    """复制步骤。"""

    _get_steps: GetSteps
    _set_steps: SetSteps
    _index: int = 0
    _dup_index: int = field(default=-1, init=False, repr=False)

    def execute(self) -> None:
        from dataclasses import replace as dc_replace

        steps = list(self._get_steps())
        if self._index >= len(steps):
            return
        self._dup_index = self._index + 1
        steps.insert(self._dup_index, dc_replace(steps[self._index]))
        self._set_steps(steps)

    def undo(self) -> None:
        steps = list(self._get_steps())
        if 0 <= self._dup_index < len(steps):
            steps.pop(self._dup_index)
            self._set_steps(steps)

    @property
    def description(self) -> str:
        return f"复制步骤 #{self._index + 1}"


@dataclass
class EditStepCommand(EditCommand):
    """编辑步骤（双击修改）。"""

    _get_steps: GetSteps
    _set_steps: SetSteps
    _index: int = 0
    _new_step: BaseStep = field(default=None)  # type: ignore[assignment]
    _old_step: BaseStep = field(default=None, init=False, repr=False)  # type: ignore[assignment]

    def execute(self) -> None:
        steps = list(self._get_steps())
        if self._index >= len(steps):
            return
        self._old_step = steps[self._index]
        steps[self._index] = self._new_step
        self._set_steps(steps)

    def undo(self) -> None:
        steps = list(self._get_steps())
        if self._index < len(steps):
            steps[self._index] = self._old_step
            self._set_steps(steps)

    @property
    def description(self) -> str:
        return f"编辑步骤 #{self._index + 1}"


@dataclass
class ClearStepsCommand(EditCommand):
    """清空所有步骤。"""

    _get_steps: GetSteps
    _set_steps: SetSteps
    _cleared: list[BaseStep] = field(default_factory=list, init=False, repr=False)

    def execute(self) -> None:
        self._cleared = list(self._get_steps())
        self._set_steps([])

    def undo(self) -> None:
        self._set_steps(list(self._cleared))

    @property
    def description(self) -> str:
        return "清空所有步骤"
