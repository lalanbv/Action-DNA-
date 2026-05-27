"""区域框选坐标转换工具。

画布坐标 → mss 坐标 → 逻辑坐标（pyautogui），供 Qt/Tkinter 区域选择器共用。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RegionCoordConverter:
    """两阶段坐标转换器：画布坐标 → mss 坐标 → 逻辑坐标。"""

    canvas_to_mss: float
    mss_to_logical: float
    offset_x: int
    offset_y: int

    def to_logical_rect(
        self, x1: int, y1: int, x2: int, y2: int,
    ) -> tuple[int, int, int, int]:
        """将画布坐标转换为逻辑坐标 (left, top, width, height)。"""
        mx1 = int(x1 / self.canvas_to_mss)
        my1 = int(y1 / self.canvas_to_mss)
        mx2 = int(x2 / self.canvas_to_mss)
        my2 = int(y2 / self.canvas_to_mss)
        lx1 = int(mx1 / self.mss_to_logical) + self.offset_x
        ly1 = int(my1 / self.mss_to_logical) + self.offset_y
        lx2 = int(mx2 / self.mss_to_logical) + self.offset_x
        ly2 = int(my2 / self.mss_to_logical) + self.offset_y
        return lx1, ly1, lx2 - lx1, ly2 - ly1

    @staticmethod
    def from_capture(
        capture,
        display_scale: float,
    ) -> RegionCoordConverter:
        """从 ScreenCapture 实例和显示缩放比创建转换器（快照当前状态）。"""
        offset_x, offset_y = capture.virtual_desktop_offset
        return RegionCoordConverter(
            canvas_to_mss=display_scale,
            mss_to_logical=capture.scale_factor,
            offset_x=offset_x,
            offset_y=offset_y,
        )
