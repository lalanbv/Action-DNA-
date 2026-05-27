"""PixelSearchDescriptor 单元测试。

覆盖: action_type、display_name、execute (mock pixel_searcher)。
"""

from unittest.mock import MagicMock

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.descriptors.pixel_search_descriptor import PixelSearchDescriptor
from src.core.vision.pixel_result import PixelSearchResult


def _make_ctx(
    action: BaseStep | None = None,
    pixel_searcher: object | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.current_node.action = action
    ctx.capture = MagicMock()
    ctx.capture.capture.return_value = MagicMock()
    ctx.extra = {}
    if pixel_searcher is not None:
        ctx.extra["pixel_searcher"] = pixel_searcher
    return ctx


# ============================================================
# 元数据
# ============================================================


class TestPixelSearchDescriptorMeta:
    def test_action_type(self):
        assert PixelSearchDescriptor.action_type() == "PIXEL_SEARCH"

    def test_display_name(self):
        assert PixelSearchDescriptor.display_name() == "像素搜索"

    def test_category(self):
        assert PixelSearchDescriptor.category() == "视觉检测"

    def test_input_types(self):
        inputs = PixelSearchDescriptor.input_types()
        assert "target_color" in inputs
        assert "color_tolerance" in inputs
        assert "color_mode" in inputs

    def test_output_types(self):
        outputs = PixelSearchDescriptor.output_types()
        assert "found" in outputs
        assert "position" in outputs
        assert "count" in outputs


# ============================================================
# execute
# ============================================================


class TestPixelSearchDescriptorExecute:
    def test_execute_no_action_returns_fail(self):
        ctx = _make_ctx(action=None)
        result = PixelSearchDescriptor().execute(ctx)
        assert result.success is False

    def test_execute_no_searcher_returns_fail(self):
        action = STEP_CLASSES[ActionType.PIXEL_SEARCH]()
        ctx = _make_ctx(action=action, pixel_searcher=None)
        result = PixelSearchDescriptor().execute(ctx)
        assert result.success is False

    def test_execute_hsv_search_found(self):
        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            target_color=(100, 200, 150),
            color_tolerance=15,
            color_mode="hsv",
        )
        searcher = MagicMock()
        searcher.search.return_value = PixelSearchResult.found_pixels(
            [(100, 200)],
        )
        ctx = _make_ctx(action=action, pixel_searcher=searcher)
        result = PixelSearchDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is True
        assert result.output_vars["position"] == (100, 200)
        assert result.output_vars["count"] == 1
        searcher.search.assert_called_once()

    def test_execute_hsv_search_not_found(self):
        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            target_color=(100, 200, 150),
            color_mode="hsv",
        )
        searcher = MagicMock()
        searcher.search.return_value = PixelSearchResult.not_found()
        ctx = _make_ctx(action=action, pixel_searcher=searcher)
        result = PixelSearchDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is False
        assert result.output_vars["count"] == 0

    def test_execute_bgr_search(self):
        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            target_color=(50, 100, 150),
            color_mode="bgr",
        )
        searcher = MagicMock()
        searcher.match_bgr_exact.return_value = PixelSearchResult.found_pixels(
            [(200, 300)],
        )
        ctx = _make_ctx(action=action, pixel_searcher=searcher)
        result = PixelSearchDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is True
        searcher.match_bgr_exact.assert_called_once()

    def test_execute_preset_search(self):
        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            color_mode="preset",
            color_preset="red",
        )
        searcher = MagicMock()
        searcher.search_preset.return_value = PixelSearchResult.found_pixels(
            [(50, 60)],
        )
        ctx = _make_ctx(action=action, pixel_searcher=searcher)
        result = PixelSearchDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is True
        searcher.search_preset.assert_called_once()

    def test_execute_no_color_returns_fail(self):
        action = STEP_CLASSES[ActionType.PIXEL_SEARCH](
            color_mode="hsv",
        )
        searcher = MagicMock()
        ctx = _make_ctx(action=action, pixel_searcher=searcher)
        result = PixelSearchDescriptor().execute(ctx)

        assert result.success is False
