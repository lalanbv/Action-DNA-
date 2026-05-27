"""服务生命周期枚举"""

from enum import Enum, auto


class ServiceLifetime(Enum):
    """服务实例的生命周期策略"""
    SINGLETON = auto()   # 全局唯一实例，首次请求时创建
    TRANSIENT = auto()   # 每次请求创建新实例
