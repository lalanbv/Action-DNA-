"""变量类型枚举，定义 9 种运行时数据类型及验证逻辑。"""

from enum import Enum
from typing import Any


_PYTHON_TYPE_MAP: dict["VariableType", type | str] = {}
_DEFAULT_FACTORY_MAP: dict["VariableType", Any] = {}


class VariableType(Enum):
    """
    变量类型枚举。

    每种类型对应一种运行时数据类型，用于：
    - 类型检查：写入时验证值类型是否匹配
    - UI 生成：根据类型生成不同的编辑控件
    - 序列化：根据类型选择序列化策略
    """

    INT = "int"
    FLOAT = "float"
    STR = "str"
    BOOL = "bool"
    COORD = "coord"
    COORD_RECT = "coord_rect"
    TIMER = "timer"
    IMAGE = "image"
    LIST = "list"

    @property
    def python_type(self) -> type | str:
        """返回对应的 Python 类型"""
        return _PYTHON_TYPE_MAP[self]

    @property
    def default_value(self) -> Any:
        """返回类型的默认值。LIST 每次返回新实例，避免共享可变对象。"""
        if self == VariableType.LIST:
            return []
        return _DEFAULT_FACTORY_MAP[self]

    def validate(self, value: Any) -> bool:
        """
        验证值是否匹配此类型。

        特殊处理：
        - INT 排除 bool（Python 中 bool 是 int 的子类）
        - COORD 检查 tuple 长度为 2 且元素为 int
        - COORD_RECT 检查 tuple 长度为 4 且元素为 int
        """
        if value is None:
            return True

        if self == VariableType.INT:
            return isinstance(value, int) and not isinstance(value, bool)
        if self == VariableType.FLOAT:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        if self == VariableType.STR:
            return isinstance(value, str)
        if self == VariableType.BOOL:
            return isinstance(value, bool)
        if self == VariableType.COORD:
            return (
                isinstance(value, tuple)
                and len(value) == 2
                and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
            )
        if self == VariableType.COORD_RECT:
            return (
                isinstance(value, tuple)
                and len(value) == 4
                and all(isinstance(v, int) and not isinstance(v, bool) for v in value)
            )
        elif self == VariableType.TIMER:
            return isinstance(value, (int, float)) and not isinstance(value, bool)
        elif self == VariableType.IMAGE:
            return True
        elif self == VariableType.LIST:
            return isinstance(value, list)

        return False


_PYTHON_TYPE_MAP = {
    VariableType.INT: int,
    VariableType.FLOAT: float,
    VariableType.STR: str,
    VariableType.BOOL: bool,
    VariableType.COORD: tuple,
    VariableType.COORD_RECT: tuple,
    VariableType.TIMER: float,
    VariableType.IMAGE: "numpy.ndarray",
    VariableType.LIST: list,
}

_DEFAULT_FACTORY_MAP = {
    VariableType.INT: 0,
    VariableType.FLOAT: 0.0,
    VariableType.STR: "",
    VariableType.BOOL: False,
    VariableType.COORD: (0, 0),
    VariableType.COORD_RECT: (0, 0, 0, 0),
    VariableType.TIMER: 0.0,
    VariableType.IMAGE: None,
}
