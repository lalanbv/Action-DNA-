"""缓动函数库 — 人类化鼠标移动曲线。

所有函数签名: (t: float) -> float, 输入 [0,1], 输出 [0,1]。
边界判断使用内联容差比较（PRACTICAL_TOLERANCE），避免函数调用开销和浮点精度问题。
"""

from collections.abc import Callable

import math

from src.utils.float_utils import PRACTICAL_TOLERANCE as _EPS

_BACK_C1 = 1.70158
_BACK_C2 = _BACK_C1 * 1.525
_TWO_PI_OVER_3 = 2 * math.pi / 3
_BOUNCE_N1 = 7.5625
_BOUNCE_D1 = 2.75
_BOUNCE_INV_D1 = 1.0 / _BOUNCE_D1
_BOUNCE_2_INV = 2.0 / _BOUNCE_D1
_BOUNCE_2_5_INV = 2.5 / _BOUNCE_D1
_BOUNCE_1_5_OFF = 1.5 / _BOUNCE_D1
_BOUNCE_2_25_OFF = 2.25 / _BOUNCE_D1
_BOUNCE_2_625_OFF = 2.625 / _BOUNCE_D1


# ---- 线性 ----


def linear(t: float) -> float:
    return t


# ---- 二次 ----


def ease_in_quad(t: float) -> float:
    return t * t


def ease_out_quad(t: float) -> float:
    return 1 - (1 - t) ** 2


def ease_in_out_quad(t: float) -> float:
    return 2 * t * t if t < 0.5 else 1 - (-2 * t + 2) ** 2 / 2


# ---- 三次 ----


def ease_in_cubic(t: float) -> float:
    return t**3


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def ease_in_out_cubic(t: float) -> float:
    return 4 * t**3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


# ---- 四次 ----


def ease_in_quart(t: float) -> float:
    return t**4


def ease_out_quart(t: float) -> float:
    return 1 - (1 - t) ** 4


def ease_in_out_quart(t: float) -> float:
    return 8 * t**4 if t < 0.5 else 1 - (-2 * t + 2) ** 4 / 2


# ---- 五次 ----


def ease_in_quint(t: float) -> float:
    return t**5


def ease_out_quint(t: float) -> float:
    return 1 - (1 - t) ** 5


def ease_in_out_quint(t: float) -> float:
    return 16 * t**5 if t < 0.5 else 1 - (-2 * t + 2) ** 5 / 2


# ---- 正弦 ----


def ease_in_sine(t: float) -> float:
    return 1 - math.cos(t * math.pi / 2)


def ease_out_sine(t: float) -> float:
    return math.sin(t * math.pi / 2)


def ease_in_out_sine(t: float) -> float:
    return -(math.cos(math.pi * t) - 1) / 2


# ---- 指数 ----


def ease_in_expo(t: float) -> float:
    return 0.0 if abs(t) <= _EPS else 2 ** (10 * t - 10)


def ease_out_expo(t: float) -> float:
    return 1.0 if abs(t - 1.0) <= _EPS else 1 - 2 ** (-10 * t)


def ease_in_out_expo(t: float) -> float:
    if abs(t) <= _EPS:
        return 0.0
    if abs(t - 1.0) <= _EPS:
        return 1.0
    return 2 ** (20 * t - 10) / 2 if t < 0.5 else (2 - 2 ** (-20 * t + 10)) / 2


# ---- 圆形 ----


def ease_in_circ(t: float) -> float:
    return 1 - math.sqrt(1 - t * t)


def ease_out_circ(t: float) -> float:
    return math.sqrt(1 - (t - 1) ** 2)


def ease_in_out_circ(t: float) -> float:
    if t < 0.5:
        return (1 - math.sqrt(1 - (2 * t) ** 2)) / 2
    return (math.sqrt(1 - (-2 * t + 2) ** 2) + 1) / 2


# ---- 背面 ----


def ease_in_back(t: float) -> float:
    return (_BACK_C1 + 1) * t**3 - _BACK_C1 * t**2


def ease_out_back(t: float) -> float:
    return 1 + (_BACK_C1 + 1) * (t - 1) ** 3 + _BACK_C1 * (t - 1) ** 2


def ease_in_out_back(t: float) -> float:
    if t < 0.5:
        return ((2 * t) ** 2 * ((_BACK_C2 + 1) * 2 * t - _BACK_C2)) / 2
    return ((2 * t - 2) ** 2 * ((_BACK_C2 + 1) * (t * 2 - 2) + _BACK_C2) + 2) / 2


# ---- 弹性 ----


def ease_out_elastic(t: float) -> float:
    if abs(t) <= _EPS:
        return 0.0
    if abs(t - 1.0) <= _EPS:
        return 1.0
    return 2 ** (-10 * t) * math.sin((t * 10 - 0.75) * _TWO_PI_OVER_3) + 1


def ease_in_elastic(t: float) -> float:
    if abs(t) <= _EPS:
        return 0.0
    if abs(t - 1.0) <= _EPS:
        return 1.0
    return -(2 ** (10 * t - 10)) * math.sin((t * 10 - 10.75) * _TWO_PI_OVER_3)


# ---- 弹跳 ----


def ease_out_bounce(t: float) -> float:
    if t < _BOUNCE_INV_D1:
        return _BOUNCE_N1 * t * t
    if t < _BOUNCE_2_INV:
        t -= _BOUNCE_1_5_OFF
        return _BOUNCE_N1 * t * t + 0.75
    if t < _BOUNCE_2_5_INV:
        t -= _BOUNCE_2_25_OFF
        return _BOUNCE_N1 * t * t + 0.9375
    t -= _BOUNCE_2_625_OFF
    return _BOUNCE_N1 * t * t + 0.984375


def ease_in_bounce(t: float) -> float:
    return 1 - ease_out_bounce(1 - t)


# 注册表：自动收集所有缓动函数（linear + ease_* 命名）
ALL_EASING_FUNCTIONS: dict[str, Callable[[float], float]] = {
    name: obj
    for name, obj in globals().items()
    if callable(obj) and (name == "linear" or name.startswith("ease_"))
}
