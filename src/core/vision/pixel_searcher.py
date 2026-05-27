"""HSV 颜色空间像素搜索器"""

import logging

import numpy as np

from src.core.vision._cv2_guard import cv2, require_cv2
from src.core.vision.pixel_result import PixelSearchResult
from src.utils.float_utils import is_zero
logger = logging.getLogger(__name__)


class PixelSearcher:
    """HSV 颜色空间像素搜索器。

    功能：
    - BGR 精确颜色匹配
    - HSV 容差搜索（对光照变化鲁棒）
    - 指定区域搜索（缩小范围提升速度）
    - 多点匹配（返回所有匹配位置）
    - 预定义颜色预设（red, green, blue 等）
    - 红色跨边界处理（HSV H 值在 0~10 和 160~180）

    HSV 范围说明：
    - H (Hue):        0~180（OpenCV 缩放后）
    - S (Saturation): 0~255
    - V (Value):      0~255
    """

    # 红色跨边界范围（预计算）
    _RED_HIGH_LOWER = np.array([160, 100, 100])
    _RED_HIGH_UPPER = np.array([180, 255, 255])
    _RED_LOW_LOWER = np.array([0, 100, 100])
    _RED_LOW_UPPER = np.array([10, 255, 255])

    # clip 常量（预计算，避免每次调用 _match_hsv 时重复分配）
    _HSV_LOWER_BOUND = np.array([0, 0, 0])
    _HSV_UPPER_BOUND = _RED_HIGH_UPPER

    def __init__(self) -> None:
        require_cv2("pixel search")
        self._color_presets: dict[str, tuple[np.ndarray, np.ndarray]] = {
            "red": (
                self._RED_LOW_LOWER,
                self._RED_LOW_UPPER,
            ),
            "red_dark": (
                self._RED_HIGH_LOWER,
                self._RED_HIGH_UPPER,
            ),
            "green": (
                np.array([35, 100, 100]),
                np.array([85, 255, 255]),
            ),
            "blue": (
                np.array([100, 100, 100]),
                np.array([130, 255, 255]),
            ),
            "yellow": (
                np.array([20, 100, 100]),
                np.array([35, 255, 255]),
            ),
            "white": (
                np.array([0, 0, 200]),
                np.array([180, 30, 255]),
            ),
            "gray": (
                np.array([0, 0, 100]),
                np.array([180, 50, 200]),
            ),
        }

    # ---- BGR 精确匹配 (D1) ----

    def match_bgr_exact(
        self,
        screenshot: np.ndarray,
        target_bgr: tuple[int, int, int],
        region: tuple[int, int, int, int] | None = None,
    ) -> PixelSearchResult:
        """在截图中搜索精确 BGR 颜色像素。

        参数：
            screenshot:  截图 (H, W, 3) BGR
            target_bgr:  目标颜色 (B, G, R)
            region:      搜索区域 (x, y, w, h)，None 表示全图

        返回：
            PixelSearchResult
        """
        search_area, offset = self._crop_region(screenshot, region)

        target = np.array(target_bgr, dtype=np.uint8)
        mask = cv2.inRange(search_area, target, target)

        return self._mask_to_result(mask, offset, region)

    # ---- HSV 容差搜索 (D2) ----

    def search(
        self,
        screenshot: np.ndarray,
        target_color: tuple[int, int, int],
        tolerance: int = 10,
        region: tuple[int, int, int, int] | None = None,
        max_results: int = 100,
    ) -> PixelSearchResult:
        """在截图中搜索目标颜色像素（HSV 容差匹配）。

        参数：
            screenshot:   截图 (H, W, 3) BGR
            target_color: 目标颜色 (H, S, V)，HSV 格式
                          H: 0~180, S: 0~255, V: 0~255
            tolerance:    颜色容差（HSV 各通道允许的偏差）
            region:       搜索区域 (x, y, w, h)，None 表示全图
            max_results:  最大返回结果数

        返回：
            PixelSearchResult
        """
        search_area, offset = self._crop_region(screenshot, region)
        hsv = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)
        return self._match_hsv(hsv, target_color, tolerance, offset, region, max_results)

    def _match_hsv(
        self,
        hsv: np.ndarray,
        target_color: tuple[int, int, int],
        tolerance: int,
        offset: tuple[int, int],
        region: tuple[int, int, int, int] | None,
        max_results: int = 100,
    ) -> PixelSearchResult:
        """在已转换的 HSV 图像上搜索目标颜色（供 search / search_multi_color 复用）。"""
        target = np.array(target_color, dtype=np.int32)
        lower = np.clip(target - tolerance, self._HSV_LOWER_BOUND, self._HSV_UPPER_BOUND).astype(np.uint8)
        upper = np.clip(target + tolerance, self._HSV_LOWER_BOUND, self._HSV_UPPER_BOUND).astype(np.uint8)

        if target_color[0] <= tolerance or target_color[0] >= 180 - tolerance:
            return self._search_red_wrap(hsv, lower, offset, max_results, region)

        mask = cv2.inRange(hsv, lower, upper)
        return self._mask_to_result(mask, offset, region, max_results)

    # ---- 预定义颜色搜索 ----

    def search_preset(
        self,
        screenshot: np.ndarray,
        color_name: str,
        region: tuple[int, int, int, int] | None = None,
    ) -> PixelSearchResult:
        """使用预定义颜色名称搜索。

        参数：
            screenshot:  截图
            color_name:  颜色名称 ("red", "green", "blue", "yellow", "white", "gray")
            region:      搜索区域

        返回：
            PixelSearchResult
        """
        if color_name not in self._color_presets:
            logger.warning("未知颜色预设: '%s'", color_name)
            return PixelSearchResult.not_found()

        search_area, offset = self._crop_region(screenshot, region)
        hsv = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)
        lower, upper = self._color_presets[color_name]

        mask = cv2.inRange(hsv, lower, upper)

        # 红色预设需要合并两个区间
        if color_name in ("red", "red_dark"):
            if color_name == "red":
                mask2 = cv2.inRange(hsv, self._RED_HIGH_LOWER, self._RED_HIGH_UPPER)
            else:
                mask2 = cv2.inRange(hsv, self._RED_LOW_LOWER, self._RED_LOW_UPPER)
            mask = cv2.bitwise_or(mask, mask2)

        return self._mask_to_result(mask, offset, region)

    # ---- 区域搜索 + 多像素 (D3) ----

    def search_multi_color(
        self,
        screenshot: np.ndarray,
        colors: list[tuple[int, int, int]],
        tolerance: int = 10,
        region: tuple[int, int, int, int] | None = None,
        require_all: bool = False,
    ) -> PixelSearchResult:
        """多点颜色搜索 — 同时搜索多种颜色。

        参数：
            screenshot:  截图 (H, W, 3) BGR
            colors:      目标颜色列表 [(H, S, V), ...]
            tolerance:   颜色容差
            region:      搜索区域
            require_all: True 时要求所有颜色都在区域内找到

        返回：
            PixelSearchResult（合并所有颜色的匹配位置）
        """
        search_area, offset = self._crop_region(screenshot, region)
        hsv = cv2.cvtColor(search_area, cv2.COLOR_BGR2HSV)

        all_positions: list[tuple[int, int]] = []

        for color in colors:
            result = self._match_hsv(hsv, color, tolerance, offset, region)
            if require_all and not result.found:
                return PixelSearchResult.not_found()
            if result.found:
                all_positions.extend(result.positions)

        # 去重
        unique = list(dict.fromkeys(all_positions))
        if not unique:
            return PixelSearchResult.not_found()

        return PixelSearchResult.found_pixels(unique, region)

    # ---- 辅助接口 ----

    def get_pixel_color(
        self,
        screenshot: np.ndarray,
        x: int,
        y: int,
        color_space: str = "hsv",
    ) -> tuple[int, int, int]:
        """获取指定像素的颜色值。

        参数：
            screenshot:   截图
            x, y:         像素坐标
            color_space:  返回颜色空间 "hsv" 或 "bgr"

        返回：
            (H, S, V) 或 (B, G, R) 颜色值
        """
        if y >= screenshot.shape[0] or x >= screenshot.shape[1]:
            return (0, 0, 0)

        bgr = screenshot[y, x]
        if color_space == "hsv":
            return self._bgr_to_hsv(int(bgr[0]), int(bgr[1]), int(bgr[2]))
        return (int(bgr[0]), int(bgr[1]), int(bgr[2]))

    @staticmethod
    def _bgr_to_hsv(b: int, g: int, r: int) -> tuple[int, int, int]:
        """纯 Python BGR→HSV 转换（OpenCV 缩放：H 0~180, S/V 0~255）。"""
        b_f, g_f, r_f = b / 255.0, g / 255.0, r / 255.0
        v = max(b_f, g_f, r_f)
        diff = v - min(b_f, g_f, r_f)

        if is_zero(diff):
            h = 0.0
        elif is_zero(v - r_f):
            h = 60.0 * (((g_f - b_f) / diff) % 6)
        elif is_zero(v - g_f):
            h = 60.0 * (((b_f - r_f) / diff) + 2)
        else:
            h = 60.0 * (((r_f - g_f) / diff) + 4)

        s = 0.0 if is_zero(v) else diff / v
        return (int(h / 2.0), int(s * 255.0), int(v * 255.0))

    # ---- 内部方法 ----

    def _crop_region(
        self,
        screenshot: np.ndarray,
        region: tuple[int, int, int, int] | None,
    ) -> tuple[np.ndarray, tuple[int, int]]:
        """裁剪搜索区域，返回 (裁剪后图像, 偏移量)"""
        if region is None:
            return screenshot, (0, 0)
        x, y, w, h = region
        if w <= 0 or h <= 0:
            raise ValueError(f"Invalid region dimensions: w={w}, h={h}")
        x = max(0, x)
        y = max(0, y)
        y2 = min(y + h, screenshot.shape[0])
        x2 = min(x + w, screenshot.shape[1])
        return screenshot[y:y2, x:x2], (x, y)

    def _mask_to_result(
        self,
        mask: np.ndarray,
        offset: tuple[int, int],
        region: tuple[int, int, int, int] | None,
        max_results: int = 100,
    ) -> PixelSearchResult:
        """将二值掩码转换为 PixelSearchResult"""
        ys, xs = np.where(mask > 0)
        if len(ys) == 0:
            return PixelSearchResult.not_found()

        count = len(xs)
        if count > max_results:
            indices = np.linspace(0, count - 1, max_results, dtype=int)
            xs = xs[indices]
            ys = ys[indices]

        # numpy 向量化：一次加偏移，zip 构建坐标
        xs_off = xs + offset[0]
        ys_off = ys + offset[1]
        coords = list(zip(xs_off.tolist(), ys_off.tolist(), strict=False))
        return PixelSearchResult.found_pixels(coords, region)

    def _search_red_wrap(
        self,
        hsv: np.ndarray,
        lower: np.ndarray,
        offset: tuple[int, int],
        max_results: int,
        region: tuple[int, int, int, int] | None,
    ) -> PixelSearchResult:
        """处理红色跨边界搜索 — HSV 中红色 H 值在 0~10 和 160~180 两个区间"""
        red1_lower = np.array([0, lower[1], lower[2]])
        red2_lower = np.array([160, lower[1], lower[2]])
        mask1 = cv2.inRange(hsv, red1_lower, self._RED_LOW_UPPER)
        mask2 = cv2.inRange(hsv, red2_lower, self._RED_HIGH_UPPER)
        mask = cv2.bitwise_or(mask1, mask2)
        return self._mask_to_result(mask, offset, region, max_results)
