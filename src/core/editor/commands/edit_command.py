"""EditCommand ABC — 所有编辑命令的抽象基类（Command 模式）。"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EditCommand(ABC):
    """编辑命令抽象基类。

    每个编辑操作封装为一个命令对象，记录执行和撤销所需信息。
    命令必须满足：
    - execute() 可重复调用（redo 时使用）
    - undo() 可完整恢复到执行前的状态
    - 命令不持有 UI 引用（仅操作数据模型）
    """

    @abstractmethod
    def execute(self) -> None:
        """执行命令（首次调用和 redo 时使用）。"""

    @abstractmethod
    def undo(self) -> None:
        """撤销命令，恢复到 execute() 之前的状态。"""

    @property
    def description(self) -> str:
        """命令描述（用于 UI 显示）。"""
        return self.__class__.__name__

    @property
    def can_merge(self) -> bool:
        """是否可与后续命令合并（用于连续操作优化）。"""
        return False

    def merge(self, other: EditCommand) -> bool:
        """尝试与另一个命令合并。返回 True 表示合并成功。"""
        return False
