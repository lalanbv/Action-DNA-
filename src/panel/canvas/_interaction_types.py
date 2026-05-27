"""InteractionHandler 共享类型和常量。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import tkinter as tk

from src.core.flow import FlowGraph


class InteractionMode(Enum):
    IDLE = auto()
    DRAGGING_NODE = auto()
    CONNECTING = auto()
    RECONNECTING = auto()
    PANNING = auto()
    SELECTING = auto()


@dataclass(frozen=True)
class ReconnectState:
    edge_id: str
    side: str  # "source" | "target"
    anchor_node: str
    anchor_port: str


@dataclass
class _PortHighlight:
    """端口高亮/恢复的共享状态（连接拖拽 + IDLE 悬停复用）"""

    item_id: int | None = None
    original_fill: str = ""
    original_outline: str = ""
    original_coords: tuple[float, ...] = ()

    @property
    def active(self) -> bool:
        return self.item_id is not None

    def apply(
        self, canvas: tk.Canvas, item_id: int, color: str, scale: float,
    ) -> None:
        self.item_id = item_id
        try:
            self.original_fill = canvas.itemcget(item_id, "fill")
            self.original_outline = canvas.itemcget(item_id, "outline")
            coords = canvas.coords(item_id)
            if len(coords) == 4:
                self.original_coords = tuple(coords)

            canvas.itemconfigure(item_id, fill=color, outline=color)

            coords = canvas.coords(item_id)
            if len(coords) == 4:
                cx = (coords[0] + coords[2]) / 2
                cy = (coords[1] + coords[3]) / 2
                r = (coords[2] - coords[0]) / 2 * scale
                canvas.coords(item_id, cx - r, cy - r, cx + r, cy + r)
        except tk.TclError:
            self.item_id = None

    def clear(self, canvas: tk.Canvas) -> None:
        if self.item_id is None:
            return
        try:
            canvas.itemconfigure(
                self.item_id,
                fill=self.original_fill,
                outline=self.original_outline,
            )
            if self.original_coords:
                canvas.coords(self.item_id, *self.original_coords)
        except tk.TclError:
            pass
        self.item_id = None
        self.original_coords = ()


_EDGE_LABEL_TO_PORT: dict[str, str] = {
    v: k for k, v in FlowGraph._PORT_LABEL_TO_EDGE.items() if k != "out"
}

_SHIFT_MASK = 0x1
_CTRL_MASK = 0x4
_META_MASK = 0x40
_SELECT_MODIFY_MASK = _SHIFT_MASK | _CTRL_MASK | _META_MASK
_PORT_HIGHLIGHT_SCALE = 1.5
_PORT_IDLE_HOVER_SCALE = 1.3
_EDGE_ENDPOINT_HIT_RADIUS = 22
_EDGE_MIDPOINT_HIT_RADIUS = 16
_EDGE_HIT_RADIUS = 12
_AUTO_INSERT_THRESHOLD = 50
_CLICK_MOTION_THRESHOLD = 5

# ── Hit-test 结果类型 ─────────────────────────────────────
HIT_PORT = "port"
HIT_NODE = "node"
HIT_EDGE = "edge"
HIT_EDGE_ENDPOINT = "edge_endpoint"
HIT_EDGE_MIDPOINT = "edge_midpoint"
HIT_CANVAS = "canvas"

# ── 重连方向 ─────────────────────────────────────────────
SIDE_SOURCE = "source"
SIDE_TARGET = "target"

# ── Info dict 键名 ───────────────────────────────────────
KEY_NODE_ID = "node_id"
KEY_EDGE_ID = "edge_id"
KEY_PORT_LABEL = "port_label"
KEY_SIDE = "side"
KEY_ITEM_ID = "item_id"

# ── 回调事件名（tkinter / Qt 共享 API）────────────────────
CB_EDGE_CREATED = "edge_created"
CB_EDGE_RECONNECTED = "edge_reconnected"
CB_EDGE_HOVER = "edge_hover"
CB_EDGE_HOVER_CLEAR = "edge_hover_clear"
CB_NODE_HOVER = "node_hover"
CB_NODE_HOVER_CLEAR = "node_hover_clear"
CB_NODE_SELECTED = "node_selected"
CB_NODES_SELECTED = "nodes_selected"
CB_EDGE_SELECTED = "edge_selected"
CB_EDGE_DESELECTED = "edge_deselected"
CB_CANVAS_DESELECTED = "canvas_deselected"
CB_NODE_MOVED = "node_moved"
CB_NODE_DRAGGING = "node_dragging"
CB_DRAG_STARTED = "drag_started"
CB_DRAG_ENDED = "drag_ended"
CB_ZOOM_REQUEST = "zoom_request"
CB_ZOOM_RESET = "zoom_reset"
CB_ZOOM_TO_FIT = "zoom_to_fit"
CB_PAN_REQUEST = "pan_request"
CB_PAN_ENDED = "pan_ended"
CB_DELETE_SELECTED = "delete_selected"
CB_DELETE_EDGE = "delete_edge"
CB_COPY_SELECTED = "copy_selected"
CB_DUPLICATE_SELECTED = "duplicate_selected"
CB_PASTE = "paste"
CB_UNDO = "undo"
CB_REDO = "redo"
CB_SEARCH = "search"
CB_ESCAPE = "escape"
CB_TOGGLE_MINIMAP = "toggle_minimap"
CB_AUTO_INSERT_CLEAR = "auto_insert_clear"
CB_AUTO_INSERT_PREVIEW = "auto_insert_preview"
CB_AUTO_INSERT = "auto_insert"
CB_NODE_DOUBLE_CLICKED = "node_double_clicked"
CB_NODE_CONTEXT_MENU = "node_context_menu"
CB_EDGE_CONTEXT_MENU = "edge_context_menu"
CB_CANVAS_CONTEXT_MENU = "canvas_context_menu"
