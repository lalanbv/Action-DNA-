"""UndoManager 单元测试。

覆盖：execute/undo/redo 双栈、命令合并、回调通知、边界情况。
"""

from unittest.mock import MagicMock

from src.core.editor.commands.edit_command import EditCommand
from src.core.editor.undo_manager import UndoManager, UndoManagerConfig


class _StubCommand(EditCommand):
    """测试用命令 — 记录 execute/undo 调用次数。"""

    def __init__(self, description: str = "stub", can_merge_flag: bool = False) -> None:
        self._desc = description
        self._mergeable = can_merge_flag
        self.execute_count = 0
        self.undo_count = 0

    def execute(self) -> None:
        self.execute_count += 1

    def undo(self) -> None:
        self.undo_count += 1

    @property
    def description(self) -> str:
        return self._desc

    @property
    def can_merge(self) -> bool:
        return self._mergeable


class _MergeableCommand(EditCommand):
    """可合并的命令 — 模拟连续移动节点。"""

    def __init__(self, value: int) -> None:
        self.value = value
        self.execute_count = 0
        self.undo_count = 0

    def execute(self) -> None:
        self.execute_count += 1

    def undo(self) -> None:
        self.undo_count += 1

    @property
    def description(self) -> str:
        return f"mergeable({self.value})"

    @property
    def can_merge(self) -> bool:
        return True

    def merge(self, other: EditCommand) -> bool:
        if not isinstance(other, _MergeableCommand):
            return False
        self.value = other.value
        return True


# ============================================================
# 基本操作
# ============================================================


class TestBasicOperations:
    def test_execute_command(self) -> None:
        mgr = UndoManager()
        cmd = _StubCommand()
        mgr.execute(cmd)
        assert cmd.execute_count == 1
        assert mgr.can_undo
        assert not mgr.can_redo

    def test_undo_command(self) -> None:
        mgr = UndoManager()
        cmd = _StubCommand()
        mgr.execute(cmd)
        result = mgr.undo()
        assert result is not None
        assert cmd.undo_count == 1
        assert not mgr.can_undo
        assert mgr.can_redo

    def test_redo_command(self) -> None:
        mgr = UndoManager()
        cmd = _StubCommand()
        mgr.execute(cmd)
        mgr.undo()
        result = mgr.redo()
        assert result is not None
        assert cmd.execute_count == 2  # execute + redo
        assert mgr.can_undo
        assert not mgr.can_redo

    def test_undo_empty_returns_none(self) -> None:
        mgr = UndoManager()
        assert mgr.undo() is None

    def test_redo_empty_returns_none(self) -> None:
        mgr = UndoManager()
        assert mgr.redo() is None

    def test_execute_clears_redo_stack(self) -> None:
        mgr = UndoManager()
        mgr.execute(_StubCommand("a"))
        mgr.execute(_StubCommand("b"))
        mgr.undo()  # undo b → redo stack has b
        assert mgr.can_redo
        mgr.execute(_StubCommand("c"))  # should clear redo
        assert not mgr.can_redo

    def test_multiple_undo_redo(self) -> None:
        mgr = UndoManager()
        cmds = [_StubCommand(f"cmd{i}") for i in range(5)]
        for cmd in cmds:
            mgr.execute(cmd)

        assert mgr.undo_count == 5
        mgr.undo()
        mgr.undo()
        assert mgr.undo_count == 3
        assert mgr.redo_count == 2

        mgr.redo()
        assert mgr.undo_count == 4
        assert mgr.redo_count == 1


# ============================================================
# 命令合并
# ============================================================


class TestCommandMerging:
    def test_mergeable_commands_merged(self) -> None:
        mgr = UndoManager()
        a = _MergeableCommand(10)
        b = _MergeableCommand(20)
        mgr.execute(a)
        mgr.execute(b)
        # b should have been merged into a, not executed separately
        assert a.value == 20
        assert mgr.undo_count == 1  # only one command on stack

    def test_merge_disabled_for_non_mergeable(self) -> None:
        mgr = UndoManager()
        mgr.execute(_StubCommand(can_merge_flag=False))
        mgr.execute(_StubCommand(can_merge_flag=False))
        assert mgr.undo_count == 2

    def test_merge_only_same_type(self) -> None:
        mgr = UndoManager()
        mgr.execute(_MergeableCommand(1))
        mgr.execute(_StubCommand(can_merge_flag=True))
        assert mgr.undo_count == 2

    def test_merge_respects_interval(self) -> None:
        import time

        config = UndoManagerConfig(merge_interval_ms=0)
        mgr = UndoManager(config)
        mgr.execute(_MergeableCommand(1))
        time.sleep(0.01)
        mgr.execute(_MergeableCommand(2))
        assert mgr.undo_count == 2


# ============================================================
# 回调通知
# ============================================================


class TestCallbacks:
    def test_on_change_called_on_execute(self) -> None:
        mgr = UndoManager()
        cb = MagicMock()
        mgr.on_change(cb)
        mgr.execute(_StubCommand())
        cb.assert_called_once()

    def test_on_change_called_on_undo(self) -> None:
        mgr = UndoManager()
        cb = MagicMock()
        mgr.on_change(cb)
        mgr.execute(_StubCommand())
        mgr.undo()
        assert cb.call_count == 2

    def test_on_change_called_on_redo(self) -> None:
        mgr = UndoManager()
        cb = MagicMock()
        mgr.on_change(cb)
        mgr.execute(_StubCommand())
        mgr.undo()
        mgr.redo()
        assert cb.call_count == 3

    def test_on_change_called_on_clear(self) -> None:
        mgr = UndoManager()
        cb = MagicMock()
        mgr.on_change(cb)
        mgr.execute(_StubCommand())
        mgr.clear()
        assert cb.call_count == 2

    def test_remove_on_change(self) -> None:
        mgr = UndoManager()
        cb = MagicMock()
        mgr.on_change(cb)
        mgr.remove_on_change(cb)
        mgr.execute(_StubCommand())
        cb.assert_not_called()

    def test_callback_exception_does_not_crash(self) -> None:
        mgr = UndoManager()
        mgr.on_change(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        mgr.execute(_StubCommand())  # should not raise


# ============================================================
# 属性
# ============================================================


class TestProperties:
    def test_undo_description(self) -> None:
        mgr = UndoManager()
        mgr.execute(_StubCommand("move node"))
        assert mgr.undo_description == "move node"

    def test_undo_description_empty(self) -> None:
        mgr = UndoManager()
        assert mgr.undo_description is None

    def test_redo_description(self) -> None:
        mgr = UndoManager()
        mgr.execute(_StubCommand("move node"))
        mgr.undo()
        assert mgr.redo_description == "move node"

    def test_redo_description_empty(self) -> None:
        mgr = UndoManager()
        assert mgr.redo_description is None

    def test_undo_redo_counts(self) -> None:
        mgr = UndoManager()
        assert mgr.undo_count == 0
        assert mgr.redo_count == 0
        mgr.execute(_StubCommand())
        mgr.execute(_StubCommand())
        assert mgr.undo_count == 2
        mgr.undo()
        assert mgr.undo_count == 1
        assert mgr.redo_count == 1


# ============================================================
# 边界情况
# ============================================================


class TestEdgeCases:
    def test_clear(self) -> None:
        mgr = UndoManager()
        mgr.execute(_StubCommand())
        mgr.execute(_StubCommand())
        mgr.undo()
        mgr.clear()
        assert not mgr.can_undo
        assert not mgr.can_redo
        assert mgr.undo_count == 0
        assert mgr.redo_count == 0

    def test_max_depth(self) -> None:
        config = UndoManagerConfig(max_depth=3)
        mgr = UndoManager(config)
        for i in range(10):
            mgr.execute(_StubCommand(f"cmd{i}"))
        assert mgr.undo_count == 3

    def test_undo_redo_cycle(self) -> None:
        mgr = UndoManager()
        cmd = _StubCommand()
        mgr.execute(cmd)
        mgr.undo()
        mgr.redo()
        mgr.undo()
        mgr.redo()
        assert cmd.execute_count == 3  # 1 initial + 2 redo
        assert cmd.undo_count == 2  # 2 undo
