"""PluginInterface ABC + PluginMetadata + PluginPermissions — 插件生命周期接口。

调用者:
  - plugin_loader.py: 加载/卸载插件时调用 get_metadata/on_load/on_unload/register_nodes
  - 所有内置插件 (combat/__init__.py, navigation/__init__.py 等)
  - plugin_context.py: 通过 TYPE_CHECKING 引用
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.plugins.plugin_context import PluginContext
    from src.core.plugins.plugin_node_registry import PluginNodeRegistry


@dataclass(frozen=True)
class PluginPermissions:
    """插件权限声明（不可变）。

    每个权限对应一种系统资源的访问能力。
    未声明的权限在运行时会被 PluginContext 拒绝。
    """

    screen_capture: bool = False
    template_matcher: bool = False
    input_control: bool = False
    events: bool = False
    file_read: bool = False
    file_write: bool = False
    network: bool = False

    def to_set(self) -> set[str]:
        """转换为权限字符串集合（与 PluginContext 兼容）。"""
        result: set[str] = set()
        if self.screen_capture:
            result.add("screen_capture")
        if self.template_matcher:
            result.add("template_matcher")
        if self.input_control:
            result.add("input_control")
        if self.events:
            result.add("events")
        if self.file_read:
            result.add("file_read")
        if self.file_write:
            result.add("file_write")
        if self.network:
            result.add("network")
        return result

    @classmethod
    def from_tuple(cls, perms: tuple[str, ...]) -> PluginPermissions:
        """从权限字符串元组创建（与 PluginMetadata.permissions 兼容）。"""
        perm_set = set(perms)
        return cls(
            screen_capture="screen_capture" in perm_set,
            template_matcher="template_matcher" in perm_set,
            input_control="input_control" in perm_set,
            events="events" in perm_set,
            file_read="file_read" in perm_set,
            file_write="file_write" in perm_set,
            network="network" in perm_set,
        )


@dataclass(frozen=True)
class PluginMetadata:
    """插件元数据（不可变）。

    与 plugin.json 清单一一对应。
    """

    plugin_id: str
    plugin_name: str
    version: str
    description: str = ""
    author: str = ""
    dependencies: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    min_app_version: str = "2.0.0"
    entry_class: str = "Plugin"

    @property
    def typed_permissions(self) -> PluginPermissions:
        """获取结构化权限对象。"""
        return PluginPermissions.from_tuple(self.permissions)


class PluginInterface(ABC):
    """插件抽象基类。

    生命周期:
        DISCOVERED -> LOADED -> ACTIVE -> UNLOADED

    - DISCOVERED: PluginLoader 扫描到 plugin.json 并解析了元数据
    - LOADED:     on_load() 成功，节点已注册到 NodeRegistry
    - ACTIVE:     插件正在参与执行
    - UNLOADED:   on_unload() 完成，节点已从 NodeRegistry 注销

    每个插件是一个 Python 包:
      plugin.json   — 清单文件（必需）
      __init__.py   — PluginInterface 实现（必需）
      descriptors/  — NodeDescriptor 子类（可选）
    """

    @abstractmethod
    def get_metadata(self) -> PluginMetadata:
        """返回插件元数据（在 DISCOVERED 阶段调用）。"""

    @abstractmethod
    def on_load(self, context: PluginContext) -> None:
        """插件加载钩子。

        在此阶段，插件应:
        1. 调用 context.registry.register() 注册所有节点描述符
        2. 调用 context.register_dialog() 注册自定义对话框（可选）
        3. 订阅事件（可选）
        4. 初始化插件内部状态

        抛出异常将导致插件加载失败（回退到 DISCOVERED 状态）。
        """

    @abstractmethod
    def on_unload(self) -> None:
        """插件卸载钩子。

        在此阶段，插件应:
        1. 释放资源（关闭文件、停止线程等）
        2. 取消事件订阅
        3. 清理插件内部状态

        NodeRegistry 中的节点注销由 PluginLoader 自动处理。
        """

    @abstractmethod
    def register_nodes(self, registry: PluginNodeRegistry) -> None:
        """向注册表注册节点描述符。

        命名空间规则:
        - 注册的 action_type 自动添加 "plugin_id." 前缀
        - 例如: combat 插件注册 "find_enemy" -> 全局键 "combat.find_enemy"
        """
