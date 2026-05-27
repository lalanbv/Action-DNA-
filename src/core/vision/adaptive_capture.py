"""自适应区域截图 — 根据历史匹配结果动态调整捕获区域。

不再每次截取全屏，而是：
1. 根据上次匹配位置推测下次可能出现的位置
2. 自动扩展 ROI 以覆盖可能的位移
3. 匹配失败时回退到全屏
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ROI:
    """矩形感兴趣区域。"""

    x: int
    y: int
    width: int
    height: int

    @property
    def area(self) -> int:
        return self.width * self.height

    def expanded(self, margin: int) -> ROI:
        return ROI(
            x=max(0, self.x - margin),
            y=max(0, self.y - margin),
            width=self.width + margin * 2,
            height=self.height + margin * 2,
        )

    def clipped(self, max_w: int, max_h: int) -> ROI:
        x2 = min(self.x + self.width, max_w)
        y2 = min(self.y + self.height, max_h)
        x = max(0, self.x)
        y = max(0, self.y)
        return ROI(x=x, y=y, width=x2 - x, height=y2 - y)

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height


@dataclass(frozen=True)
class AdaptiveConfig:
    """自适应截图配置。"""

    expansion_margin: int = 50       # ROI 扩展边距（像素）
    max_failures_before_fullscreen: int = 3  # 连续失败 N 次后回退全屏
    min_confidence: float = 0.6      # 低于此置信度视为"低质量"
    shrink_on_high_confidence: float = 0.9   # 高置信度时 ROI 缩小因子
    max_roi_ratio: float = 0.8       # ROI 面积不超过屏幕面积的比例


class AdaptiveCapture:
    """自适应区域截图管理器。

    跟踪上次匹配位置，动态调整 ROI。
    匹配失败时逐步扩大搜索区域，最终回退全屏。
    """

    def __init__(self, config: AdaptiveConfig | None = None) -> None:
        self._config = config or AdaptiveConfig()
        self._last_roi: ROI | None = None
        self._last_match_pos: tuple[int, int] | None = None
        self._consecutive_failures = 0
        self._screen_size: tuple[int, int] | None = None

    def set_screen_size(self, width: int, height: int) -> None:
        self._screen_size = (width, height)

    def get_capture_region(
        self,
        full_width: int,
        full_height: int,
    ) -> ROI | None:
        """计算下次截图区域。返回 None 表示需要全屏截图。"""
        self._screen_size = (full_width, full_height)

        if self._last_roi is None or self._consecutive_failures >= self._config.max_failures_before_fullscreen:
            return None

        expanded = self._last_roi.expanded(self._config.expansion_margin)
        clipped = expanded.clipped(full_width, full_height)

        max_area = full_width * full_height * self._config.max_roi_ratio
        if clipped.area >= max_area:
            return None

        return clipped

    def report_match(
        self,
        pos: tuple[int, int],
        rect: tuple[int, int, int, int],
        confidence: float,
    ) -> None:
        """报告成功匹配，更新 ROI。"""
        x, y, w, h = rect
        self._last_match_pos = pos
        self._consecutive_failures = 0

        if confidence >= self._config.shrink_on_high_confidence:
            margin = self._config.expansion_margin // 2
            self._last_roi = ROI(x=max(0, x - margin), y=max(0, y - margin),
                                 width=w + margin * 2, height=h + margin * 2)
        else:
            self._last_roi = ROI(x=x, y=y, width=w, height=h)

    def report_miss(self) -> None:
        """报告匹配失败。"""
        self._consecutive_failures += 1

        if self._last_roi is not None and self._screen_size:
            max_margin = max(self._screen_size[0], self._screen_size[1])
            margin = min(
                self._config.expansion_margin * (2 ** self._consecutive_failures),
                max_margin,
            )
            self._last_roi = self._last_roi.expanded(margin)
            self._last_roi = self._last_roi.clipped(*self._screen_size)

    def reset(self) -> None:
        self._last_roi = None
        self._last_match_pos = None
        self._consecutive_failures = 0

    @property
    def last_match_pos(self) -> tuple[int, int] | None:
        return self._last_match_pos

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures
