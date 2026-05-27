"""QtPluginPage — PySide6 插件管理页面。

替代 tkinter PluginPage，插件列表 + 启停控制 + 详情面板。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout, QHeaderView,
    QLabel, QTextEdit,
    QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from src.core.plugins.plugin_loader import PluginState
from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.dialogs.plugin_edit_dialog import PluginEditDialog
from src.panel.pages.page_i18n import PLUGIN_TITLE, PLUGIN_DESC
from src.panel.qt_backend.pages.base_page import QtBasePage
from src.panel.qt_backend.pages.page_registry import register_page
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button, themed_frame, themed_label
from src.utils.i18n import t

_LOADED_STATES = frozenset({PluginState.LOADED, PluginState.ACTIVE})


@register_page("plugin", label_i18n=PLUGIN_TITLE, desc_i18n=PLUGIN_DESC, icon="🧩", category="main")
class QtPluginPage(QtBasePage):
    """插件管理页面。"""

    def title(self) -> str:
        return t("plugin.title")

    def build(self) -> None:
        th = current_theme()
        sm = qt_scale_manager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md))
        main_layout.setSpacing(sm.s(8))

        self._build_toolbar(main_layout, th, sm)
        self._build_tree(main_layout, th, sm)
        self._build_buttons(main_layout, th, sm)
        self._build_detail(main_layout, th, sm)

        self._refresh()

    def _build_toolbar(self, layout: QVBoxLayout, th, sm) -> None:
        toolbar = self._build_toolbar_base(layout, "plugin.title")
        refresh_btn = themed_button(
            self, text=t("plugin.refresh"), style="secondary",
            command=self._refresh,
        )
        toolbar.addWidget(refresh_btn)

    def _build_tree(self, layout: QVBoxLayout, th, sm) -> None:
        self._tree = QTreeWidget()
        columns = [
            t("common.name"),
            t("plugin.version"),
            t("plugin.col.state"),
            t("plugin.col.nodes"),
            t("plugin.description"),
        ]
        self._tree.setHeaderLabels(columns)
        self._tree.setRootIsDecorated(False)
        self._tree.setAlternatingRowColors(True)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {th.bg_surface};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(4)}px;
                font-size: {sm.s(13)}px;
                alternate-background-color: {th.input_bg};
            }}
            QTreeWidget::item {{
                padding: {sm.s(4)}px;
                border-bottom: 1px solid {th.border_default};
            }}
            QTreeWidget::item:selected {{
                background-color: {th.accent_blue};
                color: {th.text_on_accent};
            }}
            QHeaderView::section {{
                background-color: {th.bg_surface};
                color: {th.text_muted};
                border: none;
                border-bottom: 1px solid {th.border_default};
                padding: {sm.s(4)}px {sm.s(8)}px;
                font-weight: bold;
            }}
        """)

        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        header.resizeSection(1, sm.s(70))
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, sm.s(80))
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, sm.s(60))
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        self._tree.itemSelectionChanged.connect(self._on_select)
        self._tree.itemDoubleClicked.connect(lambda _: self._toggle_selected())

        layout.addWidget(self._tree, 1)

    def _build_buttons(self, layout: QVBoxLayout, th, sm) -> None:
        btn_row = QHBoxLayout()
        self._btn_enable = themed_button(
            self, text=t("common.enable"), style="secondary",
            command=self._enable_selected,
        )
        self._btn_enable.setEnabled(False)
        btn_row.addWidget(self._btn_enable)

        self._btn_disable = themed_button(
            self, text=t("common.disable"), style="secondary",
            command=self._disable_selected,
        )
        self._btn_disable.setEnabled(False)
        btn_row.addWidget(self._btn_disable)

        self._btn_reload = themed_button(
            self, text=t("plugin.reload"), style="secondary",
            command=self._reload_selected,
        )
        self._btn_reload.setEnabled(False)
        btn_row.addWidget(self._btn_reload)

        self._btn_edit = themed_button(
            self, text=t("common.edit"), style="secondary",
            command=self._edit_selected,
        )
        self._btn_edit.setEnabled(False)
        btn_row.addWidget(self._btn_edit)

        btn_row.addStretch()
        layout.addLayout(btn_row)

    def _build_detail(self, layout: QVBoxLayout, th, sm) -> None:
        detail_frame = themed_frame(self)
        detail_layout = QVBoxLayout(detail_frame)
        detail_layout.setContentsMargins(sm.s(th.pad_sm), sm.s(th.pad_sm), sm.s(th.pad_sm), sm.s(th.pad_sm))

        detail_lbl = themed_label(self, text=t("plugin.detail"), style="subtitle")
        detail_layout.addWidget(detail_lbl)

        self._detail_text = QTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setMaximumHeight(sm.s(120))
        self._detail_text.setStyleSheet(f"""
            QTextEdit {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(3)}px;
                padding: {sm.s(4)}px;
                font-family: monospace;
            }}
        """)
        detail_layout.addWidget(self._detail_text)

        layout.addWidget(detail_frame)

    def _selected_plugin_id(self) -> str | None:
        items = self._tree.selectedItems()
        if not items:
            return None
        return items[0].data(0, Qt.UserRole)

    def _refresh(self) -> None:
        selected_id = self._selected_plugin_id()
        self._tree.clear()

        loader = self.app.plugin_loader
        if loader is None:
            return

        all_plugins = loader.get_all_plugins()

        state_labels = {
            "discovered": t("plugin.state.discovered"),
            "loaded": t("plugin.state.loaded"),
            "active": t("plugin.state.active"),
            "unloaded": t("plugin.state.unloaded"),
            "error": t("plugin.state.error"),
        }

        for plugin_id, entry in all_plugins.items():
            meta = entry.metadata
            node_count = len(entry.context.registered_types) if entry.context else 0
            state_str = state_labels.get(entry.state.value, entry.state.value)

            item = QTreeWidgetItem([
                meta.plugin_name,
                meta.version,
                state_str,
                str(node_count),
                meta.description,
            ])
            item.setData(0, Qt.UserRole, plugin_id)
            self._tree.addTopLevelItem(item)

        if selected_id:
            for i in range(self._tree.topLevelItemCount()):
                item = self._tree.topLevelItem(i)
                if item.data(0, Qt.UserRole) == selected_id:
                    self._tree.setCurrentItem(item)
                    break

    def _on_select(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            self._btn_enable.setEnabled(False)
            self._btn_disable.setEnabled(False)
            self._btn_reload.setEnabled(False)
            self._btn_edit.setEnabled(False)
            return

        loader = self.app.plugin_loader
        if loader is None:
            return

        entry = loader.get_plugin(plugin_id)
        if entry is None:
            return

        is_loaded = entry.state in _LOADED_STATES
        self._btn_enable.setEnabled(not is_loaded)
        self._btn_disable.setEnabled(is_loaded)
        self._btn_reload.setEnabled(is_loaded)
        self._btn_edit.setEnabled(True)

        self._update_detail(plugin_id, entry)

    def _update_detail(self, plugin_id: str, entry) -> None:
        meta = entry.metadata
        deps = ", ".join(meta.dependencies) if meta.dependencies else "-"
        perms = ", ".join(meta.permissions) if meta.permissions else "-"
        error_line = (
            f"\n{t('plugin.state.error')}: {entry.error_message}"
            if entry.error_message
            else ""
        )

        loader = self.app.plugin_loader
        node_types = loader.get_registered_node_types(plugin_id) if loader else []
        nodes_line = (
            f"\n{t('plugin.registered_nodes')}: {', '.join(node_types)}"
            if node_types
            else ""
        )

        manifest = loader.get_manifest_data(plugin_id) if loader else None
        enabled_val = manifest.get("enabled", True) if manifest else True
        enabled_line = f"{t('plugin.edit.auto_load')}: {'✓' if enabled_val else '✗'}"

        detail = (
            f"ID: {meta.plugin_id}\n"
            f"{t('plugin.version')}: {meta.version}  "
            f"{t('plugin.author')}: {meta.author}\n"
            f"{t('plugin.dependencies')}: {deps}\n"
            f"{t('plugin.permissions')}: {perms}\n"
            f"{enabled_line}"
            f"{nodes_line}"
            f"{error_line}"
        )

        self._detail_text.setPlainText(detail)

    def _exec_plugin_action(self, action, error_key: str) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        try:
            action()
            self._refresh()
        except (ValueError, RuntimeError) as e:
            self._show_error(t(error_key), str(e))

    def _enable_selected(self) -> None:
        self._exec_plugin_action(
            lambda: self.app.plugin_loader.load(self._selected_plugin_id()),
            "common.load_failed",
        )

    def _disable_selected(self) -> None:
        self._exec_plugin_action(
            lambda: self.app.plugin_loader.unload(self._selected_plugin_id()),
            "plugin.msg.unload_failed",
        )

    def _reload_selected(self) -> None:
        self._exec_plugin_action(
            lambda: self.app.plugin_loader.reload(self._selected_plugin_id()),
            "plugin.msg.reload_failed",
        )

    def _edit_selected(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        dlg = PluginEditDialog(self, self.app.plugin_loader, plugin_id)
        if dlg.exec() == QDialog.Accepted:
            self._refresh()

    def _toggle_selected(self) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        loader = self.app.plugin_loader
        if loader is None:
            return
        entry = loader.get_plugin(plugin_id)
        if entry is None:
            return
        if entry.state in _LOADED_STATES:
            self._disable_selected()
        else:
            self._enable_selected()
