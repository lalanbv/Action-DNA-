"""可复现随机数生成器 — 种子控制路径可复现。

提供独立的 random.Random 实例，与全局 random 状态隔离，
确保相同种子产生相同的鼠标轨迹和延迟序列。
"""

from __future__ import annotations

import random as _random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

__all__ = ["SeededRandomizer"]


class SeededRandomizer:
    """可复现的随机数生成器。

    seed=None 时委托给全局 random 模块（不可复现）。
    seed=int 时使用独立 Random 实例，路径可复现。

    用法:
        rng = SeededRandomizer(seed=42)
        rng.uniform(0.1, 0.3)  # 相同 seed 总是返回相同值
    """

    def __init__(self, seed: int | None = None) -> None:
        self._seed = seed
        if seed is not None:
            self._target: _random.Random | type(_random) = _random.Random(seed)
        else:
            self._target = _random

    @property
    def seed(self) -> int | None:
        return self._seed

    def random(self) -> float:
        return self._target.random()

    def uniform(self, a: float, b: float) -> float:
        return self._target.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._target.randint(a, b)

    def gauss(self, mu: float = 0.0, sigma: float = 1.0) -> float:
        return self._target.gauss(mu, sigma)

    def gammavariate(self, alpha: float, beta: float) -> float:
        return self._target.gammavariate(alpha, beta)

    def choice(self, seq: list) -> object:
        return self._target.choice(seq)
