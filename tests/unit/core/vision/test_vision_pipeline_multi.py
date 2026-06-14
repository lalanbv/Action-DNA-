"""VisionPipeline.TemplateMatchStep 多模板测试(mock matcher.find_any)。"""

from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.action import MatchStrategy
from src.core.vision.capture import MultiMatchResult
from src.core.vision.vision_pipeline import TemplateMatchStep


def _screen():
    """100×100 纯色屏幕帧(mock 匹配不实际使用像素)。"""
    return np.zeros((100, 100, 3), dtype=np.uint8)


def test_multitemplate_step_uses_find_any():
    """有 alt_template_paths → 走 find_any。"""
    hit = MultiMatchResult(path="alt.png", rect=(5, 6, 10, 10), confidence=0.95, strategy_used="early_exit")
    matcher = MagicMock()
    matcher.find_any.return_value = hit
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("primary.png", threshold=0.8, alt_template_paths=["alt.png"])
    out = step.execute(_screen(), ctx)
    assert matcher.find_any.called
    assert out["template_result"]["found"] is True
    assert out["template_result"]["x"] == 5
    assert out["template_result"]["y"] == 6


def test_multitemplate_step_all_miss_returns_not_found():
    matcher = MagicMock()
    matcher.find_any.return_value = None
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("primary.png", threshold=0.8, alt_template_paths=["alt.png"])
    out = step.execute(_screen(), ctx)
    assert out["template_result"]["found"] is False


def test_single_template_unchanged_uses_find():
    """无 alt_template_paths → 走原 find() 路径(向后兼容)。"""
    matcher = MagicMock()
    matcher.find.return_value = (1, 2, 3, 3)
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("primary.png", threshold=0.8)
    step.execute(_screen(), ctx)
    assert matcher.find.called
    assert not matcher.find_any.called


def test_multitemplate_passes_strategy():
    """find_any 收到指定的 match_strategy。"""
    hit = MultiMatchResult(path="primary.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    matcher = MagicMock()
    matcher.find_any.return_value = hit
    ctx = {"_matcher": matcher}
    step = TemplateMatchStep("p.png", threshold=0.8, alt_template_paths=["a.png"],
                             match_strategy=MatchStrategy.BEST_CONFIDENCE)
    step.execute(_screen(), ctx)
    assert matcher.find_any.call_args.kwargs.get("strategy") == MatchStrategy.BEST_CONFIDENCE
