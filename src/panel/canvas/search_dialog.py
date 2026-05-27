"""SearchBar — 画布节点快速搜索栏"""

import tkinter as tk
from typing import Callable

from src.core.flow import FlowGraph
from src.panel.canvas.theme import current_theme
from src.utils.i18n import t


class SearchBar(tk.Frame):
    """浮在画布上方的搜索栏，实时过滤节点并导航到选中项。"""

    def __init__(self, parent: tk.Widget, on_navigate: Callable[[str], None]) -> None:
        theme = current_theme()
        super().__init__(parent, bg=theme.bg_surface, bd=1, relief=tk.SOLID)

        self._on_navigate = on_navigate
        self._graph: FlowGraph | None = None
        self._filtered: list[tuple[str, str]] = []  # (node_id, display_text)

        # 搜索输入框
        self._entry = tk.Entry(
            self, bg=theme.bg_surface, fg=theme.text_primary,
            insertbackground=theme.text_primary,
            font=theme.font_toolbar, width=30, bd=0,
        )
        self._entry.pack(fill=tk.X, padx=(8, 4), pady=(6, 2))
        self._entry.bind("<KeyRelease>", self._on_search)
        self._entry.bind("<Return>", self._on_enter)
        self._entry.bind("<Escape>", lambda e: self._on_navigate(""))

        # 结果列表
        self._listbox = tk.Listbox(
            self, bg=theme.bg_surface, fg=theme.text_primary,
            selectbackground=theme.accent_blue, selectforeground=theme.text_on_accent,
            font=theme.font_status, height=5, bd=0, activestyle="none",
        )
        self._listbox.pack(fill=tk.BOTH, padx=(8, 4), pady=(2, 6))
        self._listbox.bind("<Double-ButtonPress-1>", self._on_list_select)
        self._listbox.bind("<Return>", self._on_list_select)

    def update_graph(self, graph: FlowGraph) -> None:
        self._graph = graph

    def grab_focus(self) -> None:
        self._entry.delete(0, tk.END)
        self._listbox.delete(0, tk.END)
        self._entry.focus_set()

    def _on_search(self, event: tk.Event) -> None:
        query = self._entry.get().strip().lower()
        self._listbox.delete(0, tk.END)
        self._filtered.clear()

        if not query or not self._graph:
            return

        for node in self._graph.nodes.values():
            desc = node.describe().lower()
            nid = node.node_id.lower()
            comment = (node.comment or "").lower()
            if query in desc or query in nid or query in comment:
                display = node.describe()
                self._filtered.append((node.node_id, display))
                self._listbox.insert(tk.END, display)

        if not self._filtered:
            self._listbox.insert(tk.END, t("workflow.search.no_results"))

    def _on_enter(self, event: tk.Event) -> None:
        if self._filtered:
            self._on_navigate(self._filtered[0][0])

    def _on_list_select(self, event: tk.Event) -> None:
        sel = self._listbox.curselection()
        if sel and sel[0] < len(self._filtered):
            self._on_navigate(self._filtered[sel[0]][0])
