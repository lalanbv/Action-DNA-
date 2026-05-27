"""真人节奏噪声工具 — Gamma 噪声扰动。

使用 Gamma(k=2, θ=0.5) 分布生成均值≈1.0、右偏的随机乘数，
使回放时序更接近真人的速度变化特征。
"""

from __future__ import annotations

import random

GAMMA_SHAPE = 2.0
GAMMA_SCALE = 0.5


def human_like_duration(base: float) -> float:
    """对基准时长施加 Gamma 噪声，生成更接近真人的持续时长。"""
    return base * random.gammavariate(GAMMA_SHAPE, GAMMA_SCALE)
