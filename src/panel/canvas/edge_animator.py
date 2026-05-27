"""EdgeAnimator — 边执行动画

功能:
- 执行时活跃边 dashoffset 动画 (80ms 间隔)
- 仅动画连接到当前执行节点的边 (性能安全)
- 支持暂停/恢复
- 流动亮点粒子效果 (支持贝塞尔/正交/直线路径)
"""

from dataclasses import dataclass

import tkinter as tk

from src.panel.canvas.edge_renderer import cubic_bezier_point
from src.panel.canvas.theme import current_theme
from src.panel.models.enums import EdgeStyle


@dataclass
class _FlowDot:
    """沿边路径移动的亮点粒子"""
    item_id: int = 0
    line_item: int = 0
    t: float = 0.0


class EdgeAnimator:
    """管理边执行动画"""

    _LINE_TAGS = ("edge",)
    _SKIP_TAGS = ("edge_label", "edge_label_bg", "edge_glow")

    def __init__(self, canvas: tk.Canvas):
        self._canvas = canvas
        self._zoom: float = 1.0
        self._active_edge_ids: set[str] = set()
        self._dash_items: list[int] = []
        self._dash_offset = 0
        self._animation_id: str | None = None
        self._running = False
        self._interval_ms = 80
        self._flow_dots: dict[str, _FlowDot] = {}
        self._dot_pool: list[_FlowDot] = []
        self._line_items_by_edge: dict[str, int] = {}
        self._edge_style: str = EdgeStyle.BEZIER

    @staticmethod
    def _is_edge_line(tags: tuple[str, ...]) -> bool:
        """判断 canvas item 是否为边的主线条（排除标签/辉光等附属元素）"""
        has_edge = False
        for t in tags:
            if t in EdgeAnimator._SKIP_TAGS:
                return False
            if t == "edge":
                has_edge = True
        return has_edge

    def _find_line_item(self, edge_id: str) -> int | None:
        """获取指定边的主线条 item ID（优先走缓存）"""
        cached = self._line_items_by_edge.get(edge_id)
        if cached is not None:
            return cached

        tag = f"edge:{edge_id}"
        for item in self._canvas.find_withtag(tag):
            if self._is_edge_line(self._canvas.gettags(item)):
                self._line_items_by_edge[edge_id] = item
                return item
        return None

    def _resolve_edge_items(self, edge_ids: set[str]) -> list[int]:
        items = []
        for edge_id in edge_ids:
            item = self._find_line_item(edge_id)
            if item is not None:
                items.append(item)
        return items

    def start(self, edge_ids: set[str], edge_style: str = EdgeStyle.BEZIER) -> None:
        """开始动画指定边"""
        self.stop()
        if not edge_ids:
            return

        self._active_edge_ids = edge_ids
        self._edge_style = edge_style
        self._dash_items = self._resolve_edge_items(edge_ids)
        self._running = True
        self._dash_offset = 0
        self._create_flow_dots(edge_ids)
        self._apply_dash()
        self._tick()

    def stop(self) -> None:
        """停止动画并恢复边的正常样式"""
        self._running = False
        if self._animation_id:
            self._canvas.after_cancel(self._animation_id)
            self._animation_id = None

        for item in self._dash_items:
            try:
                self._canvas.itemconfigure(item, dash=(), width=max(2, 2.5 * self._zoom))
            except tk.TclError:
                pass

        self._remove_flow_dots()
        # 安全网：清除所有可能残留的流动亮点
        try:
            self._canvas.delete("flow_dot")
        except tk.TclError:
            pass
        self._active_edge_ids.clear()
        self._dash_items.clear()
        self._line_items_by_edge.clear()

    def destroy(self) -> None:
        """停止动画并释放所有资源（包括对象池）。"""
        self.stop()
        for dot in self._dot_pool:
            try:
                self._canvas.delete(dot.item_id)
            except tk.TclError:
                pass
        self._dot_pool.clear()

    def is_running(self) -> bool:
        return self._running

    def set_zoom(self, zoom: float) -> None:
        """更新缩放级别，影响动画线宽。"""
        self._zoom = zoom

    def _apply_dash(self) -> None:
        """给活跃边应用动画 dash 样式"""
        w = max(3, 3.5 * self._zoom)
        for item in self._dash_items:
            try:
                self._canvas.itemconfigure(
                    item,
                    dash=(12, 6),
                    dashoffset=self._dash_offset,
                    width=w,
                )
            except tk.TclError:
                pass

    # ── 流动亮点 ──────────────────────────────────────────

    def _create_flow_dots(self, edge_ids: set[str]) -> None:
        """为每条活跃边创建或复用一个流动亮点"""
        theme = current_theme()
        for edge_id in edge_ids:
            line_item = self._find_line_item(edge_id)
            if line_item is None:
                continue
            coords = self._canvas.coords(line_item)
            if len(coords) < 2:
                continue
            x, y = coords[0], coords[1]
            r = max(3, 4 * self._zoom)

            if self._dot_pool:
                dot = self._dot_pool.pop()
                self._canvas.coords(dot.item_id, x - r, y - r, x + r, y + r)
                self._canvas.itemconfigure(dot.item_id, fill=theme.status_running, state="normal")
                dot.line_item = line_item
                dot.t = 0.0
            else:
                dot_id = self._canvas.create_oval(
                    x - r, y - r, x + r, y + r,
                    fill=theme.status_running, outline="",
                    tags=("flow_dot",),
                )
                self._canvas.tag_raise(dot_id)
                dot = _FlowDot(item_id=dot_id, line_item=line_item, t=0.0)
            self._flow_dots[edge_id] = dot

    def _remove_flow_dots(self) -> None:
        """回收流动亮点到对象池（隐藏而非删除）"""
        for dot in self._flow_dots.values():
            try:
                self._canvas.itemconfigure(dot.item_id, state="hidden")
            except tk.TclError:
                continue
            self._dot_pool.append(dot)
        self._flow_dots.clear()

    def _update_flow_dots(self) -> None:
        """更新流动亮点位置（支持贝塞尔/正交/直线路径）"""
        for dot in self._flow_dots.values():
            dot.t = (dot.t + 0.04) % 1.0
            try:
                coords = self._canvas.coords(dot.line_item)
            except tk.TclError:
                continue
            if len(coords) < 4:
                continue
            t = dot.t
            x1, y1 = coords[0], coords[1]
            x2, y2 = coords[-2], coords[-1]

            if self._edge_style == EdgeStyle.ORTHOGONAL and len(coords) >= 8:
                x, y = self._interpolate_orthogonal(coords, t)
            elif len(coords) == 8:
                cp1x, cp1y, cp2x, cp2y = coords[2], coords[3], coords[4], coords[5]
                x, y = cubic_bezier_point(x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2, t)
            else:
                x = x1 + (x2 - x1) * t
                y = y1 + (y2 - y1) * t
            r = max(3, 4 * self._zoom)
            try:
                self._canvas.coords(dot.item_id, x - r, y - r, x + r, y + r)
            except tk.TclError:
                pass

    @staticmethod
    def _interpolate_orthogonal(coords: list[float], t: float) -> tuple[float, float]:
        """沿正交折线路径插值坐标"""
        points = [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]
        if len(points) < 2:
            return points[0] if points else (0, 0)

        seg_lengths: list[float] = []
        total = 0.0
        for i in range(len(points) - 1):
            dx = points[i + 1][0] - points[i][0]
            dy = points[i + 1][1] - points[i][1]
            length = (dx * dx + dy * dy) ** 0.5
            seg_lengths.append(length)
            total += length

        if total < 1:
            return points[0]

        target = t * total
        accumulated = 0.0
        for i, seg_len in enumerate(seg_lengths):
            if accumulated + seg_len >= target:
                frac = (target - accumulated) / seg_len if seg_len > 0 else 0
                x = points[i][0] + (points[i + 1][0] - points[i][0]) * frac
                y = points[i][1] + (points[i + 1][1] - points[i][1]) * frac
                return x, y
            accumulated += seg_len

        return points[-1]

    def _tick(self) -> None:
        """动画帧"""
        if not self._running:
            return

        self._dash_offset = (self._dash_offset + 4) % 36
        self._apply_dash()
        self._update_flow_dots()
        self._animation_id = self._canvas.after(self._interval_ms, self._tick)
