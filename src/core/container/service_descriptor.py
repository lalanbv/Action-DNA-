"""服务描述符 — 注册到容器中的服务元数据"""

from __future__ import annotations

from typing import Any, Callable

from src.core.container.service_lifetime import ServiceLifetime


class ServiceDescriptor:
    """描述一个已注册的服务：如何创建、生命周期、是否已实例化"""

    __slots__ = (
        "service_type",
        "factory",
        "lifetime",
        "instance",
    )

    def __init__(
        self,
        service_type: type,
        factory: Callable[[], Any],
        lifetime: ServiceLifetime,
    ) -> None:
        self.service_type = service_type
        self.factory = factory
        self.lifetime = lifetime
        self.instance: Any = None
