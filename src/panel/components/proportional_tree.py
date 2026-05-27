"""ProportionalTreeMixin — Treeview 比例列宽度自动调整

消除 4 处重复的 _on_tree_configure 实现。
所有 Treeview 列按比例分配宽度，在窗口调整大小时自动重算。
"""

import tkinter as tk
from tkinter import ttk


class ProportionalTreeMixin:
    """为 Treeview 提供比例列宽度调整。

    用法：
        class MyPage(BasePage, ProportionalTreeMixin):
            def _build_tree(self, parent):
                tree = ttk.Treeview(parent, columns=("a", "b"), show="headings")
                self.setup_proportional_columns(tree, [
                    ("a", "列A", 0.3, tk.W),
                    ("b", "列B", 0.7, None),
                ])

    ratio 之和应为 1.0。
    """

    _prop_trees: dict[
        str, tuple[ttk.Treeview, list[tuple[str, float, str | None]], int]
    ]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

    def setup_proportional_columns(
        self,
        tree: ttk.Treeview,
        col_specs: list[tuple[str, str, float, str | None]],
        key: str = "default",
    ) -> None:
        """配置 Treeview 的比例列宽并绑定自动调整。"""
        if not hasattr(self, "_prop_trees"):
            self._prop_trees = {}

        # 卸载旧绑定，防止重复调用累积回调
        tag = f"_prop_tree_cfg_{key}"
        tree.unbind(tag)

        for col_id, heading, ratio, anchor in col_specs:
            tree.heading(col_id, text=heading)
            kw: dict = {"width": 50, "stretch": True}
            if anchor is not None:
                kw["anchor"] = anchor
            tree.column(col_id, **kw)

        ratios = [(col_id, ratio, anchor) for col_id, _, ratio, anchor in col_specs]
        self._prop_trees[key] = (tree, ratios, 0)

        tree.bind(
            "<Configure>",
            lambda e, k=key: self._on_prop_tree_configure(e, k),
            add=False,
        )

    def _on_prop_tree_configure(self, event: tk.Event, key: str) -> None:
        entry = self._prop_trees.get(key)
        if entry is None:
            return
        tree, ratios, last_w = entry
        if not tree.winfo_exists() or event.width == last_w:
            return
        self._prop_trees[key] = (tree, ratios, event.width)
        for col_id, ratio, anchor in ratios:
            kw: dict = {"width": max(30, int(event.width * ratio))}
            if anchor is not None:
                kw["anchor"] = anchor
            tree.column(col_id, **kw)
