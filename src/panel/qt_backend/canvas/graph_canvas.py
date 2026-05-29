"""QtGraphCanvas — PySide6 DAG workflow editor canvas.

替代 tkinter GraphCanvas，使用 QGraphicsScene/QGraphicsView。
内置视口剔除、坐标变换、Z 排序，消除 ~800 行手动代码。
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QTransform, QWheelEvent
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from PySide6.QtGui import QMouseEvent, QKeyEvent

from src.core.flow import FlowEdge, FlowGraph, FlowNode
from src.panel.canvas.auto_layout import apply_bfs_positions
from src.panel.models.enums import NodeExecutionState
from src.panel.canvas.theme import ThemeCallbackMixin, current_theme, on_theme_change, remove_theme_change
from src.panel.qt_backend.canvas.minimap import QtMinimap
from src.panel.qt_backend.canvas.floating_controls import QtFloatingControls

if TYPE_CHECKING:
    from src.panel.qt_backend.canvas.node_item import QtNodeItem
    from src.panel.qt_backend.canvas.edge_item import QtEdgeItem

_MIN_ZOOM = 0.1
_MAX_ZOOM = 5.0


class QtGraphCanvas(ThemeCallbackMixin, QGraphicsView):
    """QGraphicsView-based DAG canvas.

    Architecture:
    - QGraphicsScene holds all node/edge items
    - QGraphicsView provides viewport transforms (zoom/pan)
    - Built-in frustum culling replaces manual ViewportManager
    - drawBackground() replaces GridRenderer object pool
    - Item Z-values replace manual tag_lower/raise
    """

    def __init__(self, event_callback: Callable[..., None], parent=None) -> None:
        super().__init__(parent)

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-5000, -5000, 10000, 10000)
        self.setScene(self._scene)

        self.setRenderHints(
            self.renderHints()
            | QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.SmoothPixmapTransform,
        )
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.MinimalViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setInteractive(True)

        self._cached_theme = current_theme()
        self.setStyleSheet(f"background-color: {self._cached_theme.bg_primary}; border: none;")

        self._event_callback = event_callback
        self._graph: FlowGraph | None = None
        self._edge_style: str = "bezier"

        self._node_items: dict[str, QtNodeItem] = {}
        self._edge_items: dict[str, QtEdgeItem] = {}

        self._highlighted_node_id: str | None = None
        self._nodes_with_state: set[str] = set()
        self._prev_selected: set[str] = set()

        self._hovered_edge_id: str | None = None
        self._selected_edge_id: str | None = None
        self._auto_insert_edge_id: str | None = None

        self._edge_animator_timer: QTimer | None = None
        self._execution_state: str = "idle"  # idle | running | paused

        self._graph_version: int = 0
        self._last_rendered_version: int = -1
        self._destroyed = False

        self._init_theme_guard(self._on_theme_changed, RuntimeError)

        from src.panel.qt_backend.canvas.interaction_handler import QtInteractionHandler
        self._interaction = QtInteractionHandler(
            self, lambda: self._graph, self._dispatch_interaction,
        )
        self._interaction.install()

        self._minimap: QtMinimap | None = None
        self._floating_controls: QtFloatingControls | None = None

        self._last_right_click_time: float = 0.0
        self._temp_edge: QGraphicsPathItem | None = None

    @property
    def scene(self) -> QGraphicsScene:
        return self._scene

    @property
    def graph(self) -> FlowGraph | None:
        return self._graph

    @property
    def edge_style(self) -> str:
        return self._edge_style

    def zoom(self) -> float:
        return self.transform().m11()

    def offset(self) -> tuple[float, float]:
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        return rect.x(), rect.y()

    def init_overlays(self) -> None:
        """Create minimap and floating controls. Call after widget is shown."""
        if not self._floating_controls:
            self._floating_controls = QtFloatingControls(self, self)
            self._floating_controls.show()
        if not self._minimap:
            self._minimap = QtMinimap(self, self)
            # 连接拖拽手柄和齿轮按钮事件
            mm = self._minimap
            mm._drag_handle.mousePressEvent = mm.handle_mouse_press
            mm._drag_handle.mouseMoveEvent = mm.handle_mouse_move
            mm._drag_handle.mouseReleaseEvent = mm.handle_mouse_release
            mm._gear_btn.mousePressEvent = lambda e: mm._toggle_settings()
            self._minimap.show()
        self._reposition_overlays()

    def _reposition_overlays(self) -> None:
        w, h = self.viewport().width(), self.viewport().height()
        if self._floating_controls:
            self._floating_controls.reposition(w, h)
        if self._minimap:
            self._minimap.reposition_on_resize(w, h)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._reposition_overlays()

    # ── Graph lifecycle ────────────────────────────────────

    def render_graph(self, graph: FlowGraph) -> None:
        self._graph = graph
        self._graph_version += 1
        self._auto_layout_if_needed(graph)
        self._incremental_update(graph)
        if self._execution_state == "running":
            self._start_edge_animation()
        else:
            self._stop_edge_animation()
        if self._minimap:
            self._minimap.fit_to_bounds()

    def clear_graph(self) -> None:
        self._stop_edge_animation()
        if self._minimap:
            self._minimap.setVisible(False)
        if self._temp_edge:
            self._temp_edge.prepareGeometryChange()
            self._scene.removeItem(self._temp_edge)
            self._temp_edge = None
        self._scene.clear()
        self._node_items.clear()
        self._edge_items.clear()
        self._nodes_with_state.clear()
        self._prev_selected.clear()
        self._highlighted_node_id = None
        self._graph = None

    def set_edge_style(self, style: str) -> None:
        self._edge_style = style
        for edge_item in self._edge_items.values():
            edge_item.update_style(style)
        self._scene.update()

    # ── Incremental rendering ──────────────────────────────

    def _incremental_update(self, graph: FlowGraph) -> None:
        if self._graph_version == self._last_rendered_version:
            return
        self._last_rendered_version = self._graph_version

        from src.panel.qt_backend.canvas.node_item import QtNodeItem
        from src.panel.qt_backend.canvas.edge_item import QtEdgeItem

        current_node_ids = {n.node_id for n in graph.nodes.values()} if graph.nodes else set()
        current_edge_ids = {e.edge_id for e in graph.edges} if graph.edges else set()

        removed_nodes = set(self._node_items.keys()) - current_node_ids
        removed_edges = set(self._edge_items.keys()) - current_edge_ids

        for nid in removed_nodes:
            item = self._node_items.pop(nid, None)
            if item:
                item.prepareGeometryChange()
                self._scene.removeItem(item)

        for eid in removed_edges:
            item = self._edge_items.pop(eid, None)
            if item:
                item.prepareGeometryChange()
                self._scene.removeItem(item)

        if graph.nodes:
            for node in graph.nodes.values():
                if node.node_id in self._node_items:
                    self._update_node_visual(node)
                else:
                    self._add_node_visual(node)

        if graph.edges:
            for edge in graph.edges:
                if edge.edge_id in self._edge_items:
                    self._update_edge_visual(edge)
                else:
                    self._add_edge_visual(edge)

    def _add_node_visual(self, node: FlowNode) -> None:
        from src.panel.qt_backend.canvas.node_item import QtNodeItem
        item = QtNodeItem(node, self)
        item.setZValue(0)
        self._scene.addItem(item)
        self._node_items[node.node_id] = item

    def _update_node_visual(self, node: FlowNode) -> None:
        item = self._node_items.get(node.node_id)
        if item:
            item.update_from_node(node)

    def _remove_node_visual(self, node_id: str) -> None:
        item = self._node_items.pop(node_id, None)
        if item:
            item.prepareGeometryChange()
            self._scene.removeItem(item)

    def _add_edge_visual(self, edge: FlowEdge) -> None:
        from src.panel.qt_backend.canvas.edge_item import QtEdgeItem
        if not self._graph:
            return
        item = QtEdgeItem(edge, self._graph, self._edge_style, self)
        self._scene.addItem(item)
        item.setZValue(-1)
        self._edge_items[edge.edge_id] = item

    def _update_edge_visual(self, edge: FlowEdge) -> None:
        item = self._edge_items.get(edge.edge_id)
        if item and self._graph:
            item.update_from_edge(edge, self._graph)

    def _remove_edge_visual(self, edge_id: str) -> None:
        item = self._edge_items.pop(edge_id, None)
        if item:
            item.prepareGeometryChange()
            self._scene.removeItem(item)

    # ── 公共增量视觉操作 ──────────────────────────────────────

    def add_node_visual(self, node: FlowNode) -> None:
        self._add_node_visual(node)

    def remove_node_visual(self, node_id: str) -> None:
        self._remove_node_visual(node_id)
        if self._graph:
            for edge in self._graph.get_edges_for_node(node_id):
                self._remove_edge_visual(edge.edge_id)

    def add_edge_visual(self, edge: FlowEdge) -> None:
        self._add_edge_visual(edge)

    def remove_edge_visual(self, edge_id: str) -> None:
        self._remove_edge_visual(edge_id)

    def update_node_visual(self, node_id: str) -> None:
        if self._graph:
            node = self._graph.get_node(node_id)
            if node:
                self._update_node_visual(node)
                self._update_edges_for_node(node_id)

    def refresh_edge_visual(self, edge_id: str) -> None:
        if self._graph:
            edge = self._graph.get_edge(edge_id)
            if edge:
                self._update_edge_visual(edge)

    def _update_z_order(self) -> None:
        for edge_item in self._edge_items.values():
            edge_item.setZValue(-1)
        for node_item in self._node_items.values():
            node_item.setZValue(0)

    # ── Auto layout ────────────────────────────────────────

    def _auto_layout_if_needed(self, graph: FlowGraph) -> None:
        apply_bfs_positions(graph)

    # ── Zoom ───────────────────────────────────────────────

    def zoom_by(self, factor: float) -> None:
        z = self.zoom()
        new_z = max(_MIN_ZOOM, min(_MAX_ZOOM, z * factor))
        if abs(new_z - z) < 0.001:
            return
        center = self.mapToScene(self.viewport().rect().center())
        self._apply_zoom(new_z, center)

    def zoom_at(self, screen_x: float, screen_y: float, factor: float) -> None:
        z = self.zoom()
        new_z = max(_MIN_ZOOM, min(_MAX_ZOOM, z * factor))
        if abs(new_z - z) < 0.001:
            return
        anchor = self.mapToScene(int(screen_x), int(screen_y))
        self._apply_zoom(new_z, anchor)

    def zoom_reset(self) -> None:
        self._apply_zoom(1.0, self.mapToScene(self.viewport().rect().center()))

    def zoom_to_fit(self) -> None:
        if not self._node_items:
            return
        bounds = self._nodes_bounds()
        if bounds.isEmpty():
            return
        view_rect = self.viewport().rect()
        margin = 80
        sx = (view_rect.width() - margin * 2) / bounds.width()
        sy = (view_rect.height() - margin * 2) / bounds.height()
        new_z = max(_MIN_ZOOM, min(_MAX_ZOOM, sx, sy))
        center = bounds.center()
        self._apply_zoom(new_z, center)

    def _apply_zoom(self, zoom: float, center: QPointF) -> None:
        target = center

        t = QTransform()
        t.scale(zoom, zoom)
        self.setTransform(t)

        view_center = self.mapToScene(self.viewport().rect().center())
        dx = view_center.x() - target.x()
        dy = view_center.y() - target.y()
        self.translate(dx, dy)

        self.viewport().update()
        if self._floating_controls:
            self._floating_controls.update_zoom_display()
        if self._minimap:
            self._minimap.update_viewport()

    def _nodes_bounds(self) -> QRectF:
        return self._scene.itemsBoundingRect()

    # ── Wheel zoom ─────────────────────────────────────────

    def wheelEvent(self, event: QWheelEvent) -> None:
        if time.monotonic() - self._last_right_click_time < 0.3:
            event.accept()
            return
        delta = event.angleDelta().y()
        if abs(delta) < 8:
            event.accept()
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        pos = event.position()
        self.zoom_at(pos.x(), pos.y(), factor)
        event.accept()

    # ── Pan ────────────────────────────────────────────────

    def pan_by(self, dx: float, dy: float) -> None:
        self.horizontalScrollBar().setValue(
            self.horizontalScrollBar().value() - int(dx)
        )
        self.verticalScrollBar().setValue(
            self.verticalScrollBar().value() - int(dy)
        )
        self.viewport().update()

    def navigate_to_center(self, wx: float, wy: float) -> None:
        self._apply_zoom(self.zoom(), QPointF(wx, wy))
        self.viewport().update()

    # ── Node state (execution visualization) ───────────────

    def highlight_node(self, node_id: str | None) -> None:
        if self._highlighted_node_id == node_id:
            return
        old_id = self._highlighted_node_id
        self._highlighted_node_id = node_id
        if old_id:
            old_item = self._node_items.get(old_id)
            if old_item:
                old_item.set_execution_state(None)
        if node_id:
            new_item = self._node_items.get(node_id)
            if new_item:
                new_item.set_execution_state(NodeExecutionState.RUNNING)

    def set_node_state(self, node_id: str, state: str) -> None:
        self._nodes_with_state.add(node_id)
        item = self._node_items.get(node_id)
        if item:
            item.set_execution_state(state)

    def clear_node_states(self) -> None:
        for nid in self._nodes_with_state:
            item = self._node_items.get(nid)
            if item:
                item.set_execution_state(None)
        self._nodes_with_state.clear()
        self._highlighted_node_id = None

    def update_selection_rings(self, selected_ids: set[str]) -> None:
        changed = selected_ids.symmetric_difference(self._prev_selected)
        for node_id in changed:
            item = self._node_items.get(node_id)
            if item:
                item.set_selected_visual(node_id in selected_ids)
        self._prev_selected = set(selected_ids)

    # ── Background (grid) ──────────────────────────────────

    def drawBackground(self, painter, rect: QRectF) -> None:
        th = self._cached_theme
        painter.fillRect(rect, th.bg_primary)
        self._draw_grid(painter, rect, th)

    def _draw_grid(self, painter, rect: QRectF, th) -> None:
        zoom = self.transform().m11()
        spacing = 25.0
        if zoom < 0.3:
            spacing = 100.0
        elif zoom < 0.6:
            spacing = 50.0

        left = rect.left()
        top = rect.top()
        right = rect.right()
        bottom = rect.bottom()

        start_x = int(left / spacing) * spacing
        start_y = int(top / spacing) * spacing

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(th.border_default)

        radius = max(1.0, 1.5 * min(zoom, 1.0))
        path = QPainterPath()
        x = start_x
        while x <= right:
            y = start_y
            while y <= bottom:
                path.addEllipse(QPointF(x, y), radius, radius)
                y += spacing
            x += spacing
        painter.drawPath(path)

    # ── Edge visual states ─────────────────────────────────

    def _update_edge_state(
        self, attr: str, edge_id: str | None, setter: str,
    ) -> None:
        old = getattr(self, attr)
        if old == edge_id:
            return
        if old:
            item = self._edge_items.get(old)
            if item:
                getattr(item, setter)(False)
        setattr(self, attr, edge_id)
        if edge_id:
            item = self._edge_items.get(edge_id)
            if item:
                getattr(item, setter)(True)

    def set_edge_hover(self, edge_id: str | None) -> None:
        self._update_edge_state("_hovered_edge_id", edge_id, "set_hover")

    def set_edge_selected(self, edge_id: str | None) -> None:
        self._update_edge_state("_selected_edge_id", edge_id, "set_selected")

    def set_auto_insert_highlight(self, edge_id: str | None) -> None:
        self._update_edge_state("_auto_insert_edge_id", edge_id, "set_auto_insert")

    def clear_edge_states(self) -> None:
        for eid in (self._hovered_edge_id,
                    self._selected_edge_id,
                    self._auto_insert_edge_id):
            if eid:
                item = self._edge_items.get(eid)
                if item:
                    item.set_hover(False)
                    item.set_selected(False)
                    item.set_auto_insert(False)
        self._hovered_edge_id = None
        self._selected_edge_id = None
        self._auto_insert_edge_id = None

    # ── Node position updates (drag) ───────────────────────

    def update_node_position(self, node_id: str) -> None:
        item = self._node_items.get(node_id)
        if item and self._graph:
            node = self._graph.get_node(node_id)
            if node:
                item.setPos(node.pos_x, node.pos_y)
                self._update_edges_for_node(node_id)

    def _update_edges_for_node(self, node_id: str) -> None:
        if not self._graph:
            return
        for edge in self._graph.get_edges_for_node(node_id):
            item = self._edge_items.get(edge.edge_id)
            if item:
                item.update_from_edge(edge, self._graph)

    def recreate_edges_for_node(self, node_id: str) -> None:
        if not self._graph:
            return
        for edge in self._graph.get_edges_for_node(node_id):
            self._remove_edge_visual(edge.edge_id)
            self._add_edge_visual(edge)
        self._update_z_order()

    # ── Viewport / minimap helpers ─────────────────────────

    def get_viewport(self) -> tuple[float, float, float]:
        z = self.zoom()
        rect = self.mapToScene(self.viewport().rect()).boundingRect()
        return rect.x(), rect.y(), z

    def set_viewport(self, offset_x: float, offset_y: float, zoom: float) -> None:
        t = QTransform()
        t.scale(zoom, zoom)
        self.setTransform(t)
        view_center = self.mapToScene(self.viewport().rect().center())
        dx = view_center.x() - (offset_x + self.viewport().width() / zoom / 2)
        dy = view_center.y() - (offset_y + self.viewport().height() / zoom / 2)
        self.translate(dx, dy)
        self.viewport().update()

    def get_node_item(self, node_id: str) -> QtNodeItem | None:
        return self._node_items.get(node_id)

    def get_edge_item(self, edge_id: str) -> QtEdgeItem | None:
        return self._edge_items.get(edge_id)

    # ── Event dispatch (compat layer) ──────────────────────

    def dispatch_event(self, event_type: str, **kwargs) -> None:
        self._event_callback(event_type, **kwargs)

    # ── Theme ──────────────────────────────────────────────

    def _on_theme_changed(self) -> None:
        self._cached_theme = current_theme()
        th = self._cached_theme
        self.setStyleSheet(f"background-color: {th.bg_primary}; border: none;")
        for item in self._node_items.values():
            item.apply_theme()
        for item in self._edge_items.values():
            item.apply_theme()
        if self._minimap:
            self._minimap.apply_theme()
        if self._floating_controls:
            self._floating_controls.apply_theme()
        self.viewport().update()

    # ── Cleanup ────────────────────────────────────────────

    def destroy_canvas(self) -> None:
        self._destroyed = True
        self._unregister_theme_callback()
        self._stop_edge_animation()
        self.clear_graph()

    # ── Temp edge (connection preview) ───────────────────────

    def _draw_temp_edge(self, from_x: float, from_y: float, to_x: float, to_y: float) -> None:
        from PySide6.QtWidgets import QGraphicsPathItem
        if self._temp_edge is None:
            self._temp_edge = QGraphicsPathItem()
            self._temp_edge.setZValue(100)
            pen = QPen(QColor(self._cached_theme.accent_blue), 2, Qt.PenStyle.DashLine)
            self._temp_edge.setPen(pen)
            self._scene.addItem(self._temp_edge)
        path = QPainterPath(QPointF(from_x, from_y))
        dx = to_x - from_x
        dy = to_y - from_y
        dist = (dx * dx + dy * dy) ** 0.5
        if dist < 1:
            path.lineTo(to_x, to_y)
        else:
            ctrl_offset = max(25, dist * 0.35)
            path.cubicTo(
                QPointF(from_x, from_y + ctrl_offset),
                QPointF(to_x, to_y - ctrl_offset),
                QPointF(to_x, to_y),
            )
        self._temp_edge.setPath(path)

    def _clear_temp_edge(self) -> None:
        if self._temp_edge:
            self._temp_edge.prepareGeometryChange()
            self._scene.removeItem(self._temp_edge)
            self._temp_edge = None

    # ── Edge animation (simple timer-based) ────────────────

    def set_execution_state(self, state) -> None:
        """Set canvas execution state (ExecutorState or str: 'idle'|'running'|'paused')."""
        self._execution_state = state
        if state == "running":
            self._start_edge_animation()
            for item in self._edge_items.values():
                item.set_paused_visual(False)
        else:
            self._stop_edge_animation()
            is_paused = state == "paused"
            for item in self._edge_items.values():
                item.set_animating(False)
                item.set_paused_visual(is_paused)

    def _start_edge_animation(self) -> None:
        self._stop_edge_animation()
        self._edge_animator_timer = QTimer(self)
        self._edge_animator_timer.timeout.connect(self._tick_edge_animation)
        self._edge_animator_timer.start(50)

    def _stop_edge_animation(self) -> None:
        if self._edge_animator_timer:
            self._edge_animator_timer.stop()
            self._edge_animator_timer = None

    def _tick_edge_animation(self) -> None:
        if self._destroyed or not self._edge_items:
            return
        try:
            if self._highlighted_node_id and self._graph:
                active_edges = self._graph.get_edges_for_node(self._highlighted_node_id)
                active_ids = {e.edge_id for e in active_edges}
                for eid, item in list(self._edge_items.items()):
                    if eid not in self._edge_items:
                        continue
                    is_active = eid in active_ids
                    item.set_animating(is_active)
                    if is_active:
                        item.advance_animation()
            else:
                for item in list(self._edge_items.values()):
                    item.set_animating(False)
            self._scene.update()
        except RuntimeError:
            self._stop_edge_animation()

    # ── Qt event overrides (forward to interaction handler) ─

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            self._last_right_click_time = time.monotonic()
        self._interaction.handle_mouse_press(event)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._interaction.handle_mouse_move(event)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._interaction.handle_mouse_release(event)
        event.accept()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._interaction.handle_double_click(event)
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        self._interaction.handle_key_press(event)

    def _dispatch_interaction(self, event_type: str, **kwargs) -> None:
        match event_type:
            case "node_selected":
                self.update_selection_rings({kwargs["node_id"]})
                self.clear_edge_states()
                self._event_callback("node_selected", **kwargs)
            case "nodes_selected":
                self.update_selection_rings(set(kwargs.get("node_ids", [])))
                self._event_callback("nodes_selected", **kwargs)
            case "node_dragging":
                node_id = kwargs["node_id"]
                wx, wy = int(kwargs["world_x"]), int(kwargs["world_y"])
                item = self._node_items.get(node_id)
                if item:
                    item.setPos(wx, wy)
                    item.node.pos_x = wx
                    item.node.pos_y = wy
                    self._update_edges_for_node(node_id)
            case "edge_selected":
                self.set_edge_selected(kwargs.get("edge_id"))
                self._event_callback("edge_selected", **kwargs)
            case "canvas_deselected":
                self.update_selection_rings(set())
                self.clear_edge_states()
                self._event_callback("canvas_deselected")
            case "toggle_minimap":
                if hasattr(self, '_minimap') and self._minimap:
                    self._minimap.toggle()
            case "temp_edge":
                self._draw_temp_edge(**kwargs)
            case "temp_edge_clear":
                self._clear_temp_edge()
            case "auto_insert_preview":
                self.set_auto_insert_highlight(kwargs.get("edge_id"))
            case "auto_insert_clear":
                self.set_auto_insert_highlight(None)
            case "auto_insert":
                self._clear_temp_edge()
                self.set_auto_insert_highlight(None)
                self._event_callback("auto_insert", **kwargs)
            case _:
                self._event_callback(event_type, **kwargs)
