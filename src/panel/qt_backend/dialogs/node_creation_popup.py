"""QtNodeCreationPopup — PySide6 可搜索的节点创建弹窗。

替代 tkinter NodeCreationPopup，使用 QFrame + QListWidget。
右键画布空白处弹出，支持搜索筛选、键盘导航、分类列表。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from src.panel.canvas.theme import current_theme
from src.panel.components.palette_data import ACTION_PALETTE, FLOW_PALETTE
from src.panel.qt_backend.scale import qt_scale_manager
from src.utils.i18n import t


class QtNodeCreationPopup(QFrame):
    """可搜索的节点创建弹窗。"""

    def __init__(
        self,
        parent: QWidget,
        screen_x: int,
        screen_y: int,
        on_create_action,
        on_create_flow,
    ) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self._on_create_action = on_create_action
        self._on_create_flow = on_create_flow
        self._items: list[tuple[str, str, str, object]] = []
        self._ready = False

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Popup | Qt.WindowStaysOnTopHint,
        )
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {th.bg_surface};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(6)}px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sm.s(4), sm.s(4), sm.s(4), sm.s(4))
        layout.setSpacing(sm.s(4))

        self._search_entry = QLineEdit()
        self._search_entry.setPlaceholderText(t("workflow.palette.search_placeholder"))
        self._search_entry.setStyleSheet(f"""
            QLineEdit {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(4)}px;
                padding: {sm.s(4)}px {sm.s(8)}px;
                font-size: {sm.s(12)}px;
            }}
            QLineEdit:focus {{
                border-color: {th.accent_blue};
            }}
        """)
        self._search_entry.textChanged.connect(self._apply_filter)
        layout.addWidget(self._search_entry)

        self._listbox = QListWidget()
        self._listbox.setStyleSheet(f"""
            QListWidget {{
                background-color: {th.bg_surface};
                color: {th.text_primary};
                border: none;
                outline: none;
                font-size: {sm.s(12)}px;
            }}
            QListWidget::item {{
                padding: {sm.s(4)}px {sm.s(8)}px;
                border-radius: {sm.s(3)}px;
            }}
            QListWidget::item:selected {{
                background-color: {th.accent_blue};
                color: {th.text_on_accent};
            }}
            QListWidget::item:hover {{
                background-color: {th.btn_bg_hover};
            }}
        """)
        self._listbox.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self._listbox)

        self.setFixedSize(sm.s(240), sm.s(340))
        self.move(screen_x, screen_y)

        self._populate_items()
        self._apply_filter("")

        self._search_entry.setFocus()

        QTimer.singleShot(150, self._mark_ready)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key == Qt.Key_Escape:
            self.close()
            return
        if key == Qt.Key_Return or key == Qt.Key_Enter:
            self._activate_selected()
            return
        if key == Qt.Key_Up:
            self._move_selection(-1)
            return
        if key == Qt.Key_Down:
            self._move_selection(1)
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        if not self._ready:
            super().focusOutEvent(event)
            return
        reason = event.reason()
        if reason == Qt.ActiveWindowFocusReason or reason == Qt.MouseFocusReason:
            self.close()
        super().focusOutEvent(event)

    def _populate_items(self) -> None:
        action_section = t("workflow.palette.section_action")
        for at, i18n_key in ACTION_PALETTE:
            self._items.append((t(i18n_key), action_section, "action", at))

        flow_section = t("workflow.palette.section_flow")
        for nt, i18n_key in FLOW_PALETTE:
            self._items.append((t(i18n_key), flow_section, "flow", nt))

    def _apply_filter(self, query: str) -> None:
        self._listbox.clear()
        q = query.lower().strip()
        current_section = ""

        row = 0
        first_selectable: QListWidgetItem | None = None
        th = current_theme()

        for _i, (label, section, kind, data) in enumerate(self._items):
            if q and q not in label.lower() and q not in section.lower():
                continue
            if section != current_section:
                item = QListWidgetItem(f"── {section} ──")
                item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                item.setData(Qt.ForegroundRole, th.text_muted)
                self._listbox.addItem(item)
                current_section = section
                row += 1

            display_item = QListWidgetItem(f"  {label}")
            display_item.setData(Qt.UserRole, (kind, data))
            self._listbox.addItem(display_item)

            if first_selectable is None:
                first_selectable = display_item
            row += 1

        if first_selectable is not None:
            first_selectable.setSelected(True)
            self._listbox.setCurrentItem(first_selectable)

    def _move_selection(self, direction: int) -> None:
        current = self._listbox.currentRow()
        new_row = current + direction
        while 0 <= new_row < self._listbox.count():
            item = self._listbox.item(new_row)
            if item is not None and (item.flags() & Qt.ItemIsSelectable):
                self._listbox.setCurrentRow(new_row)
                return
            new_row += direction

    def _activate_selected(self) -> None:
        item = self._listbox.currentItem()
        if item is None:
            return
        data = item.data(Qt.UserRole)
        if data is None:
            return
        kind, payload = data
        self.close()
        if kind == "action":
            self._on_create_action(payload)
        elif kind == "flow":
            self._on_create_flow(payload)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.UserRole)
        if data is None:
            return
        self.close()
        kind, payload = data
        if kind == "action":
            self._on_create_action(payload)
        elif kind == "flow":
            self._on_create_flow(payload)

    def _mark_ready(self) -> None:
        self._ready = True
