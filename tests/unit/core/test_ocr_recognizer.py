"""OCRRecognizer 单元测试 — OCR 引擎可用路径。

验证 recognize、extract_number、find_text、find_text_position、ROI 管理。
RapidOCR 引擎通过 mock 隔离。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.core.vision.ocr_recognizer import OCRRecognizer
from src.core.vision.ocr_result import OCRMultiResult, OCRResult


def _screenshot(width: int = 128, height: int = 128) -> np.ndarray:
    return np.zeros((height, width, 3), dtype=np.uint8)


def _mock_ocr_result(text: str, confidence: float = 0.9, box: tuple | None = None) -> list:
    """构建 RapidOCR 格式结果 [box_points, text, confidence]。"""
    if box is None:
        box = [[10, 10], [100, 10], [100, 40], [10, 40]]
    return [box, text, confidence]


@pytest.fixture
def recognizer() -> OCRRecognizer:
    """返回 mock 了 OCR 引擎的 OCRRecognizer。"""
    with patch("src.core.vision.ocr_recognizer.OCR_AVAILABLE", True):
        r = OCRRecognizer()
        mock_engine = MagicMock()
        r._engine = mock_engine
        r._initialized = True
        return r


# ---- ROI 管理 ----


class TestROIManagement:
    def test_register_and_get(self, recognizer: OCRRecognizer) -> None:
        recognizer.register_roi("hp", (10, 20, 100, 30))
        assert recognizer.get_roi("hp") == (10, 20, 100, 30)

    def test_get_unregistered_returns_none(self, recognizer: OCRRecognizer) -> None:
        assert recognizer.get_roi("missing") is None


# ---- recognize() ----


class TestRecognize:
    def test_with_results(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("Hello", 0.95)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.recognize(_screenshot())

        assert len(result.results) == 1
        assert result.results[0].text == "Hello"
        assert result.results[0].confidence == 0.95

    def test_with_region_offset(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("World", 0.8)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.recognize(_screenshot(), region=(50, 30, 60, 40))

        assert len(result.results) == 1
        bx, by, bw, bh = result.results[0].bounding_box
        assert bx >= 50
        assert by >= 30

    def test_none_results(self, recognizer: OCRRecognizer) -> None:
        recognizer._engine.return_value = (None, None)

        result = recognizer.recognize(_screenshot())

        assert result.results == ()

    def test_engine_exception(self, recognizer: OCRRecognizer) -> None:
        recognizer._engine.side_effect = RuntimeError("OCR fail")

        result = recognizer.recognize(_screenshot())

        assert result.results == ()

    def test_multiple_results(self, recognizer: OCRRecognizer) -> None:
        raw1 = _mock_ocr_result("Line1", 0.9)
        raw2 = _mock_ocr_result("Line2", 0.8)
        recognizer._engine.return_value = ([raw1, raw2], None)

        result = recognizer.recognize(_screenshot())

        assert len(result.results) == 2
        assert result.results[0].text == "Line1"
        assert result.results[1].text == "Line2"


# ---- recognize_roi() ----


class TestRecognizeROI:
    def test_registered_roi(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("HP: 100", 0.9)
        recognizer._engine.return_value = ([raw], None)
        recognizer.register_roi("hp", (10, 10, 80, 30))

        result = recognizer.recognize_roi(_screenshot(), "hp")

        assert len(result.results) == 1
        assert "HP" in result.results[0].text

    def test_unregistered_roi(self, recognizer: OCRRecognizer) -> None:
        result = recognizer.recognize_roi(_screenshot(), "missing_roi")

        assert result.results == ()


# ---- extract_number() ----


class TestExtractNumber:
    def test_extracts_digits(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("HP: 1,234", 0.9)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.extract_number(_screenshot(), (0, 0, 100, 30))

        assert result == 1234

    def test_no_digits_returns_none(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("no numbers", 0.9)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.extract_number(_screenshot(), (0, 0, 100, 30))

        assert result is None

    def test_empty_results_returns_none(self, recognizer: OCRRecognizer) -> None:
        recognizer._engine.return_value = (None, None)

        result = recognizer.extract_number(_screenshot(), (0, 0, 100, 30))

        assert result is None


# ---- find_text() ----


class TestFindText:
    def test_exact_match(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("开始游戏", 0.95)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.find_text(_screenshot(), "开始")

        assert result is not None
        assert "开始" in result.text

    def test_fuzzy_match(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("开始游戍", 0.8)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.find_text(_screenshot(), "开始游戏", fuzzy_threshold=0.5)

        assert result is not None

    def test_no_match(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("ABC", 0.9)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.find_text(_screenshot(), "XYZ")

        assert result is None

    def test_with_region(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("target", 0.9)
        recognizer._engine.return_value = ([raw], None)

        result = recognizer.find_text(_screenshot(), "target", region=(0, 0, 50, 50))

        assert result is not None


# ---- find_text_position() ----


class TestFindTextPosition:
    def test_found(self, recognizer: OCRRecognizer) -> None:
        raw = _mock_ocr_result("Button", 0.9, box=[[20, 30], [80, 30], [80, 60], [20, 60]])
        recognizer._engine.return_value = ([raw], None)

        pos = recognizer.find_text_position(_screenshot(), "Button")

        assert pos is not None
        cx, cy = pos
        assert cx > 0
        assert cy > 0

    def test_not_found(self, recognizer: OCRRecognizer) -> None:
        recognizer._engine.return_value = (None, None)

        pos = recognizer.find_text_position(_screenshot(), "missing")

        assert pos is None


# ---- 初始化路径 ----


class TestInitialization:
    def test_init_success(self) -> None:
        mock_engine = MagicMock()
        with patch("src.core.vision.ocr_recognizer.OCR_AVAILABLE", True):
            import src.core.vision.ocr_recognizer as mod
            mod.RapidOCR = lambda: mock_engine  # type: ignore[attr-defined]
            try:
                r = OCRRecognizer()
                r._ensure_initialized()
                assert r._engine is not None
                assert r._initialized is True
            finally:
                if hasattr(mod, "RapidOCR"):
                    delattr(mod, "RapidOCR")

    def test_init_failure(self) -> None:
        with patch("src.core.vision.ocr_recognizer.OCR_AVAILABLE", True):
            import src.core.vision.ocr_recognizer as mod
            mod.RapidOCR = MagicMock(side_effect=RuntimeError("load failed"))  # type: ignore[attr-defined]
            try:
                r = OCRRecognizer()
                r._ensure_initialized()
                assert r._engine is None
                assert r._initialized is True
            finally:
                if hasattr(mod, "RapidOCR"):
                    delattr(mod, "RapidOCR")

    @patch("src.core.vision.ocr_recognizer.OCR_AVAILABLE", False)
    def test_no_ocr_available(self) -> None:
        r = OCRRecognizer()
        r._ensure_initialized()

        assert r._engine is None
        assert r._initialized is True
