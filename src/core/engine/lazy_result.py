"""LazyResult — 惰性求值包装器。

参考 Blender LazyFunction 设计：延迟计算直到值被实际消费。
用于 DAG 增量执行中，仅当节点确实需要上游结果时才触发求值。
"""

from __future__ import annotations

from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class LazyResult(Generic[T]):
    """惰性求值包装 — 值在首次访问时才计算，之后缓存。"""

    __slots__ = ("_fn", "_value", "_computed")

    def __init__(self, fn: Callable[[], T]) -> None:
        self._fn = fn
        self._value: T | None = None
        self._computed = False

    @classmethod
    def of(cls, value: T) -> LazyResult[T]:
        """直接包装已知值，无需延迟计算。"""

        def _identity() -> T:
            return value

        result = cls(_identity)
        result._value = value
        result._computed = True
        return result

    @property
    def computed(self) -> bool:
        return self._computed

    def get(self) -> T:
        """获取值，首次调用时触发计算。"""
        if not self._computed:
            self._value = self._fn()
            self._computed = True
        return self._value  # type: ignore[return-value]

    def map(self, fn: Callable[[T], Any]) -> LazyResult[Any]:
        """变换结果，返回新的惰性包装。"""
        return LazyResult(lambda: fn(self.get()))

    def __repr__(self) -> str:
        if self._computed:
            return f"LazyResult({self._value!r})"
        return "LazyResult(<unevaluated>)"


class LazyResultMap:
    """多键惰性结果映射 — 按需求值，用于节点输出端口。"""

    __slots__ = ("_entries",)

    def __init__(self) -> None:
        self._entries: dict[str, LazyResult[Any]] = {}

    def put(self, key: str, fn: Callable[[], Any]) -> None:
        self._entries[key] = LazyResult(fn)

    def put_value(self, key: str, value: Any) -> None:
        self._entries[key] = LazyResult.of(value)

    def get(self, key: str) -> Any:
        lr = self._entries.get(key)
        if lr is None:
            raise KeyError(key)
        return lr.get()

    def get_lazy(self, key: str) -> LazyResult[Any] | None:
        return self._entries.get(key)

    def keys(self) -> frozenset[str]:
        return frozenset(self._entries.keys())

    def force_all(self) -> dict[str, Any]:
        """强制求值所有条目，返回普通字典。"""
        return {k: v.get() for k, v in self._entries.items()}

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __len__(self) -> int:
        return len(self._entries)
