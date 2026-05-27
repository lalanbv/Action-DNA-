"""QtLogViewer — log viewer component using QTreeWidget.

Supports real-time updates from RingBufferLog, type-based coloring,
filtering, auto-scroll, and export.
"""

from __future__ import annotations

from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QPushButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from src.core.debug.ring_buffer_log import LogEntry, LogEventType, RingBufferLog
from src.panel.canvas.theme import current_theme
from src.panel.components.log_viewer_utils import FILTER_GROUPS, tint_for, type_color
from src.panel.qt_backend.components.base import QtDNAWidget
from src.panel.qt_backend.scale import qt_scale_manager
from src.utils.i18n import t


class QtLogViewer(QtDNAWidget):
    """Log viewer with filtering, auto-scroll, and export."""

    def __init__(
        self,
        parent: QWidget | None = None,
        log: RingBufferLog | None = None,
        max_visible: int = 200,
    ) -> None:
        super().__init__(parent)
        self._log = log
        self._max_visible = max_visible
        self._auto_scroll = True
        self._active_filter: list[LogEventType] | None = None
        self._all_entries: deque[LogEntry] = deque(maxlen=2000)

        self._build_ui()

        if self._log:
            self._load_existing_entries()
            self._log.on_append(self._on_new_entry)

    def set_log(self, log: RingBufferLog) -> None:
        if self._log:
            self._log.remove_on_append(self._on_new_entry)
        self._log = log
        self._load_existing_entries()
        log.on_append(self._on_new_entry)

    def _build_ui(self) -> None:
        th = current_theme()
        sm = qt_scale_manager()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {th.panel_header_bg};")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(sm.s(4), sm.s(2), sm.s(4), sm.s(2))

        title = QLabel(t("workflow.log.title"))
        title.setStyleSheet(f"color: {th.text_primary}; background: transparent; font-weight: bold;")
        tb_layout.addWidget(title)

        def _btn_ss(text_color: str, extra: str = "") -> str:
            return (
                f"QPushButton {{"
                f" background-color: {th.btn_bg}; color: {text_color};"
                f" border: 1px solid {th.btn_border}; border-radius: 2px;"
                f" padding: 1px {sm.s(6)}px; font-size: {sm.s(10)}px;"
                f"}}{extra}"
            )

        _checked_ss = (
            f"QPushButton:checked {{"
            f" background-color: {th.accent_blue}; color: {th.text_on_accent};"
            f"}}"
        )
        self._filter_buttons: list[QPushButton] = []
        for label_key, types in FILTER_GROUPS:
            btn = QPushButton(t(label_key))
            btn.setCheckable(True)
            btn.setStyleSheet(_btn_ss(th.text_secondary, _checked_ss))
            btn.clicked.connect(lambda checked, t=types, b=btn: self._set_filter(t, b))
            tb_layout.addWidget(btn)
            self._filter_buttons.append(btn)
        if self._filter_buttons:
            self._filter_buttons[0].setChecked(True)

        tb_layout.addStretch()

        auto_cb = QCheckBox(t("workflow.log.auto_scroll"))
        auto_cb.setChecked(True)
        auto_cb.setStyleSheet(f"color: {th.text_secondary}; background: transparent; font-size: {sm.s(10)}px;")
        auto_cb.toggled.connect(lambda c: setattr(self, "_auto_scroll", c))
        tb_layout.addWidget(auto_cb)

        _action_ss = _btn_ss(
            th.text_primary,
            f"QPushButton:hover {{ background-color: {th.btn_bg_hover}; }}",
        )
        export_btn = QPushButton(t("workflow.log.export"))
        export_btn.setStyleSheet(_action_ss)
        export_btn.clicked.connect(self._export_log)
        tb_layout.addWidget(export_btn)

        clear_btn = QPushButton(t("workflow.log.clear"))
        clear_btn.setStyleSheet(_action_ss)
        clear_btn.clicked.connect(self._clear_log)
        tb_layout.addWidget(clear_btn)

        layout.addWidget(toolbar)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels([
            t("workflow.log.col_time"),
            t("workflow.log.col_type"),
            t("workflow.log.col_node"),
            t("workflow.log.col_message"),
        ])
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {th.bg_primary}; color: {th.text_primary};
                border: none; font-size: {sm.s(11)}px;
                alternate-background-color: {th.input_bg};
            }}
            QTreeWidget::item {{
                padding: 1px 2px; border-bottom: 1px solid {th.border_default};
            }}
            QHeaderView::section {{
                background-color: {th.panel_header_bg}; color: {th.text_muted};
                border: none; border-bottom: 1px solid {th.border_default};
                padding: 2px 4px; font-size: {sm.s(10)}px;
            }}
        """)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        header.resizeSection(0, sm.s(80))
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, sm.s(80))
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, sm.s(70))
        header.setSectionResizeMode(3, QHeaderView.Stretch)

        layout.addWidget(self._tree, 1)

    def _set_filter(self, types: list[LogEventType] | None, active_btn: QPushButton) -> None:
        for btn in self._filter_buttons:
            btn.setChecked(btn is active_btn)
        self._active_filter = types
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        self._tree.clear()
        for entry in self._all_entries:
            self._insert_entry(entry)

    def _load_existing_entries(self) -> None:
        if not self._log:
            return
        for entry in self._log.get_all():
            self._all_entries.append(entry)
            self._insert_entry(entry)

    def _on_new_entry(self, entry: LogEntry) -> None:
        QTimer.singleShot(0, lambda: self._handle_new_entry(entry))

    def _handle_new_entry(self, entry: LogEntry) -> None:
        self._all_entries.append(entry)
        self._insert_entry(entry)

    def _insert_entry(self, entry: LogEntry) -> None:
        if self._active_filter is not None and entry.event_type not in self._active_filter:
            return

        color = type_color(entry.event_type)
        bg = tint_for(entry.event_type)

        item = QTreeWidgetItem([
            entry.time_str,
            entry.event_type.value,
            entry.node_id,
            entry.message,
        ])
        item.setForeground(0, color)
        item.setForeground(1, color)
        item.setForeground(2, color)
        item.setForeground(3, color)
        item.setBackground(0, bg)
        item.setBackground(1, bg)
        item.setBackground(2, bg)
        item.setBackground(3, bg)
        self._tree.addTopLevelItem(item)

        while self._tree.topLevelItemCount() > self._max_visible:
            self._tree.takeTopLevelItem(0)

        if self._auto_scroll:
            self._tree.scrollToItem(item)

    def _clear_log(self) -> None:
        if self._log:
            self._log.clear()
        self._all_entries.clear()
        self._tree.clear()

    def _export_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, t("workflow.log.export"),
            "", f"{t('dialog.filetype.json')} (*.json);;{t('dialog.filetype.all')} (*)",
        )
        if path and self._log:
            self._log.export_to_file(path)

    def apply_theme(self) -> None:
        th = current_theme()
        self.setStyleSheet(f"background-color: {th.bg_primary};")
        self._refresh_tree()

    def destroy_widget(self) -> None:
        if self._log:
            self._log.remove_on_append(self._on_new_entry)
        super().destroy_widget()
