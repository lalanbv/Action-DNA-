"""float_utils 单元测试。"""

import math

import pytest

from src.utils.float_utils import (
    PRACTICAL_TOLERANCE,
    is_close,
    is_one,
    is_zero,
    safe_float,
    safe_int,
)


# ---- is_close ----


class TestIsClose:
    def test_equal_values(self) -> None:
        assert is_close(1.0, 1.0)

    def test_within_tolerance(self) -> None:
        assert is_close(0.0, PRACTICAL_TOLERANCE / 2)

    def test_outside_tolerance(self) -> None:
        assert not is_close(0.0, PRACTICAL_TOLERANCE * 10)

    def test_custom_abs_tol(self) -> None:
        assert is_close(0.0, 0.1, abs_tol=0.2)

    def test_rel_tol(self) -> None:
        assert is_close(1e9, 1e9 + 1, rel_tol=1e-9)


# ---- is_zero ----


class TestIsZero:
    def test_exact_zero(self) -> None:
        assert is_zero(0.0)

    def test_near_zero(self) -> None:
        assert is_zero(PRACTICAL_TOLERANCE / 2)

    def test_not_zero(self) -> None:
        assert not is_zero(0.01)

    def test_negative_near_zero(self) -> None:
        assert is_zero(-PRACTICAL_TOLERANCE / 2)

    def test_custom_tol(self) -> None:
        assert is_zero(0.05, abs_tol=0.1)


# ---- is_one ----


class TestIsOne:
    def test_exact_one(self) -> None:
        assert is_one(1.0)

    def test_near_one(self) -> None:
        assert is_one(1.0 + PRACTICAL_TOLERANCE / 2)

    def test_not_one(self) -> None:
        assert not is_one(1.01)

    def test_custom_tol(self) -> None:
        assert is_one(0.95, abs_tol=0.1)


# ---- safe_float ----


class TestSafeFloat:
    def test_valid_string(self) -> None:
        assert safe_float("3.14") == pytest.approx(3.14)

    def test_int_input(self) -> None:
        assert safe_float(42) == 42.0

    def test_float_input(self) -> None:
        assert safe_float(2.5) == pytest.approx(2.5)

    def test_invalid_string_returns_default(self) -> None:
        assert safe_float("abc") == 0.0

    def test_none_returns_default(self) -> None:
        assert safe_float(None) == 0.0

    def test_custom_default(self) -> None:
        assert safe_float("bad", default=-1.0) == -1.0

    def test_nan_returns_default(self) -> None:
        assert safe_float(float("nan")) == 0.0

    def test_inf_returns_default(self) -> None:
        assert safe_float(float("inf")) == 0.0

    def test_negative_inf_returns_default(self) -> None:
        assert safe_float(float("-inf")) == 0.0

    def test_clamp_min(self) -> None:
        assert safe_float("-5.0", min_val=0.0) == 0.0

    def test_clamp_max(self) -> None:
        assert safe_float("100.0", max_val=50.0) == 50.0

    def test_clamp_both(self) -> None:
        assert safe_float("0.5", min_val=1.0, max_val=10.0) == 1.0

    def test_decimal_places(self) -> None:
        assert safe_float("3.14159", decimal_places=2) == pytest.approx(3.14)

    def test_decimal_places_zero(self) -> None:
        assert safe_float("3.7", decimal_places=0) == 4.0

    def test_string_int(self) -> None:
        assert safe_float("7") == 7.0

    def test_empty_string_returns_default(self) -> None:
        assert safe_float("") == 0.0


# ---- safe_int ----


class TestSafeInt:
    def test_valid_string(self) -> None:
        assert safe_int("42") == 42

    def test_int_input(self) -> None:
        assert safe_int(7) == 7

    def test_float_input(self) -> None:
        assert safe_int(3.7) == 3

    def test_string_float(self) -> None:
        assert safe_int("3.7") == 3

    def test_invalid_string_returns_default(self) -> None:
        assert safe_int("abc") == 0

    def test_none_returns_default(self) -> None:
        assert safe_int(None) == 0

    def test_custom_default(self) -> None:
        assert safe_int("bad", default=-1) == -1

    def test_clamp_min(self) -> None:
        assert safe_int("-5", min_val=0) == 0

    def test_clamp_max(self) -> None:
        assert safe_int("100", max_val=50) == 50

    def test_clamp_both(self) -> None:
        assert safe_int("0", min_val=1, max_val=10) == 1

    def test_empty_string_returns_default(self) -> None:
        assert safe_int("") == 0

    def test_nan_returns_default(self) -> None:
        assert safe_int(float("nan")) == 0

    def test_inf_returns_default(self) -> None:
        assert safe_int(float("inf")) == 0
