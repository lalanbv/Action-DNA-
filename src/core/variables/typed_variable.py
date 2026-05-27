"""类型化变量，支持字面值或命名引用（PlayMaker 间接引用模式）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from src.core.variables.types import VariableType
from src.core.variables.scope import VariableScope

if TYPE_CHECKING:
    from src.core.variables.pool import VariablePool


@dataclass(frozen=True)
class TypedVariable:
    """
    类型化变量，支持字面值或命名引用。

    PlayMaker 模式：变量可以是直接的值，也可以是指向 VariablePool
    中某个命名变量的引用。resolve() 方法透明地返回最终值。

    frozen=True 强制不可变：set_literal() / set_reference() 返回新对象。
    """

    var_type: VariableType
    scope: VariableScope = VariableScope.GLOBAL
    name: str = ""
    _literal_value: Any = None
    _reference_name: str | None = None

    @property
    def is_reference(self) -> bool:
        """是否为引用模式。"""
        return self._reference_name is not None

    @property
    def is_literal(self) -> bool:
        """是否为字面值模式。"""
        return self._reference_name is None

    def resolve(
        self,
        pool: VariablePool,
        _visited: tuple[str, ...] = (),
    ) -> Any:
        """
        透明解析：引用模式从 pool 获取值，字面值模式直接返回。

        支持嵌套引用（pool 中的值本身是 TypedVariable 时递归解析）
        和循环引用检测（visited 追踪已访问的引用名，保持顺序便于调试）。

        Raises:
            ValueError: 检测到循环引用
            KeyError: 引用模式下变量名不存在
        """
        if self._reference_name is None:
            return self._literal_value

        if self._reference_name in _visited:
            chain = " -> ".join((*_visited, self._reference_name))
            raise ValueError(f"检测到循环引用: {chain}")

        visited = (*_visited, self._reference_name)
        value = pool.get(self._reference_name)

        if isinstance(value, TypedVariable):
            return value.resolve(pool, visited)

        return value

    def set_literal(self, value: Any) -> TypedVariable:
        """设置字面值（不可变：返回新对象）。"""
        return TypedVariable(
            var_type=self.var_type,
            scope=self.scope,
            name=self.name,
            _literal_value=value,
            _reference_name=None,
        )

    def set_reference(self, ref_name: str) -> TypedVariable:
        """设置为引用（不可变：返回新对象）。"""
        return TypedVariable(
            var_type=self.var_type,
            scope=self.scope,
            name=self.name,
            _literal_value=None,
            _reference_name=ref_name,
        )

    def validate_value(self, value: Any) -> bool:
        """验证值是否符合变量类型。"""
        return self.var_type.validate(value)

    def __repr__(self) -> str:
        name_part = f", name={self.name!r}" if self.name else ""
        if self.is_reference:
            return (
                f"TypedVariable({self.var_type.value}{name_part}, "
                f"ref={self._reference_name!r})"
            )
        return (
            f"TypedVariable({self.var_type.value}{name_part}, "
            f"value={self._literal_value!r})"
        )
