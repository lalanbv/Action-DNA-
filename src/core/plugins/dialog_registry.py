"""DialogRegistry — 节点对话框注册表。

调用者:
  - plugin_context.py register_dialog() 方法
  - plugin_loader.py 卸载时清理对话框
"""

from __future__ import annotations

import logging
from typing import Type

logger = logging.getLogger(__name__)


class DialogRegistry:
    """节点对话框注册表。

    管理节点类型到配置对话框类的映射。
    如果某节点类型没有注册自定义对话框，使用基于 input_types() 自动生成的通用对话框。
    """

    _registry: dict[str, Type] = {}

    @classmethod
    def register(cls, action_type: str, dialog_class: Type) -> None:
        """注册对话框。"""
        if action_type in cls._registry:
            logger.warning(
                "对话框已注册: '%s'，将被覆盖为 %s",
                action_type,
                dialog_class.__name__,
            )
        cls._registry[action_type] = dialog_class

    @classmethod
    def get(cls, action_type: str) -> Type | None:
        """获取对话框类，未注册则返回 None。"""
        return cls._registry.get(action_type)

    @classmethod
    def has(cls, action_type: str) -> bool:
        """检查是否有自定义对话框。"""
        return action_type in cls._registry

    @classmethod
    def unregister(cls, action_type: str) -> None:
        """注销对话框（插件卸载时调用）。"""
        cls._registry.pop(action_type, None)
