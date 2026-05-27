"""EdgeRenderer — 流程连线渲染器 (Phase 3)

改进:
- 贝塞尔曲线平滑度 20→36 splinesteps
- 控制点优化: 短/中/长距离自适应偏移
- 上行边水平绕行偏移增加 30%
- 标签位置 t=0.35 (偏向源端)
- 药丸形圆角标签背景
- 连接验证反馈 (有效端口变绿/放大)
"""

from dataclasses import dataclass, field

import tkinter as tk

from src.core.flow import FlowEdge, FlowGraph
from src.panel.canvas.edge_geometry import (
    bezier_control_points,
    edge_label_text,
    estimate_text_width,
    orthogonal_waypoints,
    resolve_edge_world_coords,
)
from src.panel.canvas.node_renderer import port_positions
from src.panel.models.enums import EdgeStyle
from src.panel.canvas.theme import current_theme, edge_color_by_label, mix_colors


def cubic_bezier_point(
    x1: float, y1: float,
    cp1x: float, cp1y: float,
    cp2x: float, cp2y: float,
    x2: float, y2: float,
    t: float,
) -> tuple[float, float]:
    """三次贝塞尔曲线在参数 t 处的坐标。"""
    u = 1 - t
    x = u**3 * x1 + 3 * u**2 * t * cp1x + 3 * u * t**2 * cp2x + t**3 * x2
    y = u**3 * y1 + 3 * u**2 * t * cp1y + 3 * u * t**2 * cp2y + t**3 * y2
    return x, y


@dataclass
class EdgeCanvasItems:
    """一条边在 canvas 上的所有图形元素 ID"""

    line: int = 0
    glow_layers: list[int] = field(default_factory=list)
    label_bg: int = 0
    label_text: int = 0
    # 端点手柄: source (尾) / target (头/箭头)
    source_handle: int = 0
    target_handle: int = 0


def _edge_endpoints(
    edge: FlowEdge,
    graph: FlowGraph,
    offset_x: float,
    offset_y: float,
    zoom: float,
) -> tuple[float, float, float, float] | None:
    """计算连线的起止屏幕坐标

    返回 (x1, y1, x2, y2) 或 None（节点不存在时）
    """
    result = resolve_edge_world_coords(edge, graph, port_positions)
    if result is None:
        return None

    (fx, fy), (tx, ty) = result
    x1 = (fx - offset_x) * zoom
    y1 = (fy - offset_y) * zoom
    x2 = (tx - offset_x) * zoom
    y2 = (ty - offset_y) * zoom
    return x1, y1, x2, y2


# ── 贝塞尔曲线控制点 ──────────────────────────────────────

def _bezier_points(
    x1: float, y1: float, x2: float, y2: float, zoom: float
) -> tuple[float, ...]:
    """计算贝塞尔曲线控制点"""
    dx = x2 - x1
    dy = y2 - y1
    dist = (dx * dx + dy * dy) ** 0.5

    if dist < 1:
        return x1, y1, x1, y1 + 20 * zoom, x2, y2 + 20 * zoom, x2, y2

    cp1x, cp1y, cp2x, cp2y = bezier_control_points(x1, y1, x2, y2, zoom)
    return x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2


def _orthogonal_points(
    x1: float, y1: float, x2: float, y2: float, zoom: float
) -> tuple[float, ...]:
    """直角折线路径点"""
    waypoints = orthogonal_waypoints(x1, y1, x2, y2, zoom)
    if len(waypoints) == 2 and (y2 - y1) >= 0:
        (_, mid_y), (x2m, _) = waypoints
        return x1, y1, x1, mid_y, x2m, mid_y, x2, y2
    else:
        (side, _), (_, _) = waypoints
        return x1, y1, side, y1, side, y2, x2, y2


def _compute_line_points(
    x1: float, y1: float, x2: float, y2: float, zoom: float, style: str
) -> tuple[float, ...]:
    """根据样式计算线段坐标点"""
    if style == EdgeStyle.STRAIGHT:
        return x1, y1, x2, y2
    elif style == EdgeStyle.ORTHOGONAL:
        return _orthogonal_points(x1, y1, x2, y2, zoom)
    else:
        return _bezier_points(x1, y1, x2, y2, zoom)


def _line_kwargs(style: str, zoom: float) -> dict:
    """根据样式返回 create_line 的额外参数"""
    kwargs: dict = {
        "arrow": tk.LAST,
        "arrowshape": (10 * zoom, 12 * zoom, 5 * zoom),
        "width": max(2, 2.5 * zoom),
    }
    if style == EdgeStyle.BEZIER:
        kwargs["smooth"] = True
        kwargs["splinesteps"] = 36
    return kwargs


def _pill_size(text: str, zoom: float, font_size: int) -> tuple[float, float]:
    """计算药丸标签背景的 half_w, half_h"""
    text_w = estimate_text_width(text, font_size)
    pad_x = 8 * zoom
    pad_y = 5 * zoom
    return text_w / 2 + pad_x, font_size / 2 + pad_y


# ── 标签位置计算 ──────────────────────────────────────────

def _label_position(
    x1: float, y1: float, x2: float, y2: float,
    points: tuple[float, ...], style: str, t_param: float = 0.35,
) -> tuple[float, float]:
    """计算标签位置 (默认 t=0.35 偏向源端)

    对于贝塞尔曲线，使用德卡斯特里奥算法在 t 处取值。
    对于其他样式，使用线性插值。
    """
    if style == EdgeStyle.BEZIER and len(points) == 8:
        _, _, cp1x, cp1y, cp2x, cp2y, _, _ = points
        return cubic_bezier_point(x1, y1, cp1x, cp1y, cp2x, cp2y, x2, y2, t_param)
    else:
        return x1 + (x2 - x1) * t_param, y1 + (y2 - y1) * t_param


# ── 渲染 ──────────────────────────────────────────────────

def render_edge(
    canvas: tk.Canvas,
    edge: FlowEdge,
    graph: FlowGraph,
    offset_x: float,
    offset_y: float,
    zoom: float,
    style: str = EdgeStyle.BEZIER,
) -> EdgeCanvasItems | None:
    """在 canvas 上绘制一条连线"""
    items = EdgeCanvasItems()

    endpoints = _edge_endpoints(edge, graph, offset_x, offset_y, zoom)
    if endpoints is None:
        return None
    x1, y1, x2, y2 = endpoints

    tag = f"edge:{edge.edge_id}"
    theme = current_theme()
    color = edge_color_by_label(edge.label, theme)

    points = _compute_line_points(x1, y1, x2, y2, zoom, style)

    line_kwargs = _line_kwargs(style, zoom)
    items.line = canvas.create_line(
        *points,
        fill=color,
        tags=(tag, "edge"),
        **line_kwargs,
    )

    # 端点手柄: source (尾) — 实心圆, target (头) — 菱形
    handle_r = max(4, 6 * zoom)
    # Source 手柄: 实心圆 (边的起始端, from_node 出端口)
    items.source_handle = canvas.create_oval(
        x1 - handle_r, y1 - handle_r, x1 + handle_r, y1 + handle_r,
        fill=theme.edge_source_handle, outline=theme.edge_target_handle,
        width=1, tags=(tag, "edge", "edge_handle", "edge_source_handle"),
    )
    # Target 手柄: 菱形 (边的终止端, to_node 入端口, 箭头端)
    dr = handle_r * 0.75
    items.target_handle = canvas.create_polygon(
        x2, y2 - dr, x2 + dr, y2, x2, y2 + dr, x2 - dr, y2,
        fill=theme.edge_target_handle, outline=theme.edge_source_handle,
        width=1, tags=(tag, "edge", "edge_handle", "edge_target_handle"),
    )

    # 药丸形标签
    label_text = edge_label_text(edge.label)
    if label_text:
        lx, ly = _label_position(x1, y1, x2, y2, points, style, t_param=0.35)
        font_size = max(8, int(9 * zoom))

        half_w, half_h = _pill_size(label_text, zoom, font_size)

        items.label_bg = canvas.create_rectangle(
            lx - half_w, ly - half_h,
            lx + half_w, ly + half_h,
            fill=theme.bg_primary,
            outline=color,
            width=max(1, int(1.5 * zoom)),
            tags=(tag, "edge_label_bg"),
        )
        items.label_text = canvas.create_text(
            lx, ly,
            text=label_text,
            fill=theme.text_primary,
            font=(theme.font_family, font_size, "bold"),
            tags=(tag, "edge_label"),
        )

    return items


def update_edge(
    canvas: tk.Canvas,
    items: EdgeCanvasItems,
    edge: FlowEdge,
    graph: FlowGraph,
    offset_x: float,
    offset_y: float,
    zoom: float,
    style: str = EdgeStyle.BEZIER,
) -> None:
    """增量更新一条边的位置（拖拽时用）"""
    endpoints = _edge_endpoints(edge, graph, offset_x, offset_y, zoom)
    if endpoints is None:
        return
    x1, y1, x2, y2 = endpoints

    points = _compute_line_points(x1, y1, x2, y2, zoom, style)
    canvas.coords(items.line, *points)

    # 更新辉光层位置（避免拖拽时残影）
    for gid in items.glow_layers:
        try:
            canvas.coords(gid, *points)
        except tk.TclError:
            pass

    # 更新端点手柄位置
    handle_r = max(4, 6 * zoom)
    if items.source_handle:
        try:
            canvas.coords(
                items.source_handle,
                x1 - handle_r, y1 - handle_r, x1 + handle_r, y1 + handle_r,
            )
        except tk.TclError:
            pass
    if items.target_handle:
        dr = handle_r * 0.75
        try:
            canvas.coords(
                items.target_handle,
                x2, y2 - dr, x2 + dr, y2, x2, y2 + dr, x2 - dr, y2,
            )
        except tk.TclError:
            pass

    label_text = edge_label_text(edge.label)
    if items.label_text and label_text:
        lx, ly = _label_position(x1, y1, x2, y2, points, style, t_param=0.35)

        font_size = max(8, int(9 * zoom))
        half_w, half_h = _pill_size(label_text, zoom, font_size)

        if items.label_bg:
            canvas.coords(
                items.label_bg,
                lx - half_w, ly - half_h,
                lx + half_w, ly + half_h,
            )
        canvas.coords(items.label_text, lx, ly)


# ── 临时连线 (连接拖拽预览) ───────────────────────────────

def render_temp_edge(
    canvas: tk.Canvas,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    style: str = EdgeStyle.BEZIER,
    tag: str = "temp_edge",
    valid_target: bool = False,
) -> int:
    """绘制临时连线（拖拽中预览用）

    valid_target: 是否悬停在有效端口上（影响样式）
    """
    points = _compute_line_points(x1, y1, x2, y2, 1.0, style)
    theme = current_theme()

    color = theme.accent_green if valid_target else theme.edge_default
    dash = () if valid_target else (6, 4)

    line_kwargs: dict = {
        "arrow": tk.LAST,
        "arrowshape": (8, 10, 4),
        "fill": color,
        "width": 2.5 if not valid_target else 3,
        "dash": dash,
        "tags": (tag,),
    }
    if style == EdgeStyle.BEZIER:
        line_kwargs["smooth"] = True
        line_kwargs["splinesteps"] = 36

    return canvas.create_line(*points, **line_kwargs)


def update_temp_edge(
    canvas: tk.Canvas,
    item_id: int,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    style: str = EdgeStyle.BEZIER,
    valid_target: bool = False,
) -> None:
    """更新临时连线终点"""
    points = _compute_line_points(x1, y1, x2, y2, 1.0, style)
    canvas.coords(item_id, *points)

    theme = current_theme()
    color = theme.accent_green if valid_target else theme.edge_default
    dash = () if valid_target else (6, 4)
    canvas.itemconfigure(item_id, fill=color, dash=dash, width=3 if valid_target else 2.5)


# ── 边高亮效果 (悬停/选中共用) ────────────────────────────

def _ensure_glow_layers(
    canvas: tk.Canvas,
    items: EdgeCanvasItems,
    points: tuple[float, ...],
    style: str,
    tag: str,
    count: int,
) -> list[int]:
    """确保辉光层数量正确，复用已有 item。"""
    existing = items.glow_layers
    glow_kwargs: dict = {"smooth": True, "splinesteps": 36} if style == EdgeStyle.BEZIER else {}

    # 复用已有层
    for gid in existing[:count]:
        canvas.coords(gid, *points)
        canvas.itemconfigure(gid, state="normal")

    # 多余层隐藏
    for gid in existing[count:]:
        canvas.itemconfigure(gid, state="hidden")

    # 不足则创建新层
    new_layers = list(existing)
    for i in range(len(new_layers), count):
        gid = canvas.create_line(
            *points,
            fill="",
            width=1,
            tags=(tag, "edge", "edge_glow"),
            **glow_kwargs,
        )
        canvas.tag_lower(gid, items.line)
        new_layers.append(gid)

    items.glow_layers = new_layers
    return new_layers[:count]


def _apply_edge_highlight(
    canvas: tk.Canvas,
    items: EdgeCanvasItems,
    edge: FlowEdge,
    graph: FlowGraph,
    offset_x: float,
    offset_y: float,
    zoom: float,
    style: str,
    color: str,
    line_width: float,
    glow_widths: tuple[float, ...],
    glow_alphas: tuple[float, ...],
    change_fill: bool = False,
    dash: tuple[int, ...] | None = None,
) -> None:
    """边高亮共用实现: 加粗主线 + 多层辉光"""
    kw: dict = {"width": line_width}
    if change_fill:
        kw["fill"] = color
    if dash is not None:
        kw["dash"] = dash
    canvas.itemconfigure(items.line, **kw)

    endpoints = _edge_endpoints(edge, graph, offset_x, offset_y, zoom)
    if endpoints is None:
        return
    points = _compute_line_points(*endpoints, zoom, style)
    tag = f"edge:{edge.edge_id}"

    layers = _ensure_glow_layers(canvas, items, points, style, tag, len(glow_alphas))
    theme = current_theme()
    for gid, gw, ga in zip(layers, glow_widths, glow_alphas):
        blended = mix_colors(theme.bg_primary, color, ga)
        canvas.itemconfigure(gid, fill=blended, width=gw)


def _clear_edge_highlight(
    canvas: tk.Canvas,
    items: EdgeCanvasItems,
    zoom: float,
    restore_fill: str | None = None,
) -> None:
    """清除边高亮: 恢复默认线宽 + 虚线 + 可选恢复填充色"""
    kw: dict = {"width": max(2, 2.5 * zoom), "dash": ()}
    if restore_fill is not None:
        kw["fill"] = restore_fill
    canvas.itemconfigure(items.line, **kw)
    for gid in items.glow_layers:
        canvas.itemconfigure(gid, state="hidden")


def set_edge_hover(
    canvas: tk.Canvas,
    items: EdgeCanvasItems,
    edge: FlowEdge,
    graph: FlowGraph,
    offset_x: float,
    offset_y: float,
    zoom: float,
    style: str = EdgeStyle.BEZIER,
) -> None:
    """设置边悬停: 线宽 x1.5 + 多层辉光"""
    theme = current_theme()
    color = edge_color_by_label(edge.label, theme)
    base_w = max(2, 2.5 * zoom)
    _apply_edge_highlight(
        canvas, items, edge, graph, offset_x, offset_y, zoom, style,
        color=color,
        line_width=max(3, 4 * zoom),
        glow_widths=(base_w + 6, base_w + 3, base_w + 1.5),
        glow_alphas=theme.edge_hover_glow_alphas,
    )


def clear_edge_hover(canvas: tk.Canvas, items: EdgeCanvasItems, zoom: float) -> None:
    """清除边悬停效果"""
    _clear_edge_highlight(canvas, items, zoom)


def set_edge_selected(
    canvas: tk.Canvas,
    items: EdgeCanvasItems,
    edge: FlowEdge,
    graph: FlowGraph,
    offset_x: float,
    offset_y: float,
    zoom: float,
    style: str = EdgeStyle.BEZIER,
) -> None:
    """设置边选中状态: 加粗 + 高亮色 + 辉光 + 虚线"""
    theme = current_theme()
    base_w = max(2, 2.5 * zoom)
    _apply_edge_highlight(
        canvas, items, edge, graph, offset_x, offset_y, zoom, style,
        color=theme.accent_blue,
        line_width=max(3.5, 4 * zoom),
        glow_widths=(base_w + 8, base_w + 4, base_w + 2),
        glow_alphas=theme.edge_selected_glow_alphas,
        change_fill=True,
        dash=theme.edge_selected_dash,
    )


def clear_edge_selected(
    canvas: tk.Canvas,
    items: EdgeCanvasItems,
    edge: FlowEdge,
    zoom: float,
) -> None:
    """清除边选中状态"""
    theme = current_theme()
    color = edge_color_by_label(edge.label, theme)
    _clear_edge_highlight(canvas, items, zoom, restore_fill=color)

