"""轻量 DI 容器 — 服务注册、延迟创建、按需解析"""

from __future__ import annotations

import logging
import threading
from typing import Callable, TypeVar

from src.core.container.exceptions import ServiceNotFoundError
from src.core.container.service_descriptor import ServiceDescriptor
from src.core.container.service_lifetime import ServiceLifetime

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ServiceContainer:
    """服务容器：注册工厂 + 按类型解析实例

    用法::

        container = ServiceContainer()
        container.register(EventBus, lambda: EventBus(), ServiceLifetime.SINGLETON)
        bus = container.get(EventBus)
    """

    def __init__(self) -> None:
        self._descriptors: dict[type, ServiceDescriptor] = {}
        self._lock = threading.Lock()

    def register(
        self,
        service_type: type[T],
        factory: Callable[[], T],
        lifetime: ServiceLifetime = ServiceLifetime.SINGLETON,
    ) -> None:
        """注册服务工厂"""
        with self._lock:
            self._descriptors[service_type] = ServiceDescriptor(
                service_type, factory, lifetime,
            )

    def register_instance(self, service_type: type[T], instance: T) -> None:
        """直接注册已创建的实例（单例）"""
        with self._lock:
            desc = ServiceDescriptor(
                service_type, lambda: instance, ServiceLifetime.SINGLETON,
            )
            desc.instance = instance
            self._descriptors[service_type] = desc

    def get(self, service_type: type[T]) -> T:
        """按类型解析服务实例"""
        desc = self._descriptors.get(service_type)
        if desc is None:
            raise ServiceNotFoundError(service_type)
        return self._resolve(desc)

    def has(self, service_type: type) -> bool:
        """检查服务是否已注册"""
        return service_type in self._descriptors

    def try_get(self, service_type: type[T]) -> T | None:
        """按类型解析服务实例，未注册或未实例化则返回 None。"""
        desc = self._descriptors.get(service_type)
        if desc is None:
            return None
        return self._resolve(desc)

    def _resolve(self, desc: ServiceDescriptor) -> object:
        """解析服务实例 — 单例用双重检查锁，瞬态直接调用工厂。"""
        if desc.lifetime == ServiceLifetime.SINGLETON:
            if desc.instance is None:
                with self._lock:
                    if desc.instance is None:
                        desc.instance = desc.factory()
                        logger.debug("Created singleton: %s", desc.service_type.__name__)
            return desc.instance
        return desc.factory()

    def is_resolved(self, service_type: type) -> bool:
        """检查单例是否已实例化"""
        desc = self._descriptors.get(service_type)
        return desc is not None and desc.instance is not None

    def snapshot(self) -> dict[str, bool]:
        """返回服务解析状态快照（用于调试）"""
        return {
            t.__name__: (d.instance is not None)
            for t, d in self._descriptors.items()
        }
