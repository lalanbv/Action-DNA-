"""插件管理页面 — 查看插件状态、启用/禁用/编辑插件"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable

from src.core.plugins.plugin_loader import PluginState
from src.panel.canvas.theme import current_theme
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import PLUGIN_DESC, PLUGIN_TITLE
from src.panel.pages.page_registry import register_page
from src.panel.widgets import (
    themed_button,
    themed_checkbutton,
    themed_entry,
    themed_frame,
    themed_label,
    themed_labelframe,
)
from src.utils.i18n import t


@register_page("plugin", label_i18n=PLUGIN_TITLE, desc_i18n=PLUGIN_DESC, icon="🧩", category="main")
class PluginPage(BasePage):
    """插件管理页面"""

    def __init__(self, parent: tk.Widget, app, **kwargs):
        super().__init__(parent, app, **kwargs)
        self._tree: ttk.Treeview
        self._ptree_cols: list[tuple[str, float]] = []
        self._btn_enable: tk.Widget
        self._btn_disable: tk.Widget
        self._btn_reload: tk.Widget
        self._btn_edit: tk.Widget
        self._detail_text: tk.Text

    _LOADED_STATES = frozenset({PluginState.LOADED, PluginState.ACTIVE})

    def title(self) -> str:
        return t("plugin.title")

    def _selected_plugin_id(self) -> str | None:
        sel = self._tree.selection()
        return sel[0] if sel else None

    def _exec_plugin_action(
        self, action: Callable[[], None], error_key: str,
    ) -> None:
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        try:
            action()
            self._refresh()
        except (ValueError, RuntimeError) as e:
            messagebox.showerror(t(error_key), str(e))

    def build(self):
        th = current_theme()

        # ── 统一工具栏 ──
        toolbar = self._build_toolbar_base("plugin.title")

        toolbar.add_spacer()

        toolbar.make_button(
            "actions", text=t("plugin.refresh"), icon="refresh",
            command=self._refresh,
            tooltip=t("plugin.refresh"),
        )

        # 插件列表 Treeview
        columns = ("name", "version", "state", "nodes", "description")
        tree_frame = themed_frame(self.frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=th.pad_md, pady=th.pad_xs)

        self._tree = ttk.Treeview(
            tree_frame, columns=columns, show="headings", selectmode="browse",
        )
        self._tree.heading("name", text=t("common.name"))
        self._tree.heading("version", text=t("plugin.version"))
        self._tree.heading("state", text=t("plugin.col.state"))
        self._tree.heading("nodes", text=t("plugin.col.nodes"))
        self._tree.heading("description", text=t("plugin.description"))

        self._tree.column("name", width=120, minwidth=80, stretch=True)
        self._tree.column("version", width=70, minwidth=50, stretch=True)
        self._tree.column("state", width=80, minwidth=60, stretch=True)
        self._tree.column("nodes", width=60, minwidth=40, stretch=True)
        self._tree.column("description", width=300, minwidth=150, stretch=True)

        self._ptree_cols = [
            ("name", 0.18), ("version", 0.10), ("state", 0.12),
            ("nodes", 0.10), ("description", 0.50),
        ]
        self._tree.bind("<Configure>", self._on_tree_configure)

        scrollbar = ttk.Scrollbar(
            tree_frame, orient=tk.VERTICAL, command=self._tree.yview,
        )
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 底部操作按钮
        btn_frame = themed_frame(self.frame)
        btn_frame.pack(fill=tk.X, padx=th.pad_md, pady=(th.pad_xs, th.pad_md))

        self._btn_enable = themed_button(
            btn_frame, text=t("common.enable"),
            command=self._enable_selected, state=tk.DISABLED,
        )
        self._btn_enable.pack(side=tk.LEFT, padx=th.pad_xs)

        self._btn_disable = themed_button(
            btn_frame, text=t("common.disable"),
            command=self._disable_selected, state=tk.DISABLED,
        )
        self._btn_disable.pack(side=tk.LEFT, padx=th.pad_xs)

        self._btn_reload = themed_button(
            btn_frame, text=t("plugin.reload"),
            command=self._reload_selected, state=tk.DISABLED,
        )
        self._btn_reload.pack(side=tk.LEFT, padx=th.pad_xs)

        self._btn_edit = themed_button(
            btn_frame, text=t("common.edit"),
            command=self._edit_selected, state=tk.DISABLED,
        )
        self._btn_edit.pack(side=tk.LEFT, padx=th.pad_xs)

        # 详情区域
        detail_frame = themed_labelframe(self.frame, text=t("plugin.detail"))
        detail_frame.pack(fill=tk.X, padx=th.pad_md, pady=(0, th.pad_md))

        self._detail_text = tk.Text(
            detail_frame, height=5, wrap=tk.WORD, state=tk.DISABLED,
            bg=th.input_bg, fg=th.input_fg,
            insertbackground=th.text_primary, font=th.font_mono,
        )
        self._detail_text.pack(fill=tk.X, padx=th.pad_sm, pady=th.pad_xs)

        # 绑定选择事件
        self._tree.bind("<<TreeviewSelect>>", self._on_select)
        self._tree.bind("<Double-1>", lambda _: self._toggle_selected())

        # 加载数据
        self._refresh()

    def _on_tree_configure(self, event: tk.Event) -> None:
        total_w = event.width
        for col, ratio in self._ptree_cols:
            self._tree.column(col, width=max(30, int(total_w * ratio)))

    def _refresh(self) -> None:
        """刷新插件列表。"""
        selected_id = self._selected_plugin_id()

        for item in self._tree.get_children():
            self._tree.delete(item)

        loader = self.app.plugin_loader
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
            node_count = (
                len(entry.context.registered_types)
                if entry.context
                else 0
            )
            state_str = state_labels.get(
                entry.state.value, entry.state.value,
            )
            self._tree.insert(
                "", tk.END, iid=plugin_id,
                values=(
                    meta.plugin_name,
                    meta.version,
                    state_str,
                    str(node_count),
                    meta.description,
                ),
            )

        if selected_id and self._tree.exists(selected_id):
            self._tree.selection_set(selected_id)
            self._tree.focus(selected_id)

    def _on_select(self, _event) -> None:
        """选中插件时更新按钮状态和详情。"""
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            self._btn_enable.config(state=tk.DISABLED)
            self._btn_disable.config(state=tk.DISABLED)
            self._btn_reload.config(state=tk.DISABLED)
            self._btn_edit.config(state=tk.DISABLED)
            return

        entry = self.app.plugin_loader.get_plugin(plugin_id)
        if entry is None:
            return

        is_loaded = entry.state in self._LOADED_STATES
        self._btn_enable.config(
            state=tk.DISABLED if is_loaded else tk.NORMAL,
        )
        self._btn_disable.config(
            state=tk.NORMAL if is_loaded else tk.DISABLED,
        )
        self._btn_reload.config(
            state=tk.NORMAL if is_loaded else tk.DISABLED,
        )
        self._btn_edit.config(state=tk.NORMAL)

        self._update_detail(plugin_id, entry)

    def _update_detail(self, plugin_id: str, entry) -> None:
        """更新详情区域。"""
        meta = entry.metadata
        deps = ", ".join(meta.dependencies) if meta.dependencies else "-"
        perms = ", ".join(meta.permissions) if meta.permissions else "-"
        error_line = (
            f"\n{t('plugin.state.error')}: {entry.error_message}"
            if entry.error_message
            else ""
        )

        node_types = self.app.plugin_loader.get_registered_node_types(plugin_id)
        nodes_line = (
            f"\n{t('plugin.registered_nodes')}: {', '.join(node_types)}"
            if node_types
            else ""
        )

        manifest = self.app.plugin_loader.get_manifest_data(plugin_id)
        enabled_val = manifest.get("enabled", True) if manifest else True
        enabled_line = (
            f"{t('plugin.edit.auto_load')}: {'✓' if enabled_val else '✗'}"
        )

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

        self._detail_text.config(state=tk.NORMAL)
        self._detail_text.delete("1.0", tk.END)
        self._detail_text.insert("1.0", detail)
        self._detail_text.config(state=tk.DISABLED)

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
        """打开插件编辑对话框。"""
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        _PluginEditDialog(self.frame, self.app.plugin_loader, plugin_id, self._refresh)

    def _toggle_selected(self) -> None:
        """双击切换启用/禁用。"""
        plugin_id = self._selected_plugin_id()
        if plugin_id is None:
            return
        entry = self.app.plugin_loader.get_plugin(plugin_id)
        if entry is None:
            return
        if entry.state in self._LOADED_STATES:
            self._disable_selected()
        else:
            self._enable_selected()


class _PluginEditDialog(tk.Toplevel):
    """插件编辑对话框 — 编辑 plugin.json 可配置字段。"""

    def __init__(self, parent, plugin_loader, plugin_id: str, on_save_callback):
        super().__init__(parent)
        self._loader = plugin_loader
        self._plugin_id = plugin_id
        self._save_callback = on_save_callback
        th = current_theme()

        self.title(t("plugin.edit_title", plugin_id=plugin_id))
        self.resizable(False, False)
        self.configure(bg=th.dialog_bg)

        manifest = self._loader.get_manifest_data(plugin_id)
        if manifest is None:
            messagebox.showerror(t("common.load_failed"), t("plugin.msg.manifest_read_failed"))
            self.destroy()
            return

        self._manifest = manifest

        main = themed_frame(self)
        main.pack(fill=tk.BOTH, expand=True, padx=th.pad_md, pady=th.pad_md)

        row = 0

        # 插件 ID（只读）
        themed_label(main, text=t("plugin.edit.id")).grid(row=row, column=0, sticky=tk.W, pady=th.pad_xs)
        themed_label(main, text=manifest.get("plugin_id", ""), fg=th.text_muted).grid(
            row=row, column=1, sticky=tk.W, pady=th.pad_xs, columnspan=2,
        )
        row += 1

        # 入口类（只读）
        themed_label(main, text=t("plugin.edit.entry_class")).grid(
            row=row, column=0, sticky=tk.W, pady=th.pad_xs,
        )
        themed_label(
            main, text=manifest.get("entry_class", "Plugin"), fg=th.text_muted,
        ).grid(row=row, column=1, sticky=tk.W, pady=th.pad_xs, columnspan=2)
        row += 1

        # 名称
        themed_label(main, text=t("common.name")).grid(
            row=row, column=0, sticky=tk.W, pady=th.pad_xs,
        )
        self._name_var = tk.StringVar(value=manifest.get("plugin_name", ""))
        themed_entry(main, textvariable=self._name_var, width=30).grid(
            row=row, column=1, sticky=tk.W, pady=th.pad_xs, columnspan=2,
        )
        row += 1

        # 版本
        themed_label(main, text=t("plugin.version")).grid(
            row=row, column=0, sticky=tk.W, pady=th.pad_xs,
        )
        self._version_var = tk.StringVar(value=manifest.get("version", ""))
        themed_entry(main, textvariable=self._version_var, width=15).grid(
            row=row, column=1, sticky=tk.W, pady=th.pad_xs,
        )
        row += 1

        # 描述
        themed_label(main, text=t("plugin.description")).grid(
            row=row, column=0, sticky=tk.W, pady=th.pad_xs,
        )
        self._desc_var = tk.StringVar(value=manifest.get("description", ""))
        themed_entry(main, textvariable=self._desc_var, width=40).grid(
            row=row, column=1, sticky=tk.W, pady=th.pad_xs, columnspan=2,
        )
        row += 1

        # 作者
        themed_label(main, text=t("plugin.author")).grid(
            row=row, column=0, sticky=tk.W, pady=th.pad_xs,
        )
        self._author_var = tk.StringVar(value=manifest.get("author", ""))
        themed_entry(main, textvariable=self._author_var, width=20).grid(
            row=row, column=1, sticky=tk.W, pady=th.pad_xs,
        )
        row += 1

        # 自动加载
        self._enabled_var = tk.BooleanVar(value=manifest.get("enabled", True))
        themed_checkbutton(
            main, text=t("plugin.edit.auto_load"), variable=self._enabled_var,
        ).grid(row=row, column=0, columnspan=3, sticky=tk.W, pady=th.pad_xs)
        row += 1

        # 依赖（只读显示）
        deps = manifest.get("dependencies", [])
        if deps:
            themed_label(main, text=t("plugin.dependencies")).grid(
                row=row, column=0, sticky=tk.W, pady=th.pad_xs,
            )
            themed_label(main, text=", ".join(deps), fg=th.text_muted).grid(
                row=row, column=1, sticky=tk.W, pady=th.pad_xs, columnspan=2,
            )
            row += 1

        # 权限（只读显示）
        perms = manifest.get("permissions", [])
        if perms:
            themed_label(main, text=t("plugin.permissions")).grid(
                row=row, column=0, sticky=tk.W, pady=th.pad_xs,
            )
            themed_label(main, text=", ".join(perms), fg=th.text_muted).grid(
                row=row, column=1, sticky=tk.W, pady=th.pad_xs, columnspan=2,
            )
            row += 1

        # 已注册节点（只读显示）
        node_types = self._loader.get_registered_node_types(plugin_id)
        if node_types:
            themed_label(main, text=t("plugin.registered_nodes")).grid(
                row=row, column=0, sticky=tk.W, pady=th.pad_xs,
            )
            themed_label(
                main, text=", ".join(node_types), fg=th.text_muted, wraplength=300,
            ).grid(row=row, column=1, sticky=tk.W, pady=th.pad_xs, columnspan=2)
            row += 1

        # 按钮
        btn_frame = themed_frame(main)
        btn_frame.grid(row=row, column=0, columnspan=3, pady=(th.pad_md, 0))

        themed_button(
            btn_frame, text=t("common.ok"), command=self._on_save, style="primary",
        ).pack(side=tk.LEFT, padx=th.pad_xs)
        themed_button(
            btn_frame, text=t("common.cancel"), command=self.destroy,
        ).pack(side=tk.LEFT, padx=th.pad_xs)

        self.transient(parent)
        self.grab_set()
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _on_save(self) -> None:
        """保存编辑。"""
        updates = {
            "plugin_name": self._name_var.get(),
            "version": self._version_var.get(),
            "description": self._desc_var.get(),
            "author": self._author_var.get(),
            "enabled": self._enabled_var.get(),
        }
        try:
            self._loader.update_manifest(self._plugin_id, updates)
        except (ValueError, RuntimeError, OSError) as e:
            messagebox.showerror(t("common.save_failed"), str(e))
            return

        callback = self._save_callback
        self.grab_release()
        self.destroy()
        if callback:
            callback()
