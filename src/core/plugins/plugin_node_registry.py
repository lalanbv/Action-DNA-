"""PluginNodeRegistry — 插件命名空间注册表。

调用者:
  - plugin_context.py: registry 属性创建 PluginNodeRegistry 实例
  - 所有插件 register_nodes() 方法中使用
  - plugin_loader.py 间接通过 PluginContext 使用
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from src.core.engine.node_descriptor import NodeDescriptor
    from src.core.engine.node_registry import NodeRegistry


class PluginNodeRegistry:
    """插件命名空间注册表。

    包装全局 NodeRegistry，自动为 action_type 添加插件前缀。

    命名空间规则:
    - 插件 "combat" 注册 "find_enemy" -> 全局键 "combat.find_enemy"
    - 内置节点无前缀，如 "CLICK_IMAGE"、"WAIT" 等
    """

    def __init__(
        self,
        plugin_id: str,
        delegate: NodeRegistry,
        on_register: Callable[[str], None] | None = None,
    ) -> None:
        self._plugin_id = plugin_id
        self._delegate = delegate
        self._on_register = on_register

    def register(self, descriptor_class: type[NodeDescriptor]) -> None:
        """注册节点描述符（自动添加命名空间前缀）。

        创建代理子类，覆盖 action_type() 返回完整键，
        避免修改原始描述符类。
        """
        local_type = descriptor_class.action_type()
        full_type = f"{self._plugin_id}.{local_type}"

        # 创建带完整类型键的代理子类
        proxy = type(
            f"{descriptor_class.__name__}Proxy",
            (descriptor_class,),
            {},
        )

        # 覆盖 action_type 返回完整键
        @classmethod  # type: ignore[misc]
        def patched_action_type(cls: type) -> str:
            return full_type

        proxy.action_type = patched_action_type  # type: ignore[attr-defined, assignment]

        self._delegate.register(proxy)

        if self._on_register:
            self._on_register(full_type)

    def register_raw(self, descriptor_class: type[NodeDescriptor]) -> None:
        """直接注册到全局注册表（不加前缀）。

        仅用于内置插件的向后兼容，第三方插件不应使用。
        """
        self._delegate.register(descriptor_class)
        if self._on_register:
            self._on_register(descriptor_class.action_type())
