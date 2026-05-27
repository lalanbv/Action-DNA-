"""ConnectMixin — 连线/重连/中点连线逻辑。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tkinter as tk

from src.core.flow import FlowGraph
from src.panel.canvas._interaction_types import (
    CB_AUTO_INSERT_CLEAR,
    CB_EDGE_CREATED,
    CB_EDGE_HOVER_CLEAR,
    CB_EDGE_RECONNECTED,
    HIT_PORT,
    KEY_EDGE_ID,
    KEY_ITEM_ID,
    KEY_NODE_ID,
    KEY_PORT_LABEL,
    KEY_SIDE,
    SIDE_SOURCE,
    SIDE_TARGET,
    _EDGE_LABEL_TO_PORT,
    _PORT_HIGHLIGHT_SCALE,
    InteractionMode,
    ReconnectState,
)
from src.panel.canvas.edge_renderer import (
    _edge_endpoints,
    render_temp_edge,
    update_temp_edge,
)
from src.panel.canvas.node_renderer import port_positions
from src.panel.canvas.node_shared import PORT_IN, PORT_OUT_DEFAULT, PORT_OUT_PREFIX
from src.panel.canvas.theme import current_theme

if TYPE_CHECKING:
    from src.panel.canvas.graph_canvas import GraphCanvas


class ConnectMixin:
    """连线交互方法，供 InteractionHandler 继承。"""

    _canvas: GraphCanvas
    _get_graph: object
    _get_viewport: object
    _get_edge_style: object
    _callback: object
    _mode: InteractionMode
    _connect_from_node: str | None
    _connect_from_label: str | None
    _connect_from_sx: float
    _connect_from_sy: float
    _temp_edge_id: int | None
    _connect_port_highlight: object
    _reconnect_state: ReconnectState | None
    _reconnect_original_dash: tuple
    _reconnect_original_width: float
    _can_auto_insert: bool
    _auto_insert_candidate: str | None

    def _start_connecting(self, event: tk.Event, info: dict) -> None:
        port_label = info[KEY_PORT_LABEL]
        if port_label == PORT_IN:
            return

        node_id = info[KEY_NODE_ID]
        self._mode = InteractionMode.CONNECTING
        self._connect_from_node = node_id
        self._connect_from_label = port_label

        pos = self._port_at_screen(node_id, port_label)
        if pos:
            self._connect_from_sx, self._connect_from_sy = pos
        else:
            self._connect_from_sx = event.x
            self._connect_from_sy = event.y

        self._temp_edge_id = render_temp_edge(
            self._canvas,
            self._connect_from_sx,
            self._connect_from_sy,
            event.x,
            event.y,
            style=self._get_edge_style(),
        )

    def _do_connect(self, event: tk.Event) -> None:
        if self._temp_edge_id is None:
            return

        hit_type, info = self._hit_test(event.x, event.y)
        valid = (
            hit_type == HIT_PORT
            and info.get(KEY_PORT_LABEL) == PORT_IN
            and info.get(KEY_NODE_ID) != self._connect_from_node
        )

        update_temp_edge(
            self._canvas,
            self._temp_edge_id,
            self._connect_from_sx,
            self._connect_from_sy,
            event.x,
            event.y,
            style=self._get_edge_style(),
            valid_target=valid,
        )

        self._update_port_highlight(info if valid else None)

    def _end_connect(self, event: tk.Event) -> None:
        if self._temp_edge_id is not None:
            self._canvas.delete(self._temp_edge_id)
            self._temp_edge_id = None

        self._update_port_highlight(None)

        hit_type, info = self._hit_test(event.x, event.y)
        if hit_type == HIT_PORT and info.get(KEY_PORT_LABEL) == PORT_IN:
            to_node_id = info[KEY_NODE_ID]
            if to_node_id != self._connect_from_node:
                assert self._connect_from_label is not None
                label = FlowGraph.port_label_to_edge_label(self._connect_from_label)
                self._callback(
                    CB_EDGE_CREATED,
                    from_id=self._connect_from_node,
                    to_id=to_node_id,
                    label=label,
                )

        self._mode = InteractionMode.IDLE
        self._connect_from_node = None
        self._connect_from_label = None

    def _start_reconnecting(self, event: tk.Event, info: dict) -> None:
        edge_id = info[KEY_EDGE_ID]
        side = info[KEY_SIDE]
        graph = self._get_graph()
        if not graph:
            return
        edge = graph.get_edge(edge_id)
        if not edge:
            return

        if side == SIDE_SOURCE:
            anchor_node = edge.to_node
            anchor_port = PORT_IN
        else:
            anchor_node = edge.from_node
            anchor_port = _EDGE_LABEL_TO_PORT.get(edge.label, PORT_OUT_DEFAULT)

        self._reconnect_state = ReconnectState(
            edge_id=edge_id,
            side=side,
            anchor_node=anchor_node,
            anchor_port=anchor_port,
        )
        self._mode = InteractionMode.RECONNECTING

        anchor_node_obj = graph.get_node(anchor_node)
        if anchor_node_obj:
            ports = port_positions(anchor_node_obj)
            anchor_key = PORT_IN if side == SIDE_SOURCE else anchor_port
            if anchor_key in ports:
                wx, wy = ports[anchor_key]
                self._connect_from_sx, self._connect_from_sy = (
                    self._canvas.world_to_screen(wx, wy)
                )
            else:
                self._connect_from_sx = event.x
                self._connect_from_sy = event.y
        else:
            self._connect_from_sx = event.x
            self._connect_from_sy = event.y

        edge_items = self._canvas.get_edge_visual(edge_id)
        if edge_items and edge_items.line:
            try:
                self._reconnect_original_dash = self._canvas.itemcget(
                    edge_items.line, "dash"
                )
                self._reconnect_original_width = float(
                    self._canvas.itemcget(edge_items.line, "width")
                )
                self._canvas.itemconfigure(
                    edge_items.line, dash=(6, 4), width=1.5
                )
            except tk.TclError:
                pass

        self._temp_edge_id = render_temp_edge(
            self._canvas,
            self._connect_from_sx,
            self._connect_from_sy,
            event.x,
            event.y,
            style=self._get_edge_style(),
        )

    def _do_reconnect(self, event: tk.Event) -> None:
        if self._temp_edge_id is None or not self._reconnect_state:
            return
        hit_type, info = self._hit_test(event.x, event.y)
        state = self._reconnect_state

        valid = False
        if hit_type == HIT_PORT:
            port_label = info.get(KEY_PORT_LABEL, "")
            target_node = info.get(KEY_NODE_ID, "")
            if state.side == SIDE_SOURCE:
                valid = port_label != PORT_IN and target_node != state.anchor_node
            else:
                valid = port_label == PORT_IN and target_node != state.anchor_node

        update_temp_edge(
            self._canvas,
            self._temp_edge_id,
            self._connect_from_sx,
            self._connect_from_sy,
            event.x,
            event.y,
            style=self._get_edge_style(),
            valid_target=valid,
        )

        self._update_port_highlight(info if valid else None)

    def _end_reconnect(self, event: tk.Event) -> None:
        if self._temp_edge_id is not None:
            self._canvas.delete(self._temp_edge_id)
            self._temp_edge_id = None
        self._update_port_highlight(None)

        state = self._reconnect_state
        if not state:
            self._mode = InteractionMode.IDLE
            return

        self._callback(CB_EDGE_HOVER_CLEAR)

        edge_items = self._canvas.get_edge_visual(state.edge_id)
        if edge_items and edge_items.line:
            try:
                self._canvas.itemconfigure(
                    edge_items.line,
                    dash=self._reconnect_original_dash,
                    width=self._reconnect_original_width,
                )
            except tk.TclError:
                pass

        hit_type, info = self._hit_test(event.x, event.y)
        if hit_type == HIT_PORT:
            port_label = info.get(KEY_PORT_LABEL, "")
            target_node = info.get(KEY_NODE_ID, "")

            if state.side == SIDE_SOURCE and port_label != PORT_IN and target_node != state.anchor_node:
                self._callback(
                    CB_EDGE_RECONNECTED,
                    edge_id=state.edge_id,
                    side=SIDE_SOURCE,
                    new_node_id=target_node,
                    new_port=port_label,
                )
            elif state.side == SIDE_TARGET and port_label == PORT_IN and target_node != state.anchor_node:
                self._callback(
                    CB_EDGE_RECONNECTED,
                    edge_id=state.edge_id,
                    side=SIDE_TARGET,
                    new_node_id=target_node,
                    new_port=PORT_IN,
                )

        self._reconnect_state = None
        self._mode = InteractionMode.IDLE

    def _start_midpoint_connect(self, event: tk.Event, info: dict) -> None:
        edge_id = info[KEY_EDGE_ID]
        graph = self._get_graph()
        if not graph:
            return
        edge = graph.get_edge(edge_id)
        if not edge:
            return

        offset_x, offset_y, zoom = self._get_viewport()
        endpoints = _edge_endpoints(edge, graph, offset_x, offset_y, zoom)
        if endpoints is None:
            return
        sx, sy = endpoints[0], endpoints[1]
        from_key = f"{PORT_OUT_PREFIX}{edge.label}"
        from_node = graph.get_node(edge.from_node)
        assert from_node is not None
        ports = port_positions(from_node)
        if from_key not in ports:
            from_key = PORT_OUT_DEFAULT

        self._mode = InteractionMode.CONNECTING
        self._connect_from_node = edge.from_node
        self._connect_from_label = from_key
        self._connect_from_sx = sx
        self._connect_from_sy = sy

        self._temp_edge_id = render_temp_edge(
            self._canvas,
            sx, sy, event.x, event.y,
            style=self._get_edge_style(),
        )

    def _update_port_highlight(self, info: dict | None) -> None:
        self._connect_port_highlight.clear(self._canvas)

        if not info:
            return

        item_id = info.get(KEY_ITEM_ID)
        if not item_id:
            return

        self._connect_port_highlight.apply(
            self._canvas, item_id, current_theme().accent_green, _PORT_HIGHLIGHT_SCALE,
        )

    def _reset_auto_insert_state(self) -> None:
        if self._auto_insert_candidate:
            self._callback(CB_AUTO_INSERT_CLEAR)
        self._can_auto_insert = False
        self._auto_insert_candidate = None
