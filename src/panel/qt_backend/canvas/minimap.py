"""QtMinimap — PySide6 minimap as a second QGraphicsView on the same Scene.

共享 Scene 实现零重复渲染，叠加在主画布右下角。
功能:
- 视口矩形指示器 (蓝色虚线 + 缩放百分比)
- 点击/拖拽导航到对应视口位置
- 滚轮缩放主画布
- 拖拽手柄移动小地图位置
- 齿轮按钮弹出设置面板 (显示连线/标签/禁用节点/尺寸)
- 悬停显示节点名称
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QCursor, QPainter, QPen, QBrush, QColor
from PySide6.QtWidgets import (
    QFrame, QGraphicsView, QHBoxLayout, QLabel,
    QSizePolicy, QVBoxLayout, QWidget,
)

from src.panel.canvas.theme import current_theme
from src.utils.i18n import t

SIZE_MAP: dict[str, int] = {
    "small": 180,
    "medium": 260,
    "large": 340,
}


class _CheckLabel(QLabel):
    """可点击的复选框标签。"""

    def __init__(self, text: str, checked: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._text = text
        self._checked = checked
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._update_text()

    def _update_text(self) -> None:
        self.setText(f"{'☑' if self._checked else '☐'} {self._text}")

    @property
    def is_checked(self) -> bool:
        return self._checked

    def mousePressEvent(self, event) -> None:
        self._checked = not self._checked
        self._update_text()
        self._apply_style()
        super().mousePressEvent(event)

    def _apply_style(self) -> None:
        th = current_theme()
        self.setStyleSheet(f"""
            color: {th.text_primary}; font-size: 10px; border: none;
            padding: 2px 4px;
        """)


class _SizeButton(QLabel):
    """尺寸选择按钮。"""

    def __init__(self, label: str, mode: str, active: bool,
                 on_click, parent: QWidget | None = None) -> None:
        super().__init__(label, parent)
        self._mode = mode
        self._on_click = on_click
        self._active = active
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setMinimumWidth(36)
        self.setMinimumHeight(24)
        self._apply_style()

    def _apply_style(self) -> None:
        th = current_theme()
        if self._active:
            self.setStyleSheet(f"""
                background-color: {th.accent_blue}; color: {th.text_on_accent};
                border: 1px solid {th.accent_blue}; border-radius: 3px;
                font-weight: bold; font-size: 10px;
            """)
        else:
            self.setStyleSheet(f"""
                background-color: {th.btn_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: 3px;
                font-size: 10px;
            """)

    def set_active(self, active: bool) -> None:
        self._active = active
        self._apply_style()

    def mousePressEvent(self, event) -> None:
        self._on_click(self._mode)
        super().mousePressEvent(event)


class QtMinimapSettings(QWidget):
    """Qt 版小地图设置弹窗。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.show_edges = True
        self.show_labels = True
        self.show_disabled = True
        self.size_mode: str = "medium"
        self.on_change = None  # type: ignore[assignment]
        self._size_buttons: dict[str, _SizeButton] = {}
        self._build_ui()

    def _build_ui(self) -> None:
        th = current_theme()
        self.setWindowFlags(Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.bg_surface};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(8, 6, 8, 8)
        fl.setSpacing(4)
        layout.addWidget(frame)

        # 标题
        header = QLabel(t("minimap.settings"))
        header.setStyleSheet(
            f"color: {th.text_primary}; font-weight: bold; font-size: 11px; border: none;"
        )
        fl.addWidget(header)

        self._edge_cb = _CheckLabel(t("minimap.show_edges"), self.show_edges)
        fl.addWidget(self._edge_cb)

        self._label_cb = _CheckLabel(t("minimap.show_labels"), self.show_labels)
        fl.addWidget(self._label_cb)

        self._disabled_cb = _CheckLabel(t("minimap.show_disabled"), self.show_disabled)
        fl.addWidget(self._disabled_cb)

        # 分割线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {th.border_default}; border: none;")
        fl.addWidget(sep)

        size_label = QLabel(t("minimap.size"))
        size_label.setStyleSheet(
            f"color: {th.text_secondary}; font-size: 10px; border: none;"
        )
        fl.addWidget(size_label)

        size_row = QWidget()
        size_row.setStyleSheet("border: none;")
        sl = QHBoxLayout(size_row)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(4)

        for mode, label_text in [("small", "S"), ("medium", "M"), ("large", "L")]:
            btn = _SizeButton(label_text, mode, mode == self.size_mode,
                              self._set_size)
            sl.addWidget(btn)
            self._size_buttons[mode] = btn

        fl.addWidget(size_row)

    def _set_size(self, mode: str) -> None:
        self.size_mode = mode
        for m, btn in self._size_buttons.items():
            btn.set_active(m == mode)
        self._notify()
        self.close()

    def read_state(self) -> dict:
        """读取当前设置状态。"""
        self.show_edges = self._edge_cb.is_checked
        self.show_labels = self._label_cb.is_checked
        self.show_disabled = self._disabled_cb.is_checked
        return {
            "show_edges": self.show_edges,
            "show_labels": self.show_labels,
            "show_disabled": self.show_disabled,
            "size_mode": self.size_mode,
        }

    def _notify(self) -> None:
        self.read_state()
        if self.on_change:
            self.on_change()

    def popup_at(self, global_pos: QPoint) -> None:
        self.adjustSize()
        from PySide6.QtWidgets import QApplication
        screen = QApplication.screenAt(global_pos)
        if screen:
            geo = screen.availableGeometry()
            w = self.sizeHint().width()
            h = self.sizeHint().height()
            x = min(global_pos.x(), geo.right() - w - 4)
            y = global_pos.y() - h - 4
            if y < geo.top():
                y = global_pos.y() + 20
            self.move(max(0, x), max(0, y))
        self.show()


class QtMinimap(QGraphicsView):
    """Minimap overlay — shares the same QGraphicsScene as the main canvas."""

    def __init__(self, main_canvas, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._main_canvas = main_canvas
        self._scene = main_canvas.scene

        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setInteractive(False)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        self._dragging = False
        self._visible = True
        self._user_positioned = False
        self._size_mode: str = "medium"

        # 拖拽手柄状态
        self._is_dragging_handle = False
        self._drag_start_pos = QPoint()
        self._drag_start_geo = QPoint()

        # 悬停
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(200)
        self._hover_timer.timeout.connect(self._show_hover_tooltip)
        self._last_hover_pos = QPoint()
        self._tooltip_label: QLabel | None = None

        # 设置面板
        self._settings = QtMinimapSettings()
        self._settings.on_change = self._on_settings_changed

        self._update_size()
        self._build_overlay_buttons()
        self.apply_theme()

    # ── 尺寸 ──────────────────────────────────────────────

    def _current_size(self) -> tuple[int, int]:
        w = SIZE_MAP.get(self._size_mode, 260)
        h = int(w * 0.75)
        return w, h

    def _update_size(self) -> None:
        w, h = self._current_size()
        self.setFixedSize(w, h)

    # ── Overlay 按钮 ──────────────────────────────────────

    def _build_overlay_buttons(self) -> None:
        th = current_theme()
        # 齿轮按钮 (右上角)
        self._gear_btn = QLabel("⚙", self)
        self._gear_btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self._gear_btn.setStyleSheet(f"""
            color: {th.text_muted}; background: transparent;
            font-size: 12px; border: none; padding: 1px 3px;
        """)
        self._gear_btn.move(self.width() - 20, 2)
        self._gear_btn.show()

        # 拖拽手柄 (左上角)
        self._drag_handle = QLabel("✥", self)
        self._drag_handle.setCursor(QCursor(Qt.CursorShape.SizeAllCursor))
        self._drag_handle.setStyleSheet(f"""
            color: {th.text_muted}; background: transparent;
            font-size: 12px; border: none; padding: 1px 3px;
        """)
        self._drag_handle.move(3, 2)
        self._drag_handle.show()

    def _reposition_buttons(self) -> None:
        self._gear_btn.move(self.width() - 20, 2)
        self._drag_handle.move(3, 2)

    # ── 设置面板 ──────────────────────────────────────────

    def _toggle_settings(self) -> None:
        if self._settings.isVisible():
            self._settings.close()
        else:
            gear_global = self._gear_btn.mapToGlobal(
                QPoint(self._gear_btn.width(), self._gear_btn.height() + 2),
            )
            self._settings.popup_at(gear_global)

    def _on_settings_changed(self) -> None:
        self._size_mode = self._settings.size_mode
        self._update_size()
        self._reposition_buttons()
        self._reposition_in_parent()
        self.fit_to_bounds()
        self.viewport().update()

    # ── 显示/隐藏 ─────────────────────────────────────────

    def toggle(self) -> None:
        self._visible = not self._visible
        self.setVisible(self._visible)

    def show(self) -> None:
        self._visible = True
        super().show()

    # ── 定位 ──────────────────────────────────────────────

    def default_position(self, parent_w: int, parent_h: int) -> QPoint:
        margin = 10
        x = parent_w - self.width() - margin
        y = parent_h - self.height() - margin - 44
        return QPoint(max(0, x), max(0, y))

    def _reposition_in_parent(self) -> None:
        parent = self.parentWidget()
        if not parent:
            return
        pw, ph = parent.width(), parent.height()
        if pw < 10 or ph < 10:
            return
        if not self._user_positioned:
            self.move(self.default_position(pw, ph))

    def reposition_on_resize(self, parent_w: int, parent_h: int) -> None:
        if self._user_positioned:
            self.move(
                max(0, min(self.x(), parent_w - self.width())),
                max(0, min(self.y(), parent_h - self.height())),
            )
        else:
            self.move(self.default_position(parent_w, parent_h))

    # ── 场景适配 ──────────────────────────────────────────

    def update_viewport(self) -> None:
        self.viewport().update()
        self.fit_to_bounds()

    def fit_to_bounds(self) -> None:
        if not self._scene:
            return
        bounds = self._scene.itemsBoundingRect()
        if bounds.isEmpty():
            return
        self.fitInView(bounds.adjusted(-50, -50, 50, 50),
                       Qt.AspectRatioMode.KeepAspectRatio)

    # ── 绘制 ──────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        try:
            super().paintEvent(event)
        except RuntimeError:
            return

        if not self._main_canvas or not self._visible:
            return
        if getattr(self._main_canvas, '_destroyed', False):
            return

        try:
            main_vp = self._main_canvas.viewport()
            if not main_vp:
                return

            scene_rect = self._main_canvas.mapToScene(main_vp.rect()).boundingRect()
            if scene_rect.isEmpty():
                return
        except RuntimeError:
            return

        painter = QPainter(self.viewport())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        th = current_theme()

        minimap_rect = self.mapFromScene(scene_rect).boundingRect()

        # 外发光
        glow_pen = QPen(QColor(th.minimap_viewport_shadow), 1)
        painter.setPen(glow_pen)
        painter.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        painter.drawRect(minimap_rect.adjusted(-2, -2, 2, 2))

        # 视口矩形
        pen = QPen(QColor(th.minimap_viewport), 2, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor(th.minimap_viewport), Qt.BrushStyle.NoBrush))
        painter.drawRect(minimap_rect)

        # 缩放百分比
        try:
            z = self._main_canvas.zoom()
        except RuntimeError:
            z = 1.0
        zoom_text = f"{z:.0%}"
        font = painter.font()
        font.setPixelSize(10)
        painter.setFont(font)
        painter.setPen(QColor(th.text_muted))
        from PySide6.QtCore import QRect
        text_rect = QRect(0, self.height() - 16, self.width() - 6, 14)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, zoom_text)
        painter.end()

    # ── 鼠标交互 ──────────────────────────────────────────

    def mousePressEvent(self, event) -> None:
        if self._is_dragging_handle:
            return
        if event.button() == Qt.MouseButton.LeftButton:
            if self._hit_overlay_button(event.pos()):
                return
            self._dragging = True
            self._navigate_to(event.pos())

    def mouseMoveEvent(self, event) -> None:
        if self._is_dragging_handle:
            return
        if self._dragging:
            self._navigate_to(event.pos())
        else:
            self._hover_timer.stop()
            self._hide_tooltip()
            self._last_hover_pos = event.pos()
            self._hover_timer.start()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def wheelEvent(self, event) -> None:
        if getattr(self._main_canvas, '_destroyed', False):
            event.accept()
            return
        delta = event.angleDelta().y()
        if abs(delta) < 8:
            event.accept()
            return
        factor = 1.15 if delta > 0 else 1 / 1.15
        self._main_canvas.zoom_by(factor)
        event.accept()

    def _navigate_to(self, pos: QPoint) -> None:
        if getattr(self._main_canvas, '_destroyed', False):
            return
        scene_pos = self.mapToScene(pos)
        self._main_canvas.navigate_to_center(scene_pos.x(), scene_pos.y())

    def _hit_overlay_button(self, pos: QPoint) -> bool:
        for btn in (self._gear_btn, self._drag_handle):
            if btn.geometry().contains(pos):
                return True
        return False

    # ── 悬停提示 ──────────────────────────────────────────

    def _show_hover_tooltip(self) -> None:
        if self._dragging:
            return

        scene_pos = self.mapToScene(self._last_hover_pos)
        items = self._scene.items(
            scene_pos, Qt.ItemSelectionMode.IntersectsItemShape,
            Qt.SortOrder.DescendingOrder,
        )

        from src.panel.qt_backend.canvas.node_item import QtNodeItem
        node_item = None
        for item in items:
            if isinstance(item, QtNodeItem):
                node_item = item
                break

        if not node_item:
            self._hide_tooltip()
            return

        node = node_item._node
        desc = node.describe() if hasattr(node, "describe") else node.node_type
        if len(desc) > 24:
            desc = desc[:23] + "…"

        th = current_theme()
        if self._tooltip_label is None:
            self._tooltip_label = QLabel(self)
            self._tooltip_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._tooltip_label.setText(desc)
        self._tooltip_label.setStyleSheet(f"""
            background-color: {th.bg_surface};
            color: {th.text_primary};
            border: 1px solid {th.border_default};
            border-radius: 3px;
            padding: 2px 6px;
            font-size: 10px;
        """)
        self._tooltip_label.adjustSize()

        tx = max(4, min(self._last_hover_pos.x() + 10,
                        self.width() - self._tooltip_label.width() - 4))
        ty = max(4, self._last_hover_pos.y() - self._tooltip_label.height() - 4)
        self._tooltip_label.move(tx, ty)
        self._tooltip_label.raise_()
        self._tooltip_label.show()

    def _hide_tooltip(self) -> None:
        if self._tooltip_label:
            self._tooltip_label.hide()

    def leaveEvent(self, event) -> None:
        self._hover_timer.stop()
        self._hide_tooltip()
        super().leaveEvent(event)

    # ── 拖拽手柄事件 ──────────────────────────────────────

    def handle_mouse_press(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging_handle = True
            self._drag_start_pos = event.globalPos()
            self._drag_start_geo = self.pos()

    def handle_mouse_move(self, event) -> None:
        if not self._is_dragging_handle:
            return
        delta = event.globalPos() - self._drag_start_pos
        new_x = self._drag_start_geo.x() + delta.x()
        new_y = self._drag_start_geo.y() + delta.y()
        parent = self.parentWidget()
        if parent:
            new_x = max(0, min(new_x, parent.width() - self.width()))
            new_y = max(0, min(new_y, parent.height() - self.height()))
        self.move(new_x, new_y)

    def handle_mouse_release(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._is_dragging_handle = False
            self._user_positioned = True

    # ── 主题 ──────────────────────────────────────────────

    def apply_theme(self) -> None:
        th = current_theme()
        self.setStyleSheet(f"""
            QGraphicsView {{
                background-color: {th.minimap_bg_panel};
                border: 1px solid {th.minimap_border};
                border-radius: 4px;
            }}
        """)
        if hasattr(self, "_gear_btn"):
            self._gear_btn.setStyleSheet(f"""
                color: {th.text_muted}; background: transparent;
                font-size: 12px; border: none; padding: 1px 3px;
            """)
        if hasattr(self, "_drag_handle"):
            self._drag_handle.setStyleSheet(f"""
                color: {th.text_muted}; background: transparent;
                font-size: 12px; border: none; padding: 1px 3px;
            """)
        self._hide_tooltip()
        self.viewport().update()
