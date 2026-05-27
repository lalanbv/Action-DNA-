"""PixelSearcher 单元测试。

覆盖 D1-D3 验收标准：
- D1: BGR 精确颜色匹配
- D2: HSV 容差搜索
- D3: 区域搜索 + 多像素匹配
"""

import numpy as np
import pytest

pytest.importorskip("cv2")

from src.core.vision.pixel_result import PixelSearchResult
from src.core.vision.pixel_searcher import PixelSearcher


# ---- 测试辅助 ----


def _solid_image(
    height: int = 100,
    width: int = 100,
    bgr: tuple[int, int, int] = (0, 0, 255),
) -> np.ndarray:
    """生成纯色 BGR 测试图像。"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = bgr
    return img


def _two_color_image(
    height: int = 100,
    width: int = 100,
    left_bgr: tuple[int, int, int] = (0, 0, 255),
    right_bgr: tuple[int, int, int] = (0, 255, 0),
) -> np.ndarray:
    """生成左右两色测试图像。"""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    mid = width // 2
    img[:, :mid] = left_bgr
    img[:, mid:] = right_bgr
    return img


# ---- D1: BGR 精确匹配 ----


class TestBgrExact:

    def test_find_exact_color(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.match_bgr_exact(img, (0, 0, 255))
        assert result.found is True
        assert result.count > 0

    def test_no_match_wrong_color(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.match_bgr_exact(img, (255, 0, 0))
        assert result.found is False
        assert result.count == 0

    def test_partial_match_positions(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.match_bgr_exact(img, (0, 0, 255))
        assert result.found is True
        for x, _ in result.positions:
            assert x < 50

    def test_region_restricts_search(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.match_bgr_exact(img, (0, 0, 255), region=(50, 0, 50, 100))
        assert result.found is False

    def test_region_search_hit(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.match_bgr_exact(img, (0, 0, 255), region=(0, 0, 50, 100))
        assert result.found is True
        assert result.count > 0

    def test_result_positions_are_global(self):
        """区域搜索时返回的坐标应该是全局坐标。"""
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.match_bgr_exact(img, (0, 0, 255), region=(10, 10, 30, 30))
        if result.found:
            for x, y in result.positions:
                assert x >= 10
                assert y >= 10


# ---- D2: HSV 容差搜索 ----


class TestHsvTolerance:

    def test_exact_hsv_match(self):
        """纯红色 HSV (H=0, S=255, V=255) — BGR (0, 0, 255)。"""
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search(img, (0, 255, 255), tolerance=5)
        assert result.found is True

    def test_tolerance_allows_variation(self):
        """稍有偏差的颜色仍能在容差范围内匹配。"""
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search(img, (5, 255, 255), tolerance=10)
        assert result.found is True

    def test_no_match_outside_tolerance(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search(img, (120, 255, 255), tolerance=10)
        assert result.found is False

    def test_green_hsv(self):
        """绿色 BGR (0, 255, 0) → HSV 约 (60, 255, 255)。"""
        img = _solid_image(bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search(img, (60, 255, 255), tolerance=5)
        assert result.found is True

    def test_blue_hsv(self):
        """蓝色 BGR (255, 0, 0) → HSV 约 (120, 255, 255)。"""
        img = _solid_image(bgr=(255, 0, 0))
        searcher = PixelSearcher()
        result = searcher.search(img, (120, 255, 255), tolerance=5)
        assert result.found is True

    def test_two_color_split(self):
        """双色图像中搜索其中一种颜色。"""
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search(img, (60, 255, 255), tolerance=5)
        assert result.found is True
        for x, _ in result.positions:
            assert x >= 50


# ---- D2: 红色跨边界 ----


class TestRedWrap:

    def test_red_h_near_zero(self):
        """H 接近 0 的红色应触发跨边界搜索。"""
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search(img, (0, 255, 255), tolerance=5)
        assert result.found is True

    def test_red_h_near_180(self):
        """H 接近 180 的红色也应匹配。"""
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search(img, (175, 255, 255), tolerance=10)
        assert result.found is True


# ---- D3: 区域搜索 ----


class TestRegionSearch:

    def test_region_hsv(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search(img, (60, 255, 255), tolerance=5, region=(50, 0, 50, 100))
        assert result.found is True

    def test_region_miss(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search(img, (0, 255, 255), tolerance=5, region=(50, 0, 50, 100))
        assert result.found is False

    def test_search_region_recorded(self):
        """搜索结果应记录搜索区域。"""
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        region = (10, 20, 30, 40)
        result = searcher.search(img, (0, 255, 255), tolerance=5, region=region)
        assert result.search_region == region

    def test_none_region_means_full_image(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search(img, (0, 255, 255), tolerance=5, region=None)
        assert result.found is True
        assert result.search_region is None


# ---- D3: 多点匹配 ----


class TestMultiColor:

    def test_find_both_colors(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search_multi_color(
            img,
            colors=[(0, 255, 255), (60, 255, 255)],
            tolerance=10,
        )
        assert result.found is True
        assert result.count > 0

    def test_require_all_true(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search_multi_color(
            img,
            colors=[(0, 255, 255), (60, 255, 255)],
            tolerance=10,
            require_all=True,
        )
        assert result.found is True

    def test_require_all_fails_on_missing(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search_multi_color(
            img,
            colors=[(0, 255, 255), (120, 255, 255)],
            tolerance=10,
            require_all=True,
        )
        assert result.found is False

    def test_require_all_false_partial(self):
        """require_all=False 时只要有一种颜色匹配即可。"""
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search_multi_color(
            img,
            colors=[(0, 255, 255), (120, 255, 255)],
            tolerance=10,
            require_all=False,
        )
        assert result.found is True


# ---- 预设颜色搜索 ----


class TestPresetColors:

    def test_red_preset(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search_preset(img, "red")
        assert result.found is True

    def test_green_preset(self):
        img = _solid_image(bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search_preset(img, "green")
        assert result.found is True

    def test_blue_preset(self):
        img = _solid_image(bgr=(255, 0, 0))
        searcher = PixelSearcher()
        result = searcher.search_preset(img, "blue")
        assert result.found is True

    def test_unknown_preset_returns_not_found(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        result = searcher.search_preset(img, "nonexistent")
        assert result.found is False

    def test_preset_with_region(self):
        img = _two_color_image(left_bgr=(0, 0, 255), right_bgr=(0, 255, 0))
        searcher = PixelSearcher()
        result = searcher.search_preset(img, "green", region=(50, 0, 50, 100))
        assert result.found is True


# ---- PixelSearchResult 数据结构 ----


class TestPixelSearchResult:

    def test_not_found_factory(self):
        r = PixelSearchResult.not_found()
        assert r.found is False
        assert r.count == 0
        assert r.positions == ()

    def test_found_pixels_factory(self):
        positions = [(10, 20), (30, 40)]
        r = PixelSearchResult.found_pixels(positions, region=(0, 0, 100, 100))
        assert r.found is True
        assert r.count == 2
        assert r.positions == ((10, 20), (30, 40))
        assert r.search_region == (0, 0, 100, 100)

    def test_first_property(self):
        r = PixelSearchResult.found_pixels([(5, 10), (20, 30)])
        assert r.first == (5, 10)

    def test_first_empty(self):
        r = PixelSearchResult.not_found()
        assert r.first is None

    def test_center_of_mass(self):
        r = PixelSearchResult.found_pixels([(0, 0), (100, 100)])
        assert r.center_of_mass == (50, 50)

    def test_center_of_mass_empty(self):
        r = PixelSearchResult.not_found()
        assert r.center_of_mass is None

    def test_frozen(self):
        r = PixelSearchResult.not_found()
        with pytest.raises(AttributeError):
            r.found = True  # type: ignore[misc]


# ---- get_pixel_color ----


class TestGetPixelColor:

    def test_bgr_color(self):
        img = _solid_image(bgr=(100, 150, 200))
        searcher = PixelSearcher()
        color = searcher.get_pixel_color(img, 0, 0, color_space="bgr")
        assert color == (100, 150, 200)

    def test_hsv_color(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        h, s, v = searcher.get_pixel_color(img, 0, 0, color_space="hsv")
        assert h == 0
        assert s == 255
        assert v == 255

    def test_out_of_bounds(self):
        img = _solid_image(bgr=(0, 0, 255))
        searcher = PixelSearcher()
        color = searcher.get_pixel_color(img, 200, 200)
        assert color == (0, 0, 0)
