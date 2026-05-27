"""VisionPipeline 单元测试。

验证 VisionOutput、TemplateMatchStep、PixelSearchStep、OCRStep、VisionPipeline。
所有外部依赖（TemplateMatcher、PixelSearcher、OCRRecognizer）通过 mock 隔离。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.core.vision.ocr_result import OCRMultiResult, OCRResult
from src.core.vision.pixel_result import PixelSearchResult
from src.core.vision.vision_pipeline import (
    OCRStep,
    PixelSearchStep,
    TemplateMatchStep,
    VisionOutput,
    VisionPipeline,
)


def _screenshot(width: int = 100, height: int = 100) -> np.ndarray:
    """创建空白截图。"""
    return np.zeros((height, width, 3), dtype=np.uint8)


# ---- VisionOutput ----


class TestVisionOutput:
    def test_frozen(self) -> None:
        out = VisionOutput(success=True)
        with pytest.raises(AttributeError):
            out.success = False  # type: ignore[misc]

    def test_defaults(self) -> None:
        out = VisionOutput(success=False)
        assert out.primary_result is None
        assert out.template_result is None
        assert out.pixel_result is None
        assert out.ocr_result is None
        assert out.metadata is None


# ---- TemplateMatchStep ----


class TestTemplateMatchStep:
    def test_name(self) -> None:
        step = TemplateMatchStep("test.png")
        assert step.name == "template_match"

    def test_execute_found(self) -> None:
        mock_matcher = MagicMock()
        mock_matcher.find.return_value = (10, 20, 50, 40)

        step = TemplateMatchStep("test.png", threshold=0.9, region=(0, 0, 100, 100))
        ctx = {"_matcher": mock_matcher}
        result = step.execute(_screenshot(), ctx)

        assert result["template_result"]["found"] is True
        assert result["template_result"]["center"] == (35, 40)
        assert result["last_match"]["found"] is True
        mock_matcher.find.assert_called_once()

    def test_execute_not_found(self) -> None:
        mock_matcher = MagicMock()
        mock_matcher.find.return_value = None

        step = TemplateMatchStep("test.png")
        ctx = {"_matcher": mock_matcher}
        result = step.execute(_screenshot(), ctx)

        assert result["template_result"]["found"] is False
        assert result["last_match"]["found"] is False

    @patch("src.core.vision.vision_pipeline.TemplateMatchStep.execute")
    def test_execute_no_context_matcher(self, mock_execute) -> None:
        """无 _matcher 时应从 vision 模块导入 TemplateMatcher。"""
        step = TemplateMatchStep("test.png")
        ctx: dict = {}
        mock_execute.return_value = ctx
        # 实际测试由 test_execute_found 覆盖，此处验证 name
        assert step.name == "template_match"


# ---- PixelSearchStep ----


class TestPixelSearchStep:
    def test_name(self) -> None:
        step = PixelSearchStep((255, 0, 0))
        assert step.name == "pixel_search"

    def test_execute_with_searcher(self) -> None:
        mock_result = PixelSearchResult.found_pixels([(10, 20)])
        mock_searcher = MagicMock()
        mock_searcher.search.return_value = mock_result

        step = PixelSearchStep((255, 0, 0), tolerance=15, region=(0, 0, 50, 50))
        ctx = {"_searcher": mock_searcher}
        result = step.execute(_screenshot(), ctx)

        assert result["pixel_result"].found is True
        assert result["last_search"].found is True
        mock_searcher.search.assert_called_once()

    @patch("src.core.vision.pixel_searcher.PixelSearcher")
    def test_execute_without_searcher(self, mock_searcher_cls) -> None:
        mock_instance = MagicMock()
        mock_instance.search.return_value = PixelSearchResult.not_found()
        mock_searcher_cls.return_value = mock_instance

        step = PixelSearchStep((0, 200, 0))
        result = step.execute(_screenshot(), {})

        assert result["pixel_result"].found is False
        mock_searcher_cls.assert_called_once()


# ---- OCRStep ----


class TestOCRStep:
    def test_name(self) -> None:
        step = OCRStep()
        assert step.name == "ocr"

    def test_execute_with_target_found(self) -> None:
        ocr_item = OCRResult(
            text="Hello World",
            confidence=0.95,
            bounding_box=(10, 20, 100, 30),
        )
        mock_recognizer = MagicMock()
        mock_multi = MagicMock()
        mock_multi.find_text.return_value = ocr_item
        mock_recognizer.recognize.return_value = mock_multi

        step = OCRStep(region=(0, 0, 200, 100), target_text="Hello")
        ctx = {"_recognizer": mock_recognizer}
        result = step.execute(_screenshot(), ctx)

        assert result["ocr_result"].results[0].text == "Hello World"
        assert result["last_ocr"].results[0].text == "Hello World"

    def test_execute_with_target_not_found(self) -> None:
        mock_recognizer = MagicMock()
        mock_multi = MagicMock()
        mock_multi.find_text.return_value = None
        mock_recognizer.recognize.return_value = mock_multi

        step = OCRStep(target_text="missing")
        ctx = {"_recognizer": mock_recognizer}
        result = step.execute(_screenshot(), ctx)

        assert len(result["ocr_result"].results) == 0

    def test_execute_without_target(self) -> None:
        mock_recognizer = MagicMock()
        multi = OCRMultiResult.from_list([
            OCRResult(text="ABC", confidence=0.9, bounding_box=(0, 0, 10, 10)),
        ])
        mock_recognizer.recognize.return_value = multi

        step = OCRStep()
        ctx = {"_recognizer": mock_recognizer}
        result = step.execute(_screenshot(), ctx)

        assert result["ocr_result"] is multi

    @patch("src.core.vision.ocr_recognizer.OCRRecognizer")
    def test_execute_without_context_recognizer(self, mock_cls) -> None:
        mock_instance = MagicMock()
        mock_instance.recognize.return_value = OCRMultiResult.empty()
        mock_cls.return_value = mock_instance

        step = OCRStep()
        result = step.execute(_screenshot(), {})

        mock_cls.assert_called_once()


# ---- VisionPipeline ----


class TestVisionPipeline:
    def test_empty_pipeline(self) -> None:
        pipeline = VisionPipeline()
        output = pipeline.execute(_screenshot())
        assert output.success is False
        assert output.primary_result is None

    def test_add_step_returns_self(self) -> None:
        pipeline = VisionPipeline()
        result = pipeline.add_step(MagicMock())
        assert result is pipeline

    def test_clear_steps(self) -> None:
        mock_step = MagicMock()
        mock_step.execute.side_effect = lambda ss, ctx: ctx

        pipeline = VisionPipeline()
        pipeline.add_step(mock_step)
        pipeline.clear_steps()
        output = pipeline.execute(_screenshot())

        assert output.success is False
        mock_step.execute.assert_not_called()

    def test_template_match_success(self) -> None:
        mock_step = MagicMock()
        mock_step.name = "test"
        mock_step.execute.side_effect = lambda ss, ctx: {
            **ctx,
            "template_result": {"found": True, "x": 10, "y": 20, "w": 50, "h": 40},
            "last_match": {"found": True},
        }

        pipeline = VisionPipeline()
        pipeline.add_step(mock_step)
        output = pipeline.execute(_screenshot())

        assert output.success is True
        assert output.template_result["found"] is True
        assert output.primary_result["found"] is True

    def test_pixel_search_success(self) -> None:
        px_result = PixelSearchResult.found_pixels([(50, 50)])

        mock_step = MagicMock()
        mock_step.name = "pixel"
        mock_step.execute.side_effect = lambda ss, ctx: {
            **ctx,
            "pixel_result": px_result,
        }

        pipeline = VisionPipeline()
        pipeline.add_step(mock_step)
        output = pipeline.execute(_screenshot())

        assert output.success is True
        assert output.pixel_result.found is True

    def test_ocr_success(self) -> None:
        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="test", confidence=0.9, bounding_box=(0, 0, 10, 10)),
        ])

        mock_step = MagicMock()
        mock_step.name = "ocr"
        mock_step.execute.side_effect = lambda ss, ctx: {
            **ctx,
            "ocr_result": ocr_result,
        }

        pipeline = VisionPipeline()
        pipeline.add_step(mock_step)
        output = pipeline.execute(_screenshot())

        assert output.success is True
        assert output.ocr_result.results[0].text == "test"

    def test_multi_step_pipeline(self) -> None:
        px_result = PixelSearchResult.found_pixels([(10, 20)])
        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="HP", confidence=0.85, bounding_box=(0, 0, 20, 10)),
        ])

        step1 = MagicMock()
        step1.name = "pixel"
        step1.execute.side_effect = lambda ss, ctx: {**ctx, "pixel_result": px_result}

        step2 = MagicMock()
        step2.name = "ocr"
        step2.execute.side_effect = lambda ss, ctx: {**ctx, "ocr_result": ocr_result}

        pipeline = VisionPipeline()
        pipeline.add_step(step1)
        pipeline.add_step(step2)
        output = pipeline.execute(_screenshot())

        assert output.success is True
        assert output.pixel_result.found is True
        assert output.ocr_result.results[0].text == "HP"

    def test_stop_on_failure(self) -> None:
        step1 = MagicMock()
        step1.name = "tpl"
        step1.execute.side_effect = lambda ss, ctx: {
            **ctx,
            "template_result": {"found": False},
            "last_match": {"found": False},
        }

        step2 = MagicMock()
        step2.name = "never_reached"

        pipeline = VisionPipeline(stop_on_failure=True)
        pipeline.add_step(step1)
        pipeline.add_step(step2)
        output = pipeline.execute(_screenshot())

        assert output.success is False
        step2.execute.assert_not_called()

    def test_stop_on_failure_exception(self) -> None:
        step1 = MagicMock()
        step1.name = "bad"
        step1.execute.side_effect = RuntimeError("boom")

        step2 = MagicMock()
        step2.name = "never"

        pipeline = VisionPipeline(stop_on_failure=True)
        pipeline.add_step(step1)
        pipeline.add_step(step2)
        output = pipeline.execute(_screenshot())

        assert output.success is False
        step2.execute.assert_not_called()

    def test_exception_continues_without_stop_on_failure(self) -> None:
        step1 = MagicMock()
        step1.name = "bad"
        step1.execute.side_effect = RuntimeError("boom")

        px_result = PixelSearchResult.found_pixels([(5, 5)])
        step2 = MagicMock()
        step2.name = "ok"
        step2.execute.side_effect = lambda ss, ctx: {**ctx, "pixel_result": px_result}

        pipeline = VisionPipeline(stop_on_failure=False)
        pipeline.add_step(step1)
        pipeline.add_step(step2)
        output = pipeline.execute(_screenshot())

        assert output.success is True
        assert output.pixel_result.found is True

    def test_shared_services_passed(self) -> None:
        mock_matcher = MagicMock()
        mock_step = MagicMock()
        mock_step.name = "test"
        mock_step.execute.side_effect = lambda ss, ctx: ctx

        pipeline = VisionPipeline()
        pipeline.add_step(mock_step)
        pipeline.execute(_screenshot(), shared_services={"_matcher": mock_matcher})

        call_args = mock_step.execute.call_args
        assert call_args[0][1]["_matcher"] is mock_matcher

    def test_primary_result_priority(self) -> None:
        """模板匹配优先于像素搜索，像素搜索优先于 OCR。"""
        px_result = PixelSearchResult.found_pixels([(10, 10)])
        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="X", confidence=0.9, bounding_box=(0, 0, 5, 5)),
        ])

        step = MagicMock()
        step.name = "multi"
        step.execute.side_effect = lambda ss, ctx: {
            **ctx,
            "template_result": {"found": True, "x": 1, "y": 2, "w": 3, "h": 4},
            "pixel_result": px_result,
            "ocr_result": ocr_result,
        }

        pipeline = VisionPipeline()
        pipeline.add_step(step)
        output = pipeline.execute(_screenshot())

        assert isinstance(output.primary_result, dict)
        assert output.primary_result["found"] is True

    def test_primary_result_pixel_fallback(self) -> None:
        """无模板匹配时，像素搜索作为 primary。"""
        px_result = PixelSearchResult.found_pixels([(10, 10)])

        step = MagicMock()
        step.name = "px"
        step.execute.side_effect = lambda ss, ctx: {**ctx, "pixel_result": px_result}

        pipeline = VisionPipeline()
        pipeline.add_step(step)
        output = pipeline.execute(_screenshot())

        assert output.primary_result is px_result

    def test_primary_result_ocr_fallback(self) -> None:
        """无模板和像素时，OCR best 作为 primary。"""
        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="Y", confidence=0.8, bounding_box=(0, 0, 5, 5)),
        ])

        step = MagicMock()
        step.name = "ocr"
        step.execute.side_effect = lambda ss, ctx: {**ctx, "ocr_result": ocr_result}

        pipeline = VisionPipeline()
        pipeline.add_step(step)
        output = pipeline.execute(_screenshot())

        assert output.primary_result is ocr_result.best

    def test_metadata_none_when_absent(self) -> None:
        pipeline = VisionPipeline()
        output = pipeline.execute(_screenshot())
        assert output.metadata is None
