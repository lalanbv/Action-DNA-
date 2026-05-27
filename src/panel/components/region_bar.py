"""RegionBar — 统一区域选择共享组件

提供全屏/自定义模式切换 + 框选/重置按钮。

compact 模式下通过 add_to_toolbar() 将每个元素独立添加到工具栏 grid，
实现逐元素自适应换行。
"""

import tkinter as tk
from typing import Callable

from src.panel.canvas.theme import current_theme, CanvasTheme
from src.panel.widgets import (
    themed_button,
    themed_label,
    themed_radiobutton,
    themed_separator,
)
from src.utils.i18n import t


class RegionBar(tk.Frame):
    """区域选择栏：全屏/自定义 radio + 框选按钮 + 重置按钮。

    compact=True 时通过 add_to_toolbar() 将每个元素作为独立 grid cell
    添加到 ToolbarFrame，实现逐元素自适应换行。
    注意：compact 模式下自身 Frame 不可见，元素以 toolbar 为 parent 创建。
    """

    def __init__(
        self,
        parent: tk.Widget,
        on_fullscreen: Callable,
        on_pick_region: Callable,
        on_reset: Callable | None = None,
        compact: bool = False,
    ) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.toolbar_bg if compact else th.page_bg)
        self._on_fullscreen = on_fullscreen
        self._on_pick = on_pick_region
        self._on_reset = on_reset
        self._compact = compact
        self.var_mode = tk.StringVar(value="fullscreen")
        if not compact:
            self._build_full(th)

    def add_to_toolbar(self, toolbar: "ToolbarFrame", section: str) -> None:
        """以 toolbar 为 parent 创建每个元素，并作为独立 grid cell 注册。"""
        if section not in toolbar._sections:
            toolbar.add_section(section)

        rb_full = themed_radiobutton(
            toolbar, text=t("chain.fullscreen"),
            variable=self.var_mode, value="fullscreen",
            command=self._on_mode_change,
        )
        toolbar._items.append(("item", rb_full))

        rb_custom = themed_radiobutton(
            toolbar, text=t("chain.custom_region"),
            variable=self.var_mode, value="custom",
            command=self._on_mode_change,
        )
        toolbar._items.append(("item", rb_custom))

        sep = themed_separator(toolbar, orient=tk.VERTICAL)
        toolbar._items.append(("sep", sep))

        self.btn_pick = themed_button(
            toolbar, text=t("chain.pick_region"),
            command=self._on_pick, state=tk.DISABLED,
        )
        toolbar._items.append(("item", self.btn_pick))

        if self._on_reset:
            btn_reset = themed_button(
                toolbar, text=t("chain.reset_fullscreen"),
                command=self._on_reset,
            )
            toolbar._items.append(("item", btn_reset))

    def _build_full(self, th: CanvasTheme) -> None:
        """完整模式（独立区域，带标签）。"""
        themed_label(self, text=t("chain.region_label")).pack(side=tk.LEFT)

        self.var_mode = tk.StringVar(value="fullscreen")
        themed_radiobutton(
            self, text=t("chain.fullscreen"),
            variable=self.var_mode, value="fullscreen",
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)
        themed_radiobutton(
            self, text=t("chain.custom_region"),
            variable=self.var_mode, value="custom",
            command=self._on_mode_change,
        ).pack(side=tk.LEFT)

        themed_separator(self).pack(side=tk.LEFT, fill=tk.Y, padx=th.pad_sm)

        self.btn_pick = themed_button(
            self, text=t("chain.pick_region"),
            command=self._on_pick, state=tk.DISABLED,
        )
        self.btn_pick.pack(side=tk.LEFT, padx=th.pad_xs)

        if self._on_reset:
            themed_button(
                self, text=t("chain.reset_fullscreen"),
                command=self._on_reset,
            ).pack(side=tk.LEFT, padx=th.pad_xs)

    def _on_mode_change(self) -> None:
        if self.var_mode.get() == "fullscreen":
            self.btn_pick.configure(state=tk.DISABLED)
            self._on_fullscreen()
        else:
            self.btn_pick.configure(state=tk.NORMAL)

    def set_mode(self, mode: str) -> None:
        self.var_mode.set(mode)
        self.btn_pick.configure(
            state=tk.DISABLED if mode == "fullscreen" else tk.NORMAL,
        )

    def get_mode(self) -> str:
        return self.var_mode.get()

    def set_pick_enabled(self, enabled: bool) -> None:
        self.btn_pick.configure(state=tk.NORMAL if enabled else tk.DISABLED)

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.toolbar_bg if self._compact else th.page_bg)
