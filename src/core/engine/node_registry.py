"""节点类型注册表 — ComfyUI NODE_CLASS_MAPPINGS 模式。

维护 {action_type: NodeDescriptor_subclass} 映射，支持运行时注册、
分类查询和插件卸载时的注销。
"""

from __future__ import annotations

import logging
import threading
from typing import Type

from src.core.engine.node_descriptor import NodeDescriptor
from src.utils.i18n import t

logger = logging.getLogger(__name__)


class NodeRegistry:
    """节点类型注册表。

    使用方式：
    1. 内置节点用 @auto_register 装饰器在模块加载时自动注册
    2. 插件节点在插件加载时调用 NodeRegistry.register()
    3. 所有注册完成后调用 freeze()，后续 get() 不再加锁
    4. 引擎通过 NodeRegistry.get() 获取描述符类
    5. UI 通过 NodeRegistry.palette() 获取分类节点列表
    """

    _lock = threading.Lock()
    _registry: dict[str, Type[NodeDescriptor]] = {}
    _categories: dict[str, list[str]] = {}
    _frozen: bool = False

    @classmethod
    def freeze(cls) -> None:
        """冻结注册表 — 所有描述符注册完成后调用。

        冻结后 get() 不再获取锁，直接读取。
        适用于启动完成后不再动态注册/注销的场景。
        """
        with cls._lock:
            cls._frozen = True
        logger.debug(t("engine.log.registry_frozen", type_count=len(cls._registry)))

    @classmethod
    def unfreeze(cls) -> None:
        """解冻注册表 — 用于测试或插件热重载。"""
        with cls._lock:
            cls._frozen = False

    @classmethod
    def register(cls, descriptor_class: Type[NodeDescriptor]) -> None:
        """注册一个节点描述符。

        如果 action_type 已注册则发出警告并覆盖。
        覆盖时会清理旧分类索引。
        冻结状态下会先解冻。
        """
        with cls._lock:
            if cls._frozen:
                cls._frozen = False
            atype = descriptor_class.action_type()
            if atype in cls._registry:
                existing = cls._registry[atype]
                logger.warning(
                    t(
                        "engine.log.node_type_already_registered",
                        action_type=atype,
                        existing=existing.__name__,
                        new=descriptor_class.__name__,
                    )
                )
                old_cat = existing.category()
                if old_cat in cls._categories:
                    cls._categories[old_cat] = [
                        t for t in cls._categories[old_cat] if t != atype
                    ]
                    if not cls._categories[old_cat]:
                        del cls._categories[old_cat]
            cls._registry[atype] = descriptor_class
            cat = descriptor_class.category()
            if atype not in cls._categories.setdefault(cat, []):
                cls._categories[cat].append(atype)
        logger.debug(t("engine.log.register_node", action_type=atype, class_name=descriptor_class.__name__, category=cat))

    @classmethod
    def get(cls, action_type: str) -> Type[NodeDescriptor]:
        """获取节点描述符类。未注册时抛出 KeyError。"""
        if cls._frozen:
            if action_type not in cls._registry:
                raise KeyError(
                    f"未注册的节点类型: '{action_type}'。"
                    f"已注册类型: {list(cls._registry.keys())}"
                )
            return cls._registry[action_type]
        with cls._lock:
            if action_type not in cls._registry:
                raise KeyError(
                    f"未注册的节点类型: '{action_type}'。"
                    f"已注册类型: {list(cls._registry.keys())}"
                )
            return cls._registry[action_type]

    @classmethod
    def has(cls, action_type: str) -> bool:
        """检查节点类型是否已注册。"""
        if cls._frozen:
            return action_type in cls._registry
        with cls._lock:
            return action_type in cls._registry

    @classmethod
    def palette(cls) -> dict[str, list[tuple[str, str]]]:
        """返回分类节点列表，供 UI 使用。

        返回: {"基础动作": [("CLICK_IMAGE", "点击图片"), ...], ...}
        """
        if cls._frozen:
            result: dict[str, list[tuple[str, str]]] = {}
            for cat, types in cls._categories.items():
                result[cat] = [
                    (t, cls._registry[t].display_name()) for t in types
                ]
            return result
        with cls._lock:
            result: dict[str, list[tuple[str, str]]] = {}
            for cat, types in cls._categories.items():
                result[cat] = [
                    (t, cls._registry[t].display_name()) for t in types
                ]
            return result

    @classmethod
    def all_types(cls) -> list[str]:
        """返回所有已注册的 action_type。"""
        if cls._frozen:
            return list(cls._registry.keys())
        with cls._lock:
            return list(cls._registry.keys())

    @classmethod
    def unregister(cls, action_type: str) -> None:
        """注销一个节点描述符（插件卸载时使用）。"""
        with cls._lock:
            if cls._frozen:
                cls._frozen = False
            if action_type not in cls._registry:
                return
            descriptor_class = cls._registry.pop(action_type)
            cat = descriptor_class.category()
            if cat in cls._categories:
                cls._categories[cat] = [
                    t for t in cls._categories[cat] if t != action_type
                ]
                if not cls._categories[cat]:
                    del cls._categories[cat]
        logger.info(t("engine.log.unregister_node", action_type=action_type))

    @classmethod
    def clear(cls) -> None:
        """清空所有注册（测试用）。"""
        with cls._lock:
            if cls._frozen:
                cls._frozen = False
            cls._registry.clear()
            cls._categories.clear()


def auto_register(cls: Type[NodeDescriptor]) -> Type[NodeDescriptor]:
    """类装饰器：自动注册到 NodeRegistry。"""
    NodeRegistry.register(cls)
    return cls
