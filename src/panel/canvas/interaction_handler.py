"""InteractionHandler — Canvas 鼠标/键盘事件状态机

支持 Blender 风格交互:
- 连线端点拖拽重连 (RECONNECTING)
- 拖拽未连接节点到连线上自动插入 (AUTO_INSERT)
- 边中点拖出新连线 (via CONNECTING)

拆分模块:
- _interaction_types: 共享类型/常量
- _interaction_hit_test: 命中检测
- _interaction_connect: 连线/重连
- _interaction_select: 框选/选中
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

import tkinter as tk

from src.core.flow import FlowEdge, FlowGraph
from src.panel.canvas._interaction_connect import ConnectMixin
from src.panel.canvas._interaction_hit_test import HitTestMixin
from src.panel.canvas._interaction_select import SelectMixin
from src.panel.canvas._interaction_types import (
    CB_AUTO_INSERT,
    CB_AUTO_INSERT_CLEAR,
    CB_AUTO_INSERT_PREVIEW,
    CB_CANVAS_CONTEXT_MENU,
    CB_CANVAS_DESELECTED,
    CB_COPY_SELECTED,
    CB_DELETE_EDGE,
    CB_DELETE_SELECTED,
    CB_DRAG_ENDED,
    CB_DRAG_STARTED,
    CB_DUPLICATE_SELECTED,
    CB_EDGE_CONTEXT_MENU,
    CB_EDGE_HOVER,
    CB_EDGE_HOVER_CLEAR,
    CB_EDGE_SELECTED,
    CB_ESCAPE,
    CB_NODE_CONTEXT_MENU,
    CB_NODE_DOUBLE_CLICKED,
    CB_NODE_DRAGGING,
    CB_NODE_HOVER,
    CB_NODE_HOVER_CLEAR,
    CB_NODE_MOVED,
    CB_NODE_SELECTED,
    CB_NODES_SELECTED,
    CB_PAN_ENDED,
    CB_PAN_REQUEST,
    CB_PASTE,
    CB_REDO,
    CB_SEARCH,
    CB_TOGGLE_MINIMAP,
    CB_UNDO,
    CB_ZOOM_REQUEST,
    CB_ZOOM_RESET,
    CB_ZOOM_TO_FIT,
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
    SIDE_TARGET,
    _CLICK_MOTION_THRESHOLD,
    _PORT_IDLE_HOVER_SCALE,
    _SELECT_MODIFY_MASK,
    _SHIFT_MASK,
    InteractionMode,
    _PortHighlight,
)
from src.panel.canvas.node_shared import PORT_IN, TAG_SELECTION_HIGHLIGHT
from src.panel.canvas.theme import current_theme
from src.panel.models.enums import EdgeStyle

if TYPE_CHECKING:
    from src.panel.canvas.graph_canvas import GraphCanvas


class InteractionHandler(HitTestMixin, ConnectMixin, SelectMixin):
    """处理画布上的所有鼠标/键盘交互。

    通过回调函数向页面层报告事件，不直接操作 Model。
    """

    def __init__(
        self,
        canvas: GraphCanvas,
        get_graph: Callable[[], FlowGraph | None],
        get_viewport: Callable[[], tuple[float, float, float]],
        event_callback: Callable[..., None],
        get_edge_style: Callable[[], str] | None = None,
        snap_to_grid: bool = True,
    ):
        self._canvas = canvas
        self._get_graph = get_graph
        self._get_viewport = get_viewport
        self._callback = event_callback
        self._get_edge_style = get_edge_style or (lambda: EdgeStyle.BEZIER)
        self._snap_to_grid = snap_to_grid

        self._mode = InteractionMode.IDLE

        # Hover cursor throttle
        self._last_hover_x: float = 0
        self._last_hover_y: float = 0
        self._last_hover_result: tuple[str, dict] = (HIT_CANVAS, {})
        self._last_hover_node_id: str | None = None

        # 拖拽状态
        self._drag_node_id: str | None = None
        self._drag_start_sx: float = 0
        self._drag_start_sy: float = 0
        self._drag_offset_wx: float = 0
        self._drag_offset_wy: float = 0

        # 平移状态
        self._pan_start_sx: float = 0
        self._pan_start_sy: float = 0
        self._pan_origin_sx: float = 0
        self._pan_origin_sy: float = 0

        # 连线状态
        self._connect_from_node: str | None = None
        self._connect_from_label: str | None = None
        self._connect_from_sx: float = 0
        self._connect_from_sy: float = 0
        self._temp_edge_id: int | None = None

        # 选中状态
        self._selected_node_ids: set[str] = set()
        self._selected_edge_id: str | None = None

        # 框选状态
        self._select_start_sx: float = 0
        self._select_start_sy: float = 0
        self._select_rect_id: int | None = None
        self._select_count_id: int | None = None
        self._last_select_count: int = -1
        self._select_additive: bool = False

        # 端口高亮状态
        self._connect_port_highlight = _PortHighlight()

        # 重连状态
        self._reconnect_state = None
        self._reconnect_original_dash: tuple = ()
        self._reconnect_original_width: float = 2.5

        # 自动插入状态
        self._auto_insert_candidate: str | None = None
        self._can_auto_insert: bool = False

        # IDLE 端口悬停
        self._port_hover_info: tuple[str, str] | None = None
        self._idle_port_highlight = _PortHighlight()

        # 多选拖拽状态
        self._multi_drag_offsets: dict[str, tuple[float, float]] = {}

        # Motion 去抖（~60fps）
        self._motion_pending: bool = False
        self._last_motion_event: tk.Event | None = None

        # 右键菜单防重入
        self._context_menu_active: bool = False
        self._context_menu_motion_start: tuple[int, int] | None = None
        self._context_menu_pending_event: tk.Event | None = None

        self._bind_events()

    def _bind_events(self):
        c = self._canvas
        c.bind("<ButtonPress-1>", self._on_press)
        c.bind("<B1-Motion>", self._on_motion)
        c.bind("<ButtonRelease-1>", self._on_release)
        c.bind("<Double-ButtonPress-1>", self._on_double_click)
        c.bind("<ButtonPress-3>", self._on_right_click)
        c.bind("<B3-Motion>", self._on_right_motion)
        c.bind("<ButtonPress-2>", self._on_middle_press)
        c.bind("<B2-Motion>", self._on_middle_motion)
        c.bind("<ButtonRelease-2>", self._on_middle_release)
        c.bind("<MouseWheel>", self._on_mousewheel)
        c.bind("<Button-4>", lambda e: self._on_mousewheel_linux(e, 1))
        c.bind("<Button-5>", lambda e: self._on_mousewheel_linux(e, -1))
        c.bind("<Delete>", self._on_key_delete)
        c.bind("<BackSpace>", self._on_key_delete)
        c.bind("<Control-a>", self._on_key_select_all)
        c.bind("<Control-A>", self._on_key_select_all)
        c.bind("<Home>", self._on_key_home)
        c.bind("<plus>", self._on_key_zoom_in)
        c.bind("<equal>", self._on_key_zoom_in)
        c.bind("<minus>", self._on_key_zoom_out)
        c.bind("<Control-0>", self._on_key_zoom_reset)
        c.bind("<space>", self._on_key_space_press)
        c.bind("<KeyRelease-space>", self._on_key_space_release)
        c.bind("<Control-c>", self._on_key_copy)
        c.bind("<Control-C>", self._on_key_copy)
        c.bind("<Control-v>", self._on_key_paste)
        c.bind("<Control-V>", self._on_key_paste)
        c.bind("<Control-d>", self._on_key_duplicate)
        c.bind("<Control-D>", self._on_key_duplicate)
        c.bind("<Control-z>", self._on_key_undo)
        c.bind("<Control-y>", self._on_key_redo)
        c.bind("<Control-f>", self._on_key_search)
        c.bind("<Control-F>", self._on_key_search)
        c.bind("<Escape>", self._on_key_escape)
        c.bind("<Alt-m>", self._on_key_toggle_minimap)
        c.bind("<Alt-M>", self._on_key_toggle_minimap)
        c.bind("<Enter>", lambda e: c.focus_set())

    # ── 事件分发 ──────────────────────────────────────────

    def _handle_port_press(self, event: tk.Event, info: dict) -> None:
        """点击端口时：已有连线 → 重连，无连线 → 新建连接。"""
        node_id = info[KEY_NODE_ID]
        port_label = info[KEY_PORT_LABEL]
        graph = self._get_graph()

        if graph:
            edge, side = self._find_edge_at_port(graph, node_id, port_label)
            if edge and side:
                self._select_node(node_id)
                self._start_reconnecting_from_port(event, edge, side)
                return

        self._start_connecting(event, info)

    @staticmethod
    def _find_edge_at_port(
        graph: FlowGraph, node_id: str, port_label: str,
    ) -> tuple[FlowEdge | None, str | None]:
        """查找连接到指定端口的边及其侧（source/target）。"""
        for edge in graph.get_edges_for_node(node_id):
            if port_label == PORT_IN and edge.to_node == node_id:
                return edge, SIDE_TARGET
            if port_label != PORT_IN and edge.from_node == node_id:
                edge_label = FlowGraph.port_label_to_edge_label(port_label)
                if edge.label == edge_label:
                    return edge, SIDE_SOURCE
        return None, None

    def _start_reconnecting_from_port(
        self, event: tk.Event, edge: FlowEdge, side: str,
    ) -> None:
        """从端口点击发起重连（区别于点击边端点）。"""
        reconnect_info = {
            KEY_EDGE_ID: edge.edge_id,
            KEY_SIDE: side,
        }
        self._start_reconnecting(event, reconnect_info)

    def _update_hover_cursor(self, event: tk.Event) -> None:
        dx = abs(event.x - self._last_hover_x)
        dy = abs(event.y - self._last_hover_y)
        if dx < _CLICK_MOTION_THRESHOLD and dy < _CLICK_MOTION_THRESHOLD:
            hit_type = self._last_hover_result[0]
            info = self._last_hover_result[1]
        else:
            hit_type, info = self._hit_test(event.x, event.y)
            self._last_hover_x = event.x
            self._last_hover_y = event.y
            self._last_hover_result = (hit_type, info)

            if hit_type in (HIT_EDGE, HIT_EDGE_ENDPOINT, HIT_EDGE_MIDPOINT):
                self._callback(CB_EDGE_HOVER, edge_id=info.get(KEY_EDGE_ID),
                               side=info.get(KEY_SIDE))
                self._clear_hover_node()
            elif hit_type == HIT_NODE:
                self._callback(CB_EDGE_HOVER_CLEAR)
                node_id = info.get(KEY_NODE_ID)
                if node_id != self._last_hover_node_id:
                    self._last_hover_node_id = node_id
                    self._callback(CB_NODE_HOVER, node_id=node_id,
                                   screen_x=event.x, screen_y=event.y)
            else:
                self._callback(CB_EDGE_HOVER_CLEAR)
                self._clear_hover_node()

            if hit_type == HIT_PORT:
                self._set_idle_port_hover(info)
            else:
                self._clear_idle_port_hover()

        if hit_type == HIT_PORT:
            self._canvas.configure(cursor="crosshair")
        elif hit_type == HIT_NODE:
            self._canvas.configure(cursor="hand2")
        elif hit_type == HIT_EDGE_ENDPOINT:
            side = info.get(KEY_SIDE, "")
            if side == SIDE_SOURCE:
                self._canvas.configure(cursor="left_side")
            else:
                self._canvas.configure(cursor="right_side")
        elif hit_type == HIT_EDGE_MIDPOINT:
            self._canvas.configure(cursor="crosshair")
        else:
            self._canvas.configure(cursor="")

    def _clear_hover_node(self) -> None:
        if self._last_hover_node_id is not None:
            self._last_hover_node_id = None
            self._callback(CB_NODE_HOVER_CLEAR)

    def _on_press(self, event: tk.Event):
        hit_type, info = self._hit_test(event.x, event.y)
        mods = event.state if isinstance(event.state, int) else 0

        if hit_type == HIT_PORT:
            self._handle_port_press(event, info)
        elif hit_type == HIT_EDGE_ENDPOINT:
            self._select_edge(info[KEY_EDGE_ID])
            self._start_reconnecting(event, info)
        elif hit_type == HIT_EDGE_MIDPOINT:
            self._select_edge(info[KEY_EDGE_ID])
            self._start_midpoint_connect(event, info)
        elif hit_type == HIT_EDGE:
            self._select_edge(info[KEY_EDGE_ID])
        elif hit_type == HIT_NODE:
            node_id = info[KEY_NODE_ID]
            if mods & _SELECT_MODIFY_MASK:
                self._toggle_node_in_selection(node_id)
            elif node_id in self._selected_node_ids and len(self._selected_node_ids) > 1:
                self._start_multi_drag(event, info)
            else:
                self._start_dragging(event, info)
        else:
            self._start_selecting(event)

    def _on_motion(self, event: tk.Event):
        self._last_motion_event = event
        if not self._motion_pending:
            self._motion_pending = True
            self._canvas.after(16, self._dispatch_motion)

    def _dispatch_motion(self):
        self._motion_pending = False
        event = self._last_motion_event
        if event is None:
            return
        match self._mode:
            case InteractionMode.DRAGGING_NODE:
                self._do_drag(event)
            case InteractionMode.CONNECTING:
                self._do_connect(event)
            case InteractionMode.RECONNECTING:
                self._do_reconnect(event)
            case InteractionMode.PANNING:
                self._do_pan(event)
            case InteractionMode.SELECTING:
                self._do_select(event)
            case InteractionMode.IDLE:
                self._update_hover_cursor(event)

    def _on_release(self, event: tk.Event):
        match self._mode:
            case InteractionMode.DRAGGING_NODE:
                self._end_drag(event)
            case InteractionMode.CONNECTING:
                self._end_connect(event)
            case InteractionMode.RECONNECTING:
                self._end_reconnect(event)
            case InteractionMode.PANNING:
                self._end_pan(event)
            case InteractionMode.SELECTING:
                self._end_select(event)

    def _on_double_click(self, event: tk.Event):
        hit_type, info = self._hit_test(event.x, event.y)
        if hit_type == HIT_NODE:
            self._callback(CB_NODE_DOUBLE_CLICKED, node_id=info[KEY_NODE_ID])

    def _on_right_click(self, event: tk.Event):
        if self._context_menu_active:
            return
        self._context_menu_active = True
        self._context_menu_motion_start = (event.x, event.y)
        self._context_menu_pending_event = event
        self._canvas.after(30, self._do_show_context_menu)

    def _on_right_motion(self, event: tk.Event) -> None:
        if self._context_menu_active:
            self._context_menu_motion_start = (event.x, event.y)

    def _show_context_menu(
        self, canvas_x: int, canvas_y: int, root_x: int, root_y: int,
    ):
        hit_type, info = self._hit_test(canvas_x, canvas_y)
        if hit_type == HIT_NODE:
            node_id = info[KEY_NODE_ID]
            if node_id not in self._selected_node_ids or len(self._selected_node_ids) <= 1:
                self._select_node(node_id)
            self._callback(
                CB_NODE_CONTEXT_MENU,
                node_id=node_id,
                screen_x=root_x,
                screen_y=root_y,
            )
        elif hit_type in (HIT_EDGE, HIT_EDGE_ENDPOINT, HIT_EDGE_MIDPOINT):
            self._select_edge(info[KEY_EDGE_ID])
            self._callback(
                CB_EDGE_CONTEXT_MENU,
                edge_id=info[KEY_EDGE_ID],
                screen_x=root_x,
                screen_y=root_y,
            )
        else:
            self._callback(
                CB_CANVAS_CONTEXT_MENU,
                screen_x=root_x,
                screen_y=root_y,
                canvas_x=canvas_x,
                canvas_y=canvas_y,
            )

    def _on_mousewheel(self, event: tk.Event):
        factor = 1.1 if event.delta > 0 else 0.9
        self._callback(CB_ZOOM_REQUEST, screen_x=event.x, screen_y=event.y, factor=factor)

    def _on_mousewheel_linux(self, event: tk.Event, direction: int):
        factor = 1.1 if direction > 0 else 0.9
        self._callback(CB_ZOOM_REQUEST, screen_x=event.x, screen_y=event.y, factor=factor)

    # ── 键盘快捷键 ────────────────────────────────────────

    def _on_key_delete(self, _event: tk.Event):
        if self._selected_node_ids:
            self._callback(CB_DELETE_SELECTED, node_ids=list(self._selected_node_ids))
        elif self._selected_edge_id:
            self._callback(CB_DELETE_EDGE, edge_id=self._selected_edge_id)
            self._clear_edge_selection()

    def _on_key_select_all(self, _event: tk.Event):
        self.select_all()

    def _on_key_home(self, _event: tk.Event):
        self._callback(CB_ZOOM_TO_FIT)

    def _on_key_zoom_in(self, _event: tk.Event):
        cx = self._canvas.winfo_width() / 2
        cy = self._canvas.winfo_height() / 2
        self._callback(CB_ZOOM_REQUEST, screen_x=cx, screen_y=cy, factor=1.2)

    def _on_key_zoom_out(self, _event: tk.Event):
        cx = self._canvas.winfo_width() / 2
        cy = self._canvas.winfo_height() / 2
        self._callback(CB_ZOOM_REQUEST, screen_x=cx, screen_y=cy, factor=0.8)

    def _on_key_zoom_reset(self, _event: tk.Event):
        self._callback(CB_ZOOM_RESET)

    def _on_key_space_press(self, _event: tk.Event):
        if self._mode == InteractionMode.IDLE:
            self._mode = InteractionMode.PANNING
            self._canvas.configure(cursor="fleur")

    def _on_key_space_release(self, _event: tk.Event):
        if self._mode == InteractionMode.PANNING and not self._drag_node_id:
            self._mode = InteractionMode.IDLE
            self._canvas.configure(cursor="")

    def _on_key_copy(self, _event: tk.Event):
        if self._selected_node_ids:
            self._callback(CB_COPY_SELECTED, node_ids=list(self._selected_node_ids))

    def _on_key_paste(self, _event: tk.Event):
        self._callback(CB_PASTE)

    def _on_key_duplicate(self, _event: tk.Event):
        if self._selected_node_ids:
            self._callback(CB_DUPLICATE_SELECTED, node_ids=list(self._selected_node_ids))

    def _on_key_undo(self, _event: tk.Event):
        self._callback(CB_UNDO)

    def _on_key_redo(self, _event: tk.Event):
        self._callback(CB_REDO)

    def _on_key_search(self, _event: tk.Event):
        self._callback(CB_SEARCH)

    def _on_key_escape(self, _event: tk.Event):
        had_node_selection = bool(self._selected_node_ids)
        had_edge_selection = self._selected_edge_id is not None
        self._selected_node_ids.clear()
        self._clear_edge_selection()
        self._canvas.delete(TAG_SELECTION_HIGHLIGHT)
        if had_node_selection or had_edge_selection:
            self._callback(CB_CANVAS_DESELECTED)
        self._callback(CB_ESCAPE)

    def _on_key_toggle_minimap(self, _event: tk.Event):
        self._callback(CB_TOGGLE_MINIMAP)

    # ── 拖拽节点 ──────────────────────────────────────────

    def _start_dragging(self, event: tk.Event, info: dict):
        node_id = info[KEY_NODE_ID]
        self._mode = InteractionMode.DRAGGING_NODE
        self._drag_node_id = node_id
        self._canvas.raise_node(node_id)
        self._drag_start_sx = event.x
        self._drag_start_sy = event.y
        self._multi_drag_offsets.clear()
        self._canvas.configure(cursor="fleur")
        self._callback(CB_DRAG_STARTED, node_ids=[node_id])

        graph = self._get_graph()
        node = graph.get_node(node_id) if graph else None
        if node:
            wx, wy = self._canvas.screen_to_world(event.x, event.y)
            self._drag_offset_wx = wx - node.pos_x
            self._drag_offset_wy = wy - node.pos_y
        else:
            self._drag_offset_wx = 0
            self._drag_offset_wy = 0

        self._reset_auto_insert_state()
        if graph and node:
            edges = graph.get_edges_for_node(node_id)
            if not edges:
                self._can_auto_insert = True

        self._select_node(node_id)

    def _do_drag(self, event: tk.Event):
        if not self._drag_node_id:
            return

        wx, wy = self._canvas.screen_to_world(event.x, event.y)

        if self._multi_drag_offsets and len(self._selected_node_ids) > 1:
            for nid, (ox, oy) in self._multi_drag_offsets.items():
                self._callback(
                    CB_NODE_DRAGGING,
                    node_id=nid,
                    world_x=wx - ox,
                    world_y=wy - oy,
                )
            return

        new_wx = wx - self._drag_offset_wx
        new_wy = wy - self._drag_offset_wy

        self._callback(
            CB_NODE_DRAGGING,
            node_id=self._drag_node_id,
            world_x=new_wx,
            world_y=new_wy,
        )

        if self._can_auto_insert:
            result = self._nearest_edge_to_world_point(wx, wy)
            if result:
                new_candidate = result[0]
                if new_candidate != self._auto_insert_candidate:
                    if self._auto_insert_candidate:
                        self._callback(CB_AUTO_INSERT_CLEAR)
                    self._auto_insert_candidate = new_candidate
                    self._callback(
                        CB_AUTO_INSERT_PREVIEW,
                        edge_id=new_candidate,
                        node_id=self._drag_node_id,
                    )
            else:
                if self._auto_insert_candidate:
                    self._callback(CB_AUTO_INSERT_CLEAR)
                self._auto_insert_candidate = None

    def _snap(self, wx: float, wy: float) -> tuple[int, int]:
        if self._snap_to_grid:
            grid_size = current_theme().grid_spacing
            return int(round(wx / grid_size) * grid_size), \
                   int(round(wy / grid_size) * grid_size)
        return int(wx), int(wy)

    def _end_drag(self, event: tk.Event):
        if not self._drag_node_id:
            return
        self._canvas.configure(cursor="")
        wx, wy = self._canvas.screen_to_world(event.x, event.y)

        if self._multi_drag_offsets and len(self._selected_node_ids) > 1:
            dragged_ids = list(self._multi_drag_offsets.keys())
            for nid, (ox, oy) in self._multi_drag_offsets.items():
                raw_x, raw_y = wx - ox, wy - oy
                nx, ny = self._snap(raw_x, raw_y)
                self._callback(CB_NODE_MOVED, **self._snap_kwargs(nid, raw_x, raw_y, nx, ny))
            self._multi_drag_offsets.clear()
            self._callback(CB_DRAG_ENDED, node_ids=dragged_ids)
            self._mode = InteractionMode.IDLE
            self._drag_node_id = None
            self._reset_auto_insert_state()
            return

        raw_x = wx - self._drag_offset_wx
        raw_y = wy - self._drag_offset_wy
        nx, ny = self._snap(raw_x, raw_y)

        if self._can_auto_insert and self._auto_insert_candidate:
            self._callback(CB_AUTO_INSERT_CLEAR)
            self._callback(
                CB_AUTO_INSERT,
                edge_id=self._auto_insert_candidate,
                node_id=self._drag_node_id,
                x=nx,
                y=ny,
            )
            self._reset_auto_insert_state()
            self._callback(CB_DRAG_ENDED, node_ids=[self._drag_node_id])
            self._mode = InteractionMode.IDLE
            self._drag_node_id = None
            return

        self._callback(CB_NODE_MOVED, **self._snap_kwargs(self._drag_node_id, raw_x, raw_y, nx, ny))
        self._callback(CB_DRAG_ENDED, node_ids=[self._drag_node_id])
        self._mode = InteractionMode.IDLE
        self._drag_node_id = None
        self._reset_auto_insert_state()

    def _snap_kwargs(self, node_id: str, raw_x: float, raw_y: float, snap_x: int, snap_y: int) -> dict:
        """构建 node_moved 回调参数，仅在需要吸附动画时附带 snap_from 坐标。"""
        kwargs: dict = {KEY_NODE_ID: node_id, "x": snap_x, "y": snap_y}
        if snap_x != int(raw_x) or snap_y != int(raw_y):
            kwargs["snap_from_x"] = int(raw_x)
            kwargs["snap_from_y"] = int(raw_y)
        return kwargs

    # ── 平移 ──────────────────────────────────────────────

    def _start_panning(self, event: tk.Event):
        self._mode = InteractionMode.PANNING
        self._pan_start_sx = event.x
        self._pan_start_sy = event.y
        self._pan_origin_sx = event.x
        self._pan_origin_sy = event.y
        self._canvas.configure(cursor="fleur")

    def _do_pan(self, event: tk.Event):
        dx = event.x - self._pan_start_sx
        dy = event.y - self._pan_start_sy
        self._callback(CB_PAN_REQUEST, dx=dx, dy=dy)
        self._pan_start_sx = event.x
        self._pan_start_sy = event.y

    def _end_pan(self, event: tk.Event, deselect_on_click: bool = True):
        self._mode = InteractionMode.IDLE
        self._canvas.configure(cursor="")
        self._callback(CB_PAN_ENDED)
        if deselect_on_click:
            if abs(event.x - self._pan_origin_sx) < 3 and abs(event.y - self._pan_origin_sy) < 3:
                self._selected_node_ids.clear()
                self._callback(CB_CANVAS_DESELECTED)

    def _on_middle_press(self, event: tk.Event):
        self._start_panning(event)

    def _on_middle_motion(self, event: tk.Event):
        if self._mode == InteractionMode.PANNING:
            self._do_pan(event)

    def _on_middle_release(self, event: tk.Event):
        if self._mode == InteractionMode.PANNING:
            self._end_pan(event, deselect_on_click=False)

    # ── IDLE 端口悬停反馈 ─────────────────────────────────

    def _set_idle_port_hover(self, info: dict) -> None:
        item_id = info.get(KEY_ITEM_ID)
        if not item_id:
            return
        node_id = info.get(KEY_NODE_ID, "")
        port_label = info.get(KEY_PORT_LABEL, "")
        hover_key = (node_id, port_label)

        if hover_key == self._port_hover_info:
            return

        self._clear_idle_port_hover()

        self._idle_port_highlight.apply(
            self._canvas, item_id, current_theme().accent_blue, _PORT_IDLE_HOVER_SCALE,
        )
        self._port_hover_info = hover_key

    def _clear_idle_port_hover(self) -> None:
        self._idle_port_highlight.clear(self._canvas)
        self._port_hover_info = None

    # ── 配置 ──────────────────────────────────────────────

    def _reset_context_menu_guard(self) -> None:
        self._context_menu_active = False
        self._context_menu_motion_start = None
        self._context_menu_pending_event = None

    def _do_show_context_menu(self) -> None:
        event = self._context_menu_pending_event
        if not event:
            self._context_menu_active = False
            return
        start = self._context_menu_motion_start
        if start and (abs(event.x - start[0]) > _CLICK_MOTION_THRESHOLD or abs(event.y - start[1]) > _CLICK_MOTION_THRESHOLD):
            self._context_menu_active = False
            self._context_menu_pending_event = None
            return
        try:
            self._show_context_menu(event.x, event.y, event.x_root, event.y_root)
        finally:
            self._canvas.after(100, self._reset_context_menu_guard)

    def set_snap_to_grid(self, enabled: bool) -> None:
        self._snap_to_grid = enabled
