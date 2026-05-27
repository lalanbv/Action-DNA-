"""插件能力 Mixin — 声明式能力检测（参考 pluggy + OctoPrint）。

插件可通过多继承这些 Mixin 向系统声明自己具备的能力。
PluginLoader 和 PluginPage 可通过 isinstance() 检测能力，
无需鸭子类型或 hasattr 探测。

用法::

    class MyPlugin(PluginInterface, SettingsPlugin, DescriptorPlugin):
        def get_settings_schema(self) -> dict:
            return {"interval": {"type": "number", "default": 1.0}}

        def get_descriptors(self) -> list[type[NodeDescriptor]]:
            return [MyDescriptor]

所有 Mixin 方法均有默认空实现，插件只需覆盖自己关心的。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from src.core.engine.node_descriptor import NodeDescriptor


class SettingsPlugin:
    """插件有设置 UI — 可在 PluginPage 中显示设置面板。"""

    def get_settings_schema(self) -> dict[str, Any]:
        """返回设置字段定义（JSON Schema 风格）。

        格式::

            {
                "field_name": {
                    "type": "number|boolean|string|select",
                    "label": "显示名称",
                    "default": 默认值,
                    "min": 0,          # number 类型可选
                    "max": 100,        # number 类型可选
                    "step": 0.1,       # number 类型可选
                    "options": [...],  # select 类型必需
                },
                ...
            }
        """
        return {}

    def get_settings(self) -> dict[str, Any]:
        """返回当前设置值。"""
        return {}

    def apply_settings(self, values: dict[str, Any]) -> None:
        """应用新设置值。"""


class DescriptorPlugin:
    """插件注册节点描述符 — 显式声明描述符列表。

    与 register_nodes() 不同，此 Mixin 允许 PluginLoader
    在不实例化插件的情况下就知道插件提供了哪些描述符。
    """

    def get_descriptors(self) -> list[type[NodeDescriptor]]:
        """返回此插件提供的所有描述符类。"""
        return []


class DialogPlugin:
    """插件注册自定义对话框 — 声明对话框映射。"""

    def get_dialogs(self) -> dict[str, type]:
        """返回 action_type -> dialog_class 映射。"""
        return {}


class EventHandlerPlugin:
    """插件处理事件 — 声明事件处理函数。

    系统可在 on_load 时自动订阅这些处理器。
    """

    def get_event_handlers(self) -> dict[type, Callable[..., Any]]:
        """返回 event_type -> handler 映射。"""
        return {}
