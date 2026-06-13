"""find_with_score 测试:返回 (rect, score),rect 为 None 时仍返回最高分。

用带纹理的噪声图(而非纯色)——TM_CCOEFF_NORMED 对零方差区域归一化除零,
纯色模板匹配得 0 而非高置信度,无法验证命中路径。
"""

import cv2
import numpy as np

from src.core.vision.capture import TemplateMatcher


def _noise_screen(seed: int = 42, size=(200, 200)) -> np.ndarray:
    """确定性噪声图(带纹理,NCC 有定义)。"""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 256, size=(size[1], size[0], 3), dtype=np.uint8)


def _save_crop(screen: np.ndarray, x: int, y: int, tmp_path, w: int = 40, h: int = 40,
               name: str = "tpl.png") -> str:
    """从 screen 裁剪一块写为模板文件(与 screen 完全一致 → 高置信度命中)。"""
    crop = screen[y:y + h, x:x + w].copy()
    path = str(tmp_path / name)
    cv2.imwrite(path, crop)
    return path


def test_find_with_score_returns_rect_and_score(tmp_path):
    """命中时返回 (rect, score),score >= threshold。"""
    matcher = TemplateMatcher()
    screen = _noise_screen(seed=1)
    tpl = _save_crop(screen, 60, 70, tmp_path)
    rect, score = matcher.find_with_score(screen, tpl, threshold=0.8)
    assert rect is not None
    assert isinstance(rect, tuple) and len(rect) == 4
    assert 0.0 <= score <= 1.0
    assert score >= 0.8


def test_find_with_score_low_score_when_unrelated(tmp_path):
    """不相关噪声:rect 为 None,score 仍为 float。"""
    matcher = TemplateMatcher()
    screen = _noise_screen(seed=1)
    other = _noise_screen(seed=99)
    tpl = _save_crop(other, 50, 50, tmp_path)  # 来自不同噪声图
    rect, score = matcher.find_with_score(screen, tpl, threshold=0.95)
    assert rect is None
    assert isinstance(score, float)


def test_find_unchanged_returns_rect_only(tmp_path):
    """向后兼容:find() 签名与返回值不变(仅 rect)。"""
    matcher = TemplateMatcher()
    screen = _noise_screen(seed=3)
    tpl = _save_crop(screen, 80, 20, tmp_path)
    result = matcher.find(screen, tpl, threshold=0.8)
    assert result is None or (isinstance(result, tuple) and len(result) == 4)


def test_find_with_score_caches(tmp_path):
    """二次调用命中缓存,返回值一致。"""
    matcher = TemplateMatcher()
    screen = _noise_screen(seed=5)
    tpl = _save_crop(screen, 30, 90, tmp_path)
    r1 = matcher.find_with_score(screen, tpl, threshold=0.8)
    r2 = matcher.find_with_score(screen, tpl, threshold=0.8)
    assert r1 == r2
