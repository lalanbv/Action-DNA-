"""ClickImageStep 多模板字段测试。"""

from dataclasses import asdict

from src.core.action import MatchStrategy, ThresholdMode
from src.core.step_types import ClickImageStep


def test_default_fields_backward_compatible():
    """既有字段默认值不变 + 新字段默认值。"""
    step = ClickImageStep()
    assert step.image_path == ""
    assert step.threshold == 0.8
    assert step.alt_image_paths == []
    assert step.alt_thresholds == []
    assert step.match_strategy == MatchStrategy.ADAPTIVE
    assert step.threshold_mode == ThresholdMode.GLOBAL


def test_accepts_multi_template_fields():
    """可传入多模板字段。"""
    step = ClickImageStep(
        image_path="a.png",
        alt_image_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE,
        threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    assert step.alt_image_paths == ["b.png", "c.png"]
    assert step.alt_thresholds == [0.7, None]
    assert step.match_strategy == MatchStrategy.BEST_CONFIDENCE
    assert step.threshold_mode == ThresholdMode.PER_TEMPLATE


def test_step_serializes_via_asdict():
    """asdict 能往返新字段(序列化机制依赖)。"""
    step = ClickImageStep(image_path="a.png", alt_image_paths=["b.png"], alt_thresholds=[None])
    d = asdict(step)
    assert d["alt_image_paths"] == ["b.png"]
    assert d["alt_thresholds"] == [None]
    assert d["match_strategy"] == MatchStrategy.ADAPTIVE
    assert d["threshold_mode"] == ThresholdMode.GLOBAL
