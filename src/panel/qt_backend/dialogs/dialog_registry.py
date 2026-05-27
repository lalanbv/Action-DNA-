"""QtDialogRegistry — Qt 后端步骤对话框注册表。

根据 backend_selector 选择 tkinter 或 Qt 对话框类。
插件注册的对话框也通过此类统一管理。
"""

from __future__ import annotations

import logging
from typing import Type

from src.core.action import ActionType
from src.panel.backend_selector import use_qt_backend

logger = logging.getLogger(__name__)

# 延迟导入，避免循环依赖
_TK_DIALOG_REGISTRY: type | None = None
_QT_DIALOG_MAP: dict[ActionType, type] | None = None


def _get_tk_registry() -> type:
    global _TK_DIALOG_REGISTRY
    if _TK_DIALOG_REGISTRY is None:
        from src.panel.dialogs.dialog_registry import DialogRegistry
        _TK_DIALOG_REGISTRY = DialogRegistry
    return _TK_DIALOG_REGISTRY


def _get_qt_dialog_map() -> dict[ActionType, type]:
    global _QT_DIALOG_MAP
    if _QT_DIALOG_MAP is None:
        from src.panel.qt_backend.dialogs.step_dialogs import get_qt_dialog_class
        from src.core.action import ActionType
        _QT_DIALOG_MAP = {}
        for at in ActionType:
            cls = get_qt_dialog_class(at)
            if cls is not None:
                _QT_DIALOG_MAP[at] = cls
    return _QT_DIALOG_MAP


class QtDialogRegistry:
    """双后端步骤对话框注册表。

    根据 use_qt_backend() 自动选择对应后端的对话框类。
    插件通过 register_plugin_dialog() 注册自定义对话框。
    """

    _plugin_overrides: dict[ActionType, type] = {}

    @classmethod
    def get(cls, action_type: ActionType) -> type | None:
        if action_type in cls._plugin_overrides:
            return cls._plugin_overrides[action_type]
        if use_qt_backend():
            return _get_qt_dialog_map().get(action_type)
        return _get_tk_registry().get(action_type)

    @classmethod
    def has(cls, action_type: ActionType) -> bool:
        return cls.get(action_type) is not None

    @classmethod
    def register_plugin(
        cls, action_type: ActionType, dialog_class: type,
    ) -> None:
        cls._plugin_overrides[action_type] = dialog_class
        logger.info("Plugin dialog registered: %s → %s", action_type.value, dialog_class.__name__)

    @classmethod
    def unregister_plugin(cls, action_type: ActionType) -> None:
        cls._plugin_overrides.pop(action_type, None)

    @classmethod
    def all_registered(cls) -> dict[ActionType, type]:
        result: dict[ActionType, type] = {}
        if use_qt_backend():
            result.update(_get_qt_dialog_map())
        else:
            result.update(_get_tk_registry().all_registered())
        result.update(cls._plugin_overrides)
        return result
