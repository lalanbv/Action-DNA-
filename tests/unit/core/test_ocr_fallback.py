"""OCR 降级测试 — rapidocr 未安装时所有方法安全返回空结果。

验证：当 OCR_AVAILABLE=False 时，OCRRecognizer 不抛异常、不影响其他功能。
"""

from unittest.mock import patch

import numpy as np
import pytest

from src.core.vision.ocr_recognizer import OCRRecognizer
from src.core.vision.ocr_result import OCRMultiResult, OCRResult


@pytest.fixture
def screenshot() -> np.ndarray:
    """128x128 黑色截图"""
    return np.zeros((128, 128, 3), dtype=np.uint8)


@pytest.fixture
def recognizer_no_ocr() -> OCRRecognizer:
    """返回 OCR 不可用状态下的 OCRRecognizer"""
    with patch("src.core.vision.ocr_recognizer.OCR_AVAILABLE", False):
        r = OCRRecognizer()
        r._ensure_initialized()
        return r


# ============================================================
# _ensure_initialized 降级行为
# ============================================================


class TestEnsureInitialized:
    def test_no_retry_after_failure(self, recognizer_no_ocr: OCRRecognizer) -> None:
        """首次初始化失败后不再重试"""
        assert recognizer_no_ocr._initialized is True

    def test_engine_is_none(self, recognizer_no_ocr: OCRRecognizer) -> None:
        """引擎实例为 None"""
        assert recognizer_no_ocr._engine is None


# ============================================================
# recognize() 降级
# ============================================================


class TestRecognizeFallback:
    def test_returns_empty_multi_result(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        result = recognizer_no_ocr.recognize(screenshot)
        assert isinstance(result, OCRMultiResult)
        assert result.results == ()

    def test_with_region_returns_empty(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        result = recognizer_no_ocr.recognize(screenshot, region=(10, 10, 50, 50))
        assert result.results == ()


# ============================================================
# recognize_roi() 降级
# ============================================================


class TestRecognizeRoiFallback:
    def test_unregistered_roi_returns_empty(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        result = recognizer_no_ocr.recognize_roi(screenshot, "hp")
        assert result.results == ()

    def test_registered_roi_returns_empty(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        recognizer_no_ocr.register_roi("hp", (10, 10, 50, 50))
        result = recognizer_no_ocr.recognize_roi(screenshot, "hp")
        assert result.results == ()


# ============================================================
# extract_number() 降级
# ============================================================


class TestExtractNumberFallback:
    def test_returns_none(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        result = recognizer_no_ocr.extract_number(screenshot, (10, 10, 50, 50))
        assert result is None


# ============================================================
# find_text() 降级
# ============================================================


class TestFindTextFallback:
    def test_returns_none(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        result = recognizer_no_ocr.find_text(screenshot, "任意文本")
        assert result is None

    def test_with_region_returns_none(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        result = recognizer_no_ocr.find_text(
            screenshot, "文本", region=(10, 10, 50, 50)
        )
        assert result is None


# ============================================================
# find_text_position() 降级
# ============================================================


class TestFindTextPositionFallback:
    def test_returns_none(
        self, recognizer_no_ocr: OCRRecognizer, screenshot: np.ndarray
    ) -> None:
        result = recognizer_no_ocr.find_text_position(screenshot, "任意文本")
        assert result is None


# ============================================================
# ROI 管理不受 OCR 可用性影响
# ============================================================


class TestRoiManagementStillWorks:
    def test_register_and_get_roi(self, recognizer_no_ocr: OCRRecognizer) -> None:
        region = (10, 20, 100, 30)
        recognizer_no_ocr.register_roi("gold", region)
        assert recognizer_no_ocr.get_roi("gold") == region

    def test_get_unregistered_roi_returns_none(
        self, recognizer_no_ocr: OCRRecognizer
    ) -> None:
        assert recognizer_no_ocr.get_roi("nonexistent") is None


# ============================================================
# VisionPipeline 中 OCRStep 降级
# ============================================================


class TestOCRStepInPipeline:
    def test_ocr_step_returns_empty_when_no_engine(
        self, screenshot: np.ndarray
    ) -> None:
        from src.core.vision.vision_pipeline import OCRStep, VisionPipeline

        with patch("src.core.vision.ocr_recognizer.OCR_AVAILABLE", False):
            pipeline = VisionPipeline()
            pipeline.add_step(OCRStep())
            output = pipeline.execute(screenshot)

        assert output.ocr_result is not None
        assert output.ocr_result.results == ()
        assert output.success is False

    def test_ocr_step_with_target_text_returns_empty(
        self, screenshot: np.ndarray
    ) -> None:
        from src.core.vision.vision_pipeline import OCRStep, VisionPipeline

        with patch("src.core.vision.ocr_recognizer.OCR_AVAILABLE", False):
            pipeline = VisionPipeline()
            pipeline.add_step(OCRStep(target_text="开始游戏"))
            output = pipeline.execute(screenshot)

        assert output.ocr_result is not None
        assert output.ocr_result.results == ()


# ============================================================
# 其他视觉功能不受 OCR 不可用影响
# ============================================================


class TestOtherVisionUnaffected:
    def test_pixel_searcher_works_without_ocr(self, screenshot: np.ndarray) -> None:
        pytest.importorskip("cv2")
        from src.core.vision.pixel_searcher import PixelSearcher

        searcher = PixelSearcher()
        # 使用绿色在全黑截图中搜索 — 保证 found=False
        result = searcher.search(
            screenshot, target_color=(0, 255, 0), tolerance=5
        )
        assert isinstance(result.found, bool)  # 不抛异常即通过

    def test_ocr_result_module_independent(self) -> None:
        """OCRResult 数据结构不依赖 rapidocr"""
        empty = OCRResult.empty()
        assert empty.text == ""

        multi = OCRMultiResult.from_list([
            OCRResult(text="测试", confidence=0.9, bounding_box=(0, 0, 10, 10)),
        ])
        assert multi.best is not None
        assert multi.best.text == "测试"
