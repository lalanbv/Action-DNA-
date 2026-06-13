"""find_any 多模板编排测试(ADAPTIVE / FIRST_MATCH / BEST_CONFIDENCE 三策略)。"""

import cv2
import numpy as np

from src.core.action import MatchStrategy
from src.core.vision.capture import MultiMatchResult, TemplateMatcher


def _noise(seed: int, size=(200, 200)) -> np.ndarray:
    """确定性带纹理噪声图(NCC 有定义)。"""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)


def _crop(screen: np.ndarray, x: int, y: int, tmp_path, name: str, w: int = 40, h: int = 40) -> str:
    """裁剪 screen 一块作模板(与 screen 完全一致 → 高置信度命中)。"""
    crop = screen[y:y + h, x:x + w].copy()
    path = str(tmp_path / name)
    cv2.imwrite(path, crop)
    return path


def test_find_any_single_template_equivalent_to_find(tmp_path):
    """单模板时 find_any 退化为单模板,返回 MultiMatchResult。"""
    matcher = TemplateMatcher()
    screen = _noise(seed=1)
    tpl = _crop(screen, 60, 70, tmp_path, "p.png")
    result = matcher.find_any(screen, [tpl], threshold=0.8, strategy=MatchStrategy.ADAPTIVE)
    assert result is not None
    assert isinstance(result, MultiMatchResult)
    assert result.rect is not None
    assert result.path == tpl


def test_find_any_empty_paths_returns_none():
    """空模板列表 → None。"""
    matcher = TemplateMatcher()
    screen = _noise(seed=1)
    assert matcher.find_any(screen, [], threshold=0.8) is None


def test_find_any_first_match_returns_first_hit(tmp_path):
    """FIRST_MATCH:第一个命中即返回(即使后续也可能命中)。"""
    matcher = TemplateMatcher()
    screen = _noise(seed=2)
    p1 = _crop(screen, 30, 30, tmp_path, "a.png")
    p2 = _crop(screen, 120, 120, tmp_path, "b.png")
    result = matcher.find_any(screen, [p1, p2], threshold=0.8, strategy=MatchStrategy.FIRST_MATCH)
    assert result is not None
    assert result.path == p1
    assert result.strategy_used == "first_match"


def test_find_any_best_confidence_strategy_used(tmp_path):
    """BEST_CONFIDENCE:扫完全部,strategy_used == best_of。"""
    matcher = TemplateMatcher()
    screen = _noise(seed=3)
    p1 = _crop(screen, 30, 30, tmp_path, "a.png")
    p2 = _crop(screen, 120, 120, tmp_path, "b.png")
    result = matcher.find_any(screen, [p1, p2], threshold=0.8, strategy=MatchStrategy.BEST_CONFIDENCE)
    assert result is not None
    assert result.strategy_used == "best_of"


def test_find_any_all_miss_returns_none(tmp_path):
    """全部未达阈值 → None。"""
    matcher = TemplateMatcher()
    screen = _noise(seed=5)
    other = _noise(seed=99)
    p1 = _crop(other, 20, 20, tmp_path, "a.png")
    p2 = _crop(other, 100, 100, tmp_path, "b.png")
    result = matcher.find_any(screen, [p1, p2], threshold=0.95, strategy=MatchStrategy.ADAPTIVE)
    assert result is None


def test_find_any_per_template_thresholds(tmp_path):
    """per_template_thresholds:模板用各自有效阈值。"""
    matcher = TemplateMatcher()
    screen = _noise(seed=7)
    p1 = _crop(screen, 40, 40, tmp_path, "a.png")  # 完全匹配
    result = matcher.find_any(
        screen, [p1], threshold=0.9,
        strategy=MatchStrategy.ADAPTIVE, per_template_thresholds=[0.8],
    )
    assert result is not None


def test_find_any_adaptive_early_exit_on_high_confidence(tmp_path):
    """ADAPTIVE:高确信(>= eff + 0.08)提前退出,strategy_used=early_exit。"""
    matcher = TemplateMatcher()
    screen = _noise(seed=9)
    p1 = _crop(screen, 50, 50, tmp_path, "a.png")  # 完全匹配,置信度≈1.0
    result = matcher.find_any(screen, [p1], threshold=0.8, strategy=MatchStrategy.ADAPTIVE)
    assert result is not None
    assert result.strategy_used == "early_exit"
