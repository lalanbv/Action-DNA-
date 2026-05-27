"""统一变量池，提供类型化、分层作用域、线程安全的变量管理。"""

from __future__ import annotations

import contextlib
import copy
import datetime
import logging
import re
import threading
import time
import weakref
from dataclasses import dataclass
from typing import Any, Callable

from src.core.variables.types import VariableType
from src.core.variables.scope import VariableScope

logger = logging.getLogger(__name__)

_IMMUTABLE_TYPES = (str, int, float, bool, type(None), tuple, frozenset, bytes)


@dataclass
class _VarEntry:
    """内部变量条目（D3 引入 TypedVariable 后重构为存储 TypedVariable）。"""
    var_type: VariableType
    scope: VariableScope
    value: Any


class VariablePool:
    """
    统一变量池（Single Source of Truth）。

    特性：
    - 类型化：每个变量有明确类型
    - 分层作用域：GLOBAL / NODE / STEP
    - 线程安全：读写操作加 RLock（可重入，支持 set() 内部调用 declare()）
    - 可观察：变量变更时触发回调
    - 支持 {{var_name}} 模板引用解析
    """

    TEMPLATE_PATTERN = re.compile(r"\{\{(\w+(?:\.\w+)*)\}\}")

    def __init__(self) -> None:
        self._scopes: dict[VariableScope, dict[str, _VarEntry]] = {
            VariableScope.GLOBAL: {},
            VariableScope.NODE: {},
            VariableScope.STEP: {},
        }
        self._lock = threading.RLock()
        self._change_callbacks: list[Callable[[str, Any, Any, VariableScope], None]] = []
        self._builtin_resolvers: dict[str, Callable[[], Any]] = {}
        self._scope_stack: list[VariableScope] = []
        self._init_builtins()

    # ---- 声明与查询 ----

    def declare(
        self,
        name: str,
        var_type: VariableType,
        scope: VariableScope = VariableScope.GLOBAL,
        initial_value: Any = None,
    ) -> None:
        """
        声明一个变量。

        Args:
            name: 变量名（同一作用域内唯一）
            var_type: 变量类型
            scope: 作用域
            initial_value: 初始值（None 使用类型默认值）

        Raises:
            TypeError: 初始值类型不匹配
        """
        with self._lock:
            if name in self._scopes[scope]:
                logger.warning("变量 '%s' 在 %s 作用域已存在，覆盖", name, scope.value)

            value = initial_value if initial_value is not None else var_type.default_value

            if not var_type.validate(value):
                raise TypeError(
                    f"变量 '{name}' 的初始值 {value!r} "
                    f"不匹配类型 {var_type.value}"
                )

            self._scopes[scope][name] = _VarEntry(var_type=var_type, scope=scope, value=value)
            logger.debug("声明变量: %s [%s] = %r (%s)", name, var_type.value, value, scope.value)

    def get(self, name: str, scope: VariableScope | None = None) -> Any:
        """
        获取变量值。

        Args:
            name: 变量名
            scope: 指定作用域。None 时按 STEP -> NODE -> GLOBAL 顺序查找。

        Returns:
            变量值

        Raises:
            KeyError: 变量不存在
        """
        with self._lock:
            if name.startswith(("sys.", "exec.", "region.")):
                return self._resolve_builtin(name)

            if scope is not None:
                if name in self._scopes[scope]:
                    return self._scopes[scope][name].value
                raise KeyError(f"变量 '{name}' 在 {scope.value} 作用域中不存在")

            for s in (VariableScope.STEP, VariableScope.NODE, VariableScope.GLOBAL):
                if name in self._scopes[s]:
                    return self._scopes[s][name].value

            raise KeyError(
                f"变量 '{name}' 在任何作用域中都不存在。"
                f"已声明变量: {sorted(self._all_names())}"
            )

    def set(
        self,
        name: str,
        value: Any,
        scope: VariableScope = VariableScope.GLOBAL,
    ) -> None:
        """
        设置变量值。未声明时自动推断类型并创建。

        Args:
            name: 变量名
            value: 新值
            scope: 作用域

        Raises:
            TypeError: 值类型不匹配声明类型
        """
        with self._lock:
            if name not in self._scopes[scope]:
                logger.debug("变量 '%s' 未声明，自动创建", name)
                var_type = self._infer_type(value)
                self.declare(name, var_type, scope, value)
                return

            entry = self._scopes[scope][name]

            if not entry.var_type.validate(value):
                raise TypeError(
                    f"变量 '{name}' 的值 {value!r} "
                    f"不匹配声明类型 {entry.var_type.value}"
                )

            old_value = entry.value
            if old_value == value:
                return

            self._scopes[scope][name] = _VarEntry(
                var_type=entry.var_type, scope=scope, value=value
            )
            callbacks_snapshot = list(self._change_callbacks)
            logger.debug("设置变量: %s = %r -> %r (%s)", name, old_value, value, scope.value)

        self._fire_change_unlocked(callbacks_snapshot, name, old_value, value, scope)

    def increment(self, name: str, step: int = 1, scope: VariableScope = VariableScope.GLOBAL) -> int:
        """原子递增 INT 变量并返回新值。变量不存在时自动创建（值为 step）。"""
        with self._lock:
            if name not in self._scopes[scope]:
                self.declare(name, VariableType.INT, scope, initial_value=step)
                return step
            entry = self._scopes[scope][name]
            old_value = entry.value
            new_value = old_value + step
            self._scopes[scope][name] = _VarEntry(
                var_type=entry.var_type, scope=scope, value=new_value
            )
            callbacks_snapshot = list(self._change_callbacks)
        self._fire_change_unlocked(callbacks_snapshot, name, old_value, new_value, scope)
        return new_value

    def has(self, name: str, scope: VariableScope | None = None) -> bool:
        """检查变量是否存在"""
        with self._lock:
            if scope is not None:
                return name in self._scopes[scope]
            return any(name in self._scopes[s] for s in VariableScope)

    def get_type(self, name: str) -> VariableType | None:
        """获取变量的类型，不存在返回 None"""
        with self._lock:
            for s in VariableScope:
                if name in self._scopes[s]:
                    return self._scopes[s][name].var_type
            return None

    # ---- 作用域管理 ----

    def push_scope(self, scope: VariableScope) -> None:
        """进入新作用域"""
        with self._lock:
            self._scope_stack.append(scope)
            logger.debug("进入作用域: %s (栈深度: %d)", scope.value, len(self._scope_stack))

    def pop_scope(self, scope: VariableScope) -> None:
        """退出作用域，清除该作用域下所有变量"""
        with self._lock:
            self._scopes[scope].clear()
            if self._scope_stack:
                if self._scope_stack[-1] == scope:
                    self._scope_stack.pop()
                else:
                    logger.warning(
                        "pop_scope 栈顶不匹配: 期望 %s，实际 %s",
                        self._scope_stack[-1].value,
                        scope.value,
                    )
            logger.debug("退出作用域: %s", scope.value)

    # ---- 模板解析 ----

    def resolve_template(self, template: str) -> str:
        """
        解析 {{var_name}} 模板引用。未知变量保留原样。

        Args:
            template: 包含 {{var_name}} 占位符的字符串

        Returns:
            替换后的字符串
        """
        # 提取所有变量名，一次加锁批量读取，锁外做替换
        names = set(self.TEMPLATE_PATTERN.findall(template))
        if not names:
            return template

        with self._lock:
            values: dict[str, Any] = {}
            for var_name in names:
                if var_name.startswith(("sys.", "exec.", "region.")):
                    with contextlib.suppress(KeyError):
                        values[var_name] = self._resolve_builtin(var_name)
                else:
                    for s in (VariableScope.STEP, VariableScope.NODE, VariableScope.GLOBAL):
                        if var_name in self._scopes[s]:
                            values[var_name] = self._scopes[s][var_name].value
                            break

        def replacer(match: re.Match) -> str:
            var_name = match.group(1)
            if var_name in values:
                return str(values[var_name])
            logger.warning("模板引用的变量 '%s' 不存在", var_name)
            return match.group(0)

        return self.TEMPLATE_PATTERN.sub(replacer, template)

    # ---- 快照与恢复 ----

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """
        获取所有变量的快照。

        调用方不得修改 get() 返回的可变值（list 等），否则快照期间可能读到
        部分修改的状态。始终通过 set() 替换整个值。

        Returns:
            {"global": {"var": value, ...}, "node": {...}, "step": {...}}
        """
        # 快速路径：锁内只复制引用，锁外 deepcopy
        with self._lock:
            staged: list[tuple[str, str, Any, bool]] = []
            for scope in VariableScope:
                for name, entry in self._scopes[scope].items():
                    is_immutable = isinstance(entry.value, _IMMUTABLE_TYPES)
                    staged.append((scope.value, name, entry.value, is_immutable))

        result: dict[str, dict[str, Any]] = {s.value: {} for s in VariableScope}
        for scope_name, name, value, is_immutable in staged:
            result[scope_name][name] = value if is_immutable else copy.deepcopy(value)
        return result

    def from_snapshot(self, snapshot: dict[str, Any]) -> None:
        """从快照恢复变量（原子操作，一次性加锁）

        已有变量会校验值类型是否匹配声明类型。
        """
        with self._lock:
            for scope_name, variables in snapshot.items():
                scope = VariableScope(scope_name)
                for name, value in variables.items():
                    if name in self._scopes[scope]:
                        entry = self._scopes[scope][name]
                        if not entry.var_type.validate(value):
                            raise TypeError(
                                f"快照恢复变量 '{name}' 的值 {value!r} "
                                f"不匹配声明类型 {entry.var_type.value}"
                            )
                        self._scopes[scope][name] = _VarEntry(
                            var_type=entry.var_type, scope=scope, value=value
                        )
                    else:
                        var_type = self._infer_type(value)
                        self._scopes[scope][name] = _VarEntry(
                            var_type=var_type, scope=scope, value=value
                        )

    # ---- 变更监听 ----

    def on_change(self, callback: Callable[[str, Any, Any, VariableScope], None]) -> None:
        """
        注册变更回调。

        回调签名：callback(var_name: str, old_value: Any, new_value: Any, scope: VariableScope)
        """
        with self._lock:
            self._change_callbacks.append(callback)

    def remove_on_change(self, callback: Callable) -> None:
        """移除变更回调"""
        with self._lock:
            self._change_callbacks = [cb for cb in self._change_callbacks if cb != callback]

    # ---- 运行时依赖注入 ----

    def set_runtime_resolvers(
        self,
        mouse_x_fn: Callable[[], int],
        mouse_y_fn: Callable[[], int],
        screen_w_fn: Callable[[], int],
        screen_h_fn: Callable[[], int],
        region_fn: Callable[[], tuple[int, int, int, int]] | None = None,
    ) -> None:
        """设置运行时依赖的解析器（延迟注入，避免硬耦合 pyautogui）"""
        updates: dict[str, Callable[[], Any]] = {
            "sys.mouse_x": mouse_x_fn,
            "sys.mouse_y": mouse_y_fn,
            "sys.screen_w": screen_w_fn,
            "sys.screen_h": screen_h_fn,
        }

        if region_fn:
            def _make_region_resolver(axis: str) -> Callable[[], int]:
                def _resolve() -> int:
                    r = region_fn()
                    mapping = {"region.x": r[0], "region.y": r[1], "region.w": r[2], "region.h": r[3]}
                    return mapping.get(axis, 0)
                return _resolve

            for axis in ["region.x", "region.y", "region.w", "region.h"]:
                updates[axis] = _make_region_resolver(axis)

        with self._lock:
            self._builtin_resolvers.update(updates)

    # ---- 内部方法 ----

    def _init_builtins(self) -> None:
        """初始化内置变量解析器（使用 weakref 打断 self → lambda → self 循环引用）"""
        pool_ref = weakref.ref(self)

        def _step_var(key: str) -> Any:
            pool = pool_ref()
            if pool is None:
                return 0
            scope = pool._scopes.get(VariableScope.STEP, {})
            entry = scope.get(key)
            return entry.value if entry else 0

        self._builtin_resolvers = {
            "sys.time": lambda: datetime.datetime.now().strftime("%H:%M:%S"),
            "sys.date": lambda: datetime.datetime.now().strftime("%Y-%m-%d"),
            "sys.timestamp": time.time,
            "exec.loop_count": lambda: _step_var("__loop_count"),
            "exec.step_count": lambda: _step_var("__step_count"),
            "exec.step_index": lambda: _step_var("__step_index"),
        }

    def _resolve_builtin(self, name: str) -> Any:
        """解析内置变量"""
        if name in self._builtin_resolvers:
            return self._builtin_resolvers[name]()
        raise KeyError(f"未知的内置变量: '{name}'")

    def _fire_change_unlocked(
        self, callbacks: list[Callable[[str, Any, Any, VariableScope], None]],
        name: str, old_value: Any, new_value: Any, scope: VariableScope,
    ) -> None:
        """在锁外触发变更回调，避免阻塞其他线程的池操作"""
        for callback in callbacks:
            try:
                callback(name, old_value, new_value, scope)
            except Exception as e:  # pylint: disable=broad-exception-caught
                logger.error("变量变更回调出错: %s", e)

    def _infer_type(self, value: Any) -> VariableType:
        """从值推断变量类型。bool 必须在 int 之前检查。

        不支持的值类型抛出 TypeError（如含 float 元素的 tuple、
        长度非 2/4 的 tuple、dict 等）。
        """
        if isinstance(value, bool):
            return VariableType.BOOL
        if isinstance(value, int):
            return VariableType.INT
        if isinstance(value, float):
            return VariableType.FLOAT
        if isinstance(value, str):
            return VariableType.STR
        if isinstance(value, tuple):
            if len(value) == 2 and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
                return VariableType.COORD
            if len(value) == 4 and all(isinstance(v, int) and not isinstance(v, bool) for v in value):
                return VariableType.COORD_RECT
            raise TypeError(f"无法推断 tuple 值的类型: {value!r}，仅支持长度 2 (COORD) 或 4 (COORD_RECT) 的 int tuple")
        if isinstance(value, list):
            return VariableType.LIST
        raise TypeError(f"无法推断值 {value!r} 的变量类型")

    def _all_names(self) -> set[str]:  # type: ignore[valid-type]
        """获取所有作用域中的变量名"""
        names: set[str] = set()
        for scope_vars in self._scopes.values():
            names.update(scope_vars.keys())
        return names
