"""ServiceProvider 协议 — 页面通过此接口访问服务，不直接引用 PanelApp"""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

T = TypeVar("T")


@runtime_checkable
class ServiceProvider(Protocol):
    """页面服务访问接口

    页面通过此协议获取共享服务，避免与 PanelApp 具体实现耦合。
    """

    def get(self, service_type: type[T]) -> T:
        """按类型解析服务实例"""
        ...

    @property
    def event_bus(self): ...

    @property
    def executor(self): ...

    @property
    def capture(self): ...

    @property
    def matcher(self): ...

    @property
    def hotkey_manager(self): ...

    @property
    def toast_manager(self): ...

    @property
    def plugin_loader(self): ...

    @property
    def input_ctrl(self): ...

    @property
    def node_registry(self): ...

    @property
    def root(self): ...

    def navigate_to(self, page_id: str, **kwargs) -> None: ...
