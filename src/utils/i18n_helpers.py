"""i18n_helpers — i18n 组件化工具集

提供 UI 控件中常用的 i18n 映射工具，消除 (value, i18n_key) → display → 反向查找 样板代码。

组件:
- I18nOptions: 下拉框 / 单选组的 (value, i18n_key) 映射
- I18nEnum: 枚举类型 → i18n 显示名的自动映射
"""

from __future__ import annotations

from enum import Enum
from typing import TypeVar

from src.utils.i18n import t

T = TypeVar("T", bound=Enum)


class I18nOptions:
    """i18n 感知的选项列表，用于下拉框和单选组。

    用法::

        opts = I18nOptions([
            ("once", "schedule.type.once"),
            ("interval", "schedule.type.interval"),
        ])
        combo["values"] = opts.display_values()
        value = opts.value_from_display(combo.get())
    """

    __slots__ = ("_options",)

    def __init__(self, options: list[tuple[str, str]]) -> None:
        self._options: list[tuple[str, str]] = tuple(options)

    def display_values(self) -> list[str]:
        return [t(key) for _, key in self._options]

    def value_from_display(self, display: str) -> str | None:
        for val, key in self._options:
            if t(key) == display:
                return val
        return None

    def display_from_value(self, value: str) -> str | None:
        for val, key in self._options:
            if val == value:
                return t(key)
        return None

    def items(self) -> list[tuple[str, str]]:
        return list(self._options)

    def value_at(self, index: int) -> str | None:
        if 0 <= index < len(self._options):
            return self._options[index][0]
        return None

    def __len__(self) -> int:
        return len(self._options)


class I18nEnum:
    """枚举类型 → i18n 显示名的自动映射。

    用法::

        class Fruit(Enum):
            APPLE = "apple"
            BANANA = "banana"

        ie = I18nEnum(Fruit, {
            Fruit.APPLE: "fruit.apple",
            Fruit.BANANA: "fruit.banana",
        })
        label = ie.display(Fruit.APPLE)    # → t("fruit.apple")
        fruit = ie.from_display(label)      # → Fruit.APPLE
    """

    __slots__ = ("_enum_cls", "_mapping")

    def __init__(self, enum_cls: type[T], mapping: dict[T, str]) -> None:
        self._enum_cls = enum_cls
        self._mapping: dict[T, str] = dict(mapping)

    def display(self, member: T) -> str:
        return t(self._mapping[member])

    def from_display(self, display: str) -> T | None:
        for member, key in self._mapping.items():
            if t(key) == display:
                return member
        return None

    def all_displays(self) -> list[str]:
        return [t(key) for key in self._mapping.values()]

    def all_items(self) -> list[tuple[T, str]]:
        return [(member, t(key)) for member, key in self._mapping.items()]
