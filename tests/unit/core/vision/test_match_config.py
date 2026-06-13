"""match_config 纯逻辑测试。"""

from src.core.action import MatchStrategy, ThresholdMode
from src.core.vision.match_config import (
    AUTO_THRESHOLD,
    effective_thresholds,
    normalize_templates,
    resolve_find_any_params,
)


# ── normalize_templates ───────────────────────────────

def test_normalize_drops_empty_paths():
    """空路径被过滤,对应阈值一起移除。"""
    primary, alts, thr = normalize_templates("a.png", ["", "b.png", ""], [None, 0.7, None])
    assert primary == "a.png"
    assert alts == ["b.png"]
    assert thr == [0.7]


def test_normalize_dedupes_paths():
    """重复路径去重,保留第一次出现的阈值。"""
    primary, alts, thr = normalize_templates("a.png", ["b.png", "b.png", "c.png"], [0.7, 0.8, None])
    assert alts == ["b.png", "c.png"]
    assert thr == [0.7, None]


def test_normalize_aligns_threshold_length_padding():
    """alt_thresholds 比 alt_image_paths 短 → 补 None。"""
    primary, alts, thr = normalize_templates("a.png", ["b.png", "c.png", "d.png"], [0.7])
    assert thr == [0.7, None, None]


def test_normalize_aligns_threshold_length_truncates():
    """alt_thresholds 比 alt_image_paths 长 → 截断。"""
    primary, alts, thr = normalize_templates("a.png", ["b.png"], [0.7, 0.8, 0.9])
    assert thr == [0.7]


def test_normalize_empty_alts():
    """空备用图保持原样。"""
    primary, alts, thr = normalize_templates("a.png", [], [])
    assert primary == "a.png"
    assert alts == []
    assert thr == []


# ── effective_thresholds ──────────────────────────────

def test_effective_thresholds_auto():
    """AUTO 模式:所有模板统一用 AUTO_THRESHOLD。"""
    eff = effective_thresholds(ThresholdMode.AUTO, 0.8, [None, 0.7], 3)
    assert eff == [AUTO_THRESHOLD, AUTO_THRESHOLD, AUTO_THRESHOLD]


def test_effective_thresholds_global():
    """GLOBAL 模式:全部用基础阈值。"""
    eff = effective_thresholds(ThresholdMode.GLOBAL, 0.8, [0.7, None], 3)
    assert eff == [0.8, 0.8, 0.8]


def test_effective_thresholds_per_template():
    """PER_TEMPLATE 模式:主图用全局,alt 覆盖值或继承全局。"""
    eff = effective_thresholds(ThresholdMode.PER_TEMPLATE, 0.8, [0.7, None], 3)
    assert eff == [0.8, 0.7, 0.8]


# ── resolve_find_any_params ───────────────────────────

def test_resolve_basic_per_template():
    """解析出 paths / per_thresholds / strategy。"""
    paths, per_thr, strategy = resolve_find_any_params(
        primary_path="a.png",
        alt_paths=["b.png", "c.png"],
        base_threshold=0.8,
        alt_thresholds=[0.7, None],
        threshold_mode=ThresholdMode.PER_TEMPLATE,
        match_strategy=MatchStrategy.ADAPTIVE,
    )
    assert paths == ["a.png", "b.png", "c.png"]
    assert per_thr == [0.8, 0.7, 0.8]
    assert strategy == MatchStrategy.ADAPTIVE


def test_resolve_auto_mode():
    """AUTO 模式下 per_thresholds 全部替换为 AUTO_THRESHOLD。"""
    paths, per_thr, strategy = resolve_find_any_params(
        primary_path="a.png",
        alt_paths=["b.png"],
        base_threshold=0.8,
        alt_thresholds=[None],
        threshold_mode=ThresholdMode.AUTO,
        match_strategy=MatchStrategy.ADAPTIVE,
    )
    assert per_thr == [AUTO_THRESHOLD, AUTO_THRESHOLD]
