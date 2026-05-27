"""节点类型颜色映射 — NodeType → 主题色"""

from src.core.flow import NodeType
from src.panel.canvas.node_shared import PORT_IN, PORT_OUT_TRUE, PORT_OUT_FALSE, PORT_OUT_LOOP, PORT_OUT_EXIT
from src.panel.canvas.theme.tokens import CanvasTheme
from src.panel.canvas.theme.theme_manager import current_theme
from src.panel.models.enums import EdgeLabel

_NODE_ACCENT: dict[NodeType, tuple[str, str]] = {
    NodeType.START:     ("accent_green",  "accent_green_dim"),
    NodeType.END:       ("accent_red",    "accent_red_dim"),
    NodeType.ACTION:    ("accent_blue",   "accent_blue_dim"),
    NodeType.CONDITION: ("accent_orange", "accent_orange_dim"),
    NodeType.MERGE:     ("accent_gray",   "accent_gray_dim"),
    NodeType.LOOP:      ("accent_mauve",  "accent_mauve_dim"),
}
_NODE_DEFAULT = ("accent_blue", "accent_blue_dim")


def node_fill_color(node_type: NodeType, theme: CanvasTheme | None = None) -> str:
    t = theme or current_theme()
    fill, _ = _NODE_ACCENT.get(node_type, _NODE_DEFAULT)
    return getattr(t, fill)


def node_border_color(node_type: NodeType, theme: CanvasTheme | None = None) -> str:
    t = theme or current_theme()
    _, border = _NODE_ACCENT.get(node_type, _NODE_DEFAULT)
    return getattr(t, border)


def port_fill_color(label: str, theme: CanvasTheme | None = None) -> str:
    t = theme or current_theme()
    if label == PORT_IN: return t.port_in_fill
    if label == PORT_OUT_TRUE: return t.edge_true
    if label == PORT_OUT_FALSE: return t.edge_false
    if label == PORT_OUT_LOOP: return t.edge_loop
    if label == PORT_OUT_EXIT: return t.edge_exit
    return t.edge_default


def edge_color_by_label(label: str, theme: CanvasTheme | None = None) -> str:
    t = theme or current_theme()
    if label == EdgeLabel.TRUE: return t.edge_true
    if label == EdgeLabel.FALSE: return t.edge_false
    if label == EdgeLabel.DEFAULT: return t.edge_default
    if label == EdgeLabel.TIMEOUT: return t.edge_timeout
    if label == EdgeLabel.LOOP: return t.edge_loop
    if label == EdgeLabel.EXIT: return t.edge_exit
    return t.edge_default
