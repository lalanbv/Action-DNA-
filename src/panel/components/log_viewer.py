"""LogViewer — 日志查看器 UI 组件 (P5 增强版)

基于 Treeview 显示 RingBufferLog 中的日志条目，
支持实时更新、类型着色、自动滚动、类型过滤和导出。
"""

from __future__ import annotations

import tkinter as tk
from collections import deque
from tkinter import ttk, filedialog

from src.core.debug.ring_buffer_log import LogEntry, LogEventType, RingBufferLog
from src.panel.canvas.theme import current_theme
from src.panel.components.log_viewer_utils import FILTER_GROUPS, tint_for, type_color
from src.utils.i18n import t


class LogViewer(tk.Frame):
    """日志查看器 UI 组件。

    嵌入到 WorkflowPage 或单独的调试面板中。
    通过 RingBufferLog.on_append 回调实现实时更新。
    """

    def __init__(
        self,
        parent: tk.Widget,
        log: RingBufferLog,
        max_visible: int = 200,
    ) -> None:
        theme = current_theme()
        super().__init__(parent, bg=theme.panel_bg)
        self._log = log
        self._max_visible = max_visible
        self._auto_scroll = True
        self._active_filter: list[LogEventType] | None = None
        self._all_entries: deque[LogEntry] = deque(maxlen=2000)
        self._filter_var = tk.StringVar(value="workflow.log.filter_all")

        self._build_ui()
        self._load_existing_entries()
        self._register_log_callback()

    # ── 辅助 ──────────────────────────────────────────────

    @staticmethod
    def _make_log_btn(parent: tk.Frame, text: str, command: callable) -> "LabelButton":
        from src.panel.widgets import LabelButton
        theme = current_theme()
        return LabelButton(
            parent,
            text=text,
            command=command,
            bg=theme.btn_bg,
            fg=theme.text_primary,
            activeforeground=theme.text_primary,
            border_color=theme.btn_border,
            font=theme.font_toolbar,
            padx=6,
            pady=1,
        )

    # ── 构建 UI ────────────────────────────────────────────

    def _build_ui(self) -> None:
        theme = current_theme()

        # 工具栏
        toolbar = tk.Frame(self, bg=theme.panel_header_bg)
        toolbar.pack(fill=tk.X)

        tk.Label(
            toolbar, text=t("workflow.log.title"),
            bg=theme.panel_header_bg, fg=theme.text_primary,
            font=theme.font_toolbar,
        ).pack(side=tk.LEFT, padx=5)

        # 类型过滤按钮
        filter_frame = tk.Frame(toolbar, bg=theme.panel_header_bg)
        filter_frame.pack(side=tk.LEFT, padx=8)
        from src.panel.canvas.scale import scale_manager
        sm = scale_manager()
        for label, types in FILTER_GROUPS:
            rb = tk.Radiobutton(
                filter_frame,
                text=t(label),
                variable=self._filter_var,
                value=label,
                command=lambda t=types: self._set_filter(t),
                bg=theme.panel_header_bg,
                fg=theme.text_secondary,
                selectcolor=theme.bg_surface,
                activebackground=theme.panel_header_bg,
                activeforeground=theme.text_primary,
                font=(theme.font_family, sm.s(8)),
                indicatoron=0,
                bd=1,
                relief=tk.FLAT,
                padx=6,
                pady=1,
            )
            rb.pack(side=tk.LEFT, padx=1)

        self._auto_scroll_var = tk.BooleanVar(value=True)
        tk.Checkbutton(
            toolbar,
            text=t("workflow.log.auto_scroll"),
            variable=self._auto_scroll_var,
            command=self._on_auto_scroll_toggle,
            bg=theme.panel_header_bg,
            fg=theme.text_secondary,
            selectcolor=theme.bg_surface,
            activebackground=theme.panel_header_bg,
            activeforeground=theme.text_primary,
            font=(theme.font_family, sm.s(8)),
        ).pack(side=tk.RIGHT, padx=5)

        self._make_log_btn(toolbar, t("workflow.log.clear"), self._clear_log).pack(
            side=tk.RIGHT, padx=2,
        )
        self._make_log_btn(toolbar, t("workflow.log.export"), self._export_log).pack(
            side=tk.RIGHT, padx=2,
        )

        # Treeview
        columns = ("time", "type", "node", "message")
        self._tree = ttk.Treeview(
            self, columns=columns, show="headings", height=8,
        )
        self._tree.heading("time", text=t("workflow.log.col_time"))
        self._tree.heading("type", text=t("workflow.log.col_type"))
        self._tree.heading("node", text=t("workflow.log.col_node"))
        self._tree.heading("message", text=t("workflow.log.col_message"))

        self._tree.column("time", width=100, minwidth=80, stretch=True)
        self._tree.column("type", width=100, minwidth=80, stretch=True)
        self._tree.column("node", width=80, minwidth=60, stretch=True)
        self._tree.column("message", width=300, minwidth=200, stretch=True)

        self._log_cols = [
            ("time", 0.15), ("type", 0.15), ("node", 0.12), ("message", 0.58),
        ]
        self._tree.bind("<Configure>", self._on_tree_configure)

        scrollbar = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # 标签样式: 前景色 + 行背景着色
        for event_type in LogEventType:
            self._tree.tag_configure(
                event_type.value,
                foreground=type_color(event_type),
                background=tint_for(event_type),
            )

    # ── 过滤 ──────────────────────────────────────────────

    def _on_tree_configure(self, event: tk.Event) -> None:
        total_w = event.width
        for col, ratio in self._log_cols:
            self._tree.column(col, width=max(30, int(total_w * ratio)))

    def _set_filter(self, types: list[LogEventType] | None) -> None:
        self._active_filter = types
        self._refresh_tree()

    def _refresh_tree(self) -> None:
        """根据当前过滤条件重新填充 Treeview"""
        for item in self._tree.get_children():
            self._tree.delete(item)
        for entry in self._all_entries:
            self._insert_entry(entry)

    # ── 数据加载 ──────────────────────────────────────────

    def _load_existing_entries(self) -> None:
        for entry in self._log.get_all():
            self._all_entries.append(entry)
            self._insert_entry(entry)

    def _register_log_callback(self) -> None:
        self._log.on_append(self._on_new_entry)

    def _on_new_entry(self, entry: LogEntry) -> None:
        self.after(0, self._handle_new_entry, entry)

    def _handle_new_entry(self, entry: LogEntry) -> None:
        self._all_entries.append(entry)
        self._insert_entry(entry)

    def _insert_entry(self, entry: LogEntry) -> None:
        """插入单条日志到 Treeview (考虑过滤)"""
        if self._active_filter is not None and entry.event_type not in self._active_filter:
            return

        item_id = self._tree.insert(
            "",
            tk.END,
            values=(
                entry.time_str,
                entry.event_type.value,
                entry.node_id,
                entry.message,
            ),
            tags=(entry.event_type.value,),
        )

        children = self._tree.get_children()
        while len(children) > self._max_visible:
            self._tree.delete(children[0])
            children = self._tree.get_children()

        if self._auto_scroll:
            self._tree.see(item_id)

    # ── 操作 ──────────────────────────────────────────────

    def _on_auto_scroll_toggle(self) -> None:
        self._auto_scroll = self._auto_scroll_var.get()

    def _clear_log(self) -> None:
        self._log.clear()
        self._all_entries.clear()
        for item in self._tree.get_children():
            self._tree.delete(item)

    def _export_log(self) -> None:
        filepath = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[(t("dialog.filetype.json"), "*.json"), (t("dialog.filetype.all"), "*.*")],
        )
        if filepath:
            self._log.export_to_file(filepath)

    def destroy(self) -> None:
        """注销回调，防止页面销毁后 TclError"""
        self._log.remove_on_append(self._on_new_entry)
        super().destroy()

    def rebuild_tags(self) -> None:
        """重建 Treeview tag 样式（主题切换后调用）"""
        for event_type in LogEventType:
            self._tree.tag_configure(
                event_type.value,
                foreground=type_color(event_type),
                background=tint_for(event_type),
            )
