"""内置变量工具函数 — 计数器等高层 API。

底层内置变量（sys.*, exec.*, region.*）在 VariablePool._init_builtins() 中注册。
本模块提供计数器 increment/reset 等便捷操作。

计时器功能由 ConditionEvaluator（condition.py）直接管理，使用 time.monotonic()。
"""

from src.core.variables.pool import VariablePool
from src.core.variables.types import VariableType
from src.core.variables.scope import VariableScope

_COUNTER_PREFIX = "counter."


# ---- 计数器 ----


def increment_counter(pool: VariablePool, name: str, step: int = 1, scope: VariableScope = VariableScope.GLOBAL) -> int:
    """递增计数器并返回新值。不存在时自动创建并从 step 开始。原子操作。"""
    full_name = f"{_COUNTER_PREFIX}{name}"
    return pool.increment(full_name, step, scope)


def get_counter(pool: VariablePool, name: str, scope: VariableScope = VariableScope.GLOBAL) -> int:
    """获取计数器值。不存在时返回 0。"""
    full_name = f"{_COUNTER_PREFIX}{name}"
    if not pool.has(full_name, scope):
        return 0
    return pool.get(full_name, scope)


def reset_counter(pool: VariablePool, name: str, scope: VariableScope = VariableScope.GLOBAL) -> None:
    """重置计数器为 0。"""
    full_name = f"{_COUNTER_PREFIX}{name}"
    if pool.has(full_name, scope):
        pool.set(full_name, 0, scope)
    else:
        pool.declare(full_name, VariableType.INT, scope, initial_value=0)
