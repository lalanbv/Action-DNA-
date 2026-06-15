"""预分配缓冲池 — 双缓冲架构消除截图撕裂。

DoubleBufferPool: 写入缓冲与读取缓冲分离，grab_into() 写入 write buffer 后
原子交换到 read buffer，get_latest_frame() 始终返回完整帧。

BufferPool: 向后兼容别名，功能不变（单缓冲）。
"""

import threading

import numpy as np
from mss.base import MSSBase

from src.core.vision._cv2_guard import cv2, require_cv2
from src.utils.i18n import t

__all__ = ["BufferPool", "DoubleBufferPool"]


class DoubleBufferPool:
    """双缓冲截图池 — 写入缓冲与读取缓冲分离。

    grab_into(): 写入 write buffer，完成后原子交换到 read buffer。
    get_latest_frame(): 非阻塞读取，始终返回完整帧。
    """

    def __init__(self) -> None:
        self._write_bgra: np.ndarray | None = None
        self._write_bgr: np.ndarray | None = None
        self._read_bgr: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None
        self._lock = threading.Lock()
        self._swap_lock = threading.Lock()

    def _ensure(self, h: int, w: int) -> None:
        if self._shape == (h, w):
            return
        self._write_bgra = np.empty((h, w, 4), dtype=np.uint8)
        self._write_bgr = np.empty((h, w, 3), dtype=np.uint8)
        self._read_bgr = np.empty((h, w, 3), dtype=np.uint8)
        self._shape = (h, w)

    def grab_into(self, sct: MSSBase, monitor: dict) -> np.ndarray:
        """截屏到写入缓冲区，原子交换后返回读取缓冲区视图。

        线程安全：写入和交换通过 Lock 保护。
        """
        require_cv2("screen capture")
        with self._lock:
            shot = sct.grab(monitor)
            h, w = shot.size[1], shot.size[0]
            self._ensure(h, w)
            if self._write_bgra is None or self._write_bgr is None:
                raise RuntimeError(t("vision.exc.double_buffer_uninitialized"))
            raw = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(h, w, 4)
            np.copyto(self._write_bgra[:h, :w], raw)
            cv2.cvtColor(
                self._write_bgra[:h, :w], cv2.COLOR_BGRA2BGR,
                dst=self._write_bgr[:h, :w],
            )
            # 原子交换 write → read
            with self._swap_lock:
                self._read_bgr, self._write_bgr = self._write_bgr, self._read_bgr
            return self._read_bgr[:h, :w]

    def get_latest_frame(self) -> np.ndarray | None:
        """非阻塞读取最新完整帧（副本）。"""
        with self._swap_lock:
            if self._read_bgr is not None and self._shape is not None:
                h, w = self._shape
                return self._read_bgr[:h, :w].copy()
            return None


class BufferPool:
    """单缓冲截图池（向后兼容）。

    为屏幕截图预分配 BGRA + BGR 两个 numpy 缓冲区。
    grab_into() 复用已有缓冲区，避免每次截图分配新数组。
    当截图尺寸变化时自动重新分配。
    线程安全：通过 Lock 保护 grab_into()，允许多个监控线程并发截屏。
    """

    def __init__(self) -> None:
        self._bgra: np.ndarray | None = None
        self._bgr: np.ndarray | None = None
        self._shape: tuple[int, int] | None = None  # (h, w)
        self._lock = threading.Lock()

    def _ensure(self, h: int, w: int) -> None:
        if self._shape == (h, w):
            return
        self._bgra = np.empty((h, w, 4), dtype=np.uint8)
        self._bgr = np.empty((h, w, 3), dtype=np.uint8)
        self._shape = (h, w)

    def grab_into(self, sct: MSSBase, monitor: dict) -> np.ndarray:
        """截屏到预分配缓冲区，返回 BGR 数组视图（借用，下次调用后失效）

        线程安全：截图、写入和颜色转换通过 Lock 保护。
        """
        require_cv2("screen capture")

        with self._lock:
            shot = sct.grab(monitor)
            h, w = shot.size[1], shot.size[0]
            self._ensure(h, w)
            if self._bgra is None or self._bgr is None:
                raise RuntimeError(t("vision.exc.buffer_uninitialized"))
            raw = np.frombuffer(shot.bgra, dtype=np.uint8).reshape(h, w, 4)
            np.copyto(self._bgra[:h, :w], raw)
            cv2.cvtColor(self._bgra[:h, :w], cv2.COLOR_BGRA2BGR, dst=self._bgr[:h, :w])
            return self._bgr[:h, :w]
