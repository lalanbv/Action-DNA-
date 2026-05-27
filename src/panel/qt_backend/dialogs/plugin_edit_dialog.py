"""PluginEditDialog — 插件编辑对话框。

从 plugin_page.py 抽取的独立对话框模块。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button
from src.utils.i18n import t


class PluginEditDialog(QDialog):
    """插件编辑对话框。"""

    def __init__(self, parent: QWidget, plugin_loader, plugin_id: str) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self._loader = plugin_loader
        self._plugin_id = plugin_id

        self.setWindowTitle(t("plugin.edit_title", plugin_id=plugin_id))
        self.setMinimumSize(sm.s(420), sm.s(400))
        self.setModal(True)

        manifest = plugin_loader.get_manifest_data(plugin_id)
        if manifest is None:
            QMessageBox.critical(
                self, t("common.load_failed"),
                t("plugin.msg.manifest_read_failed"),
            )
            self.reject()
            return

        self._manifest = manifest

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sm.s(12), sm.s(12), sm.s(12), sm.s(12))
        layout.setSpacing(sm.s(6))

        form = QFormLayout()
        form.setSpacing(sm.s(6))

        label_style = f"color: {th.text_primary};"
        value_style = f"color: {th.text_muted};"
        entry_style = f"""
            QLineEdit {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px;
            }}
        """

        id_lbl = QLabel(manifest.get("plugin_id", ""))
        id_lbl.setStyleSheet(value_style)
        id_lbl_field = QLabel(t("plugin.edit.id"))
        id_lbl_field.setStyleSheet(label_style)
        form.addRow(id_lbl_field, id_lbl)

        entry_lbl = QLabel(manifest.get("entry_class", "Plugin"))
        entry_lbl.setStyleSheet(value_style)
        entry_lbl_field = QLabel(t("plugin.edit.entry_class"))
        entry_lbl_field.setStyleSheet(label_style)
        form.addRow(entry_lbl_field, entry_lbl)

        self._name_entry = QLineEdit(manifest.get("plugin_name", ""))
        self._name_entry.setStyleSheet(entry_style)
        name_field = QLabel(t("common.name"))
        name_field.setStyleSheet(label_style)
        form.addRow(name_field, self._name_entry)

        self._version_entry = QLineEdit(manifest.get("version", ""))
        self._version_entry.setStyleSheet(entry_style)
        ver_field = QLabel(t("plugin.version"))
        ver_field.setStyleSheet(label_style)
        form.addRow(ver_field, self._version_entry)

        self._desc_entry = QLineEdit(manifest.get("description", ""))
        self._desc_entry.setStyleSheet(entry_style)
        desc_field = QLabel(t("plugin.description"))
        desc_field.setStyleSheet(label_style)
        form.addRow(desc_field, self._desc_entry)

        self._author_entry = QLineEdit(manifest.get("author", ""))
        self._author_entry.setStyleSheet(entry_style)
        author_field = QLabel(t("plugin.author"))
        author_field.setStyleSheet(label_style)
        form.addRow(author_field, self._author_entry)

        self._enabled_cb = QCheckBox(t("plugin.edit.auto_load"))
        self._enabled_cb.setChecked(manifest.get("enabled", True))
        self._enabled_cb.setStyleSheet(f"color: {th.text_primary};")
        form.addRow(self._enabled_cb)

        deps = manifest.get("dependencies", [])
        if deps:
            deps_lbl = QLabel(", ".join(deps))
            deps_lbl.setStyleSheet(value_style)
            deps_lbl.setWordWrap(True)
            deps_field = QLabel(t("plugin.dependencies"))
            deps_field.setStyleSheet(label_style)
            form.addRow(deps_field, deps_lbl)

        perms = manifest.get("permissions", [])
        if perms:
            perms_lbl = QLabel(", ".join(perms))
            perms_lbl.setStyleSheet(value_style)
            perms_lbl.setWordWrap(True)
            perms_field = QLabel(t("plugin.permissions"))
            perms_field.setStyleSheet(label_style)
            form.addRow(perms_field, perms_lbl)

        node_types = plugin_loader.get_registered_node_types(plugin_id)
        if node_types:
            nodes_lbl = QLabel(", ".join(node_types))
            nodes_lbl.setStyleSheet(value_style)
            nodes_lbl.setWordWrap(True)
            nodes_field = QLabel(t("plugin.registered_nodes"))
            nodes_field.setStyleSheet(label_style)
            form.addRow(nodes_field, nodes_lbl)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = themed_button(self, text=t("common.ok"), style="primary", command=self._on_save)
        btn_row.addWidget(ok_btn)
        cancel_btn = themed_button(self, text=t("common.cancel"), style="secondary", command=self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        updates = {
            "plugin_name": self._name_entry.text(),
            "version": self._version_entry.text(),
            "description": self._desc_entry.text(),
            "author": self._author_entry.text(),
            "enabled": self._enabled_cb.isChecked(),
        }
        try:
            self._loader.update_manifest(self._plugin_id, updates)
        except (ValueError, RuntimeError, OSError) as e:
            QMessageBox.critical(self, t("common.save_failed"), str(e))
            return
        self.accept()
