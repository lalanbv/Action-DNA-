"""HitTestMixin — 命中检测逻辑。"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from src.core.flow import FlowGraph
from src.panel.canvas._interaction_types import (
    HIT_CANVAS,
    HIT_EDGE,
    HIT_EDGE_ENDPOINT,
    HIT_EDGE_MIDPOINT,
    HIT_NODE,
    HIT_PORT,
    KEY_EDGE_ID,
    KEY_ITEM_ID,
    KEY_NODE_ID,
    KEY_PORT_LABEL,
    KEY_SIDE,
    SIDE_SOURCE,
    _AUTO_INSERT_THRESHOLD,
    _EDGE_ENDPOINT_HIT_RADIUS,
    _EDGE_HIT_RADIUS,
    _EDGE_MIDPOINT_HIT_RADIUS,
)
from src.panel.canvas.edge_renderer import (
    _compute_line_points,
    _edge_endpoints,
    cubic_bezier_point,
)
from src.panel.canvas.node_renderer import (
    node_intersects_rect,
    port_positions,
)

if TYPE_CHECKING:
    from src.panel.canvas.graph_canvas import GraphCanvas


def _sample_polyline(points: tuple[float, ...], t: float) -> tuple[float, float]:
    """在折线路径上按参数 t ∈ [0,1] 插值取点。

    points 是扁平坐标 (x0, y0, x1, y1, ..., xn, yn)。
    t=0 返回起点，t=1 返回终点。
    """
    if len(points) < 4:
        return points[0], points[1] if len(points) >= 2 else (0.0, 0.0)

    num_segments = (len(points) // 2) - 1
    if num_segments < 1:
        return points[0], points[1]

    seg_f = t * num_segments
    seg_i = min(int(seg_f), num_segments - 1)
    seg_t = seg_f - seg_i

    i0 = seg_i * 2
    i1 = i0 + 2
    x = points[i0] + (points[i1] - points[i0]) * seg_t
    y = points[i0 + 1] + (points[i1 + 1] - points[i0 + 1]) * seg_t
    return x, y


class HitTestMixin:
    """命中检测方法，供 InteractionHandler 继承。"""

    _canvas: GraphCanvas
    _get_graph: object
    _get_viewport: object
    _get_edge_style: object
    _drag_node_id: str | None

    def _hit_test(self, screen_x: float, screen_y: float) -> tuple[str, dict]:
        """检测鼠标位置命中了什么。

        优先级: port > node > edge_endpoint > edge_midpoint > edge > canvas

        节点优先级最高（仅次于端口）：点击节点区域时永远不会选中背后的连线。
        """
        items = self._canvas.find_overlapping(
            screen_x - 5, screen_y - 5, screen_x + 5, screen_y + 5
        )
        node_hit: tuple[str, dict] | None = None
        edge_tag_hit: str | None = None
        # find_overlapping returns items bottom-to-top; iterate reverse
        # so the LAST matching node (topmost in z-order) wins.
        for item_id in reversed(items):
            tags = self._canvas.gettags(item_id)
            for tag in tags:
                if tag.startswith("port:"):
                    parts = tag.split(":")
                    if len(parts) >= 3:
                        return HIT_PORT, {
                            KEY_NODE_ID: parts[1],
                            KEY_PORT_LABEL: parts[2],
                            KEY_ITEM_ID: item_id,
                        }
                if tag.startswith("node:"):
                    node_hit = (HIT_NODE, {KEY_NODE_ID: tag.split(":")[1]})
                if tag.startswith("edge:") and not edge_tag_hit:
                    edge_tag_hit = tag.split(":")[1]

        # 节点优先于一切（端口除外）
        if node_hit:
            return node_hit

        # 几何兜底：tag 检测不到时用世界坐标判定节点包围盒
        geo_node = self._node_at_screen(screen_x, screen_y)
        if geo_node:
            return HIT_NODE, {KEY_NODE_ID: geo_node}

        edge_hit = self._detect_edge_hit(screen_x, screen_y)
        if edge_hit and edge_hit[0] == HIT_EDGE_ENDPOINT:
            return edge_hit

        if edge_hit:
            return edge_hit

        # Fallback: click on edge label/glow item detected by tag
        if edge_tag_hit:
            return HIT_EDGE, {KEY_EDGE_ID: edge_tag_hit}

        return HIT_CANVAS, {}

    def _detect_edge_hit(
        self, screen_x: float, screen_y: float
    ) -> tuple[str, dict] | None:
        graph = self._get_graph()
        if not graph:
            return None
        offset_x, offset_y, zoom = self._get_viewport()

        best_type: str | None = None
        best_info: dict = {}
        best_dist = float("inf")

        for edge in graph.edges:
            if not self._canvas.has_edge_visual(edge.edge_id):
                continue
            endpoints = _edge_endpoints(edge, graph, offset_x, offset_y, zoom)
            if endpoints is None:
                continue
            sx1, sy1, sx2, sy2 = endpoints

            style = self._get_edge_style()
            points = _compute_line_points(sx1, sy1, sx2, sy2, zoom, style)

            min_dist, best_t = self._sample_edge_distance(
                screen_x, screen_y, points, style, sx1, sy1, sx2, sy2,
            )

            if min_dist > _EDGE_HIT_RADIUS:
                continue

            if min_dist < best_dist:
                best_dist = min_dist
                if min_dist <= _EDGE_ENDPOINT_HIT_RADIUS:
                    side = SIDE_SOURCE if best_t < 0.5 else SIDE_TARGET
                    best_type = HIT_EDGE_ENDPOINT
                    best_info = {KEY_EDGE_ID: edge.edge_id, KEY_SIDE: side}
                elif (
                    abs(best_t - 0.5) < 0.2
                    and min_dist <= _EDGE_MIDPOINT_HIT_RADIUS
                ):
                    best_type = HIT_EDGE_MIDPOINT
                    best_info = {KEY_EDGE_ID: edge.edge_id}
                else:
                    best_type = HIT_EDGE
                    best_info = {KEY_EDGE_ID: edge.edge_id}

        if best_type:
            return best_type, best_info
        return None

    @staticmethod
    def _sample_edge_distance(
        px: float,
        py: float,
        points: tuple[float, ...],
        style: str,
        sx1: float,
        sy1: float,
        sx2: float,
        sy2: float,
        count: int = 25,
    ) -> tuple[float, float]:
        """计算屏幕点到连线的最短距离及对应参数 t。

        points 是 _compute_line_points 返回的扁平坐标元组:
          bezier:  (x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2)  len=8
          orthogonal: (x1, y1, ..., x2, y2)  多段折线
          straight: (x1, y1, x2, y2)
        """
        min_dist = float("inf")
        best_t = 0.5
        # Orthogonal lines have few segments; fewer samples suffice
        if style == "orthogonal" and len(points) >= 4:
            actual_count = max(8, (len(points) // 2) * 3)
        else:
            actual_count = count
        for i in range(actual_count):
            t = i / (actual_count - 1)
            if style == "bezier" and len(points) == 8:
                x, y = cubic_bezier_point(*points, t)
            elif style == "orthogonal" and len(points) >= 4:
                x, y = _sample_polyline(points, t)
            else:
                x = sx1 + (sx2 - sx1) * t
                y = sy1 + (sy2 - sy1) * t
            dist = math.hypot(px - x, py - y)
            if dist < min_dist:
                min_dist = dist
                best_t = t
        return min_dist, best_t

    def _port_at_screen(self, node_id: str, port_label: str) -> tuple[float, float] | None:
        graph = self._get_graph()
        node = graph.get_node(node_id) if graph else None
        if not node:
            return None
        ports = port_positions(node)
        if port_label not in ports:
            return None
        wx, wy = ports[port_label]
        return self._canvas.world_to_screen(wx, wy)

    def _nodes_in_world_rect(
        self, graph: FlowGraph, wx1: float, wy1: float, wx2: float, wy2: float,
    ) -> set[str]:
        result: set[str] = set()
        for n in graph.nodes.values():
            if node_intersects_rect(n, wx1, wy1, wx2, wy2):
                result.add(n.node_id)
        return result

    def _node_at_screen(self, screen_x: float, screen_y: float) -> str | None:
        """几何兜底: 用世界坐标检测鼠标是否在某个节点的包围盒内。

        逆序遍历以优先匹配后添加的（视觉上最上层的）节点。
        """
        graph = self._get_graph()
        if not graph:
            return None
        wx, wy = self._canvas.screen_to_world(screen_x, screen_y)
        for node in reversed(list(graph.nodes.values())):
            if node_intersects_rect(node, wx, wy, wx, wy):
                return node.node_id
        return None

    def _nearest_edge_to_world_point(
        self, wx: float, wy: float
    ) -> tuple[str, float, float] | None:
        graph = self._get_graph()
        if not graph:
            return None
        offset_x, offset_y, zoom = self._get_viewport()
        best: tuple[str, float, float] | None = None
        best_dist = float("inf")

        for edge in graph.edges:
            if edge.from_node == self._drag_node_id or edge.to_node == self._drag_node_id:
                continue
            if not self._canvas.has_edge_visual(edge.edge_id):
                continue

            endpoints = _edge_endpoints(edge, graph, offset_x, offset_y, zoom)
            if endpoints is None:
                continue
            sx1, sy1, sx2, sy2 = endpoints
            ssx = (wx - offset_x) * zoom
            ssy = (wy - offset_y) * zoom

            style = self._get_edge_style()
            points = _compute_line_points(sx1, sy1, sx2, sy2, zoom, style)

            min_dist, best_t = self._sample_edge_distance(
                ssx, ssy, points, style, sx1, sy1, sx2, sy2,
            )

            if min_dist < best_dist:
                best_dist = min_dist
                best = (edge.edge_id, min_dist / zoom if zoom > 0 else min_dist, best_t)

        if best and best[1] < _AUTO_INSERT_THRESHOLD:
            return best
        return None
