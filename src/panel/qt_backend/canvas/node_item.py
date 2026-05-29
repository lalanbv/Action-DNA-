"""QtNodeItem — PySide6 DAG node graphics item.

替代 tkinter node_renderer.py 的 _rounded_rect_coords 多边形近似，
使用 QPainterPath 原生圆角矩形，单 QGraphicsWidget 替代 ~15 个 Canvas items。
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsWidget, QStyleOptionGraphicsItem, QWidget,
)

from src.core.flow import FlowNode, NodeType
from src.panel.models.enums import NodeExecutionState
from src.panel.canvas.node_shared import (
    CORNER_RADIUS,
    LOD_MINIMAL,
    LOD_FULL,
    LOD_SIMPLIFIED,
    PORT_RADIUS,
    PORT_VISUAL_RADIUS,
    PORT_DOT_SCALE,
    PORT_LABEL_OFFSET,
    PORT_LABEL_WIDTH,
    PORT_LABEL_HEIGHT,
    NODE_ICONS as _NODE_ICONS,
    body_text_lines as _body_text_lines,
    lod_level,
    node_size,
    node_spec,
    port_label as _port_label,
    port_positions,
)
from src.panel.canvas.theme import (
    current_theme,
    node_fill_color,
    node_border_color,
    port_fill_color,
)

_FONT_MINIMAL = QFont()
_FONT_MINIMAL.setPixelSize(11)

_FONT_HEADER = QFont()
_FONT_HEADER.setPixelSize(12)
_FONT_HEADER.setBold(True)

_FONT_BODY = QFont()
_FONT_BODY.setPixelSize(10)
_FONT_BODY.setBold(True)

_FONT_BODY_SMALL = QFont()
_FONT_BODY_SMALL.setPixelSize(9)

_FONT_PORT = QFont()
_FONT_PORT.setPixelSize(8)


class QtNodeItem(QGraphicsWidget):
    """Single QGraphicsWidget for a DAG node — replaces ~15 Canvas items."""

    def __init__(self, node: FlowNode, canvas=None) -> None:
        super().__init__()
        self._node = node
        self._canvas = canvas
        self._execution_state: str | None = None
        self._is_selected_visual = False
        self._cached_zoom: float = 1.0

        w, h = node_size(node)
        self.setMinimumSize(w, h)
        self.setPreferredSize(w, h)
        self.setMaximumSize(w, h)
        self.setPos(node.pos_x, node.pos_y)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, False)

        self.setZValue(0)

    @property
    def node(self) -> FlowNode:
        return self._node

    @property
    def node_id(self) -> str:
        return self._node.node_id

    def update_from_node(self, node: FlowNode) -> None:
        self._node = node
        self.setPos(node.pos_x, node.pos_y)
        w, h = node_size(node)
        self.setMinimumSize(w, h)
        self.setPreferredSize(w, h)
        self.setMaximumSize(w, h)
        self.update()

    def set_execution_state(self, state: str | None) -> None:
        self._execution_state = state
        self.update()

    def set_selected_visual(self, selected: bool) -> None:
        self._is_selected_visual = selected
        self.update()

    def apply_theme(self) -> None:
        self.update()

    def boundingRect(self) -> QRectF:
        w, h = node_size(self._node)
        return QRectF(-2, -2, w + 4, h + 4)

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        th = current_theme()
        w, h, header_h, body_h, port_strip_h = node_spec(self._node)
        r = CORNER_RADIUS
        node_type = self._node.node_type

        zoom = 1.0
        if self._canvas and not getattr(self._canvas, '_destroyed', False):
            try:
                zoom = self._canvas.zoom()
            except RuntimeError:
                zoom = self._cached_zoom
        if zoom != self._cached_zoom:
            self._cached_zoom = zoom
        lod = lod_level(self._cached_zoom)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if lod == LOD_MINIMAL:
            self._paint_minimal(painter, th, w, h)
            return

        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(QRectF(2, 2, w, h), r, r)
        painter.fillPath(shadow_path, QColor(0, 0, 0, 40))

        border_color = node_border_color(node_type)
        fill_color = node_fill_color(node_type)
        pen_width = 2.0 if self._is_selected_visual else 1.0
        border_pen = QPen(QColor(border_color), pen_width)

        body_path = QPainterPath()
        body_path.addRoundedRect(QRectF(0, 0, w, h), r, r)
        painter.setPen(border_pen)
        painter.fillPath(body_path, QColor(th.bg_surface))
        painter.drawPath(body_path)

        header_clip = QPainterPath()
        header_clip.addRoundedRect(QRectF(0, 0, w, header_h), r, r)
        header_clip.addRect(QRectF(0, header_h - r, w, r))
        painter.setClipPath(header_clip)
        painter.fillPath(body_path, QColor(fill_color))
        painter.setClipping(False)

        self._paint_header_text(painter, th, w, header_h)
        self._paint_body_text(painter, th, w, header_h, body_h, node_type)

        if lod in (LOD_FULL, LOD_SIMPLIFIED):
            self._paint_ports(painter, th, w, h, header_h, body_h, node_type)

        if self._execution_state:
            self._paint_execution_state(painter, th, w, h)

        if self._is_selected_visual:
            sel_path = QPainterPath()
            sel_path.addRoundedRect(QRectF(-2, -2, w + 4, h + 4), r + 2, r + 2)
            painter.setPen(QPen(QColor(th.accent_blue), 2.5))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(sel_path)

    def _paint_minimal(self, painter: QPainter, th, w: float, h: float) -> None:
        fill = node_fill_color(self._node.node_type)
        painter.setPen(QPen(QColor(node_border_color(self._node.node_type)), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(QRectF(0, 0, w, h), CORNER_RADIUS, CORNER_RADIUS)

        title = self._node_title()
        painter.setPen(QColor(th.text_on_accent))
        painter.setFont(_FONT_MINIMAL)
        painter.drawText(QRectF(4, 0, w - 8, h), Qt.AlignmentFlag.AlignCenter, title)

    def _paint_header_text(
        self, painter: QPainter, th, w: float, header_h: float,
    ) -> None:
        icon = _NODE_ICONS.get(self._node.node_type, "")
        title = self._node_title()

        painter.setFont(_FONT_HEADER)
        painter.setPen(QColor(th.text_on_accent))

        icon_w = painter.fontMetrics().horizontalAdvance(icon) + 4 if icon else 0
        painter.drawText(
            QRectF(8, 0, icon_w, header_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            icon,
        )
        painter.drawText(
            QRectF(8 + icon_w, 0, w - 16 - icon_w, header_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            title,
        )

    def _paint_body_text(
        self, painter: QPainter, th, w: float, header_h: float,
        body_h: float, node_type: NodeType,
    ) -> None:
        line1, line2 = _body_text_lines(self._node)

        painter.setFont(_FONT_BODY)
        painter.setPen(QColor(th.text_secondary))

        line_h = body_h / 2
        painter.drawText(
            QRectF(8, header_h, w - 16, line_h),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            line1,
        )

        if line2 and body_h >= 40:
            painter.setFont(_FONT_BODY_SMALL)
            painter.setPen(QColor(th.text_muted))
            painter.drawText(
                QRectF(8, header_h + line_h, w - 16, line_h),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                line2,
            )

    def _paint_ports(
        self, painter: QPainter, th, w: float, h: float,
        header_h: float, body_h: float, node_type: NodeType,
    ) -> None:
        positions = port_positions(self._node)
        nx = self._node.pos_x
        ny = self._node.pos_y

        for label, (wx, wy) in positions.items():
            local_x = wx - nx
            local_y = wy - ny
            is_input = label == "in"
            color = port_fill_color(label, th)

            if is_input:
                # 输入端口 — 菱形轮廓（空心）
                d = PORT_VISUAL_RADIUS
                path = QPainterPath()
                path.moveTo(local_x, local_y - d)
                path.lineTo(local_x + d, local_y)
                path.lineTo(local_x, local_y + d)
                path.lineTo(local_x - d, local_y)
                path.closeSubpath()
                painter.setPen(QPen(QColor(th.port_in_outline), 2))
                painter.setBrush(QColor(th.bg_surface))
                painter.drawPath(path)
            else:
                # 输出端口 — 实心圆
                r = PORT_VISUAL_RADIUS
                painter.setPen(QPen(QColor(th.port_out_outline), 1.5))
                painter.setBrush(QColor(color))
                painter.drawEllipse(QPointF(local_x, local_y), r, r)

            port_lbl = _port_label(node_type, label)
            if port_lbl:
                painter.setFont(_FONT_PORT)
                painter.setPen(QColor(th.text_muted))
                offset = PORT_VISUAL_RADIUS + 4
                is_output = not is_input
                text_x = local_x + offset if is_output else local_x - offset
                align = Qt.AlignmentFlag.AlignLeft if is_output else Qt.AlignmentFlag.AlignRight
                painter.drawText(
                    QRectF(text_x - PORT_LABEL_WIDTH / 2, local_y - PORT_LABEL_HEIGHT / 2, PORT_LABEL_WIDTH, PORT_LABEL_HEIGHT),
                    align | Qt.AlignmentFlag.AlignVCenter,
                    port_lbl,
                )

    _STATE_VISUALS: dict[NodeExecutionState, tuple[str, int]] = {
        NodeExecutionState.RUNNING: ("status_running", 40),
        NodeExecutionState.SUCCESS: ("status_success", 30),
        NodeExecutionState.ERROR: ("status_error", 30),
    }

    def _paint_execution_state(
        self, painter: QPainter, th, w: float, h: float,
    ) -> None:
        visual = self._STATE_VISUALS.get(self._execution_state)
        if visual is None:
            return
        theme_attr, alpha = visual
        color = QColor(getattr(th, theme_attr))
        color.setAlpha(alpha)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, w, h), CORNER_RADIUS, CORNER_RADIUS)
        painter.fillPath(path, color)

    def _node_title(self) -> str:
        return self._node.comment or self._node.describe()

