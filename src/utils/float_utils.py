"""浮点数精度工具 — 统一比较、舍入和校验。"""

from __future__ import annotations

import math

PRACTICAL_TOLERANCE: float = 1e-9


def is_close(
    a: float,
    b: float,
    *,
    rel_tol: float = 0.0,
    abs_tol: float = PRACTICAL_TOLERANCE,
) -> bool:
    """带容差的浮点比较，默认绝对容差 1e-9。"""
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def is_zero(a: float, *, abs_tol: float = PRACTICAL_TOLERANCE) -> bool:
    return abs(a) <= abs_tol


def is_one(a: float, *, abs_tol: float = PRACTICAL_TOLERANCE) -> bool:
    return abs(a - 1.0) <= abs_tol


def safe_float(
    value: str | int | float,
    *,
    min_val: float | None = None,
    max_val: float | None = None,
    default: float = 0.0,
    decimal_places: int | None = None,
) -> float:
    """安全浮点转换 + 范围钳制 + 可选舍入。NaN/Inf 回退 default。"""
    try:
        result = float(value)
    except (ValueError, TypeError):
        return default

    if not math.isfinite(result):
        return default

    if min_val is not None:
        result = max(result, min_val)
    if max_val is not None:
        result = min(result, max_val)

    if decimal_places is not None:
        result = round(result, decimal_places)

    return result


def safe_int(
    value: str | int | float,
    *,
    min_val: int | None = None,
    max_val: int | None = None,
    default: int = 0,
) -> int:
    """安全整数转换 + 范围钳制。先 float 再 int 避免 "3.0" → ValueError。"""
    try:
        result = int(float(value))
    except (ValueError, TypeError, OverflowError):
        return default

    if min_val is not None:
        result = max(result, min_val)
    if max_val is not None:
        result = min(result, max_val)

    return result
