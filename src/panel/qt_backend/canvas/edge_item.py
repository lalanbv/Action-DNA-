"""QtEdgeItem — PySide6 DAG edge graphics item.

替代 tkinter edge_renderer.py，使用 QGraphicsPathItem 原生贝塞尔曲线，
消除手动 splinesteps 和坐标变换。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush, QColor, QFont, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QStyleOptionGraphicsItem, QWidget,
)

from src.core.flow import FlowEdge, FlowGraph
from src.panel.canvas.edge_geometry import (
    bezier_control_points,
    edge_label_text,
    orthogonal_waypoints,
    resolve_edge_world_coords,
)
from src.panel.canvas.theme import current_theme, edge_color_by_label
from src.panel.models.enums import EdgeStyle
from src.panel.canvas.node_shared import port_positions

_ANIMATION_PHASE_MAX = 20


def _edge_endpoints(
    edge: FlowEdge, graph: FlowGraph,
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    return resolve_edge_world_coords(edge, graph, port_positions)


def _bezier_path(
    x1: float, y1: float, x2: float, y2: float,
) -> QPainterPath:
    dx = x2 - x1
    dy = y2 - y1
    dist = (dx * dx + dy * dy) ** 0.5

    path = QPainterPath(QPointF(x1, y1))
    if dist < 1:
        path.lineTo(x2, y2)
        return path

    cp1x, cp1y, cp2x, cp2y = bezier_control_points(x1, y1, x2, y2)
    path.cubicTo(QPointF(cp1x, cp1y), QPointF(cp2x, cp2y), QPointF(x2, y2))
    return path


def _orthogonal_path(
    x1: float, y1: float, x2: float, y2: float,
) -> QPainterPath:
    path = QPainterPath(QPointF(x1, y1))
    waypoints = orthogonal_waypoints(x1, y1, x2, y2)
    for wx, wy in waypoints:
        path.lineTo(wx, wy)
    path.lineTo(x2, y2)
    return path


def _compute_path(
    x1: float, y1: float, x2: float, y2: float, style: str,
) -> QPainterPath:
    if style == EdgeStyle.STRAIGHT:
        path = QPainterPath(QPointF(x1, y1))
        path.lineTo(x2, y2)
        return path
    elif style == EdgeStyle.ORTHOGONAL:
        return _orthogonal_path(x1, y1, x2, y2)
    else:
        return _bezier_path(x1, y1, x2, y2)


class QtEdgeItem(QGraphicsItem):
    """Single QGraphicsPathItem for a DAG edge — line + optional label."""

    def __init__(
        self,
        edge: FlowEdge,
        graph: FlowGraph,
        style: str = EdgeStyle.BEZIER,
        canvas=None,
    ) -> None:
        super().__init__()
        self._edge = edge
        self._graph = graph
        self._style = style
        self._canvas = canvas
        self._is_hover = False
        self._is_selected = False
        self._is_auto_insert = False
        self._is_animating = False
        self._is_paused = False
        self._animation_phase = 0
        self._cached_base_color = edge_color_by_label(edge.label, current_theme())

        self._rebuild_path()
        self.setAcceptHoverEvents(True)
        self.setZValue(-1)

    @property
    def edge(self) -> FlowEdge:
        return self._edge

    @property
    def edge_id(self) -> str:
        return self._edge.edge_id

    def _rebuild_path(self) -> None:
        endpoints = _edge_endpoints(self._edge, self._graph)
        if endpoints is None:
            self._path = QPainterPath()
            self._source = (0, 0)
            self._target = (0, 0)
            return

        (x1, y1), (x2, y2) = endpoints
        self._source = (x1, y1)
        self._target = (x2, y2)
        self._path = _compute_path(x1, y1, x2, y2, self._style)
        self.prepareGeometryChange()

    def update_from_edge(self, edge: FlowEdge, graph: FlowGraph) -> None:
        self._edge = edge
        self._graph = graph
        self._cached_base_color = edge_color_by_label(edge.label, current_theme())
        self._rebuild_path()
        self.update()

    def update_style(self, style: str) -> None:
        self._style = style
        self._rebuild_path()
        self.update()

    def set_hover(self, hover: bool) -> None:
        self._is_hover = hover
        self.update()

    def set_selected(self, selected: bool) -> None:
        self._is_selected = selected
        self.update()

    def set_auto_insert(self, auto: bool) -> None:
        self._is_auto_insert = auto
        self.update()

    def set_animating(self, animating: bool) -> None:
        if self._is_animating == animating:
            return
        self._is_animating = animating
        self.update()

    def set_paused_visual(self, paused: bool) -> None:
        self._is_paused = paused
        self.update()

    def apply_theme(self) -> None:
        th = current_theme()
        self._cached_base_color = edge_color_by_label(self._edge.label, th)
        self.update()

    def advance_animation(self) -> None:
        self._animation_phase = (self._animation_phase + 1) % _ANIMATION_PHASE_MAX
        self.update()

    def _label_pos(self, t_param: float = 0.35) -> tuple[float, float]:
        if self._style == EdgeStyle.BEZIER and not self._path.isEmpty():
            length = self._path.length()
            if length < 1:
                return self._source
            target = t_param * length
            pt = self._path.pointAtPercent(min(1.0, self._path.percentAtLength(target)))
            return pt.x(), pt.y()
        x1, y1 = self._source
        x2, y2 = self._target
        return x1 + (x2 - x1) * t_param, y1 + (y2 - y1) * t_param

    def boundingRect(self) -> QRectF:
        margin = 20
        return self._path.boundingRect().adjusted(-margin, -margin, margin, margin)

    def shape(self) -> QPainterPath:
        stroked = QPainterPath(self._path)
        stroked.closeSubpath()
        return stroked

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        if self._path.isEmpty():
            return

        th = current_theme()
        color = self._cached_base_color
        line_width = 2.5

        if self._is_auto_insert or self._is_selected:
            color = th.accent_blue
        if self._is_auto_insert:
            line_width = 5.0
        elif self._is_selected:
            line_width = 4.0
            glow_color = QColor(color)
            glow_color.setAlpha(60)
            painter.setPen(QPen(glow_color, 10))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._path)

        if self._is_hover:
            line_width = 4.0
            glow_color = QColor(color)
            glow_color.setAlpha(40)
            painter.setPen(QPen(glow_color, 8))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(self._path)

        pen = QPen(QColor(color), line_width)
        if self._is_auto_insert:
            pen.setDashPattern([8, 4])
        elif self._is_paused:
            pen.setDashPattern([6, 3])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawPath(self._path)

        self._paint_arrow(painter, color, line_width)
        self._paint_label(painter, th)
        self._paint_flow_animation(painter, th, color)

    def _paint_arrow(self, painter: QPainter, color: str, line_width: float) -> None:
        if self._path.isEmpty():
            return
        t = 0.98
        p_end = self._path.pointAtPercent(t)
        p_before = self._path.pointAtPercent(max(0, t - 0.05))
        dx = p_end.x() - p_before.x()
        dy = p_end.y() - p_before.y()
        length = (dx * dx + dy * dy) ** 0.5
        if length < 0.1:
            return

        dx /= length
        dy /= length
        arrow_size = max(6, line_width * 3)

        p1 = QPointF(
            p_end.x() - arrow_size * dx + arrow_size * 0.5 * dy,
            p_end.y() - arrow_size * dy - arrow_size * 0.5 * dx,
        )
        p2 = QPointF(
            p_end.x() - arrow_size * dx - arrow_size * 0.5 * dy,
            p_end.y() - arrow_size * dy + arrow_size * 0.5 * dx,
        )

        arrow = QPainterPath()
        arrow.moveTo(p_end)
        arrow.lineTo(p1)
        arrow.lineTo(p2)
        arrow.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(arrow)

    def _paint_label(self, painter: QPainter, th) -> None:
        label_text = edge_label_text(self._edge.label)
        if not label_text:
            return

        lx, ly = self._label_pos()

        font = QFont()
        font.setPixelSize(9)
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        text_w = fm.horizontalAdvance(label_text)
        text_h = fm.height()
        pad_x = 6
        pad_y = 3

        bg_rect = QRectF(
            lx - text_w / 2 - pad_x,
            ly - text_h / 2 - pad_y,
            text_w + pad_x * 2,
            text_h + pad_y * 2,
        )

        painter.setPen(QPen(QColor(th.border_default), 1))
        painter.setBrush(QColor(th.bg_primary))
        painter.drawRoundedRect(bg_rect, 4, 4)

        painter.setPen(QColor(th.text_primary))
        painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, label_text)

    def _paint_flow_animation(
        self, painter: QPainter, th, color: str,
    ) -> None:
        if not self._is_animating or self._path.isEmpty() or self._path.length() < 10:
            return

        num_dots = 3
        spacing = _ANIMATION_PHASE_MAX / num_dots
        dot_radius = 2.5

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))

        for i in range(num_dots):
            phase = (self._animation_phase + i * spacing) % _ANIMATION_PHASE_MAX
            t = phase / _ANIMATION_PHASE_MAX
            pt = self._path.pointAtPercent(t)
            painter.drawEllipse(pt, dot_radius, dot_radius)
