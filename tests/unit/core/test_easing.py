"""缓动函数库单元测试。"""

import math

import pytest

from src.core.easing import ALL_EASING_FUNCTIONS


class TestEasingBoundaries:
    """所有缓动函数 f(0)≈0, f(1)≈1。"""

    @pytest.mark.parametrize("name,func", list(ALL_EASING_FUNCTIONS.items()))
    def test_start_value(self, name, func):
        assert abs(func(0.0)) < 1e-6, f"{name}: f(0) != 0"

    @pytest.mark.parametrize("name,func", list(ALL_EASING_FUNCTIONS.items()))
    def test_end_value(self, name, func):
        assert abs(func(1.0) - 1.0) < 1e-6, f"{name}: f(1) != 1"


class TestEasingRange:
    """输出在合理范围内（允许轻微过冲如 back/elastic）。"""

    @pytest.mark.parametrize("name,func", list(ALL_EASING_FUNCTIONS.items()))
    def test_output_range(self, name, func):
        ts = [i / 100 for i in range(101)]
        values = [func(t) for t in ts]
        assert min(values) >= -0.5, f"{name}: min={min(values)} < -0.5"
        assert max(values) <= 1.5, f"{name}: max={max(values)} > 1.5"


class TestEasingMonotonic:
    """ease_in_out 系列应近似单调递增。"""

    _IN_OUT_FUNCS = {
        n: f for n, f in ALL_EASING_FUNCTIONS.items() if "in_out" in n
    }

    @pytest.mark.parametrize("name,func", list(_IN_OUT_FUNCS.items()))
    def test_in_out_monotonic(self, name, func):
        ts = [i / 100 for i in range(101)]
        values = [func(t) for t in ts]
        for i in range(1, len(values)):
            assert values[i] >= values[i - 1] - 0.01, f"{name}: 非单调 at t={ts[i]}"


class TestEasingRegistry:
    """注册表完整性。"""

    def test_registry_not_empty(self):
        assert len(ALL_EASING_FUNCTIONS) >= 20

    def test_all_callable(self):
        for name, func in ALL_EASING_FUNCTIONS.items():
            result = func(0.5)
            assert isinstance(result, float), f"{name} 返回非 float"

    def test_linear(self):
        from src.core.easing import linear
        assert linear(0.0) == 0.0
        assert linear(0.5) == 0.5
        assert linear(1.0) == 1.0
