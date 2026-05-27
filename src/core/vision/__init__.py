"""视觉检测模块 — 截图、模板匹配、像素搜索、OCR、可组合管线"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.vision.capture import ScreenCapture, TemplateMatcher
    from src.core.vision.ocr_recognizer import OCRRecognizer
    from src.core.vision.ocr_result import OCRMultiResult, OCRResult
    from src.core.vision.pixel_result import PixelSearchResult
    from src.core.vision.pixel_searcher import PixelSearcher
    from src.core.vision.vision_pipeline import (
        OCRStep,
        PixelSearchStep,
        TemplateMatchStep,
        VisionOutput,
        VisionPipeline,
        VisionStep,
    )

__all__ = [
    "ScreenCapture",
    "TemplateMatcher",
    "PixelSearchResult",
    "PixelSearcher",
    "OCRResult",
    "OCRMultiResult",
    "OCRRecognizer",
    "VisionPipeline",
    "VisionStep",
    "VisionOutput",
    "TemplateMatchStep",
    "PixelSearchStep",
    "OCRStep",
]

_lazy_imports: dict[str, str] = {
    "ScreenCapture": "src.core.vision.capture",
    "TemplateMatcher": "src.core.vision.capture",
    "PixelSearcher": "src.core.vision.pixel_searcher",
    "PixelSearchResult": "src.core.vision.pixel_result",
    "OCRResult": "src.core.vision.ocr_result",
    "OCRMultiResult": "src.core.vision.ocr_result",
    "OCRRecognizer": "src.core.vision.ocr_recognizer",
    "VisionPipeline": "src.core.vision.vision_pipeline",
    "VisionStep": "src.core.vision.vision_pipeline",
    "VisionOutput": "src.core.vision.vision_pipeline",
    "TemplateMatchStep": "src.core.vision.vision_pipeline",
    "PixelSearchStep": "src.core.vision.vision_pipeline",
    "OCRStep": "src.core.vision.vision_pipeline",
}


def __getattr__(name: str):
    """PEP 562 lazy imports — defer cv2 dependency until first actual use."""
    if name in _lazy_imports:
        import importlib

        mod = importlib.import_module(_lazy_imports[name])
        value = getattr(mod, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return list(set(__all__) | set(globals().keys()))
