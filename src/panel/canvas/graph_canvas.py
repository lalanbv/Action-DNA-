"""GraphCanvas — 可视化节点图编辑器画布"""

import logging
import time
import tkinter as tk
from typing import Callable

_logger = logging.getLogger(__name__)

from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.panel.canvas.auto_layout import all_nodes_at_origin
from src.panel.canvas.edge_animator import EdgeAnimator
from src.panel.canvas.node_shared import LAYOUT_SPACING_Y, LAYOUT_START_X, LAYOUT_START_Y
from src.panel.models.enums import EdgeStyle, NodeExecutionState
from src.panel.canvas.edge_renderer import (
    EdgeCanvasItems,
    _compute_line_points,
    _edge_endpoints,
    clear_edge_hover,
    clear_edge_selected,
    render_edge,
    set_edge_hover,
    set_edge_selected,
    update_edge,
)
from src.panel.canvas.interaction_handler import InteractionHandler
from src.panel.canvas.minimap import Minimap
from src.panel.canvas.node_renderer import (
    NodeCanvasItems,
    render_node,
    update_node_position,
)
from src.panel.canvas.grid_renderer import GridRenderer
from src.panel.canvas.render_stats import RenderStats, RenderStatsCollector
from src.panel.canvas.viewport import ViewportManager, graph_bounds
from src.panel.canvas.zoom_controller import ZoomController
from src.panel.canvas.theme import ThemeCallbackMixin, current_theme, mix_colors, on_theme_change, remove_theme_change
from src.panel.components.toolbar_tooltip import CanvasTooltip

_FAST_MOVE_THRESHOLD_PX = 200
_ZOOM_MIN = 0.2
_ZOOM_MAX = 3.0
_AUTO_LAYOUT_START_X = LAYOUT_START_X
_AUTO_LAYOUT_START_Y = LAYOUT_START_Y
_AUTO_LAYOUT_SPACING_Y = LAYOUT_SPACING_Y
_AUTO_LAYOUT_BRANCH_X = 200
_END_NODE_X = 400
_END_NODE_START_Y = 20
_END_NODE_Y_OFFSET = 120


class GraphCanvas(ThemeCallbackMixin, tk.Canvas):
    """节点图画布 — 视口变换、渲染调度、交互分发"""

    def __init__(self, parent: tk.Widget, event_callback: Callable[..., None], **kwargs):
        theme = current_theme()
        super().__init__(parent, bg=theme.bg_primary, highlightthickness=0, **kwargs)

        self._event_callback = event_callback  # 向页面层报告事件

        # 视口状态
        self._offset_x: float = 0.0
        self._offset_y: float = 0.0
        self._zoom: float = 1.0

        # 当前图数据
        self._graph: FlowGraph | None = None

        # 渲染缓存: node_id -> NodeCanvasItems
        self._node_items: dict[str, NodeCanvasItems] = {}

        # 渲染缓存: edge_id -> EdgeCanvasItems
        self._edge_items: dict[str, EdgeCanvasItems] = {}

        # 网格渲染器（对象池优化）
        self._grid_renderer = GridRenderer(self)

        # 视口裁剪管理器
        self._viewport_mgr = ViewportManager()

        # 视口刷新去抖
        self._viewport_refresh_id: str | None = None

        # 平滑缩放控制器
        self._zoom_controller = ZoomController(
            canvas=self,
            on_update=self._apply_zoom_state,
        )

        # 高亮状态
        self._highlighted_node_id: str | None = None

        # 节点执行状态: node_id -> NodeExecutionState
        self._node_state_map: dict[str, str] = {}

        # 边悬停状态
        self._hovered_edge_id: str | None = None
        self._auto_insert_edge_id: str | None = None

        # 连线样式
        self._edge_style: str = EdgeStyle.BEZIER

        # 上一次选中集合（用于 diff 更新选择环）
        self._prev_selected: set[str] = set()

        # 渲染签名缓存: node_id -> 元组签名（避免 CONDITION 等节点每次全量重建）
        self._node_render_signatures: dict[str, tuple] = {}

        # 渲染统计
        self._render_stats_collector = RenderStatsCollector()

        # 拖拽边更新节流: 脏节点集合 + after_idle token
        self._drag_dirty_nodes: set[str] = set()
        self._drag_edge_flush_id: str | None = None

        # z-order 脏标记
        self._z_order_dirty: bool = True

        # 边动画器
        self._edge_animator = EdgeAnimator(self)

        # 交互处理器（必须在 Minimap 之前初始化，因为 Minimap lambda 引用 _interaction）
        self._interaction: InteractionHandler = InteractionHandler(
            canvas=self,
            get_graph=lambda: self._graph,
            get_viewport=lambda: (self._offset_x, self._offset_y, self._zoom),
            get_edge_style=lambda: self._edge_style,
            event_callback=self._dispatch_interaction,
        )

        # 小地图
        self._minimap = Minimap(
            canvas=self,
            get_graph=lambda: self._graph,
            get_viewport=lambda: (self._offset_x, self._offset_y, self._zoom),
            on_pan=lambda dx, dy: self._pan_by(dx, dy),
            get_selected_nodes=lambda: self._interaction.get_selected_nodes(),
            get_node_states=lambda: self._get_node_states(),
            get_selected_edge=lambda: self._interaction.get_selected_edge(),
            on_refresh_grid=lambda: self._refresh_grid(),
        )

        # 节点悬浮提示
        self._node_tooltip = CanvasTooltip(self)

        # Canvas 尺寸变化时重绘网格
        self._grid_resize_id: str | None = None
        self._grid_refresh_id: str | None = None
        self._initial_grid_done: bool = False
        self.bind("<Configure>", self._on_canvas_configure)

        self._init_theme_guard(self._on_theme_changed, tk.TclError)

    # ── 坐标变换 ──────────────────────────────────────────

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        return (wx - self._offset_x) * self._zoom, (wy - self._offset_y) * self._zoom

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        return sx / self._zoom + self._offset_x, sy / self._zoom + self._offset_y

    def viewport_center(self) -> tuple[float, float]:
        """返回当前视口中心的世界坐标"""
        w = self.winfo_width()
        h = self.winfo_height()
        return self.screen_to_world(w / 2, h / 2)

    # ── 渲染 ──────────────────────────────────────────────

    def render_graph(self, graph: FlowGraph) -> None:
        """增量重绘 — 对比前后差异，只更新变化部分。
        首次调用（无旧图）时执行全量渲染，后续调用走 diff 路径。
        """
        t0 = time.monotonic()
        self._edge_animator.stop()
        self._graph = graph
        self._highlighted_node_id = None

        self._auto_layout_if_needed(graph)

        old_nodes = set(self._node_items.keys())
        new_nodes = set(graph.nodes.keys())

        removed = old_nodes - new_nodes
        added = new_nodes - old_nodes
        common = old_nodes & new_nodes

        # 移除已删除的节点（关联边由下方通用边清理逻辑兜底）
        if removed:
            for nid in removed:
                self.delete(f"node:{nid}")
                self._node_items.pop(nid, None)
                self._node_render_signatures.pop(nid, None)
                self._node_state_map.pop(nid, None)
            self._mark_z_order_dirty()

        # 移除不再存在的边
        new_edge_ids = {e.edge_id for e in graph.edges}
        for eid in list(self._edge_items.keys()):
            if eid not in new_edge_ids:
                self.delete(f"edge:{eid}")
                self._edge_items.pop(eid, None)
        if set(self._edge_items.keys()) != new_edge_ids:
            self._mark_z_order_dirty()

        # 添加新边
        for edge in graph.edges:
            if edge.edge_id not in self._edge_items:
                self._create_edge_visual(edge)

        # 添加新节点
        for nid in added:
            node = graph.nodes[nid]
            self._create_node_visual(node)

        # 更新位置/内容变化的节点
        updated = 0
        for nid in common:
            node = graph.nodes[nid]
            needs_update, _ = self._node_needs_update(nid, node)
            if needs_update:
                self.delete(f"node:{nid}")
                self._node_items.pop(nid, None)
                self._create_node_visual(node)
                self._update_edges_for_node(nid)
                updated += 1

        self._ensure_z_order()
        self._minimap.schedule_full_redraw()
        self._viewport_mgr.mark_all_visible(graph)

        # 取消待处理的视口刷新，避免刚渲染的边被立即移除
        if self._viewport_refresh_id:
            self.after_cancel(self._viewport_refresh_id)
            self._viewport_refresh_id = None

        # 网格重绘（仅在首次或视口变化时需要）
        if not self._initial_grid_done:
            self._delayed_initial_grid()
            self._initial_grid_done = True
        else:
            self._draw_grid()

        elapsed_ms = (time.monotonic() - t0) * 1000
        estimated_items = len(self._node_items) * 8 + len(self._edge_items) * 4
        self._render_stats_collector.record(RenderStats(
            node_count=len(graph.nodes),
            visible_node_count=len(self._node_items),
            edge_count=len(graph.edges),
            canvas_item_count=estimated_items,
            render_time_ms=round(elapsed_ms, 2),
            diff_added=len(added),
            diff_removed=len(removed),
            diff_updated=updated,
        ))
        if estimated_items > 5000:
            _logger.warning("Canvas items: ~%d (>5000)", estimated_items)

    @property
    def render_stats(self) -> RenderStats | None:
        return self._render_stats_collector.last

    def _node_needs_update(self, node_id: str, node: FlowNode) -> tuple[bool, tuple]:
        """检查节点是否需要重新渲染，返回 (needs_update, signature)。"""
        items = self._node_items.get(node_id)
        if items is None:
            return True, ()
        sig = self._node_signature(node, self._node_state_map.get(node_id))
        if self._node_render_signatures.get(node_id) != sig:
            return True, sig
        return False, sig

    @staticmethod
    def _node_signature(node: FlowNode, state: str | None = None) -> tuple:
        """生成节点渲染签名元组（含位置、内容、执行状态）"""
        parts: list[object] = [node.node_type.name, node.comment, node.enabled,
                               node.pos_x, node.pos_y, state or ""]
        if node.action:
            parts.append(node.action)
        if node.condition:
            parts.append(node.condition)
        if node.loop_count:
            parts.append(node.loop_count)
        return tuple(parts)

    # ── 增量渲染（避免全量 delete+redraw）───────────────────

    def add_node_visual(self, node: FlowNode) -> None:
        """增量添加单个节点可视化"""
        items = render_node(self, node, self._offset_x, self._offset_y, self._zoom, theme=current_theme())
        self._node_items[node.node_id] = items
        self._node_render_signatures[node.node_id] = self._node_signature(node, self._node_state_map.get(node.node_id))
        self._viewport_mgr.visible_nodes.add(node.node_id)
        self._ensure_z_order()
        self._minimap.schedule_full_redraw()

    def remove_node_visual(self, node_id: str) -> None:
        """增量移除单个节点可视化 + 关联边"""
        self.delete(f"node:{node_id}")
        self._node_items.pop(node_id, None)
        self._node_render_signatures.pop(node_id, None)
        self._node_state_map.pop(node_id, None)
        self._viewport_mgr.visible_nodes.discard(node_id)
        # 移除关联的边图形
        if self._graph:
            for edge in self._graph.get_edges_for_node(node_id):
                self.delete(f"edge:{edge.edge_id}")
                self._edge_items.pop(edge.edge_id, None)
                self._viewport_mgr.visible_edges.discard(edge.edge_id)
        self._minimap.schedule_full_redraw()

    def update_node_visual(self, node_id: str) -> None:
        """增量更新单个节点可视化 + 关联边"""
        if not self._graph:
            return
        node = self._graph.get_node(node_id)
        if not node:
            return
        # 删除旧图形并重新绘制
        self.delete(f"node:{node_id}")
        self._node_items.pop(node_id, None)
        items = render_node(self, node, self._offset_x, self._offset_y, self._zoom, theme=current_theme())
        self._node_items[node_id] = items
        self._node_render_signatures[node_id] = self._node_signature(node, self._node_state_map.get(node_id))
        # 重绘关联边（样式可能变化，需要 delete+recreate）
        self._update_edges_for_node(node_id)

    def add_edge_visual(self, edge) -> None:
        """增量添加一条边可视化"""
        if self._graph:
            eid = edge.edge_id
            if eid in self._edge_items:
                self.remove_edge_visual(eid)
            items = render_edge(
                self, edge, self._graph, self._offset_x, self._offset_y, self._zoom, self._edge_style
            )
            if items:
                self._edge_items[eid] = items
            self._viewport_mgr.visible_edges.add(eid)
            self._ensure_z_order()
        self._minimap.schedule_full_redraw(invalidate_bounds=False)

    def remove_edge_visual(self, edge_id: str) -> None:
        """增量移除一条边可视化"""
        if self._hovered_edge_id == edge_id:
            self._hovered_edge_id = None
        self.delete(f"edge:{edge_id}")
        self._edge_items.pop(edge_id, None)
        self._viewport_mgr.visible_edges.discard(edge_id)
        self._minimap.schedule_full_redraw(invalidate_bounds=False)

    def set_edge_style(self, style: str) -> None:
        """设置连线样式: 'bezier' | 'orthogonal' | 'straight'"""
        if style == self._edge_style:
            return
        self._edge_style = style
        if self._graph:
            self._edge_items.clear()
            self.delete("edge", "edge_label_bg", "edge_label")
            for edge in self._graph.edges:
                items = render_edge(
                    self, edge, self._graph, self._offset_x, self._offset_y, self._zoom, style
                )
                if items:
                    self._edge_items[edge.edge_id] = items
            self._minimap.schedule_full_redraw(invalidate_bounds=False)

    def get_edge_style(self) -> str:
        """返回当前连线样式"""
        return self._edge_style

    def has_edge_visual(self, edge_id: str) -> bool:
        """检查指定边是否已渲染"""
        return edge_id in self._edge_items

    def get_edge_visual(self, edge_id: str) -> EdgeCanvasItems | None:
        """获取指定边的画布元素，不存在时返回 None"""
        return self._edge_items.get(edge_id)

    def set_snap_to_grid(self, enabled: bool) -> None:
        """设置网格吸附"""
        self._interaction.set_snap_to_grid(enabled)

    def select_all_nodes(self) -> None:
        """全选所有节点"""
        self._interaction.select_all()

    def get_selected_nodes(self) -> set[str]:
        """获取当前选中的节点 ID 集合"""
        return self._interaction.get_selected_nodes()

    def _get_node_states(self) -> dict[str, str]:
        """获取节点执行状态映射 (供小地图使用)"""
        states = dict(self._node_state_map)
        if self._highlighted_node_id:
            states[self._highlighted_node_id] = NodeExecutionState.RUNNING
        return states

    def set_node_state(self, node_id: str, state: str) -> None:
        """设置节点执行状态"""
        self._node_state_map[node_id] = state
        if node_id not in self._node_items:
            return
        theme = current_theme()
        border_color = {
            NodeExecutionState.COMPLETED: theme.accent_green,
            NodeExecutionState.ERROR: theme.accent_red,
        }.get(state)
        if border_color:
            self._update_node_border(node_id, border_color)
        elif state in (NodeExecutionState.PENDING, NodeExecutionState.RUNNING):
            self._update_node_border(node_id, theme.border_default)

    def clear_node_states(self) -> None:
        """清除所有节点执行状态。"""
        theme = current_theme()
        for node_id in self._node_state_map:
            self._update_node_border(node_id, theme.border_default)
        self._node_state_map.clear()

    def _update_node_border(self, node_id: str, color: str) -> None:
        items = self._node_items.get(node_id)
        if items is None or items.body == 0:
            return
        try:
            self.itemconfig(items.body, outline=color)
        except tk.TclError:
            pass

    def _create_node_visual(self, node: FlowNode) -> None:
        items = render_node(self, node, self._offset_x, self._offset_y, self._zoom, theme=current_theme())
        self._node_items[node.node_id] = items
        self._node_render_signatures[node.node_id] = self._node_signature(
            node, self._node_state_map.get(node.node_id),
        )
        self._mark_z_order_dirty()

    def _create_edge_visual(self, edge: FlowEdge) -> None:
        if not self._graph:
            return
        self.delete(f"edge:{edge.edge_id}")
        self._edge_items.pop(edge.edge_id, None)
        items = render_edge(
            self, edge, self._graph,
            self._offset_x, self._offset_y, self._zoom, self._edge_style,
        )
        if items:
            self._edge_items[edge.edge_id] = items
        self._mark_z_order_dirty()

    def _draw_grid(self) -> None:
        """通过 GridRenderer 对象池绘制背景点阵网格"""
        theme = current_theme()
        self._grid_renderer.update(
            self._offset_x, self._offset_y, self._zoom,
            theme.grid_spacing, theme.grid_dot, theme.grid_dot_sub, theme.grid_line,
        )

    def _delayed_initial_grid(self) -> None:
        """首次渲染时延迟绘制网格，确保 canvas 已有实际尺寸。

        如果 canvas 尚未映射（winfo_width < 2），轮询重试直到可用。
        """
        self.update_idletasks()
        if self.winfo_width() < 2:
            self._initial_grid_done = False
            self.after(30, self._delayed_initial_grid)
            return
        self._draw_grid()

    def _auto_layout_if_needed(self, graph: FlowGraph) -> None:
        """如果所有节点位置都是 (0,0)，按执行顺序自动排列"""
        has_custom_pos = not all_nodes_at_origin(
            list(graph.nodes.values()),
            threshold=1,
            exclude_types=(NodeType.START, NodeType.END),
        )
        if has_custom_pos:
            # 仍然给 START/END 设置默认位置
            start = graph.get_node("start")
            end = graph.get_node("end")
            if start and start.pos_x == 0 and start.pos_y == 0:
                start.pos_x = _END_NODE_X
                start.pos_y = _END_NODE_START_Y
            if end and end.pos_x == 0 and end.pos_y == 0:
                max_y = max(
                    (n.pos_y for n in graph.nodes.values()
                     if n.node_id not in ("start", "end")),
                    default=_AUTO_LAYOUT_SPACING_Y,
                )
                end.pos_x = _END_NODE_X
                end.pos_y = max_y + _END_NODE_Y_OFFSET
            return

        # 按执行顺序从上到下排列
        ordered = graph.ordered_nodes()
        for i, node in enumerate(ordered):
            node.pos_x = _AUTO_LAYOUT_START_X
            node.pos_y = _AUTO_LAYOUT_START_Y + i * _AUTO_LAYOUT_SPACING_Y

        # 条件/循环分支横向展开
        for node in ordered:
            if node.node_type in (NodeType.CONDITION, NodeType.LOOP):
                outgoing = graph.get_outgoing_edges(node.node_id)
                for j, edge in enumerate(outgoing):
                    target = graph.get_node(edge.to_node)
                    if target:
                        offset = int((j - len(outgoing) / 2) * _AUTO_LAYOUT_BRANCH_X)
                        self._shift_subtree(graph, target, offset, 0)

    def _shift_subtree(
        self,
        graph: FlowGraph,
        node: FlowNode,
        dx: int,
        depth: int,
        visited: set[str] | None = None,
    ) -> None:
        """递归偏移子树（用于自动布局条件分支）"""
        if depth > 20:
            return
        if visited is None:
            visited = set()
        if node.node_id in visited:
            return
        visited.add(node.node_id)
        node.pos_x += dx
        for edge in graph.get_outgoing_edges(node.node_id):
            target = graph.get_node(edge.to_node)
            if target:
                self._shift_subtree(graph, target, dx, depth + 1, visited)

    # ── 高亮 ──────────────────────────────────────────────

    def _set_selection_ring(self, node_id: str, selected: bool) -> None:
        """设置单个节点的选择环视觉状态"""
        items = self._node_items.get(node_id)
        if not items:
            return
        theme = current_theme()
        if selected:
            glow_color = mix_colors(theme.bg_primary, theme.border_selected, theme.selection_ring_glow_alpha)
            self.itemconfigure(items.selection_ring_glow, outline=glow_color, width=4)
            self.itemconfigure(items.selection_ring, outline=theme.border_selected, width=2)
        else:
            self.itemconfigure(items.selection_ring_glow, outline="", width=4)
            self.itemconfigure(items.selection_ring, outline="", width=2)

    def highlight_node(self, node_id: str | None) -> None:
        """高亮指定节点（执行可视化）+ 活跃边动画"""
        if node_id == self._highlighted_node_id:
            return

        if self._highlighted_node_id and self._highlighted_node_id in self._node_items:
            is_selected = self._highlighted_node_id in self._interaction.get_selected_nodes()
            self._set_selection_ring(self._highlighted_node_id, is_selected)

        self._edge_animator.stop()
        self._highlighted_node_id = node_id

        if node_id and node_id in self._node_items:
            theme = current_theme()
            items = self._node_items[node_id]
            glow_color = mix_colors(theme.bg_primary, theme.status_running, theme.selection_ring_glow_alpha)
            self.itemconfigure(items.selection_ring_glow, outline=glow_color, width=4)
            self.itemconfigure(items.selection_ring, outline=theme.status_running, width=2)
            self.raise_node(node_id)

            if self._graph:
                active_edges = self._get_active_edges(node_id)
                if active_edges:
                    self._edge_animator.start(active_edges, self._edge_style)

    def _get_active_edges(self, node_id: str) -> set[str]:
        """查找连接到指定节点的所有边 ID"""
        if not self._graph:
            return set()
        return {e.edge_id for e in self._graph.get_edges_for_node(node_id)}

    # ── 缩放 ──────────────────────────────────────────────

    def zoom_by(self, factor: float) -> None:
        """以画布中心缩放"""
        cx = self.winfo_width() / 2
        cy = self.winfo_height() / 2
        self._zoom_at(cx, cy, factor)

    def zoom_at(self, screen_x: float, screen_y: float, factor: float) -> None:
        """以指定屏幕坐标为中心缩放"""
        self._zoom_at(screen_x, screen_y, factor)

    def zoom_reset(self) -> None:
        """重置视口"""
        self._offset_x = 0.0
        self._offset_y = 0.0
        self._zoom = 1.0
        if self._graph:
            self.render_graph(self._graph)
        self._event_callback("zoom_changed", zoom=self._zoom)

    def zoom_to_fit(self) -> None:
        """缩放至适配所有节点，10% 边距，居中显示"""
        if not self._graph or not self._graph.nodes:
            return

        min_x, min_y, max_x, max_y = graph_bounds(self._graph)

        if min_x >= max_x or min_y >= max_y:
            return

        canvas_w = self.winfo_width()
        canvas_h = self.winfo_height()
        if canvas_w < 10 or canvas_h < 10:
            return

        world_w = max_x - min_x
        world_h = max_y - min_y
        margin = 0.1

        scale_x = canvas_w / (world_w * (1 + margin))
        scale_y = canvas_h / (world_h * (1 + margin))
        self._zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, min(scale_x, scale_y)))

        center_wx = (min_x + max_x) / 2
        center_wy = (min_y + max_y) / 2

        self._offset_x = center_wx - canvas_w / self._zoom / 2
        self._offset_y = center_wy - canvas_h / self._zoom / 2

        # 直接应用最终状态，避免 animate_to 产生 8 帧冗余动画
        self._apply_zoom_state(self._zoom, self._offset_x, self._offset_y)

    def _incremental_zoom_update(self) -> None:
        """缩放时增量更新节点/边位置（避免 delete+recreate）"""
        if not self._graph:
            return

        self._draw_grid()

        for node_id, items in self._node_items.items():
            node = self._graph.get_node(node_id)
            if node:
                update_node_position(
                    self, items, node, self._offset_x, self._offset_y, self._zoom,
                    theme=current_theme(),
                )

        for edge_id, edge_items in self._edge_items.items():
            edge = self._graph.get_edge(edge_id)
            if edge:
                update_edge(
                    self, edge_items, edge, self._graph,
                    self._offset_x, self._offset_y, self._zoom, self._edge_style,
                )

    def _apply_zoom_state(self, zoom: float, ox: float, oy: float) -> None:
        """ZoomController 回调: 应用插值后的缩放状态"""
        self._zoom = zoom
        self._offset_x = ox
        self._offset_y = oy
        self._edge_animator.set_zoom(zoom)
        if self._graph:
            self._incremental_zoom_update()
            self._refresh_viewport()
        self._event_callback("zoom_changed", zoom=zoom)
        self._minimap.update_viewport()

    def _zoom_at(self, screen_x: float, screen_y: float, factor: float) -> None:
        wx, wy = self.screen_to_world(screen_x, screen_y)

        old_zoom, old_ox, old_oy = self._zoom, self._offset_x, self._offset_y
        target_zoom = max(_ZOOM_MIN, min(_ZOOM_MAX, self._zoom * factor))
        target_ox = wx - screen_x / target_zoom
        target_oy = wy - screen_y / target_zoom

        self._zoom = target_zoom
        self._offset_x = target_ox
        self._offset_y = target_oy

        if self._graph:
            self._zoom_controller.animate_to(
                target_zoom=target_zoom,
                target_ox=target_ox,
                target_oy=target_oy,
                current_zoom=old_zoom,
                current_ox=old_ox,
                current_oy=old_oy,
            )

        self._event_callback("zoom_changed", zoom=self._zoom)
        self._minimap.update_viewport()

    # ── 视口公共接口 ──────────────────────────────────────────

    def get_viewport(self) -> tuple[float, float, float]:
        return self._offset_x, self._offset_y, self._zoom

    def set_viewport(self, offset_x: float, offset_y: float, zoom: float) -> None:
        self._offset_x = offset_x
        self._offset_y = offset_y
        self._zoom = zoom

    def reposition_minimap(self) -> None:
        if hasattr(self, "_minimap"):
            self._minimap.reposition()

    def apply_theme(self) -> None:
        """Apply current theme to canvas subsystems (minimap, etc.)."""
        if hasattr(self, "_minimap"):
            self._minimap.apply_theme()

    def _pan_by(self, dx: float, dy: float) -> None:
        """按屏幕像素偏移平移视口"""
        if dx == 0 and dy == 0:
            return
        self._offset_x -= dx / self._zoom
        self._offset_y -= dy / self._zoom
        # 移动全部画布项（minimap 在独立 Canvas 上不受影响，网格紧随重绘）
        self.move("all", dx, dy)
        self._draw_grid()
        self._minimap.update_viewport()
        self._schedule_viewport_refresh()

    def _refresh_grid(self) -> None:
        """重建网格并更新小地图视口（去抖，避免连续快速操作卡顿）"""
        if self._grid_refresh_id:
            self.after_cancel(self._grid_refresh_id)
        self._grid_refresh_id = self.after(0, self._do_grid_refresh)

    def _do_grid_refresh(self) -> None:
        self._grid_refresh_id = None
        if self._viewport_refresh_id:
            self.after_cancel(self._viewport_refresh_id)
            self._viewport_refresh_id = None
        self._draw_grid()
        self._minimap.update_viewport()
        self._refresh_viewport()

    def _schedule_viewport_refresh(self) -> None:
        """去抖调度视口裁剪刷新"""
        if self._viewport_refresh_id:
            self.after_cancel(self._viewport_refresh_id)
        self._viewport_refresh_id = self.after(50, self._do_viewport_refresh)

    def _do_viewport_refresh(self) -> None:
        self._viewport_refresh_id = None
        self._refresh_viewport()

    def _refresh_viewport(self) -> None:
        """增量视口裁剪: 创建进入视口的节点/边，移除离开的"""
        if not self._graph or not self._graph.nodes:
            return

        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw < 10 or ch < 10:
            return

        entered_nodes, exited_nodes, entered_edges, exited_edges = self._viewport_mgr.update(
            self._graph, self._offset_x, self._offset_y, self._zoom, cw, ch,
        )

        # 移除离开视口的边
        for edge_id in exited_edges:
            self.delete(f"edge:{edge_id}")
            self._edge_items.pop(edge_id, None)

        # 移除离开视口的节点
        for node_id in exited_nodes:
            self.delete(f"node:{node_id}")
            self._node_items.pop(node_id, None)

        # 创建进入视口的边 + 恢复丢失的边（单次遍历）
        visible_edges = self._viewport_mgr.visible_edges
        for edge in self._graph.edges:
            eid = edge.edge_id
            needs_create = eid in entered_edges or (
                eid in visible_edges and eid not in self._edge_items
            )
            if needs_create:
                self._create_edge_visual(edge)

        # 创建进入视口的节点
        for node_id in entered_nodes:
            node = self._graph.get_node(node_id)
            if node:
                self._create_node_visual(node)

        self._ensure_z_order()

    def _on_canvas_configure(self, _event: tk.Event) -> None:
        """Canvas 尺寸变化时防抖重绘网格和小地图。"""
        if self._grid_resize_id:
            self.after_cancel(self._grid_resize_id)
        self._grid_resize_id = self.after(30, self._on_resize_end)

    def _on_resize_end(self) -> None:
        """防抖到期后重绘网格和小地图。"""
        self._grid_resize_id = None
        self._draw_grid()
        self._minimap.schedule_full_redraw()
        if self._viewport_refresh_id:
            self.after_cancel(self._viewport_refresh_id)
        self._viewport_refresh_id = self.after(30, self._do_viewport_refresh)

    def _on_theme_changed(self) -> None:
        """主题切换时更新画布背景和网格颜色。"""
        theme = current_theme()
        self.configure(bg=theme.bg_primary)
        self._draw_grid()

    def destroy_canvas(self) -> None:
        """清理资源：取消定时器、移除主题回调。"""
        self._unregister_theme_callback()
        for timer_id in (self._grid_resize_id, self._grid_refresh_id,
                         self._viewport_refresh_id):
            if timer_id is not None:
                try:
                    self.after_cancel(timer_id)
                except tk.TclError:
                    pass
        self._grid_resize_id = None
        self._grid_refresh_id = None
        self._viewport_refresh_id = None
        self._edge_animator.destroy()
        self._zoom_controller.destroy()
        self._minimap.destroy()
        self._node_tooltip.destroy()

    def navigate_to_center(self, wx: float, wy: float) -> None:
        """将视口中心移动到世界坐标 (wx, wy)"""
        canvas_w = self.winfo_width()
        canvas_h = self.winfo_height()
        target_ox = wx - canvas_w / self._zoom / 2
        target_oy = wy - canvas_h / self._zoom / 2
        dx = (self._offset_x - target_ox) * self._zoom
        dy = (self._offset_y - target_oy) * self._zoom
        self._pan_by(dx, dy)

    # ── 交互分发 ──────────────────────────────────────────

    def _update_selection_rings(self, selected_ids: set[str]) -> None:
        """仅更新选中状态发生变化的节点选择环"""
        changed = selected_ids.symmetric_difference(self._prev_selected)
        for node_id in changed:
            if node_id == self._highlighted_node_id:
                continue
            self._set_selection_ring(node_id, node_id in selected_ids)
        self._prev_selected = set(selected_ids)

    def _ensure_z_order(self) -> None:
        """grid(底) < edge < edge_glow < edge_handle < edge_label_bg < edge_label < nodes(顶)

        tag_lower(X) 将 X 放到堆叠最底，所以按 目标顶部→底部 的顺序调用。
        仅在脏标记为 True 时执行。
        """
        if not self._z_order_dirty:
            return
        self._z_order_dirty = False
        self.tag_lower("edge_label")
        self.tag_lower("edge_label_bg")
        self.tag_lower("edge_handle")
        self.tag_lower("edge_glow")
        self.tag_lower("edge")
        self.tag_lower("grid")

    def _mark_z_order_dirty(self) -> None:
        """标记 z-order 需要刷新。"""
        self._z_order_dirty = True

    def raise_node(self, node_id: str) -> None:
        """将节点提升到同层最上方。"""
        self.tag_raise(f"node:{node_id}")

    def _dispatch_interaction(self, event_type: str, **kwargs):
        """将 InteractionHandler 的事件转换为页面层事件"""
        match event_type:
            case "node_selected":
                self._update_selection_rings({kwargs["node_id"]})
                self._clear_edge_selected_state()
                self._event_callback("node_selected", **kwargs)
            case "nodes_selected":
                self._update_selection_rings(set(kwargs.get("node_ids", [])))
                self._event_callback("nodes_selected", **kwargs)
            case "node_moved":
                snap_fx = kwargs.get("snap_from_x")
                snap_fy = kwargs.get("snap_from_y")
                if snap_fx is not None and snap_fy is not None:
                    self._animate_snap(
                        kwargs["node_id"], snap_fx, snap_fy, kwargs["x"], kwargs["y"],
                    )
                else:
                    self._event_callback("node_moved", **kwargs)
            case "node_dragging":
                self._handle_dragging(kwargs)
            case "node_double_clicked":
                self._event_callback("node_double_clicked", **kwargs)
            case "edge_created":
                self._event_callback("edge_created", **kwargs)
            case "edge_context_menu":
                self._event_callback("edge_context_menu", **kwargs)
            case "edge_selected":
                self._update_selection_rings(set())
                self._set_edge_selected_state(kwargs.get("edge_id"))
                self._event_callback("edge_selected", **kwargs)
            case "edge_deselected":
                self._clear_edge_selected_state(kwargs.get("edge_id"))
            case "delete_edge":
                self._clear_edge_selected_state()
                self._event_callback("delete_edge", **kwargs)
            case "node_context_menu":
                self._event_callback("node_context_menu", **kwargs)
            case "canvas_context_menu":
                self._event_callback("canvas_context_menu", **kwargs)
            case "canvas_deselected":
                self._update_selection_rings(set())
                self._clear_edge_selected_state()
                self._event_callback("canvas_deselected")
            case "zoom_request":
                self.zoom_at(kwargs["screen_x"], kwargs["screen_y"], kwargs["factor"])
            case "pan_request":
                self._pan_by(kwargs["dx"], kwargs["dy"])
            case "pan_ended":
                self._refresh_grid()
            case "delete_selected":
                self._event_callback("delete_selected", **kwargs)
            case "zoom_to_fit":
                self.zoom_to_fit()
            case "zoom_reset":
                self.zoom_reset()
            case "copy_selected":
                self._event_callback("copy_selected", **kwargs)
            case "paste":
                self._event_callback("paste")
            case "duplicate_selected":
                self._event_callback("duplicate_selected", **kwargs)
            case "undo":
                self._event_callback("undo")
            case "redo":
                self._event_callback("redo")
            case "search":
                self._event_callback("search")
            case "escape":
                self._event_callback("escape")
            case "toggle_minimap":
                self._minimap.toggle()
            case "edge_hover":
                self._set_edge_hover_state(kwargs.get("edge_id"))
            case "edge_hover_clear":
                self._clear_edge_hover_state()
            case "edge_reconnected":
                self._clear_edge_hover_state()
                self._clear_edge_selected_state()
                self._event_callback("edge_reconnected", **kwargs)
            case "auto_insert_preview":
                self._set_auto_insert_highlight(kwargs.get("edge_id"))
            case "auto_insert_clear":
                self._clear_auto_insert_highlight()
            case "auto_insert":
                self._event_callback("auto_insert", **kwargs)
            case "drag_started":
                self._node_tooltip.cancel()
                self._apply_drag_shadow_lift(kwargs.get("node_ids", []))
            case "node_hover":
                node_id = kwargs.get("node_id")
                if node_id and self._graph:
                    node = self._graph.get_node(node_id)
                    if node:
                        self._node_tooltip.schedule(
                            node.describe(),
                            kwargs.get("screen_x", 0), kwargs.get("screen_y", 0),
                        )
            case "node_hover_clear":
                self._node_tooltip.cancel()
            case "drag_ended":
                self._clear_drag_shadow_lift(kwargs.get("node_ids", []))
                self._minimap.schedule_full_redraw()

    def _handle_dragging(self, kwargs: dict) -> None:
        """拖拽时增量更新节点位置"""
        node_id = kwargs.get("node_id")
        if not node_id or node_id not in self._node_items:
            return

        node = self._graph.get_node(node_id) if self._graph else None
        if not node:
            return

        new_x = int(kwargs["world_x"])
        new_y = int(kwargs["world_y"])

        # 计算屏幕偏移量
        dx = (new_x - node.pos_x) * self._zoom
        dy = (new_y - node.pos_y) * self._zoom

        # 更新节点的世界坐标
        node.pos_x = new_x
        node.pos_y = new_y

        # 快速路径：用 canvas.move 做像素偏移（无需重算 polygon 坐标）
        if abs(dx) < _FAST_MOVE_THRESHOLD_PX and abs(dy) < _FAST_MOVE_THRESHOLD_PX:
            self.move(f"node:{node_id}", dx, dy)
        else:
            items = self._node_items[node_id]
            update_node_position(
                self, items, node, self._offset_x, self._offset_y, self._zoom,
                theme=current_theme(),
            )

        # 延迟批量更新关联边（节流：after_idle 合并同一帧内的多次 mouse motion）
        self._drag_dirty_nodes.add(node_id)
        if self._drag_edge_flush_id is None:
            self._drag_edge_flush_id = self.after_idle(self._flush_drag_edges)

        # 小地图跟随更新（30ms 去抖，不影响性能）
        self._minimap.schedule_full_redraw(invalidate_bounds=False)

    def _update_edges_for_node(self, node_id: str) -> None:
        """增量更新与指定节点关联的所有边（复用已有 item，缺失时创建）"""
        if not self._graph:
            return

        for edge in self._graph.get_edges_for_node(node_id):
            edge_items = self._edge_items.get(edge.edge_id)
            if edge_items:
                update_edge(
                    self, edge_items, edge, self._graph,
                    self._offset_x, self._offset_y, self._zoom, self._edge_style,
                )
            else:
                new_items = render_edge(
                    self, edge, self._graph,
                    self._offset_x, self._offset_y, self._zoom, self._edge_style,
                )
                if new_items:
                    self._edge_items[edge.edge_id] = new_items

    def _flush_drag_edges(self) -> None:
        """批量更新拖拽中脏节点的关联边（after_idle 回调）"""
        self._drag_edge_flush_id = None
        dirty = self._drag_dirty_nodes.copy()
        self._drag_dirty_nodes.clear()
        for node_id in dirty:
            self._update_edges_for_node(node_id)

    def _apply_drag_shadow_lift(self, node_ids: list[str]) -> None:
        """拖拽时增强节点阴影（视觉抬起效果）"""
        theme = current_theme()
        lift_color = mix_colors(theme.bg_primary, theme.shadow_color, theme.drag_shadow_lift_alpha)
        for nid in node_ids:
            items = self._node_items.get(nid)
            if items and items.shadow:
                self.itemconfigure(items.shadow, fill=lift_color)
            if items and items.shadow_outer:
                self.itemconfigure(items.shadow_outer, fill=lift_color)

    def _clear_drag_shadow_lift(self, node_ids: list[str]) -> None:
        """拖拽结束后恢复节点阴影"""
        theme = current_theme()
        outer_color = mix_colors(theme.bg_primary, theme.shadow_color, theme.shadow_outer_alpha)
        inner_color = mix_colors(theme.bg_primary, theme.shadow_color, theme.shadow_inner_alpha)
        for nid in node_ids:
            items = self._node_items.get(nid)
            if not items:
                continue
            if items.shadow:
                self.itemconfigure(items.shadow, fill=inner_color)
            if items.shadow_outer:
                self.itemconfigure(items.shadow_outer, fill=outer_color)

    def _animate_snap(
        self, node_id: str, from_x: int, from_y: int, to_x: int, to_y: int,
    ) -> None:
        """平滑吸附动画: 从 from_xy 过渡到 to_xy（纯屏幕空间，不修改模型）"""
        from src.core.easing import ease_out_quad

        theme = current_theme()
        total_frames = theme.snap_anim_frames
        interval = theme.snap_anim_interval_ms

        node = self._graph.get_node(node_id) if self._graph else None
        if not node:
            self._event_callback("node_moved", node_id=node_id, x=to_x, y=to_y)
            return

        # 当前模型位置 → 未吸附位置的屏幕偏移
        offset_to_from_dx = (from_x - node.pos_x) * self._zoom
        offset_to_from_dy = (from_y - node.pos_y) * self._zoom
        self.move(f"node:{node_id}", offset_to_from_dx, offset_to_from_dy)
        self._update_edges_for_node(node_id)

        # from → to 的屏幕总偏移
        snap_dx = (to_x - from_x) * self._zoom
        snap_dy = (to_y - from_y) * self._zoom
        prev_t = 0.0

        def _tick() -> None:
            nonlocal prev_t
            if prev_t >= 1.0:
                # 最终帧：还原初始偏移，让外部回调统一设置模型
                self.move(f"node:{node_id}", -offset_to_from_dx, -offset_to_from_dy)
                self._event_callback("node_moved", node_id=node_id, x=to_x, y=to_y)
                self._minimap.schedule_full_redraw(invalidate_bounds=False)
                return
            t = ease_out_quad(min(prev_t + 1.0 / total_frames, 1.0))
            dx = snap_dx * (t - prev_t)
            dy = snap_dy * (t - prev_t)
            prev_t = t
            self.move(f"node:{node_id}", dx, dy)
            self._update_edges_for_node(node_id)
            self.after(interval, _tick)

        self.after(interval, _tick)

    def refresh_edge_visual(self, edge_id: str) -> None:
        """重建单条边的视觉元素（标签/颜色变更后调用）。"""
        if not self._graph:
            return
        edge = self._graph.get_edge(edge_id)
        if not edge:
            return
        self.delete(f"edge:{edge_id}")
        self._edge_items.pop(edge_id, None)
        new_items = render_edge(
            self, edge, self._graph,
            self._offset_x, self._offset_y, self._zoom, self._edge_style,
        )
        if new_items:
            self._edge_items[edge_id] = new_items
        self._ensure_z_order()

    @staticmethod
    def _set_handle_colors(
        canvas: tk.Canvas, items: EdgeCanvasItems,
        src_fill: str, src_outline: str,
        tgt_fill: str, tgt_outline: str,
    ) -> None:
        """更新边端点手柄颜色"""
        if items.source_handle:
            try:
                canvas.itemconfigure(
                    items.source_handle, fill=src_fill, outline=src_outline,
                )
            except tk.TclError:
                pass
        if items.target_handle:
            try:
                canvas.itemconfigure(
                    items.target_handle, fill=tgt_fill, outline=tgt_outline,
                )
            except tk.TclError:
                pass

    def _set_edge_hover_state(self, edge_id: str | None) -> None:
        """设置边悬停效果"""
        if edge_id == self._hovered_edge_id:
            return

        # 清除旧悬停
        self._clear_edge_hover_state()

        if not edge_id or not self._graph:
            return

        edge_items = self._edge_items.get(edge_id)
        edge = self._graph.get_edge(edge_id)
        if not edge or not edge_items:
            return

        self._hovered_edge_id = edge_id
        set_edge_hover(
            self, edge_items, edge, self._graph,
            self._offset_x, self._offset_y, self._zoom, self._edge_style,
        )
        theme = current_theme()
        self._set_handle_colors(
            self, edge_items,
            src_fill=theme.accent_green, src_outline=theme.accent_green,
            tgt_fill=theme.accent_orange, tgt_outline=theme.accent_orange,
        )

    def _clear_edge_hover_state(self) -> None:
        """清除边悬停效果"""
        if self._hovered_edge_id:
            items = self._edge_items.get(self._hovered_edge_id)
            if items:
                clear_edge_hover(self, items, self._zoom)
                theme = current_theme()
                self._set_handle_colors(
                    self, items,
                    src_fill=theme.edge_source_handle,
                    src_outline=theme.edge_target_handle,
                    tgt_fill=theme.edge_target_handle,
                    tgt_outline=theme.edge_source_handle,
                )
            self._hovered_edge_id = None

    def _set_edge_selected_state(self, edge_id: str | None) -> None:
        """设置边选中视觉效果"""
        self._clear_edge_selected_state()
        if not edge_id or not self._graph:
            return
        edge = self._graph.get_edge(edge_id)
        edge_items = self._edge_items.get(edge_id)
        if not edge or not edge_items:
            return
        set_edge_selected(
            self, edge_items, edge, self._graph,
            self._offset_x, self._offset_y, self._zoom, self._edge_style,
        )
        theme = current_theme()
        self._set_handle_colors(
            self, edge_items,
            src_fill=theme.accent_green, src_outline=theme.accent_green,
            tgt_fill=theme.accent_orange, tgt_outline=theme.accent_orange,
        )

    def _clear_edge_selected_state(self, edge_id: str | None = None) -> None:
        """清除边选中视觉效果"""
        if not edge_id:
            edge_id = self._interaction.get_selected_edge()
        if not edge_id or not self._graph:
            return
        edge = self._graph.get_edge(edge_id)
        edge_items = self._edge_items.get(edge_id)
        if edge and edge_items:
            clear_edge_selected(self, edge_items, edge, self._zoom)
            theme = current_theme()
            self._set_handle_colors(
                self, edge_items,
                src_fill=theme.edge_source_handle,
                src_outline=theme.edge_target_handle,
                tgt_fill=theme.edge_target_handle,
                tgt_outline=theme.edge_source_handle,
            )

    # ── 自动插入高亮 ──────────────────────────────────────

    def _set_auto_insert_highlight(self, edge_id: str | None) -> None:
        """自动插入预览时高亮目标边"""
        self._clear_auto_insert_highlight()
        if not edge_id or not self._graph:
            return
        edge_items = self._edge_items.get(edge_id)
        edge = self._graph.get_edge(edge_id)
        if not edge or not edge_items:
            return
        self._auto_insert_edge_id = edge_id
        theme = current_theme()
        try:
            self.itemconfigure(
                edge_items.line,
                width=max(4, 5 * self._zoom),
                dash=(8, 4),
            )
            for gid in edge_items.glow_layers:
                endpoints_data = _edge_endpoints(
                    edge, self._graph, self._offset_x, self._offset_y, self._zoom
                )
                if endpoints_data:
                    pts = _compute_line_points(*endpoints_data, self._zoom, self._edge_style)
                    self.coords(gid, *pts)
                    self.itemconfigure(
                        gid, state="normal",
                        fill=theme.accent_blue, width=max(8, 10 * self._zoom),
                    )
        except tk.TclError:
            pass

    def _clear_auto_insert_highlight(self) -> None:
        """清除自动插入高亮

        复用 clear_edge_hover: 它恢复默认 width + dash=()，
        正好覆盖 auto-insert 设置的 dash=(8,4) + 加粗效果。
        """
        aid = self._auto_insert_edge_id
        if not aid:
            return
        edge_items = self._edge_items.get(aid)
        if edge_items:
            clear_edge_hover(self, edge_items, self._zoom)
        self._auto_insert_edge_id = None
