"""ZoomController — 平滑缩放动画，ease-out-cubic 缓动

核心特性:
- ease-out-cubic 缓动函数，视觉上快速响应后平滑减速
- ~8 帧 / 120ms 完成过渡
- 支持中断: 新缩放请求取消当前动画
- 每帧插值 zoom + offset → 更新画布
"""

import tkinter as tk
from typing import Callable

from src.core.easing import ease_out_cubic


class ZoomController:
    """管理平滑缩放动画"""

    __slots__ = (
        "_canvas", "_on_update", "_animation_id",
        "_start_zoom", "_target_zoom",
        "_start_ox", "_start_oy", "_target_ox", "_target_oy",
        "_duration_ms", "_frame_count", "_start_time",
    )

    def __init__(
        self,
        canvas: tk.Canvas,
        on_update: Callable[[float, float, float], None],
        duration_ms: int = 120,
        frame_count: int = 8,
    ) -> None:
        self._canvas = canvas
        self._on_update = on_update
        self._animation_id: str | None = None
        self._duration_ms = duration_ms
        self._frame_count = frame_count
        # 动画状态
        self._start_zoom: float = 1.0
        self._target_zoom: float = 1.0
        self._start_ox: float = 0.0
        self._start_oy: float = 0.0
        self._target_ox: float = 0.0
        self._target_oy: float = 0.0
        self._start_time: float = 0.0

    def animate_to(
        self,
        target_zoom: float,
        target_ox: float,
        target_oy: float,
        current_zoom: float,
        current_ox: float,
        current_oy: float,
    ) -> None:
        """从当前视口状态平滑过渡到目标状态"""
        # 取消正在进行的动画
        self.cancel()

        self._start_zoom = current_zoom
        self._target_zoom = target_zoom
        self._start_ox = current_ox
        self._start_oy = current_oy
        self._target_ox = target_ox
        self._target_oy = target_oy

        frame_ms = max(1, self._duration_ms // self._frame_count)
        self._start_time = 0.0
        self._tick(0, frame_ms)

    def cancel(self) -> None:
        """取消当前动画"""
        if self._animation_id:
            self._canvas.after_cancel(self._animation_id)
            self._animation_id = None

    def destroy(self) -> None:
        """取消动画并释放资源。"""
        self.cancel()

    def _tick(self, frame: int, frame_ms: int) -> None:
        """动画帧回调"""
        t = frame / self._frame_count
        eased = ease_out_cubic(t)

        zoom = self._start_zoom + (self._target_zoom - self._start_zoom) * eased
        ox = self._start_ox + (self._target_ox - self._start_ox) * eased
        oy = self._start_oy + (self._target_oy - self._start_oy) * eased

        self._on_update(zoom, ox, oy)

        if frame < self._frame_count:
            self._animation_id = self._canvas.after(
                frame_ms, self._tick, frame + 1, frame_ms,
            )
        else:
            # 确保精确到达目标
            self._on_update(self._target_zoom, self._target_ox, self._target_oy)
            self._animation_id = None

    @property
    def is_animating(self) -> bool:
        return self._animation_id is not None
