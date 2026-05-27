"""ViewportManager — 视口裁剪管理，只渲染可见区域内的节点和边

核心优化:
- AABB 包围盒检测，仅渲染视口内 (+200px 滞后边距) 的节点/边
- 增量 diff: 返回 entered/exited 差集，避免全量重建
- 200px 滞后边距减少快速平移时的进出闪烁
"""

from src.core.flow import FlowGraph, FlowNode
from src.panel.canvas.node_renderer import node_size, node_intersects_rect

MARGIN_PX = 200
EDGE_MARGIN_BASE = 200  # 贝塞尔控制点额外偏移余量（世界坐标，含 zoom 补偿）


def graph_bounds(graph: FlowGraph) -> tuple[float, float, float, float]:
    """计算所有节点的 AABB 边界 (min_x, min_y, max_x, max_y)。"""
    if not graph.nodes:
        return 0.0, 0.0, 600.0, 400.0
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")
    for node in graph.nodes.values():
        nw, nh = node_size(node)
        min_x = min(min_x, node.pos_x)
        min_y = min(min_y, node.pos_y)
        max_x = max(max_x, node.pos_x + nw)
        max_y = max(max_y, node.pos_y + nh)
    return min_x, min_y, max_x, max_y


class ViewportManager:
    """跟踪可见节点/边集合，计算增量差集"""

    __slots__ = (
        "_visible_nodes",
        "_visible_edges",
        "_cached_bounds",
        "_cached_graph_version",
    )

    def __init__(self) -> None:
        self._visible_nodes: set[str] = set()
        self._visible_edges: set[str] = set()
        self._cached_bounds: tuple[float, float, float, float] | None = None
        self._cached_graph_version: int = -1

    @property
    def visible_nodes(self) -> set[str]:
        return self._visible_nodes

    @property
    def visible_edges(self) -> set[str]:
        return self._visible_edges

    def visible_bounds(
        self,
        offset_x: float,
        offset_y: float,
        zoom: float,
        canvas_w: float,
        canvas_h: float,
    ) -> tuple[float, float, float, float]:
        """返回可见世界坐标区域 (wx1, wy1, wx2, wy2)，含滞后边距"""
        margin = MARGIN_PX / zoom
        wx1 = offset_x - margin
        wy1 = offset_y - margin
        wx2 = offset_x + canvas_w / zoom + margin
        wy2 = offset_y + canvas_h / zoom + margin
        return wx1, wy1, wx2, wy2

    def compute_visibility(
        self,
        graph: FlowGraph,
        offset_x: float,
        offset_y: float,
        zoom: float,
        canvas_w: float,
        canvas_h: float,
    ) -> tuple[set[str], set[str]]:
        """计算当前视口下可见的节点 ID 和边 ID 集合"""
        bounds = self.visible_bounds(offset_x, offset_y, zoom, canvas_w, canvas_h)
        return self.compute_visibility_bounds(graph, *bounds)

    def compute_visibility_bounds(
        self,
        graph: FlowGraph,
        wx1: float,
        wy1: float,
        wx2: float,
        wy2: float,
    ) -> tuple[set[str], set[str]]:
        """根据给定世界坐标区域计算可见集合"""
        visible_nodes: set[str] = set()
        for node in graph.nodes.values():
            if node_intersects_rect(node, wx1, wy1, wx2, wy2):
                visible_nodes.add(node.node_id)

        visible_edges: set[str] = set()
        for edge in graph.edges:
            if edge.from_node in visible_nodes or edge.to_node in visible_nodes:
                visible_edges.add(edge.edge_id)
            else:
                from_node = graph.get_node(edge.from_node)
                to_node = graph.get_node(edge.to_node)
                if from_node and to_node and self._edge_path_intersects(
                    from_node, to_node, wx1, wy1, wx2, wy2,
                ):
                    visible_edges.add(edge.edge_id)

        return visible_nodes, visible_edges

    def diff(
        self, old_set: set[str], new_set: set[str],
    ) -> tuple[set[str], set[str]]:
        """计算集合差: (entered, exited)"""
        return new_set - old_set, old_set - new_set

    def update(
        self,
        graph: FlowGraph,
        offset_x: float,
        offset_y: float,
        zoom: float,
        canvas_w: float,
        canvas_h: float,
    ) -> tuple[set[str], set[str], set[str], set[str]]:
        """增量更新可见集合并返回差集

        Returns: (entered_nodes, exited_nodes, entered_edges, exited_edges)
        """
        bounds = self.visible_bounds(offset_x, offset_y, zoom, canvas_w, canvas_h)
        graph_sig = (len(graph.nodes), len(graph.edges))

        if bounds == self._cached_bounds and graph_sig == self._cached_graph_version:
            return set(), set(), set(), set()

        new_nodes, new_edges = self.compute_visibility_bounds(graph, *bounds)

        entered_nodes, exited_nodes = self.diff(self._visible_nodes, new_nodes)
        entered_edges, exited_edges = self.diff(self._visible_edges, new_edges)

        self._visible_nodes = new_nodes
        self._visible_edges = new_edges
        self._cached_bounds = bounds
        self._cached_graph_version = graph_sig

        return entered_nodes, exited_nodes, entered_edges, exited_edges

    def reset(self) -> None:
        """清空可见集合 (图结构变化时调用)"""
        self._visible_nodes = set()
        self._visible_edges = set()
        self._cached_bounds = None

    @staticmethod
    def _edge_path_intersects(
        from_node: FlowNode,
        to_node: FlowNode,
        wx1: float,
        wy1: float,
        wx2: float,
        wy2: float,
    ) -> bool:
        """检查两端节点均在视口外时，连线路径是否穿过视口区域"""
        fnw, fnh = node_size(from_node)
        tnw, tnh = node_size(to_node)
        fx = from_node.pos_x + fnw / 2
        fy = from_node.pos_y + fnh / 2
        tx = to_node.pos_x + tnw / 2
        ty = to_node.pos_y + tnh / 2

        # bezier 控制点偏移最大 160*zoom 屏幕像素 = 160 世界坐标，
        # 加上上行边水平绕行的额外偏移，使用 EDGE_MARGIN_BASE 保证覆盖
        margin = EDGE_MARGIN_BASE
        dist_sq = (fx - tx) ** 2 + (fy - ty) ** 2
        margin += (dist_sq ** 0.5) * 0.35

        ex1 = min(fx, tx) - margin
        ey1 = min(fy, ty) - margin
        ex2 = max(fx, tx) + margin
        ey2 = max(fy, ty) + margin

        return ex2 >= wx1 and ex1 <= wx2 and ey2 >= wy1 and ey1 <= wy2

    def mark_all_visible(self, graph: FlowGraph) -> None:
        """标记所有节点/边为可见 (全量渲染后调用)"""
        self._visible_nodes = set(graph.nodes.keys())
        self._visible_edges = {e.edge_id for e in graph.edges}
