"""VisionPipeline 集成测试 — 组合检测管线端到端验证。

覆盖：单步/多步组合、条件跳过、shared_services 注入、VisionOutput 汇总。
"""

from unittest.mock import MagicMock

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


@pytest.fixture
def screenshot() -> np.ndarray:
    """256x256 黑色截图"""
    return np.zeros((256, 256, 3), dtype=np.uint8)


@pytest.fixture
def screenshot_with_red() -> np.ndarray:
    """256x256 截图，中心区域有红色像素"""
    img = np.zeros((256, 256, 3), dtype=np.uint8)
    img[120:130, 120:130] = (0, 0, 255)  # BGR red
    return img


# ============================================================
# 单步执行
# ============================================================


class TestSingleStepTemplate:
    def test_template_match_found(self, screenshot: np.ndarray) -> None:
        matcher = MagicMock()
        matcher.find.return_value = (10, 20, 30, 40)

        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("test.png", threshold=0.8))
        output = pipeline.execute(
            screenshot, shared_services={"_matcher": matcher}
        )

        assert output.success is True
        assert output.template_result is not None
        assert output.template_result["found"] is True
        assert output.template_result["center"] == (25, 40)

    def test_template_match_not_found(self, screenshot: np.ndarray) -> None:
        matcher = MagicMock()
        matcher.find.return_value = None

        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("test.png"))
        output = pipeline.execute(
            screenshot, shared_services={"_matcher": matcher}
        )

        assert output.success is False
        assert output.template_result["found"] is False


class TestSingleStepPixel:
    def test_pixel_search_found(self, screenshot_with_red: np.ndarray) -> None:
        pipeline = VisionPipeline()
        pipeline.add_step(PixelSearchStep((0, 0, 255), tolerance=10))
        output = pipeline.execute(screenshot_with_red)

        assert output.success is True
        assert output.pixel_result is not None
        assert output.pixel_result.found is True

    def test_pixel_search_not_found(self, screenshot: np.ndarray) -> None:
        pipeline = VisionPipeline()
        pipeline.add_step(PixelSearchStep((0, 255, 0), tolerance=5))
        output = pipeline.execute(screenshot)

        assert output.success is False
        assert output.pixel_result is not None
        assert output.pixel_result.found is False


class TestSingleStepOCR:
    def test_ocr_with_mock(self, screenshot: np.ndarray) -> None:
        ocr_result = OCRMultiResult.from_list([
            OCRResult(
                text="开始游戏", confidence=0.95, bounding_box=(10, 20, 80, 30)
            ),
        ])
        recognizer = MagicMock()
        recognizer.recognize.return_value = ocr_result

        pipeline = VisionPipeline()
        pipeline.add_step(OCRStep())
        output = pipeline.execute(
            screenshot, shared_services={"_recognizer": recognizer}
        )

        assert output.success is True
        assert output.ocr_result is not None
        assert output.ocr_result.best is not None
        assert output.ocr_result.best.text == "开始游戏"


# ============================================================
# 多步组合
# ============================================================


class TestMultiStepPipeline:
    def test_template_then_pixel_both_found(
        self, screenshot_with_red: np.ndarray
    ) -> None:
        matcher = MagicMock()
        matcher.find.return_value = (50, 50, 40, 40)

        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("enemy.png"))
        pipeline.add_step(PixelSearchStep((0, 0, 255), tolerance=10))
        output = pipeline.execute(
            screenshot_with_red, shared_services={"_matcher": matcher}
        )

        assert output.success is True
        assert output.template_result["found"] is True
        assert output.pixel_result.found is True
        assert output.primary_result == output.template_result

    def test_all_three_steps(self, screenshot_with_red: np.ndarray) -> None:
        matcher = MagicMock()
        matcher.find.return_value = (10, 10, 20, 20)

        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="HP", confidence=0.9, bounding_box=(5, 5, 30, 15)),
        ])
        recognizer = MagicMock()
        recognizer.recognize.return_value = ocr_result

        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("ui.png"))
        pipeline.add_step(PixelSearchStep((0, 0, 255), tolerance=10))
        pipeline.add_step(OCRStep())
        output = pipeline.execute(
            screenshot_with_red,
            shared_services={"_matcher": matcher, "_recognizer": recognizer},
        )

        assert output.success is True
        assert output.template_result["found"] is True
        assert output.pixel_result.found is True
        assert output.ocr_result is not None
        assert len(output.ocr_result.results) > 0

    def test_fallback_to_pixel_when_template_fails(
        self, screenshot_with_red: np.ndarray
    ) -> None:
        matcher = MagicMock()
        matcher.find.return_value = None

        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("missing.png"))
        pipeline.add_step(PixelSearchStep((0, 0, 255), tolerance=10))
        output = pipeline.execute(
            screenshot_with_red, shared_services={"_matcher": matcher}
        )

        assert output.success is True
        assert output.template_result["found"] is False
        assert output.pixel_result.found is True
        assert isinstance(output.primary_result, PixelSearchResult)

    def test_fallback_to_ocr_when_others_fail(
        self, screenshot: np.ndarray
    ) -> None:
        matcher = MagicMock()
        matcher.find.return_value = None

        ocr_result = OCRMultiResult.from_list([
            OCRResult(
                text="确定", confidence=0.88, bounding_box=(100, 50, 40, 20)
            ),
        ])
        recognizer = MagicMock()
        recognizer.recognize.return_value = ocr_result

        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("missing.png"))
        pipeline.add_step(PixelSearchStep((0, 255, 0), tolerance=5))
        pipeline.add_step(OCRStep())
        output = pipeline.execute(
            screenshot,
            shared_services={"_matcher": matcher, "_recognizer": recognizer},
        )

        assert output.success is True
        assert output.primary_result is not None


# ============================================================
# stop_on_failure 模式
# ============================================================


class TestStopOnFailure:
    def test_stops_on_template_failure(self, screenshot: np.ndarray) -> None:
        matcher = MagicMock()
        matcher.find.return_value = None

        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="文字", confidence=0.9, bounding_box=(0, 0, 10, 10)),
        ])
        recognizer = MagicMock()
        recognizer.recognize.return_value = ocr_result

        pipeline = VisionPipeline(stop_on_failure=True)
        pipeline.add_step(TemplateMatchStep("missing.png"))
        pipeline.add_step(OCRStep())
        output = pipeline.execute(
            screenshot,
            shared_services={"_matcher": matcher, "_recognizer": recognizer},
        )

        assert output.success is False
        assert output.ocr_result is None

    def test_continues_when_stop_disabled(self, screenshot: np.ndarray) -> None:
        matcher = MagicMock()
        matcher.find.return_value = None

        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="文字", confidence=0.9, bounding_box=(0, 0, 10, 10)),
        ])
        recognizer = MagicMock()
        recognizer.recognize.return_value = ocr_result

        pipeline = VisionPipeline(stop_on_failure=False)
        pipeline.add_step(TemplateMatchStep("missing.png"))
        pipeline.add_step(OCRStep())
        output = pipeline.execute(
            screenshot,
            shared_services={"_matcher": matcher, "_recognizer": recognizer},
        )

        assert output.success is True
        assert output.ocr_result is not None


# ============================================================
# OCRStep target_text 过滤
# ============================================================


class TestOCRStepTargetText:
    def test_target_text_found(self, screenshot: np.ndarray) -> None:
        ocr_result = OCRMultiResult.from_list([
            OCRResult(
                text="开始游戏", confidence=0.9, bounding_box=(10, 20, 80, 30)
            ),
            OCRResult(text="设置", confidence=0.85, bounding_box=(10, 60, 40, 20)),
        ])
        recognizer = MagicMock()
        recognizer.recognize.return_value = ocr_result

        pipeline = VisionPipeline()
        pipeline.add_step(OCRStep(target_text="开始"))
        output = pipeline.execute(
            screenshot, shared_services={"_recognizer": recognizer}
        )

        assert output.ocr_result is not None
        assert output.ocr_result.best is not None
        assert "开始" in output.ocr_result.best.text

    def test_target_text_not_found(self, screenshot: np.ndarray) -> None:
        ocr_result = OCRMultiResult.from_list([
            OCRResult(text="设置", confidence=0.9, bounding_box=(10, 60, 40, 20)),
        ])
        recognizer = MagicMock()
        recognizer.recognize.return_value = ocr_result

        pipeline = VisionPipeline()
        pipeline.add_step(OCRStep(target_text="退出"))
        output = pipeline.execute(
            screenshot, shared_services={"_recognizer": recognizer}
        )

        assert output.ocr_result is not None
        assert output.ocr_result.results == ()
        assert output.success is False


# ============================================================
# VisionOutput 不可变
# ============================================================


class TestVisionOutputImmutable:
    def test_frozen(self) -> None:
        output = VisionOutput(success=True)
        with pytest.raises(AttributeError):
            output.success = False  # type: ignore[misc]


# ============================================================
# clear_steps
# ============================================================


class TestClearSteps:
    def test_clear_and_reuse(self, screenshot: np.ndarray) -> None:
        matcher = MagicMock()
        matcher.find.return_value = (10, 10, 20, 20)

        pipeline = VisionPipeline()
        pipeline.add_step(TemplateMatchStep("first.png"))
        pipeline.clear_steps()
        pipeline.add_step(TemplateMatchStep("second.png"))
        output = pipeline.execute(
            screenshot, shared_services={"_matcher": matcher}
        )

        assert output.success is True
        assert matcher.find.call_count == 1
