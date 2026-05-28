"""QtInteractionHandler — PySide6 canvas interaction.

替代 tkinter InteractionHandler 全局 FSM。
Qt 简化: Item 自处理事件，scene.itemAt() 替代手动 hit-test。
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QMouseEvent, QKeyEvent
from PySide6.QtWidgets import QGraphicsItem

from src.core.flow import FlowGraph
from src.panel.models.enums import EdgeLabel
from src.panel.canvas.node_shared import PORT_HIT_RADIUS, PORT_IN, port_positions
from src.panel.qt_backend.canvas.node_item import QtNodeItem
from src.panel.qt_backend.canvas.edge_item import QtEdgeItem

if TYPE_CHECKING:
    from src.panel.qt_backend.canvas.graph_canvas import QtGraphCanvas

_SNAP_GRID = 10
_AUTO_INSERT_DIST = 40


def _snap(x: float, grid: int = _SNAP_GRID) -> float:
    return round(x / grid) * grid


def _point_to_segment_dist(
    px: float, py: float, x1: float, y1: float, x2: float, y2: float,
) -> float:
    dx, dy = x2 - x1, y2 - y1
    len_sq = dx * dx + dy * dy
    if len_sq < 0.001:
        return ((px - x1) ** 2 + (py - y1) ** 2) ** 0.5
    t = max(0, min(1, ((px - x1) * dx + (py - y1) * dy) / len_sq))
    proj_x, proj_y = x1 + t * dx, y1 + t * dy
    return ((px - proj_x) ** 2 + (py - proj_y) ** 2) ** 0.5


class _Mode(Enum):
    IDLE = auto()
    DRAGGING = auto()
    CONNECTING = auto()
    SELECTING = auto()
    PANNING = auto()


class QtInteractionHandler:
    """Handles mouse/keyboard interaction for QtGraphCanvas.

    Dispatches events through the canvas event_callback to the page layer.
    """

    def __init__(
        self,
        canvas: QtGraphCanvas,
        get_graph: Callable[[], FlowGraph | None],
        event_callback: Callable[..., None],
    ) -> None:
        self._canvas = canvas
        self._get_graph = get_graph
        self._callback = event_callback
        self._mode = _Mode.IDLE

        self._selected_node_ids: set[str] = set()
        self._selected_edge_id: str | None = None

        self._drag_node_id: str | None = None
        self._drag_start_scene: QPointF = QPointF()
        self._drag_node_start_pos: tuple[float, float] = (0, 0)
        self._multi_drag_offsets: dict[str, tuple[float, float]] = {}

        self._pan_last_pos: QPointF = QPointF()

        self._select_start: QPointF = QPointF()
        self._select_additive: bool = False

        self._connect_from_node: str | None = None
        self._connect_from_port: str | None = None
        self._connect_from_pos: tuple[float, float] = (0, 0)

        self._snap_to_grid: bool = True

        self._can_auto_insert: bool = False
        self._auto_insert_candidate: str | None = None

    def install(self) -> None:
        self._canvas.setMouseTracking(True)
        self._canvas.viewport().installEventFilter(self._canvas)

    def get_selected_edge(self) -> str | None:
        return self._selected_edge_id

    # ── Mouse events (called from QGraphicsView event overrides) ──

    def handle_mouse_press(self, event: QMouseEvent) -> None:
        scene_pos = self._canvas.mapToScene(event.pos())
        button = event.button()

        if button == Qt.MouseButton.LeftButton:
            self._on_left_press(scene_pos, event)
        elif button == Qt.MouseButton.MiddleButton:
            self._start_pan(scene_pos)
        elif button == Qt.MouseButton.RightButton:
            self._on_right_click(scene_pos, event)

    def handle_mouse_move(self, event: QMouseEvent) -> None:
        scene_pos = self._canvas.mapToScene(event.pos())

        match self._mode:
            case _Mode.DRAGGING:
                self._do_drag(scene_pos)
            case _Mode.CONNECTING:
                self._do_connect_move(scene_pos)
            case _Mode.PANNING:
                self._do_pan(scene_pos)
            case _Mode.SELECTING:
                self._do_select(scene_pos)
            case _Mode.IDLE:
                self._update_hover(scene_pos)

    def handle_mouse_release(self, event: QMouseEvent) -> None:
        scene_pos = self._canvas.mapToScene(event.pos())
        button = event.button()

        if button == Qt.MouseButton.LeftButton:
            match self._mode:
                case _Mode.DRAGGING:
                    self._end_drag(scene_pos)
                case _Mode.CONNECTING:
                    self._callback("temp_edge_clear")
                    self._end_connect(scene_pos)
                case _Mode.SELECTING:
                    self._end_select()
                case _Mode.PANNING:
                    self._mode = _Mode.IDLE
        elif button == Qt.MouseButton.MiddleButton:
            if self._mode == _Mode.PANNING:
                self._mode = _Mode.IDLE

    def handle_double_click(self, event: QMouseEvent) -> None:
        scene_pos = self._canvas.mapToScene(event.pos())
        item = self._hit_node(scene_pos)
        if item:
            self._callback("node_double_clicked", node_id=item.node_id)

    def handle_key_press(self, event: QKeyEvent) -> None:
        key = event.key()
        mods = event.modifiers()

        if key in (Qt.Key_Delete, Qt.Key_Backspace):
            if self._selected_node_ids:
                self._callback("delete_selected", node_ids=list(self._selected_node_ids))
            elif self._selected_edge_id:
                self._callback("delete_edge", edge_id=self._selected_edge_id)
        elif key == Qt.Key_A and mods & Qt.KeyboardModifier.ControlModifier:
            self._select_all()
        elif key in (Qt.Key_Plus, Qt.Key_Equal):
            self._canvas.zoom_by(1.15)
        elif key == Qt.Key_Minus:
            self._canvas.zoom_by(1 / 1.15)
        elif key == Qt.Key_0 and mods & Qt.KeyboardModifier.ControlModifier:
            self._canvas.zoom_reset()
        elif key == Qt.Key_F:
            self._canvas.zoom_to_fit()
        elif key == Qt.Key_Space and not mods:
            self._canvas.zoom_to_fit()
        elif key == Qt.Key_C and mods & Qt.KeyboardModifier.ControlModifier:
            self._callback("copy_selected", node_ids=list(self._selected_node_ids))
        elif key == Qt.Key_V and mods & Qt.KeyboardModifier.ControlModifier:
            self._callback("paste")
        elif key == Qt.Key_D and mods & Qt.KeyboardModifier.ControlModifier:
            self._callback("duplicate_selected", node_ids=list(self._selected_node_ids))
        elif key == Qt.Key_Z and mods & Qt.KeyboardModifier.ControlModifier:
            self._callback("undo")
        elif key == Qt.Key_Y and mods & Qt.KeyboardModifier.ControlModifier:
            self._callback("redo")
        elif key == Qt.Key_F and mods & Qt.KeyboardModifier.ControlModifier:
            self._callback("search")
        elif key == Qt.Key_Escape:
            self._deselect_all()
            self._callback("escape")
        elif key == Qt.Key_M and mods & Qt.KeyboardModifier.AltModifier:
            self._callback("toggle_minimap")

    # ── Hit testing ────────────────────────────────────────

    def _hit_test(self, scene_pos: QPointF) -> tuple:
        """Single-pass hit test. Returns (port_hit, node_item, edge_item)."""
        port_hit = None
        node_item = None
        edge_item = None
        for item in self._canvas.scene.items(scene_pos):
            if isinstance(item, QtNodeItem):
                if node_item is None:
                    node_item = item
                if port_hit is None:
                    positions = port_positions(item.node)
                    nx = item.node.pos_x
                    ny = item.node.pos_y
                    for port_name, (px, py) in positions.items():
                        local_x = px - nx
                        local_y = py - ny
                        dist = ((scene_pos.x() - item.pos().x() - local_x) ** 2 +
                                (scene_pos.y() - item.pos().y() - local_y) ** 2) ** 0.5
                        if dist <= PORT_HIT_RADIUS:
                            port_hit = (item.node_id, port_name)
                            break
            elif isinstance(item, QtEdgeItem) and edge_item is None:
                edge_item = item
            if port_hit and node_item and edge_item:
                break
        return port_hit, node_item, edge_item

    def _hit_node(self, scene_pos: QPointF) -> QtNodeItem | None:
        _, node, _ = self._hit_test(scene_pos)
        return node

    def _hit_edge(self, scene_pos: QPointF) -> QtEdgeItem | None:
        _, _, edge = self._hit_test(scene_pos)
        return edge

    def _hit_port(self, scene_pos: QPointF) -> tuple[str, str] | None:
        port, _, _ = self._hit_test(scene_pos)
        return port

    # ── Left click ─────────────────────────────────────────

    def _on_left_press(self, scene_pos: QPointF, event: QMouseEvent) -> None:
        port_hit = self._hit_port(scene_pos)
        if port_hit:
            node_id, port_name = port_hit
            self._start_connecting(scene_pos, node_id, port_name)
            return

        node_item = self._hit_node(scene_pos)
        if node_item:
            node_id = node_item.node_id
            mods = event.modifiers()
            if mods & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier):
                self._toggle_node_selection(node_id)
            elif node_id in self._selected_node_ids and len(self._selected_node_ids) > 1:
                self._start_multi_drag(scene_pos)
            else:
                self._select_node(node_id)
                self._start_drag(scene_pos, node_id)
            return

        edge_item = self._hit_edge(scene_pos)
        if edge_item:
            self._select_edge(edge_item.edge_id)
            return

        self._start_selecting(scene_pos, event)

    # ── Dragging ───────────────────────────────────────────

    def _start_drag(self, scene_pos: QPointF, node_id: str) -> None:
        self._mode = _Mode.DRAGGING
        self._drag_node_id = node_id
        self._drag_start_scene = scene_pos
        graph = self._get_graph()
        if graph:
            node = graph.get_node(node_id)
            if node:
                self._drag_node_start_pos = (node.pos_x, node.pos_y)
        self._can_auto_insert = False
        self._auto_insert_candidate = None
        if graph and node_id:
            edges = graph.get_edges_for_node(node_id)
            if not edges:
                self._can_auto_insert = True

    def _start_multi_drag(self, scene_pos: QPointF) -> None:
        self._mode = _Mode.DRAGGING
        self._drag_node_id = None
        self._drag_start_scene = scene_pos
        self._multi_drag_offsets.clear()
        graph = self._get_graph()
        if not graph:
            return
        for nid in self._selected_node_ids:
            node = graph.get_node(nid)
            if node:
                self._multi_drag_offsets[nid] = (node.pos_x, node.pos_y)

    def _compute_drag_positions(
        self, scene_pos: QPointF,
    ) -> list[tuple[str, float, float]]:
        dx = scene_pos.x() - self._drag_start_scene.x()
        dy = scene_pos.y() - self._drag_start_scene.y()
        if self._drag_node_id:
            new_x = self._drag_node_start_pos[0] + dx
            new_y = self._drag_node_start_pos[1] + dy
            if self._snap_to_grid:
                new_x = _snap(new_x)
                new_y = _snap(new_y)
            return [(self._drag_node_id, new_x, new_y)]
        result = []
        for nid, (ox, oy) in self._multi_drag_offsets.items():
            new_x = ox + dx
            new_y = oy + dy
            if self._snap_to_grid:
                new_x = _snap(new_x)
                new_y = _snap(new_y)
            result.append((nid, new_x, new_y))
        return result

    def _do_drag(self, scene_pos: QPointF) -> None:
        if not self._get_graph():
            return
        for nid, new_x, new_y in self._compute_drag_positions(scene_pos):
            self._callback("node_dragging", node_id=nid, world_x=new_x, world_y=new_y)

        if self._can_auto_insert and self._drag_node_id:
            result = self._nearest_edge_to_point(scene_pos.x(), scene_pos.y())
            if result:
                new_candidate = result
                if new_candidate != self._auto_insert_candidate:
                    if self._auto_insert_candidate:
                        self._callback("auto_insert_clear")
                    self._auto_insert_candidate = new_candidate
                    self._callback("auto_insert_preview", edge_id=new_candidate)
            else:
                if self._auto_insert_candidate:
                    self._callback("auto_insert_clear")
                self._auto_insert_candidate = None

    def _end_drag(self, scene_pos: QPointF) -> None:
        self._mode = _Mode.IDLE
        if self._can_auto_insert and self._auto_insert_candidate and self._drag_node_id:
            positions = self._compute_drag_positions(scene_pos)
            _, snap_x, snap_y = positions[0] if positions else (self._drag_node_id, 0, 0)
            self._callback("auto_insert_clear")
            self._callback(
                "auto_insert",
                edge_id=self._auto_insert_candidate,
                node_id=self._drag_node_id,
                x=int(snap_x),
                y=int(snap_y),
            )
            self._auto_insert_candidate = None
            self._can_auto_insert = False
            self._drag_node_id = None
            self._multi_drag_offsets.clear()
            return

        for nid, new_x, new_y in self._compute_drag_positions(scene_pos):
            self._callback("node_moved", node_id=nid, world_x=new_x, world_y=new_y)
        self._drag_node_id = None
        self._multi_drag_offsets.clear()
        if self._auto_insert_candidate:
            self._callback("auto_insert_clear")
        self._auto_insert_candidate = None
        self._can_auto_insert = False

    # ── Connecting ─────────────────────────────────────────

    def _start_connecting(self, scene_pos: QPointF, node_id: str, port_name: str) -> None:
        self._mode = _Mode.CONNECTING
        self._connect_from_node = node_id
        self._connect_from_port = port_name
        graph = self._get_graph()
        if graph:
            node = graph.get_node(node_id)
            if node:
                positions = port_positions(node)
                if port_name in positions:
                    self._connect_from_pos = positions[port_name]

    def _do_connect_move(self, scene_pos: QPointF) -> None:
        if not self._connect_from_node:
            return
        fx, fy = self._connect_from_pos
        self._callback("temp_edge", from_x=fx, from_y=fy, to_x=scene_pos.x(), to_y=scene_pos.y())

    def _end_connect(self, scene_pos: QPointF) -> None:
        self._mode = _Mode.IDLE
        from_node = self._connect_from_node
        from_port = self._connect_from_port
        self._connect_from_node = None
        self._connect_from_port = None

        if not from_node:
            return

        port_hit = self._hit_port(scene_pos)
        if port_hit:
            to_node_id, to_port = port_hit
            if to_node_id != from_node and to_port == PORT_IN:
                label = from_port.replace("out_", "") if from_port.startswith("out_") else EdgeLabel.DEFAULT
                self._callback(
                    "edge_created",
                    from_node=from_node,
                    to_node=to_node_id,
                    label=label,
                )

    # ── Panning ────────────────────────────────────────────

    def _start_pan(self, scene_pos: QPointF) -> None:
        self._mode = _Mode.PANNING
        self._pan_last_pos = scene_pos

    def _do_pan(self, scene_pos: QPointF) -> None:
        dx = scene_pos.x() - self._pan_last_pos.x()
        dy = scene_pos.y() - self._pan_last_pos.y()
        z = self._canvas.zoom()
        self._canvas.pan_by(-dx * z, -dy * z)
        self._pan_last_pos = scene_pos

    # ── Selecting ──────────────────────────────────────────

    def _start_selecting(self, scene_pos: QPointF, event: QMouseEvent) -> None:
        self._mode = _Mode.SELECTING
        self._select_start = scene_pos
        self._select_additive = bool(
            event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
        )
        if not self._select_additive:
            self._deselect_all()

    def _do_select(self, scene_pos: QPointF) -> None:
        rect = QRectF(
            min(self._select_start.x(), scene_pos.x()),
            min(self._select_start.y(), scene_pos.y()),
            abs(scene_pos.x() - self._select_start.x()),
            abs(scene_pos.y() - self._select_start.y()),
        )
        found: set[str] = set()
        for item in self._canvas.scene.items(rect):
            if isinstance(item, QtNodeItem):
                found.add(item.node_id)
        if not self._select_additive:
            self._selected_node_ids = found
        else:
            self._selected_node_ids = self._selected_node_ids | found
        self._canvas.update_selection_rings(self._selected_node_ids)

    def _end_select(self) -> None:
        self._mode = _Mode.IDLE
        if self._selected_node_ids:
            self._callback("nodes_selected", node_ids=list(self._selected_node_ids))
        else:
            self._callback("canvas_deselected")

    # ── Selection helpers ──────────────────────────────────

    def _select_node(self, node_id: str) -> None:
        self._selected_node_ids = {node_id}
        self._selected_edge_id = None
        self._canvas.update_selection_rings(self._selected_node_ids)
        self._canvas.clear_edge_states()
        self._callback("node_selected", node_id=node_id)

    def _toggle_node_selection(self, node_id: str) -> None:
        if node_id in self._selected_node_ids:
            self._selected_node_ids.discard(node_id)
        else:
            self._selected_node_ids.add(node_id)
        self._canvas.update_selection_rings(self._selected_node_ids)
        self._callback("nodes_selected", node_ids=list(self._selected_node_ids))

    def _select_edge(self, edge_id: str) -> None:
        self._selected_edge_id = edge_id
        self._canvas.set_edge_selected(edge_id)
        self._callback("edge_selected", edge_id=edge_id)

    def _select_all(self) -> None:
        graph = self._get_graph()
        if not graph:
            return
        self._selected_node_ids = set(graph.nodes.keys())
        self._canvas.update_selection_rings(self._selected_node_ids)
        self._callback("nodes_selected", node_ids=list(self._selected_node_ids))

    def _deselect_all(self) -> None:
        self._selected_node_ids.clear()
        self._selected_edge_id = None
        self._canvas.update_selection_rings(set())
        self._canvas.clear_edge_states()
        self._callback("canvas_deselected")

    # ── Hover ──────────────────────────────────────────────

    def _update_hover(self, scene_pos: QPointF) -> None:
        port_hit = self._hit_port(scene_pos)
        if port_hit:
            self._canvas.setCursor(Qt.CursorShape.CrossCursor)
            return

        node_item = self._hit_node(scene_pos)
        if node_item:
            self._canvas.setCursor(Qt.CursorShape.PointingHandCursor)
            return

        edge_item = self._hit_edge(scene_pos)
        if edge_item:
            self._canvas.setCursor(Qt.CursorShape.PointingHandCursor)
            self._canvas.set_edge_hover(edge_item.edge_id)
        else:
            self._canvas.setCursor(Qt.CursorShape.ArrowCursor)
            self._canvas.set_edge_hover(None)

    # ── Right click ────────────────────────────────────────

    def _on_right_click(self, scene_pos: QPointF, event: QMouseEvent) -> None:
        node_item = self._hit_node(scene_pos)
        if node_item:
            self._select_node(node_item.node_id)
            screen_pos = event.screenPos()
            self._callback(
                "node_context_menu",
                node_id=node_item.node_id,
                screen_x=screen_pos.x(),
                screen_y=screen_pos.y(),
            )
            return

        edge_item = self._hit_edge(scene_pos)
        if edge_item:
            self._select_edge(edge_item.edge_id)
            screen_pos = event.screenPos()
            self._callback(
                "edge_context_menu",
                edge_id=edge_item.edge_id,
                screen_x=screen_pos.x(),
                screen_y=screen_pos.y(),
            )
            return

        screen_pos = event.screenPos()
        self._callback(
            "canvas_context_menu",
            screen_x=screen_pos.x(),
            screen_y=screen_pos.y(),
        )

    # ── Auto-insert helpers ─────────────────────────────────

    def _nearest_edge_to_point(self, wx: float, wy: float) -> str | None:
        graph = self._get_graph()
        if not graph:
            return None
        best_id: str | None = None
        best_dist = _AUTO_INSERT_DIST
        drag_id = self._drag_node_id
        for edge in graph.edges:
            if drag_id and (edge.from_node == drag_id or edge.to_node == drag_id):
                continue
            from_node = graph.get_node(edge.from_node)
            to_node = graph.get_node(edge.to_node)
            if not from_node or not to_node:
                continue
            from_ports = port_positions(from_node)
            to_ports = port_positions(to_node)
            from_key = f"out_{edge.label}"
            if from_key not in from_ports:
                from_key = "out_default"
            if from_key not in from_ports or "in" not in to_ports:
                continue
            fx, fy = from_ports[from_key]
            tx, ty = to_ports["in"]
            dist = _point_to_segment_dist(wx, wy, fx, fy, tx, ty)
            if dist < best_dist:
                best_dist = dist
                best_id = edge.edge_id
        return best_id
