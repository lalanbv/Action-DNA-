"""插件系统核心 — 约定式插件架构。"""

from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata, PluginPermissions
from src.core.plugins.capabilities import (
    DescriptorPlugin,
    DialogPlugin,
    EventHandlerPlugin,
    SettingsPlugin,
)

__all__ = [
    "DescriptorPlugin",
    "DialogPlugin",
    "EventHandlerPlugin",
    "PluginInterface",
    "PluginMetadata",
    "PluginPermissions",
    "SettingsPlugin",
]
