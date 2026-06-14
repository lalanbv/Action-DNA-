"""Condition 多模板条件判定测试(mock matcher.find_any,不触达 cv2/xxh3_64)。"""

import threading
from unittest.mock import MagicMock

import pytest

from src.core.action import MatchStrategy, ThresholdMode
from src.core.condition import Condition, ConditionEvaluator, ConditionType
from src.core.vision.capture import MultiMatchResult


def _evaluator(find_any_results):
    """构造假 ConditionEvaluator:capture.grab_reuse() 返回 mock 屏幕帧;
    matcher.find_any 按 find_any_results 顺序返回(每次调用一个)。
    """
    ev = ConditionEvaluator.__new__(ConditionEvaluator)
    ev._capture = MagicMock()
    ev._capture.grab_reuse.return_value = MagicMock(name="screen")
    ev._matcher = MagicMock()
    ev._matcher.find_any.side_effect = find_any_results
    ev._variables = {}
    ev._timers = {}
    ev._lock = threading.Lock()
    return ev


def _image_cond(alt_paths=None, alt_thresholds=None, mode=ThresholdMode.GLOBAL,
                strategy=MatchStrategy.ADAPTIVE, threshold=0.8):
    """构造 IMAGE_FOUND 条件(主图 primary.png + 可选备用图)。"""
    return Condition(
        condition_type=ConditionType.IMAGE_FOUND,
        image_path="primary.png",
        threshold=threshold,
        alt_image_paths=alt_paths or [],
        alt_thresholds=alt_thresholds or [],
        match_strategy=strategy,
        threshold_mode=mode,
    )


def test_condition_has_multi_template_fields():
    """Condition dataclass 默认携带多模板字段(向后兼容)。"""
    cond = Condition(condition_type=ConditionType.IMAGE_FOUND)
    assert cond.alt_image_paths == []
    assert cond.alt_thresholds == []
    assert cond.match_strategy == MatchStrategy.ADAPTIVE
    assert cond.threshold_mode == ThresholdMode.GLOBAL


def test_image_found_primary_miss_alt_hit_is_true():
    """主图 miss + 备用图 hit → find_any 返回命中 → IMAGE_FOUND True。"""
    hit = MultiMatchResult(path="alt.png", rect=(10, 20, 30, 30), confidence=0.9, strategy_used="early_exit")
    ev = _evaluator([hit])
    cond = _image_cond(alt_paths=["alt.png"])
    assert ev.evaluate(cond) is True
    # 应改用 find_any(而非 find)
    assert ev._matcher.find_any.called


def test_image_found_all_miss_is_false():
    """全部未命中 → IMAGE_FOUND False。"""
    ev = _evaluator([None])
    cond = _image_cond(alt_paths=["alt.png"])
    assert ev.evaluate(cond) is False


def test_image_not_found_all_miss_is_true():
    """IMAGE_NOT_FOUND = 全部未命中 → True。"""
    ev = _evaluator([None])
    cond = Condition(
        condition_type=ConditionType.IMAGE_NOT_FOUND,
        image_path="primary.png", alt_image_paths=["alt.png"],
    )
    assert ev.evaluate(cond) is True


def test_image_not_found_any_hit_is_false():
    """IMAGE_NOT_FOUND 但有命中 → False。"""
    hit = MultiMatchResult(path="primary.png", rect=(1, 2, 3, 3), confidence=0.95, strategy_used="early_exit")
    ev = _evaluator([hit])
    cond = Condition(
        condition_type=ConditionType.IMAGE_NOT_FOUND,
        image_path="primary.png", alt_image_paths=["alt.png"],
    )
    assert ev.evaluate(cond) is False


def test_image_found_no_image_path_is_false():
    """无主图路径 → 直接 False(不调用匹配器)。"""
    ev = _evaluator([])
    cond = Condition(condition_type=ConditionType.IMAGE_FOUND, image_path="")
    assert ev.evaluate(cond) is False


def test_image_found_passes_resolved_params():
    """find_any 收到的 template_paths 含 primary + alt,strategy 来自 cond。"""
    hit = MultiMatchResult(path="alt.png", rect=(1, 2, 3, 3), confidence=0.9, strategy_used="early_exit")
    ev = _evaluator([hit])
    cond = _image_cond(alt_paths=["alt.png"], strategy=MatchStrategy.BEST_CONFIDENCE)
    ev.evaluate(cond)
    call = ev._matcher.find_any.call_args
    paths = call.kwargs.get("template_paths") or call.args[1]
    assert "primary.png" in paths and "alt.png" in paths
    assert call.kwargs.get("strategy") == MatchStrategy.BEST_CONFIDENCE
