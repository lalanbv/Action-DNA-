"""线程安全的截图帧缓存 — 为多个 BackgroundMonitor 提供共享帧。

包装 ScreenCapture，提供：
- TTL 缓存：多个 monitor 在同一时间窗口内共享同一帧
- 线程安全：Lock 保护所有读写操作
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from src.core.vision import ScreenCapture


class SharedFrameProvider:
    """线程安全的截图帧缓存提供器。

    多个 BackgroundMonitor 共享此实例，通过 TTL 缓存减少重复截图。
    """

    _DEFAULT_CACHE_TTL = 0.03

    def __init__(
        self,
        capture: ScreenCapture,
        cache_ttl: float | None = None,
    ) -> None:
        if cache_ttl is None:
            try:
                from src.core.config import load_config
                cfg = load_config()
                cache_ttl = cfg.schedule.frame_cache_ttl
            except Exception:
                cache_ttl = self._DEFAULT_CACHE_TTL
        self._capture = capture
        self._cache_ttl = cache_ttl
        self._lock = threading.Lock()

        self._cached_frame: np.ndarray | None = None
        self._frame_time: float = 0.0

    def _acquire_frame(self) -> np.ndarray:
        """获取或刷新缓存帧（线程安全，需在锁内调用）。"""
        now = time.monotonic()
        if (
            self._cached_frame is not None
            and now - self._frame_time < self._cache_ttl
        ):
            return self._cached_frame

        frame = self._capture.grab_reuse()
        self._cached_frame = frame
        self._frame_time = now
        return self._cached_frame

    def get_frame(self) -> np.ndarray:
        """获取最新帧的副本（线程安全）。

        TTL 内多个调用者共享同一帧，避免重复截图。
        返回缓存帧的副本，确保调用者不会因后续 grab() 覆写内部 buffer。
        """
        with self._lock:
            return self._acquire_frame().copy()

    def get_frame_reuse(self) -> np.ndarray:
        """获取最新帧（高性能路径，缓存命中时零分配）。

        调用者不得持有返回值跨下一次 grab() 调用。
        """
        with self._lock:
            return self._acquire_frame()

    def invalidate(self) -> None:
        """手动使缓存失效（如区域变更后调用）。"""
        with self._lock:
            self._cached_frame = None
            self._frame_time = 0.0

    @property
    def cache_age(self) -> float:
        """当前缓存的年龄（秒）。"""
        with self._lock:
            if self._cached_frame is None:
                return float("inf")
            return time.monotonic() - self._frame_time
