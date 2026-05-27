"""OCRDescriptor — OCR 文字检测描述符。

截图 → OCR 识别 → 文本匹配/数值提取 → 输出结果到变量池。
支持模糊匹配、数值提取、可用性检查（rapidocr 未安装时优雅降级）。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["OCRDescriptor"]


@auto_register
class OCRDescriptor(NodeDescriptor):
    """OCR 文字检测描述符 — 在截图中识别文字并匹配目标文本。

    流程：截图 → OCR 识别 → 文本匹配 → 输出结果。
    通过 ExecutionContext.extra["ocr_recognizer"] 注入 OCRRecognizer。
    rapidocr 未安装时返回 success=True, found=False（优雅降级）。
    """

    @classmethod
    def action_type(cls) -> str:
        return "OCR_CHECK"

    @classmethod
    def display_name(cls) -> str:
        return "OCR文字检测"

    @classmethod
    def category(cls) -> str:
        return "视觉检测"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "target_text": PortDef(
                "string", "目标文本（空=识别全部）",
                required=False, default="",
            ),
            "ocr_region": PortDef(
                "string", "识别区域 (x,y,w,h) 或空=全图",
                required=False, default=None,
            ),
            "ocr_fuzzy": PortDef(
                "bool", "模糊匹配", required=False, default=True,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "found": PortDef("bool", "是否找到目标文本", required=False),
            "text": PortDef("string", "识别到的文本", required=False),
            "position": PortDef("string", "文本位置 (x,y)", required=False),
            "all_texts": PortDef("string", "所有识别文本 (JSON数组)", required=False),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        if action is None:
            return NodeResult.fail("OCR_CHECK 节点缺少步骤配置")

        ocr_recognizer = ctx.extra.get("ocr_recognizer")
        if ocr_recognizer is None:
            return NodeResult.ok(found=False, text="", all_texts="[]")

        screenshot = ctx.capture.grab()
        region = action.ocr_region
        target = action.target_text

        if target:
            return self._search_text(ocr_recognizer, screenshot, target, region, action.ocr_fuzzy)
        return self._recognize_all(ocr_recognizer, screenshot, region)

    def _search_text(
        self,
        ocr_recognizer: object,
        screenshot: object,
        target: str,
        region: tuple[int, int, int, int] | None,
        fuzzy: bool,
    ) -> NodeResult:
        result = ocr_recognizer.find_text(screenshot, target, region, fuzzy=fuzzy)

        if result is not None:
            try:
                box = result.bounding_box
                x, y, w, h = box
            except (TypeError, ValueError):
                logger.warning("OCR bounding_box 格式异常: %r", result.bounding_box)
                return NodeResult.ok(found=True, text=result.text)
            logger.info("OCR 找到文本 '%s' (置信度: %.2f)", result.text, result.confidence)
            return NodeResult.ok(
                found=True,
                text=result.text,
                position=(x + w // 2, y + h // 2),
            )

        logger.info("OCR 未找到目标文本: '%s'", target)
        return NodeResult.ok(found=False, text="")

    def _recognize_all(
        self,
        ocr_recognizer: object,
        screenshot: object,
        region: tuple[int, int, int, int] | None,
    ) -> NodeResult:
        multi = ocr_recognizer.recognize(screenshot, region)
        texts = multi.texts

        logger.info("OCR 识别到 %d 行文本", len(texts))
        return NodeResult.ok(
            found=len(texts) > 0,
            all_texts=texts,
            text=" ".join(texts),
        )
