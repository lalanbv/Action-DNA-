"""WorkflowPaletteMixin — 节点面板构建、搜索、折叠、帮助标签页。"""

import tkinter as tk
from tkinter import ttk

from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.canvas.scale import scale_manager
from src.utils.platform import IS_MACOS, IS_LINUX
from src.panel.widgets import (
    LabelButton,
    themed_entry,
    themed_frame,
    themed_label,
    themed_separator,
)
from src.panel.components.palette_data import (
    ACTION_PALETTE as _ACTION_PALETTE,
    FLOW_PALETTE as _FLOW_PALETTE,
)
from src.utils.i18n import t


class WorkflowPaletteMixin:
    """节点面板相关方法，供 WorkflowPage 继承。

    依赖 self 属性:
        _paned, _palette_mode, _palette_labels, _palette_btn_widgets,
        _palette_buttons, _canvas
    """

    def _build_node_palette(self):
        theme = current_theme()
        sm = scale_manager()
        self._palette_outer = tk.Frame(
            self._paned, bg=theme.panel_bg, width=sm.s(theme.panel_width_left),
        )
        self._palette_outer.pack_propagate(False)

        self._section_arrows: dict[str, tk.Label] = {}
        self._section_bodies: dict[str, tk.Frame] = {}
        self._section_headers: dict[str, tk.Frame] = {}
        self._section_expanded: dict[str, bool] = {}
        self._palette_buttons: list[tk.Frame] = []
        self._palette_btn_widgets: list[LabelButton] = []
        self._palette_labels: list[tk.Label] = []

        self._notebook = ttk.Notebook(self._palette_outer)
        self._notebook.pack(fill=tk.BOTH, expand=True)

        self._build_nodes_tab(theme, sm)
        self._build_monitor_tab(theme, sm)
        self._build_help_tab_wrapper(theme, sm)

        self.frame.after(150, self._force_palette_refresh)

    # ── 节点标签页 ──────────────────────────────────────────

    def _build_nodes_tab(self, theme, sm):
        nodes_tab = tk.Frame(self._notebook, bg=theme.panel_bg)
        self._notebook.add(nodes_tab, text=t("workflow.tab.nodes"))

        self._palette_search_var = tk.StringVar()
        search_entry = themed_entry(
            nodes_tab, textvariable=self._palette_search_var,
        )
        search_entry.pack(fill=tk.X, padx=sm.s(4), pady=(sm.s(4), sm.s(2)))
        search_entry.bind("<KeyRelease>", self._on_palette_search)

        self._palette_search_placeholder = t("workflow.palette.search_placeholder")
        self._palette_search_entry = search_entry
        self._palette_search_entry.insert(0, self._palette_search_placeholder)
        self._palette_search_entry.configure(fg=theme.text_muted)
        self._palette_search_entry.bind("<FocusIn>", self._on_search_focus_in)
        self._palette_search_entry.bind("<FocusOut>", self._on_search_focus_out)

        self._palette_canvas = tk.Canvas(
            nodes_tab, highlightthickness=0, bg=theme.panel_bg,
        )
        self._palette_scrollbar = ttk.Scrollbar(
            nodes_tab, orient=tk.VERTICAL,
            command=self._palette_canvas.yview,
        )
        self._palette_inner = tk.Frame(self._palette_canvas, bg=theme.panel_bg)

        self._palette_inner.bind("<Configure>", self._on_palette_configure)
        self._palette_win_id = self._palette_canvas.create_window(
            (0, 0), window=self._palette_inner, anchor=tk.NW,
        )
        self._palette_canvas.configure(yscrollcommand=self._palette_scrollbar.set)

        self._palette_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._palette_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._palette_canvas.bind("<Enter>", self._palette_bind_wheel)
        self._palette_canvas.bind("<Leave>", self._palette_unbind_wheel)
        self._palette_inner.bind("<Enter>", self._palette_bind_wheel)

        self._build_action_section(sm)
        self._build_flow_section(sm)
        self._update_section_counts()

    def _build_action_section(self, sm):
        row_idx = 0
        body_action = self._build_collapsible_section(
            self._palette_inner, t("workflow.palette.section_action"), "action",
        )
        for action_type, i18n_key in _ACTION_PALETTE:
            color = node_fill_color("ACTION")
            row, btn = self._make_palette_button(
                body_action, f"+ {t(i18n_key)}", color,
                lambda at=action_type: self._on_add_action_node(at),
            )
            row.grid(row=row_idx, column=0, sticky="ew", padx=2, pady=1)
            row._palette_text = t(i18n_key)
            row._palette_section_key = "action"
            self._palette_buttons.append(row)
            self._palette_btn_widgets.append(btn)
            row_idx += 1

    def _build_flow_section(self, sm):
        from src.core.flow import NodeType

        row_idx = 0
        body_flow = self._build_collapsible_section(
            self._palette_inner, t("workflow.palette.section_flow"), "flow",
        )
        for node_type, i18n_key in _FLOW_PALETTE:
            color = node_fill_color(node_type)
            row, btn = self._make_palette_button(
                body_flow, t(i18n_key), color,
                lambda nt=node_type: self._on_add_node(nt),
            )
            row.grid(row=row_idx, column=0, sticky="ew", padx=2, pady=1)
            row._palette_text = t(i18n_key)
            row._palette_section_key = "flow"
            self._palette_buttons.append(row)
            self._palette_btn_widgets.append(btn)
            row_idx += 1

        for node_type, i18n_key in [
            (NodeType.START, "workflow.palette.start"),
            (NodeType.END, "workflow.palette.end"),
        ]:
            color = node_fill_color(node_type)
            row, btn = self._make_palette_button(
                body_flow, t(i18n_key), color,
                lambda nt=node_type: self._on_add_node(nt),
            )
            row.grid(row=row_idx, column=0, sticky="ew", padx=2, pady=1)
            row._palette_text = t(i18n_key)
            row._palette_section_key = "flow"
            self._palette_buttons.append(row)
            self._palette_btn_widgets.append(btn)
            row_idx += 1

    # ── 监控标签页 ──────────────────────────────────────────

    def _build_monitor_tab(self, theme, sm):
        from src.core.flow import NodeType

        monitor_tab = tk.Frame(self._notebook, bg=theme.panel_bg)
        self._notebook.add(monitor_tab, text=t("workflow.tab.monitor"))

        monitor_color = node_fill_color(NodeType.CONDITION)
        row_m, btn_m = self._make_palette_button(
            monitor_tab, t("workflow.palette.add_monitor"), monitor_color,
            self._on_add_monitor,
        )
        row_m.pack(fill=tk.X, padx=sm.s(4), pady=sm.s(2))
        row_m._palette_text = t("workflow.palette.add_monitor")
        self._palette_buttons.append(row_m)
        self._palette_btn_widgets.append(btn_m)

        self._monitor_tree = ttk.Treeview(
            monitor_tab, columns=("enabled", "name", "action", "interval"),
            show="headings", height=6,
        )
        self._monitor_tree.heading("enabled", text="✓")
        self._monitor_tree.heading("name", text=t("common.name"))
        self._monitor_tree.heading("action", text=t("chain.mon.col.action"))
        self._monitor_tree.heading("interval", text=t("chain.mon.col.interval"))
        self._monitor_tree.column("enabled", width=25, anchor=tk.CENTER, stretch=False)
        self._monitor_tree.column("name", width=60, anchor=tk.W, stretch=True)
        self._monitor_tree.column("action", width=50, anchor=tk.CENTER, stretch=True)
        self._monitor_tree.column("interval", width=35, anchor=tk.CENTER, stretch=True)
        self._monitor_tree.bind("<Double-1>", lambda _: self._on_edit_monitor())
        self._monitor_tree.bind("<Delete>", lambda _: self._on_delete_monitor())
        self._monitor_tree.pack(fill=tk.BOTH, expand=True, padx=sm.s(4), pady=sm.s(2))

        mon_btn_frame = themed_frame(monitor_tab)
        mon_btn_frame.pack(fill=tk.X, padx=sm.s(4), pady=sm.s(2))
        from src.panel.widgets import themed_button as _tb
        _tb(mon_btn_frame, text="✎", command=self._on_edit_monitor, padx=4).pack(side=tk.LEFT, padx=1)
        _tb(mon_btn_frame, text="✓", command=self._on_toggle_monitor, padx=4).pack(side=tk.LEFT, padx=1)
        _tb(mon_btn_frame, text="✕", command=self._on_delete_monitor, padx=4).pack(side=tk.LEFT, padx=1)

    # ── 帮助标签页 ──────────────────────────────────────────

    def _build_help_tab_wrapper(self, theme, sm):
        help_tab = tk.Frame(self._notebook, bg=theme.panel_bg)
        self._notebook.add(help_tab, text=t("workflow.tab.help"))
        self._build_help_tab(help_tab)

    def _build_help_tab(self, parent: tk.Frame) -> None:
        theme = current_theme()
        sm = scale_manager()

        help_canvas = tk.Canvas(parent, highlightthickness=0, bg=theme.panel_bg)
        help_scrollbar = ttk.Scrollbar(
            parent, orient=tk.VERTICAL, command=help_canvas.yview,
        )
        help_inner = tk.Frame(help_canvas, bg=theme.panel_bg)
        help_inner.bind(
            "<Configure>",
            lambda _: help_canvas.configure(scrollregion=help_canvas.bbox("all")),
        )
        win_id = help_canvas.create_window((0, 0), window=help_inner, anchor=tk.NW)
        help_canvas.configure(yscrollcommand=help_scrollbar.set)
        help_canvas.bind(
            "<Configure>",
            lambda _: help_canvas.itemconfigure(win_id, width=help_canvas.winfo_width()),
        )
        help_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        help_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        px = sm.s(6)
        py = sm.s(4)

        self._build_help_action_section(help_inner, theme, sm, px, py)
        themed_separator(help_inner).pack(fill=tk.X, padx=px, pady=py)
        self._build_help_flow_section(help_inner, theme, sm, px, py)
        themed_separator(help_inner).pack(fill=tk.X, padx=px, pady=py)

        tk.Label(
            help_inner, text=t("workflow.help.hint"),
            bg=theme.panel_bg, fg=theme.text_muted,
            font=(theme.font_family, sm.s(8)), wraplength=sm.s(160),
            justify=tk.LEFT,
        ).pack(anchor=tk.W, padx=px, pady=(py, sm.s(8)))

    def _build_help_action_section(self, parent, theme, sm, px, py):
        tk.Label(
            parent, text=t("workflow.help.action.title"),
            bg=theme.panel_bg, fg=theme.accent_blue,
            font=(theme.font_family, sm.s(9), "bold"),
        ).pack(anchor=tk.W, padx=px, pady=(py, 2))

        help_action_items = [
            ("action_type.click_image", "workflow.help.click_image"),
            ("action_type.wait", "workflow.help.wait"),
            ("action_type.wait_random", "workflow.help.wait_random"),
            ("action_type.press_key", "workflow.help.press_key"),
            ("action_type.click_pos", "workflow.help.click_pos"),
            ("action_type.scroll", "workflow.help.mouse_scroll"),
            ("action_type.hold_key", "workflow.help.hold_key"),
            ("action_type.mouse_move", "workflow.help.mouse_move"),
            ("action_type.mouse_drag", "workflow.help.mouse_drag"),
            ("action_type.key_combo", "workflow.help.key_combo"),
            ("action_type.multi_key", "workflow.help.multi_key_sequence"),
            ("action_type.idle", "workflow.help.idle_behavior"),
            ("action_type.start_timer", "workflow.help.start_timer"),
        ]
        for name_key, desc_key in help_action_items:
            frame = tk.Frame(parent, bg=theme.panel_bg)
            frame.pack(fill=tk.X, padx=px, pady=1)
            tk.Label(
                frame, text=t(name_key), bg=theme.panel_bg,
                fg=theme.text_primary, font=(theme.font_family, sm.s(8), "bold"),
                width=8, anchor=tk.NW,
            ).pack(side=tk.LEFT, padx=(0, sm.s(4)))
            tk.Label(
                frame, text=t(desc_key), bg=theme.panel_bg,
                fg=theme.text_muted, font=(theme.font_family, sm.s(8)),
                wraplength=sm.s(140), anchor=tk.NW, justify=tk.LEFT,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _build_help_flow_section(self, parent, theme, sm, px, py):
        tk.Label(
            parent, text=t("workflow.help.flow.title"),
            bg=theme.panel_bg, fg=theme.accent_orange,
            font=(theme.font_family, sm.s(9), "bold"),
        ).pack(anchor=tk.W, padx=px, pady=(py, 2))

        help_flow_items = [
            ("workflow.node.start", "workflow.help.start"),
            ("workflow.node.end", "workflow.help.end"),
            ("workflow.node.condition", "workflow.help.condition"),
            ("workflow.node.merge", "workflow.help.merge"),
            ("workflow.node.loop", "workflow.help.loop"),
        ]
        for name_key, desc_key in help_flow_items:
            frame = tk.Frame(parent, bg=theme.panel_bg)
            frame.pack(fill=tk.X, padx=px, pady=1)
            tk.Label(
                frame, text=t(name_key), bg=theme.panel_bg,
                fg=theme.text_primary, font=(theme.font_family, sm.s(8), "bold"),
                width=8, anchor=tk.NW,
            ).pack(side=tk.LEFT, padx=(0, sm.s(4)))
            tk.Label(
                frame, text=t(desc_key), bg=theme.panel_bg,
                fg=theme.text_muted, font=(theme.font_family, sm.s(8)),
                wraplength=sm.s(140), anchor=tk.NW, justify=tk.LEFT,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ── 可折叠分组 ──────────────────────────────────────────

    def _build_collapsible_section(self, parent, title, key):
        theme = current_theme()
        sm = scale_manager()
        header = tk.Frame(parent, bg=theme.panel_header_bg, cursor="hand2")
        header.pack(fill=tk.X, pady=(sm.s(6), 0))

        arrow = tk.Label(
            header, text="▼", bg=theme.panel_header_bg, fg=theme.text_muted,
            font=(theme.font_family, sm.s(8)),
        )
        arrow.pack(side=tk.LEFT, padx=(sm.s(4), sm.s(2)))

        tk.Label(
            header, text=title, bg=theme.panel_header_bg, fg=theme.text_primary,
            font=(theme.font_family, sm.s(9), "bold"),
        ).pack(side=tk.LEFT)

        count_label = tk.Label(
            header, text="", bg=theme.panel_header_bg, fg=theme.text_muted,
            font=(theme.font_family, sm.s(7)),
        )
        count_label.pack(side=tk.LEFT, padx=(sm.s(4), 0))
        self._section_count_labels: dict[str, tk.Label] = {}
        self._section_count_labels[key] = count_label

        body = tk.Frame(parent, bg=theme.panel_bg)
        body.pack(fill=tk.X)

        self._section_arrows[key] = arrow
        self._section_bodies[key] = body
        self._section_headers[key] = header
        self._section_expanded[key] = True

        header.bind("<Button-1>", lambda e, k=key: self._toggle_section(k))
        arrow.bind("<Button-1>", lambda e, k=key: self._toggle_section(k))
        for child in header.winfo_children():
            if child is not arrow:
                child.bind("<Button-1>", lambda e, k=key: self._toggle_section(k))

        # 悬停反馈
        header.bind("<Enter>", lambda e, h=header, a=arrow, c=count_label: self._on_section_hover(h, a, c, True))
        header.bind("<Leave>", lambda e, h=header, a=arrow, c=count_label: self._on_section_hover(h, a, c, False))

        return body

    def _toggle_section(self, key):
        if self._section_expanded[key]:
            self._section_bodies[key].pack_forget()
            self._section_arrows[key].configure(text="▶")
            self._section_expanded[key] = False
        else:
            self._section_bodies[key].pack(fill=tk.X, after=self._section_headers[key])
            self._section_arrows[key].configure(text="▼")
            self._section_expanded[key] = True

    def _on_section_hover(self, header, arrow, count_label, entering):
        theme = current_theme()
        bg = theme.hover_highlight if entering else theme.panel_header_bg
        fg = theme.text_primary if entering else theme.text_muted
        for widget in (header, arrow, count_label):
            widget.configure(bg=bg)
        for child in header.winfo_children():
            if child not in (arrow, count_label):
                try:
                    child.configure(bg=bg)
                except tk.TclError:
                    pass
        if not entering:
            try:
                count_label.configure(fg=fg)
            except tk.TclError:
                pass

    def _update_section_counts(self):
        counts: dict[str, int] = {}
        for row_frame in self._palette_buttons:
            sec_key = getattr(row_frame, "_palette_section_key", None)
            if sec_key:
                counts[sec_key] = counts.get(sec_key, 0) + 1
        if hasattr(self, "_section_count_labels"):
            for key, label in self._section_count_labels.items():
                cnt = counts.get(key, 0)
                label.configure(text=f"({cnt})")

    # ── 面板按钮工厂 ──────────────────────────────────────────

    def _make_palette_button(self, parent, text, color, command):
        theme = current_theme()
        sm = scale_manager()
        row = themed_frame(parent)

        bar_canvas = tk.Canvas(
            row, width=sm.s(3), height=sm.s(16),
            bg=theme.panel_bg, highlightthickness=0,
        )
        bar_canvas.pack(side=tk.LEFT, padx=(sm.s(2), sm.s(3)))
        bar_canvas.create_rectangle(0, sm.s(2), sm.s(3), sm.s(14), fill=color, outline="")

        btn = LabelButton(
            row, text=text, command=command,
            bg=theme.btn_bg, fg=theme.text_primary,
            activeforeground=theme.text_primary,
            font=theme.font_small,
            anchor=tk.W,
            border_color=theme.btn_border,
        )
        btn.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if not hasattr(self, "_palette_labels"):
            self._palette_labels = []
        self._palette_labels.append(btn)
        return row, btn

    # ── 搜索过滤 ──────────────────────────────────────────

    def _on_search_focus_in(self, event):
        theme = current_theme()
        if self._palette_search_entry.get() == self._palette_search_placeholder:
            self._palette_search_entry.delete(0, tk.END)
            self._palette_search_entry.configure(fg=theme.text_primary)

    def _on_search_focus_out(self, event):
        theme = current_theme()
        if not self._palette_search_entry.get().strip():
            self._palette_search_entry.insert(0, self._palette_search_placeholder)
            self._palette_search_entry.configure(fg=theme.text_muted)

    def _on_palette_search(self, event):
        query = self._palette_search_var.get().lower().strip()
        section_has_visible: dict[str, bool] = {}
        for row_frame in self._palette_buttons:
            text = row_frame._palette_text.lower()
            visible = not query or query in text
            if visible:
                row_frame.grid()
            else:
                row_frame.grid_remove()
            sec_key = getattr(row_frame, "_palette_section_key", None)
            if sec_key:
                section_has_visible.setdefault(sec_key, False)
                if visible:
                    section_has_visible[sec_key] = True
        for sec_key, has_visible in section_has_visible.items():
            if query:
                if has_visible and not self._section_expanded.get(sec_key, True):
                    self._toggle_section(sec_key)
                elif not has_visible and self._section_expanded.get(sec_key, True):
                    self._toggle_section(sec_key)
        self._on_palette_configure(None)

    # ── 滚动辅助 ──────────────────────────────────────────

    def _force_palette_refresh(self):
        if not self._palette_canvas.winfo_exists():
            return
        self._palette_inner.update_idletasks()
        self._palette_canvas.configure(scrollregion=self._palette_canvas.bbox("all"))
        self._palette_canvas.itemconfigure(
            self._palette_win_id, width=self._palette_canvas.winfo_width(),
        )

    def _on_palette_configure(self, event):
        cw = self._palette_canvas.winfo_width()
        if cw < 2:
            return
        self._palette_canvas.configure(scrollregion=self._palette_canvas.bbox("all"))
        self._palette_canvas.itemconfigure(self._palette_win_id, width=cw)

    def _on_palette_mousewheel(self, event):
        if IS_MACOS:
            self._palette_canvas.yview_scroll(-event.delta, "units")
        elif IS_LINUX:
            if event.num == 4:
                self._palette_canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                self._palette_canvas.yview_scroll(1, "units")
        else:
            self._palette_canvas.yview_scroll(-event.delta // 120, "units")

    def _palette_bind_wheel(self, event=None):
        if IS_LINUX:
            self._palette_canvas.bind_all("<Button-4>", self._on_palette_mousewheel)
            self._palette_canvas.bind_all("<Button-5>", self._on_palette_mousewheel)
        else:
            self._palette_canvas.bind_all("<MouseWheel>", self._on_palette_mousewheel)

    def _palette_unbind_wheel(self, event=None):
        if IS_LINUX:
            self._palette_canvas.unbind_all("<Button-4>")
            self._palette_canvas.unbind_all("<Button-5>")
        else:
            self._palette_canvas.unbind_all("<MouseWheel>")
