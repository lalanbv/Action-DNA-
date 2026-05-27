"""属性验证系统 — 受 Blender RNA PropertyRNA 启发。

提供类型检查、范围校验和描述信息的属性定义。
用于配置加载时验证用户输入，防止非法值静默通过。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, ClassVar

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PropertyDef:
    """属性定义 — 带类型检查和范围校验。"""

    name: str
    prop_type: type
    default: Any
    min_value: Any | None = None
    max_value: Any | None = None
    description: str = ""
    on_update: Callable[[str, Any, Any], None] | None = None

    def validate(self, value: Any) -> Any:
        """验证并转换值，不符合要求时抛出 ValueError。"""
        if not isinstance(value, self.prop_type):
            try:
                value = self.prop_type(value)
            except (ValueError, TypeError) as e:
                raise ValueError(
                    f"{self.name}: 无法转换为 {self.prop_type.__name__}，"
                    f"当前值: {value!r}"
                ) from e

        if self.min_value is not None and value < self.min_value:
            raise ValueError(
                f"{self.name} 必须 >= {self.min_value}，当前值: {value}"
            )
        if self.max_value is not None and value > self.max_value:
            raise ValueError(
                f"{self.name} 必须 <= {self.max_value}，当前值: {value}"
            )
        return value


class ValidatedConfig:
    """基类：使用 PropertyDef 定义的验证配置。

    子类需要定义 _properties 类变量，__init__ 会自动验证所有属性。
    """

    _properties: ClassVar[dict[str, PropertyDef]] = {}

    def __init__(self, **kwargs: Any) -> None:
        for name, prop in self._properties.items():
            value = kwargs.get(name, prop.default)
            validated = prop.validate(value)
            object.__setattr__(self, name, validated)
            if prop.on_update is not None and name in kwargs:
                prop.on_update(name, prop.default, validated)

    def to_dict(self) -> dict[str, Any]:
        """序列化为字典。"""
        return {k: getattr(self, k) for k in self._properties}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ValidatedConfig:
        """从字典反序列化，自动验证。缺失字段使用默认值。"""
        validated: dict[str, Any] = {}
        for name, prop in cls._properties.items():
            if name in data:
                validated[name] = prop.validate(data[name])
            else:
                validated[name] = prop.default
        return cls(**validated)

    def __repr__(self) -> str:
        items = ", ".join(
            f"{k}={getattr(self, k)!r}" for k in self._properties
        )
        return f"{self.__class__.__name__}({items})"
