"""ProfileBar — 统一配置文件管理共享组件

提供 Combobox 选择 + 加载/保存/另存为/删除 + 可选导出/导入按钮。

compact 模式下通过 add_to_toolbar() 将每个元素独立添加到工具栏 grid，
实现逐元素自适应换行。
"""

import tkinter as tk
from tkinter import ttk
from typing import Callable

from src.panel.canvas.theme import current_theme, CanvasTheme
from src.panel.widgets import themed_button, themed_frame, themed_label
from src.utils.i18n import t


class ProfileBar(tk.Frame):
    """统一配置文件管理栏。

    compact=True 时通过 add_to_toolbar() 将每个元素作为独立 grid cell
    添加到 ToolbarFrame，实现逐元素自适应换行。
    注意：compact 模式下自身 Frame 不可见，元素以 toolbar 为 parent 创建。
    """

    def __init__(
        self,
        parent: tk.Widget,
        on_load: Callable,
        on_save: Callable,
        on_save_as: Callable,
        on_delete: Callable,
        on_export: Callable | None = None,
        on_import: Callable | None = None,
        compact: bool = False,
    ) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.toolbar_bg if compact else th.page_bg)
        self._on_load = on_load
        self._on_save = on_save
        self._on_save_as = on_save_as
        self._on_delete = on_delete
        self._on_export = on_export
        self._on_import = on_import
        self._compact = compact
        self.var_profile_name = tk.StringVar()
        self.combo_profiles: ttk.Combobox | None = None
        if not compact:
            self._build_full(th)

    def add_to_toolbar(self, toolbar: "ToolbarFrame", section: str) -> None:
        """以 toolbar 为 parent 创建每个元素，并作为独立 grid cell 注册。"""
        if section not in toolbar._sections:
            toolbar.add_section(section)

        self.combo_profiles = ttk.Combobox(
            toolbar, textvariable=self.var_profile_name,
            width=16, state="readonly",
        )
        toolbar._items.append(("item", self.combo_profiles))

        for text, cmd in [
            (t("chain.load"), self._on_load),
            (t("chain.save"), self._on_save),
            (t("common.save_as"), self._on_save_as),
            (t("common.delete"), self._on_delete),
        ]:
            btn = themed_button(toolbar, text=text, command=cmd)
            toolbar._items.append(("item", btn))

        if self._on_export:
            btn = themed_button(toolbar, text=t("chain.export"), command=self._on_export)
            toolbar._items.append(("item", btn))
        if self._on_import:
            btn = themed_button(toolbar, text=t("chain.import"), command=self._on_import)
            toolbar._items.append(("item", btn))

    def _build_full(self, th: CanvasTheme) -> None:
        """双行模式（独立区域）。"""
        row1 = themed_frame(self)
        row1.pack(fill=tk.X, padx=th.pad_xs, pady=(th.pad_xs, 0))

        themed_label(row1, text=t("chain.profile_label")).pack(side=tk.LEFT)
        self.combo_profiles = ttk.Combobox(
            row1, textvariable=self.var_profile_name,
            width=20, state="readonly",
        )
        self.combo_profiles.pack(side=tk.LEFT, padx=th.pad_xs)

        themed_button(row1, text=t("chain.load"), command=self._on_load).pack(
            side=tk.LEFT, padx=th.pad_xs,
        )
        themed_button(row1, text=t("chain.save"), command=self._on_save).pack(
            side=tk.LEFT, padx=th.pad_xs,
        )
        themed_button(row1, text=t("common.save_as"), command=self._on_save_as).pack(
            side=tk.LEFT, padx=th.pad_xs,
        )
        themed_button(row1, text=t("common.delete"), command=self._on_delete).pack(
            side=tk.LEFT, padx=th.pad_xs,
        )

        if self._on_export or self._on_import:
            row2 = themed_frame(self)
            row2.pack(fill=tk.X, padx=th.pad_xs, pady=(th.pad_xs, th.pad_xs))
            if self._on_export:
                themed_button(row2, text=t("chain.export"), command=self._on_export).pack(
                    side=tk.LEFT, padx=th.pad_xs,
                )
            if self._on_import:
                themed_button(row2, text=t("chain.import"), command=self._on_import).pack(
                    side=tk.LEFT, padx=th.pad_xs,
                )

    def refresh_list(self, names: list[str], current: str | None = None) -> None:
        if self.combo_profiles is None:
            return
        self.combo_profiles["values"] = names
        if current and current in names:
            self.var_profile_name.set(current)
        elif names:
            self.var_profile_name.set(names[0])
        else:
            self.var_profile_name.set("")

    def get_selected(self) -> str:
        return self.var_profile_name.get()

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.toolbar_bg if self._compact else th.page_bg)
