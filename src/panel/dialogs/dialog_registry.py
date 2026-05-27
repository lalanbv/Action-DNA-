"""DialogRegistry — 步骤对话框注册表。"""

from __future__ import annotations

import logging
from typing import Type

from src.core.action import ActionType
from src.panel.dialogs.base_dialog import StepDialogBase

logger = logging.getLogger(__name__)


class DialogRegistry:
    """步骤对话框注册表。

    管理 ActionType → StepDialogBase 子类的映射。
    内置对话框在模块加载时自动注册。
    """

    _registry: dict[ActionType, Type[StepDialogBase]] = {}

    @classmethod
    def register(cls, action_type: ActionType, dialog_class: Type[StepDialogBase]) -> None:
        cls._registry[action_type] = dialog_class

    @classmethod
    def get(cls, action_type: ActionType) -> Type[StepDialogBase] | None:
        return cls._registry.get(action_type)

    @classmethod
    def has(cls, action_type: ActionType) -> bool:
        return action_type in cls._registry

    @classmethod
    def unregister(cls, action_type: ActionType) -> None:
        cls._registry.pop(action_type, None)

    @classmethod
    def all_registered(cls) -> dict[ActionType, Type[StepDialogBase]]:
        return dict(cls._registry)
