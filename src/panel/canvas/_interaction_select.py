"""SelectMixin — 框选/选中/多选拖拽逻辑。"""

from __future__ import annotations

from typing import TYPE_CHECKING

import tkinter as tk

from src.panel.canvas._interaction_types import (
    CB_CANVAS_DESELECTED,
    CB_DRAG_STARTED,
    CB_EDGE_DESELECTED,
    CB_EDGE_SELECTED,
    CB_NODE_SELECTED,
    CB_NODES_SELECTED,
    KEY_NODE_ID,
    _CLICK_MOTION_THRESHOLD,
    _SELECT_MODIFY_MASK,
    InteractionMode,
)
from src.panel.canvas.node_shared import (
    FONT_BOLD,
    TAG_SELECTION_HIGHLIGHT,
    TAG_SELECT_RECT,
)
from src.panel.canvas.theme import current_theme

if TYPE_CHECKING:
    from src.panel.canvas.graph_canvas import GraphCanvas


class SelectMixin:
    """选中交互方法，供 InteractionHandler 继承。"""

    _canvas: GraphCanvas
    _get_graph: object
    _callback: object
    _mode: InteractionMode
    _selected_node_ids: set[str]
    _selected_edge_id: str | None
    _select_start_sx: float
    _select_start_sy: float
    _select_rect_id: int | None
    _select_count_id: int | None
    _last_select_count: int
    _select_additive: bool
    _multi_drag_offsets: dict[str, tuple[float, float]]

    def _start_selecting(self, event: tk.Event) -> None:
        self._mode = InteractionMode.SELECTING
        self._select_start_sx = event.x
        self._select_start_sy = event.y
        self._select_rect_id = None
        self._last_select_count = -1
        mods = event.state if isinstance(event.state, int) else 0
        self._select_additive = bool(mods & _SELECT_MODIFY_MASK)
        if not self._select_additive:
            self._selected_node_ids.clear()
            self._clear_edge_selection()

    def _do_select(self, event: tk.Event) -> None:
        x1 = min(self._select_start_sx, event.x)
        y1 = min(self._select_start_sy, event.y)
        x2 = max(self._select_start_sx, event.x)
        y2 = max(self._select_start_sy, event.y)

        theme = current_theme()
        if self._select_rect_id is None:
            self._select_rect_id = self._canvas.create_rectangle(
                x1, y1, x2, y2,
                fill="",
                outline=theme.selection_box, width=1.5, dash=(6, 3),
                tags=(TAG_SELECT_RECT,),
            )
        else:
            self._canvas.coords(self._select_rect_id, x1, y1, x2, y2)

        graph = self._get_graph()
        if graph:
            w1x, w1y = self._canvas.screen_to_world(x1, y1)
            w2x, w2y = self._canvas.screen_to_world(x2, y2)
            count = len(self._nodes_in_world_rect(graph, w1x, w1y, w2x, w2y))
            if count > 0:
                bx = x2 + 6
                by = y1 - 6
                if count != self._last_select_count:
                    self._last_select_count = count
                    badge_text = f"{count}"
                    font_size = 10
                    if self._select_count_id:
                        self._canvas.coords(self._select_count_id, bx, by)
                        self._canvas.itemconfigure(self._select_count_id, text=badge_text)
                    else:
                        self._select_count_id = self._canvas.create_text(
                            bx, by, text=badge_text,
                            fill=theme.text_on_accent,
                            font=(theme.font_family, font_size, FONT_BOLD),
                            anchor="se",
                            tags=(TAG_SELECT_RECT,),
                        )
                elif self._select_count_id:
                    self._canvas.coords(self._select_count_id, bx, by)
            elif self._select_count_id:
                self._canvas.delete(self._select_count_id)
                self._select_count_id = None
                self._last_select_count = -1

    def _end_select(self, event: tk.Event) -> None:
        if self._select_rect_id is not None:
            self._canvas.delete(self._select_rect_id)
            self._select_rect_id = None
        if self._select_count_id is not None:
            self._canvas.delete(self._select_count_id)
            self._select_count_id = None

        dx = abs(event.x - self._select_start_sx)
        dy = abs(event.y - self._select_start_sy)
        if dx < _CLICK_MOTION_THRESHOLD and dy < _CLICK_MOTION_THRESHOLD:
            if not self._select_additive:
                self._selected_node_ids.clear()
                self._callback(CB_CANVAS_DESELECTED)
            self._mode = InteractionMode.IDLE
            return

        x1 = min(self._select_start_sx, event.x)
        y1 = min(self._select_start_sy, event.y)
        x2 = max(self._select_start_sx, event.x)
        y2 = max(self._select_start_sy, event.y)

        graph = self._get_graph()
        if not graph:
            self._mode = InteractionMode.IDLE
            return

        if not self._select_additive:
            self._selected_node_ids.clear()

        w1x, w1y = self._canvas.screen_to_world(x1, y1)
        w2x, w2y = self._canvas.screen_to_world(x2, y2)
        new_ids = self._nodes_in_world_rect(graph, w1x, w1y, w2x, w2y)

        if self._select_additive:
            self._selected_node_ids = self._selected_node_ids | new_ids
        else:
            self._selected_node_ids = new_ids

        if len(self._selected_node_ids) == 1:
            node_id = next(iter(self._selected_node_ids))
            self._callback(CB_NODE_SELECTED, node_id=node_id)
        elif len(self._selected_node_ids) > 1:
            self._callback(CB_NODES_SELECTED, node_ids=list(self._selected_node_ids))
        else:
            self._callback(CB_CANVAS_DESELECTED)

        self._mode = InteractionMode.IDLE

    def _start_multi_drag(self, event: tk.Event, info: dict) -> None:
        self._mode = InteractionMode.DRAGGING_NODE
        self._drag_node_id = info[KEY_NODE_ID]
        self._drag_start_sx = event.x
        self._drag_start_sy = event.y

        self._canvas.configure(cursor="fleur")

        wx, wy = self._canvas.screen_to_world(event.x, event.y)
        self._multi_drag_offsets.clear()

        graph = self._get_graph()
        if not graph:
            return

        for nid in self._selected_node_ids:
            node = graph.get_node(nid)
            if node:
                self._multi_drag_offsets[nid] = (wx - node.pos_x, wy - node.pos_y)

        self._callback(CB_DRAG_STARTED, node_ids=list(self._selected_node_ids))

    def _select_node(self, node_id: str) -> None:
        self._clear_edge_selection()
        self._selected_node_ids = {node_id}
        self._callback(CB_NODE_SELECTED, node_id=node_id)

    def _select_edge(self, edge_id: str) -> None:
        self._selected_node_ids.clear()
        self._canvas.delete(TAG_SELECTION_HIGHLIGHT)
        if self._selected_edge_id == edge_id:
            return
        self._clear_edge_selection()
        self._selected_edge_id = edge_id
        self._callback(CB_EDGE_SELECTED, edge_id=edge_id)

    def _clear_edge_selection(self) -> None:
        if self._selected_edge_id:
            old_id = self._selected_edge_id
            self._selected_edge_id = None
            self._callback(CB_EDGE_DESELECTED, edge_id=old_id)

    def get_selected_edge(self) -> str | None:
        return self._selected_edge_id

    def _toggle_node_in_selection(self, node_id: str) -> None:
        self._clear_edge_selection()
        if node_id in self._selected_node_ids:
            self._selected_node_ids = self._selected_node_ids - {node_id}
        else:
            self._selected_node_ids = self._selected_node_ids | {node_id}

        count = len(self._selected_node_ids)
        if count == 1:
            self._callback(CB_NODE_SELECTED, node_id=next(iter(self._selected_node_ids)))
        elif count > 1:
            self._callback(CB_NODES_SELECTED, node_ids=list(self._selected_node_ids))
        else:
            self._callback(CB_CANVAS_DESELECTED)

    def select_all(self) -> set[str]:
        graph = self._get_graph()
        if not graph:
            return set()
        self._selected_node_ids = set(graph.nodes.keys())
        self._callback(CB_NODES_SELECTED, node_ids=list(self._selected_node_ids))
        return self._selected_node_ids

    def get_selected_nodes(self) -> set[str]:
        return set(self._selected_node_ids)
