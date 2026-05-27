"""OCRDescriptor 单元测试。

覆盖: action_type、display_name、execute (mock ocr_recognizer / 降级)。
"""

from unittest.mock import MagicMock

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.descriptors.ocr_descriptor import OCRDescriptor
from src.core.vision.ocr_result import OCRMultiResult, OCRResult


def _make_ctx(
    action: BaseStep | None = None,
    ocr_recognizer: object | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.current_node.action = action
    ctx.capture = MagicMock()
    ctx.capture.grab.return_value = MagicMock()
    ctx.extra = {}
    if ocr_recognizer is not None:
        ctx.extra["ocr_recognizer"] = ocr_recognizer
    return ctx


# ============================================================
# 元数据
# ============================================================


class TestOCRDescriptorMeta:
    def test_action_type(self):
        assert OCRDescriptor.action_type() == "OCR_CHECK"

    def test_display_name(self):
        assert OCRDescriptor.display_name() == "OCR文字检测"

    def test_category(self):
        assert OCRDescriptor.category() == "视觉检测"

    def test_input_types(self):
        inputs = OCRDescriptor.input_types()
        assert "target_text" in inputs
        assert "ocr_region" in inputs
        assert "ocr_fuzzy" in inputs

    def test_output_types(self):
        outputs = OCRDescriptor.output_types()
        assert "found" in outputs
        assert "text" in outputs
        assert "position" in outputs
        assert "all_texts" in outputs


# ============================================================
# execute
# ============================================================


class TestOCRDescriptorExecute:
    def test_execute_no_action_returns_fail(self):
        ctx = _make_ctx(action=None)
        result = OCRDescriptor().execute(ctx)
        assert result.success is False

    def test_execute_no_recognizer_graceful_degradation(self):
        action = STEP_CLASSES[ActionType.OCR_CHECK](target_text="hello")
        ctx = _make_ctx(action=action, ocr_recognizer=None)
        result = OCRDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is False
        assert result.output_vars["text"] == ""

    def test_execute_search_text_found(self):
        action = STEP_CLASSES[ActionType.OCR_CHECK](target_text="开始")
        recognizer = MagicMock()
        ocr_result = OCRResult(
            text="开始游戏",
            confidence=0.95,
            bounding_box=(100, 200, 80, 30),
        )
        recognizer.find_text.return_value = ocr_result

        ctx = _make_ctx(action=action, ocr_recognizer=recognizer)
        result = OCRDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is True
        assert result.output_vars["text"] == "开始游戏"
        assert result.output_vars["position"] == (140, 215)
        recognizer.find_text.assert_called_once()

    def test_execute_search_text_not_found(self):
        action = STEP_CLASSES[ActionType.OCR_CHECK](target_text="不存在")
        recognizer = MagicMock()
        recognizer.find_text.return_value = None

        ctx = _make_ctx(action=action, ocr_recognizer=recognizer)
        result = OCRDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is False

    def test_execute_recognize_all(self):
        action = STEP_CLASSES[ActionType.OCR_CHECK](target_text="")
        recognizer = MagicMock()
        multi = OCRMultiResult.from_list([
            OCRResult(text="第一行", confidence=0.9, bounding_box=(10, 10, 80, 20)),
            OCRResult(text="第二行", confidence=0.85, bounding_box=(10, 40, 80, 20)),
        ])
        recognizer.recognize.return_value = multi

        ctx = _make_ctx(action=action, ocr_recognizer=recognizer)
        result = OCRDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is True
        assert result.output_vars["all_texts"] == ["第一行", "第二行"]
        assert result.output_vars["text"] == "第一行 第二行"
        recognizer.recognize.assert_called_once()

    def test_execute_recognize_all_empty(self):
        action = STEP_CLASSES[ActionType.OCR_CHECK](target_text="")
        recognizer = MagicMock()
        multi = OCRMultiResult.empty()
        recognizer.recognize.return_value = multi

        ctx = _make_ctx(action=action, ocr_recognizer=recognizer)
        result = OCRDescriptor().execute(ctx)

        assert result.success is True
        assert result.output_vars["found"] is False
