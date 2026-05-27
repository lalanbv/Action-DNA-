"""edge_geometry — tkinter / Qt 共享的边几何计算。

纯数学函数，不含任何 GUI 依赖。两个后端导入后各自包装为输出格式：
- tkinter: flat tuple + zoom 缩放
- Qt:      QPainterPath（zoom 传 1.0，缩放由 transform 处理）
"""

from collections.abc import Callable

from src.core.flow import FlowEdge, FlowGraph
from src.panel.canvas.node_shared import PORT_IN, PORT_OUT_DEFAULT, PORT_OUT_PREFIX
from src.panel.models.enums import EdgeLabel
from src.utils.i18n import t

# ── 标签映射（延迟构建，避免 import 时 i18n 未就绪）────

_EDGE_LABEL_KEYS: dict[str, str] = {
    EdgeLabel.TRUE: "workflow.edge.true",
    EdgeLabel.FALSE: "workflow.edge.false",
    EdgeLabel.TIMEOUT: "workflow.edge.timeout",
    EdgeLabel.LOOP: "workflow.edge.loop",
    EdgeLabel.EXIT: "workflow.edge.exit",
}


def edge_label_text(label: str) -> str:
    return t(_EDGE_LABEL_KEYS[label]) if label in _EDGE_LABEL_KEYS else ""


# ── 端口解析 ──────────────────────────────────────────────

def resolve_edge_ports(
    edge: FlowEdge,
    graph: FlowGraph,
    from_port_positions: dict[str, tuple[float, float]],
    to_port_positions: dict[str, tuple[float, float]],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """解析边的源/目标端口坐标。

    返回 ((fx, fy), (tx, ty)) 或 None（端口不存在时）。
    port_positions 由调用方从后端特有的 port_positions() 获取。
    """
    from_key = f"{PORT_OUT_PREFIX}{edge.label}"
    if from_key not in from_port_positions:
        from_key = PORT_OUT_DEFAULT
    if from_key not in from_port_positions:
        return None

    if PORT_IN not in to_port_positions:
        return None

    return from_port_positions[from_key], to_port_positions[PORT_IN]


def resolve_edge_world_coords(
    edge: FlowEdge,
    graph: FlowGraph,
    port_positions_fn: "Callable",
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """解析边的源/目标世界坐标（不含 zoom/offset 变换）。

    port_positions_fn: 后端特有的 port_positions(node) 函数。
    返回 ((fx, fy), (tx, ty)) 或 None。
    """
    from_node = graph.get_node(edge.from_node)
    to_node = graph.get_node(edge.to_node)
    if not from_node or not to_node:
        return None

    return resolve_edge_ports(
        edge, graph,
        port_positions_fn(from_node),
        port_positions_fn(to_node),
    )


# ── 贝塞尔控制点 ──────────────────────────────────────────

def bezier_control_points(
    x1: float, y1: float, x2: float, y2: float, zoom: float = 1.0,
) -> tuple[float, float, float, float]:
    """计算贝塞尔曲线的两个控制点 (cp1x, cp1y, cp2x, cp2y)。

    zoom=1.0 时为 Qt 后端（缩放由 transform 处理）。
    """
    dx = x2 - x1
    dy = y2 - y1
    dist = (dx * dx + dy * dy) ** 0.5

    min_offset = 25 * zoom
    if dist < 80 * zoom:
        ctrl_offset = max(min_offset, dist * 0.4)
    elif dist < 300 * zoom:
        ctrl_offset = dist * 0.35
    else:
        ctrl_offset = min(140 * zoom, dist * 0.3)

    if dy >= 0:
        return x1, y1 + ctrl_offset, x2, y2 - ctrl_offset

    side_offset = max(60 * zoom, abs(dx) * 0.5 + 40 * zoom)
    if dx >= 0:
        return x1 + side_offset, y1, x2 + side_offset, y2
    return x1 - side_offset, y1, x2 - side_offset, y2


# ── 直角折线路径点 ────────────────────────────────────────

def orthogonal_waypoints(
    x1: float, y1: float, x2: float, y2: float, zoom: float = 1.0,
) -> list[tuple[float, float]]:
    """计算直角折线的中间路径点（不含首尾）。

    返回路径点列表：下行边为 [(x1,mid_y),(x2,mid_y)]，
    上行边为 [(side,y1),(side,y2)]。
    """
    dy = y2 - y1

    if dy >= 0:
        mid_y = (y1 + y2) / 2
        return [(x1, mid_y), (x2, mid_y)]

    dx = x2 - x1
    offset = max(40 * zoom, abs(dx) * 0.3 + 30 * zoom) * 1.3
    side = x1 + offset if dx >= 0 else x1 - offset
    return [(side, y1), (side, y2)]


# ── 文本宽度估算 ──────────────────────────────────────────

def estimate_text_width(
    text: str, font_size: int, latin_width: float | None = None,
) -> float:
    """估算文本像素宽度（区分 CJK 宽字符与 Latin 窄字符）。

    latin_width: 单个 Latin 字符的像素宽度。
        默认 font_size * 0.6，minimap 可传 font_size - 2。
    """
    if latin_width is None:
        latin_width = max(3, font_size * 0.6)
    cjk_width = font_size + 2
    w = 0.0
    for ch in text:
        cp = ord(ch)
        if (0x4E00 <= cp <= 0x9FFF
                or 0x3000 <= cp <= 0x303F
                or 0xFF00 <= cp <= 0xFFEF):
            w += cjk_width
        else:
            w += latin_width
    return w
