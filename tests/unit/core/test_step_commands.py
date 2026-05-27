"""step_commands 单元测试。

覆盖 DeleteStepsCommand、MoveStepCommand、DuplicateStepCommand、
EditStepCommand、ClearStepsCommand 的 do/undo 对称性。
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from src.core.action import ActionType
from src.core.editor.undo_manager import UndoManager
from src.core.editor.commands.step_commands import (
    ClearStepsCommand,
    DeleteStepsCommand,
    DuplicateStepCommand,
    EditStepCommand,
    MoveStepCommand,
)
from src.core.step_types import BaseStep, ClickPosStep


def _make_step(pos_x: int = 100, pos_y: int = 200, **overrides) -> BaseStep:
    return ClickPosStep(pos_x=pos_x, pos_y=pos_y, recorded_duration=0.1, **overrides)


@pytest.fixture
def steps_store():
    """简单的 steps 列表 + getter/setter 回调。"""
    data = {"steps": [_make_step(pos_x=i * 10, pos_y=i * 20) for i in range(5)]}

    def get_steps() -> list[BaseStep]:
        return data["steps"]

    def set_steps(s: list[BaseStep]) -> None:
        data["steps"] = s

    return data, get_steps, set_steps


# ── DeleteStepsCommand ──────────────────────────────────────────


class TestDeleteStepsCommand:
    def test_delete_single(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = DeleteStepsCommand(
            _get_steps=get_steps, _set_steps=set_steps, _indices=[2]
        )
        cmd.execute()
        assert len(data["steps"]) == 4
        assert data["steps"][2].pos_x == 30  # was index 3

        cmd.undo()
        assert len(data["steps"]) == 5
        assert data["steps"][2].pos_x == 20

    def test_delete_multiple(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = DeleteStepsCommand(
            _get_steps=get_steps, _set_steps=set_steps, _indices=[1, 3]
        )
        cmd.execute()
        assert len(data["steps"]) == 3
        assert data["steps"][0].pos_x == 0
        assert data["steps"][1].pos_x == 20
        assert data["steps"][2].pos_x == 40

        cmd.undo()
        assert len(data["steps"]) == 5
        assert [s.pos_x for s in data["steps"]] == [0, 10, 20, 30, 40]

    def test_delete_all(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = DeleteStepsCommand(
            _get_steps=get_steps,
            _set_steps=set_steps,
            _indices=list(range(5)),
        )
        cmd.execute()
        assert len(data["steps"]) == 0

        cmd.undo()
        assert len(data["steps"]) == 5

    def test_description(self, steps_store):
        _, get_steps, set_steps = steps_store
        cmd1 = DeleteStepsCommand(
            _get_steps=get_steps, _set_steps=set_steps, _indices=[0]
        )
        assert "删除步骤" == cmd1.description

        cmd2 = DeleteStepsCommand(
            _get_steps=get_steps, _set_steps=set_steps, _indices=[0, 1, 2]
        )
        assert "3" in cmd2.description


# ── MoveStepCommand ──────────────────────────────────────────────


class TestMoveStepCommand:
    def test_move_down(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = MoveStepCommand(
            _get_steps=get_steps, _set_steps=set_steps, _from_index=1, _to_index=2
        )
        cmd.execute()
        assert data["steps"][1].pos_x == 20  # was index 2
        assert data["steps"][2].pos_x == 10  # was index 1

        cmd.undo()
        assert data["steps"][1].pos_x == 10
        assert data["steps"][2].pos_x == 20

    def test_move_up(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = MoveStepCommand(
            _get_steps=get_steps, _set_steps=set_steps, _from_index=3, _to_index=2
        )
        cmd.execute()
        assert data["steps"][2].pos_x == 30
        assert data["steps"][3].pos_x == 20

        cmd.undo()
        assert data["steps"][2].pos_x == 20
        assert data["steps"][3].pos_x == 30

    def test_move_out_of_bounds(self, steps_store):
        data, get_steps, set_steps = steps_store
        original = list(data["steps"])
        cmd = MoveStepCommand(
            _get_steps=get_steps, _set_steps=set_steps, _from_index=10, _to_index=0
        )
        cmd.execute()
        assert data["steps"] == original


# ── DuplicateStepCommand ─────────────────────────────────────────


class TestDuplicateStepCommand:
    def test_duplicate(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = DuplicateStepCommand(
            _get_steps=get_steps, _set_steps=set_steps, _index=1
        )
        cmd.execute()
        assert len(data["steps"]) == 6
        assert data["steps"][1].pos_x == 10
        assert data["steps"][2].pos_x == 10  # duplicate

        cmd.undo()
        assert len(data["steps"]) == 5
        assert data["steps"][1].pos_x == 10
        assert data["steps"][2].pos_x == 20

    def test_duplicate_last(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = DuplicateStepCommand(
            _get_steps=get_steps, _set_steps=set_steps, _index=4
        )
        cmd.execute()
        assert len(data["steps"]) == 6
        assert data["steps"][5].pos_x == 40


# ── EditStepCommand ──────────────────────────────────────────────


class TestEditStepCommand:
    def test_edit(self, steps_store):
        data, get_steps, set_steps = steps_store
        new_step = _make_step(pos_x=999, pos_y=888)
        cmd = EditStepCommand(
            _get_steps=get_steps,
            _set_steps=set_steps,
            _index=2,
            _new_step=new_step,
        )
        cmd.execute()
        assert data["steps"][2].pos_x == 999

        cmd.undo()
        assert data["steps"][2].pos_x == 20

    def test_redo(self, steps_store):
        data, get_steps, set_steps = steps_store
        new_step = _make_step(pos_x=777)
        cmd = EditStepCommand(
            _get_steps=get_steps,
            _set_steps=set_steps,
            _index=0,
            _new_step=new_step,
        )
        cmd.execute()
        assert data["steps"][0].pos_x == 777

        cmd.undo()
        assert data["steps"][0].pos_x == 0

        cmd.execute()  # redo
        assert data["steps"][0].pos_x == 777


# ── ClearStepsCommand ────────────────────────────────────────────


class TestClearStepsCommand:
    def test_clear_and_undo(self, steps_store):
        data, get_steps, set_steps = steps_store
        cmd = ClearStepsCommand(_get_steps=get_steps, _set_steps=set_steps)
        cmd.execute()
        assert len(data["steps"]) == 0

        cmd.undo()
        assert len(data["steps"]) == 5
        assert data["steps"][0].pos_x == 0

    def test_clear_description(self, steps_store):
        _, get_steps, set_steps = steps_store
        cmd = ClearStepsCommand(_get_steps=get_steps, _set_steps=set_steps)
        assert "清空" in cmd.description


# ── UndoManager 集成（step_commands）─────────────────────────────


class TestStepCommandsUndoIntegration:
    def test_undo_redo_delete(self, steps_store):
        data, get_steps, set_steps = steps_store
        manager = UndoManager()
        cmd = DeleteStepsCommand(
            _get_steps=get_steps, _set_steps=set_steps, _indices=[1, 3]
        )
        manager.execute(cmd)
        assert len(data["steps"]) == 3

        manager.undo()
        assert len(data["steps"]) == 5

        manager.redo()
        assert len(data["steps"]) == 3

    def test_multiple_operations(self, steps_store):
        data, get_steps, set_steps = steps_store
        manager = UndoManager()

        # 删除步骤
        manager.execute(
            DeleteStepsCommand(
                _get_steps=get_steps, _set_steps=set_steps, _indices=[2]
            )
        )
        assert len(data["steps"]) == 4

        # 复制步骤
        manager.execute(
            DuplicateStepCommand(
                _get_steps=get_steps, _set_steps=set_steps, _index=0
            )
        )
        assert len(data["steps"]) == 5

        # 撤销复制
        manager.undo()
        assert len(data["steps"]) == 4

        # 撤销删除
        manager.undo()
        assert len(data["steps"]) == 5
        assert data["steps"][2].pos_x == 20

    def test_clear_redo_stack_on_new_command(self, steps_store):
        data, get_steps, set_steps = steps_store
        manager = UndoManager()

        manager.execute(
            DeleteStepsCommand(
                _get_steps=get_steps, _set_steps=set_steps, _indices=[0]
            )
        )
        manager.undo()
        assert manager.can_redo

        # 新操作清空 redo 栈
        manager.execute(
            DeleteStepsCommand(
                _get_steps=get_steps, _set_steps=set_steps, _indices=[4]
            )
        )
        assert not manager.can_redo
