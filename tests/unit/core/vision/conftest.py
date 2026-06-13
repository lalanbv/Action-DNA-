"""vision 测试专用 conftest。

环境兼容:Python 3.14 等部分构建不含 hashlib.xxh3_64(计算截图哈希用)。
当 xxh3_64 不可用时,把 compute_image_hash 替换为 sha256 回退(逻辑与原函数一致,
仅哈希算法不同)。生产/CI 若有 xxh3_64 则自动 no-op,不影响真实行为。

仅作用于本目录(及子目录)的测试,且条件触发;mock 匹配器的既有测试不受影响
(它们不调用真实 compute_image_hash)。
"""

from __future__ import annotations

import hashlib

import numpy as np
import pytest

_HAS_XXH3 = hasattr(hashlib, "xxh3_64")


def _sha256_image_hash(image: np.ndarray) -> int:
    """compute_image_hash 的 sha256 回退:降采样 + 均值量化 + sha256 取前 8 字节。"""
    h, w = image.shape[:2]
    step_h = max(1, h // 32)
    step_w = max(1, w // 32)
    small = image[::step_h, ::step_w]
    vals = (
        (small.mean(axis=-1) * 0.03125).astype(np.int32)
        if small.ndim == 3
        else (small * 0.03125).astype(np.int32)
    )
    return int.from_bytes(hashlib.sha256(vals.tobytes()).digest()[:8], "little")


@pytest.fixture(autouse=True)
def _patch_image_hash_when_xxh3_missing(monkeypatch):
    """xxh3_64 缺失时,在 capture 与 vision_pipeline 命名空间替换 compute_image_hash。"""
    if _HAS_XXH3:
        return
    import src.core.vision.capture as capture_mod
    import src.core.vision.vision_pipeline as vp_mod
    monkeypatch.setattr(capture_mod, "compute_image_hash", _sha256_image_hash, raising=False)
    monkeypatch.setattr(vp_mod, "compute_image_hash", _sha256_image_hash, raising=False)
