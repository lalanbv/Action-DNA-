"""UndoManager — 撤销/重做管理器（Command 模式双栈实现）。"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

from src.core.editor.commands.edit_command import EditCommand
from src.utils.i18n import t

logger = logging.getLogger(__name__)


@dataclass
class UndoManagerConfig:
    """撤销管理器配置。"""

    max_depth: int = 100
    merge_interval_ms: float = 500


class UndoManager:
    """撤销/重做管理器。

    维护 _undo_stack 和 _redo_stack 双栈。
    新操作清空 redo 栈；命令可在时间窗口内合并。
    栈变化时通过回调通知 UI。
    """

    def __init__(self, config: UndoManagerConfig | None = None) -> None:
        self._config = config or UndoManagerConfig()
        self._undo_stack: deque[EditCommand] = deque(maxlen=self._config.max_depth)
        self._redo_stack: deque[EditCommand] = deque(maxlen=self._config.max_depth)
        self._change_callbacks: list[Callable] = []
        self._last_execute_time: float = 0.0

    def execute(self, command: EditCommand) -> None:
        now = time.monotonic()
        merged = False
        if self._undo_stack and self._can_merge(self._undo_stack[-1], command, now) and self._undo_stack[-1].merge(command):
            merged = True
            logger.debug(t("editor.log.command_merged", desc=command.description))

        if not merged:
            command.execute()
            self._undo_stack.append(command)

        self._redo_stack.clear()
        self._last_execute_time = now
        self._notify_change()

    def undo(self) -> EditCommand | None:
        if not self._undo_stack:
            return None
        command = self._undo_stack.pop()
        command.undo()
        self._redo_stack.append(command)
        logger.debug(t("editor.log.undo", desc=command.description))
        self._notify_change()
        return command

    def redo(self) -> EditCommand | None:
        if not self._redo_stack:
            return None
        command = self._redo_stack.pop()
        command.execute()
        self._undo_stack.append(command)
        logger.debug(t("editor.log.redo", desc=command.description))
        self._notify_change()
        return command

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0

    @property
    def undo_description(self) -> str | None:
        return self._undo_stack[-1].description if self._undo_stack else None

    @property
    def redo_description(self) -> str | None:
        return self._redo_stack[-1].description if self._redo_stack else None

    @property
    def undo_count(self) -> int:
        return len(self._undo_stack)

    @property
    def redo_count(self) -> int:
        return len(self._redo_stack)

    def on_change(self, callback: Callable) -> None:
        self._change_callbacks.append(callback)

    def remove_on_change(self, callback: Callable) -> None:
        self._change_callbacks = [cb for cb in self._change_callbacks if cb != callback]

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._notify_change()

    def _can_merge(self, prev: EditCommand, current: EditCommand, now: float) -> bool:
        if not prev.can_merge:
            return False
        if not isinstance(current, type(prev)):
            return False
        if (now - self._last_execute_time) * 1000 > self._config.merge_interval_ms:
            return False
        return True

    def _notify_change(self) -> None:
        for callback in self._change_callbacks:
            try:
                callback()
            except Exception:
                logger.exception(t("editor.log.callback_exception"))
