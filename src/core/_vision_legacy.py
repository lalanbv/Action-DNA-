"""向后兼容垫片 — ScreenCapture/TemplateMatcher 已迁移到 src.core.vision.capture。"""

from src.core.vision.capture import ScreenCapture, TemplateMatcher

__all__ = ["ScreenCapture", "TemplateMatcher"]
