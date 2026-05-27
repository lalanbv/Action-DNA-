"""QtMinimap — PySide6 minimap as a second QGraphicsView on the same Scene.

替代 tkinter Minimap (680 行)，共享 Scene 实现零重复渲染。
点击/拖拽导航到对应视口位置。
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QPainter, QPen, QBrush, QColor
from PySide6.QtWidgets import QGraphicsView, QWidget, QVBoxLayout

from src.panel.canvas.theme import current_theme

_MINIMAP_WIDTH = 260
_MINIMAP_HEIGHT = 195
_MINIMAP_MARGIN = 10


class QtMinimap(QGraphicsView):
    """Minimap overlay — shares the same QGraphicsScene as the main canvas.

    Renders a scaled-down overview with a viewport rectangle indicator.
    Click/drag to navigate the main canvas viewport.
    """

    def __init__(self, main_canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._main_canvas = main_canvas
        self._scene = main_canvas.scene

        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)

        self.setFixedSize(_MINIMAP_WIDTH, _MINIMAP_HEIGHT)

        self._dragging = False
        self._visible = True

        self.apply_theme()

    def toggle(self) -> None:
        self._visible = not self._visible
        self.setVisible(self._visible)

    def update_viewport(self) -> None:
        self.viewport().update()
        self.fit_to_bounds()

    def fit_to_bounds(self) -> None:
        if not self._scene or self._scene.items() == []:
            return
        bounds = self._scene.itemsBoundingRect().adjusted(-50, -50, 50, 50)
        self.fitInView(bounds, Qt.AspectRatioMode.KeepAspectRatio)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)

        if not self._main_canvas or not self._visible:
            return

        main_viewport = self._main_canvas.viewport()
        if not main_viewport:
            return

        scene_rect = self._main_canvas.mapToScene(main_viewport.rect()).boundingRect()

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        th = current_theme()
        pen = QPen(QColor(th.accent_blue), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(th.accent_blue), Qt.BrushStyle.NoBrush))

        minimap_rect = self.mapFromScene(scene_rect).boundingRect()
        painter.drawRect(minimap_rect)

        z = self._main_canvas.zoom()
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(th.text_muted))
        painter.drawText(
            minimap_rect.bottomRight() + QPoint(4, 12),
            f"{z:.0%}",
        )
        painter.end()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._navigate_to(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._navigate_to(event.pos())

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def _navigate_to(self, pos: QPoint) -> None:
        scene_pos = self.mapToScene(pos)
        self._main_canvas.navigate_to_center(scene_pos.x(), scene_pos.y())

    def apply_theme(self) -> None:
        th = current_theme()
        self.setStyleSheet(f"""
            QGraphicsView {{
                background-color: {th.bg_surface};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        self.viewport().update()
