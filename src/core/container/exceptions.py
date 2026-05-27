"""DI 容器异常类型"""

from __future__ import annotations


class ServiceNotFoundError(KeyError):
    """请求的服务类型未在容器中注册。

    继承 KeyError 以保持与现有 ``except KeyError`` 处理器的兼容性。
    """

    def __init__(self, service_type: type) -> None:
        self.service_type = service_type
        super().__init__(f"Service not registered: {service_type.__name__}")
