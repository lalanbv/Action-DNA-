"""builtins 模块测试 — 计数器工具函数。"""

import pytest

from src.core.variables.pool import VariablePool
from src.core.variables.scope import VariableScope
from src.core.variables.builtins import (
    increment_counter,
    get_counter,
    reset_counter,
)


# ---- 计数器 ----


class TestIncrementCounter:

    def test_creates_counter_on_first_increment(self, pool):
        val = increment_counter(pool, "loops")
        assert val == 1
        assert pool.has("counter.loops")

    def test_increments_existing(self, pool):
        increment_counter(pool, "loops")
        val = increment_counter(pool, "loops")
        assert val == 2

    def test_custom_step(self, pool):
        val = increment_counter(pool, "jumps", step=5)
        assert val == 5
        val = increment_counter(pool, "jumps", step=5)
        assert val == 10

    def test_scope_specific(self, pool):
        increment_counter(pool, "steps", scope=VariableScope.STEP)
        assert pool.has("counter.steps", VariableScope.STEP)
        assert not pool.has("counter.steps", VariableScope.GLOBAL)


class TestGetCounter:

    def test_returns_zero_when_missing(self, pool):
        assert get_counter(pool, "missing") == 0

    def test_returns_current_value(self, pool):
        increment_counter(pool, "loops")
        increment_counter(pool, "loops")
        assert get_counter(pool, "loops") == 2


class TestResetCounter:

    def test_resets_to_zero(self, pool):
        increment_counter(pool, "loops")
        increment_counter(pool, "loops")
        reset_counter(pool, "loops")
        assert get_counter(pool, "loops") == 0

    def test_creates_if_missing(self, pool):
        reset_counter(pool, "new_counter")
        assert get_counter(pool, "new_counter") == 0
