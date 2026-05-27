"""PropertyPanel — 通用右侧属性面板共享组件

提供可复用的属性面板容器，支持空状态提示和动态内容填充。
使用 ScrollableFrame 替代手动 Canvas+Scrollbar 滚动实现。
"""

import tkinter as tk

from typing import Callable

from src.panel.canvas.scale import scale_manager, ScrollableFrame
from src.panel.canvas.theme import current_theme, CanvasTheme
from src.panel.widgets import themed_frame, themed_label, themed_separator
from src.utils.i18n import t


class PropertyPanel(tk.Frame):
    """可折叠右侧属性面板。"""

    def __init__(
        self,
        parent: tk.Widget,
        width: int = 260,
        title: str = "",
    ) -> None:
        th = current_theme()
        sm = scale_manager()
        super().__init__(parent, bg=th.panel_bg, width=sm.s(width))
        self.pack_propagate(False)
        self._title = title
        self._width = width
        self._build(th)

    def _build(self, th: CanvasTheme) -> None:
        self._header = themed_frame(self)
        self._header.pack(fill=tk.X, padx=th.pad_sm, pady=(th.pad_sm, 0))
        self._title_var = tk.StringVar(value=self._title)
        self._title_label = themed_label(
            self._header, textvariable=self._title_var, style="section",
        )
        self._title_label.pack(side=tk.LEFT)

        themed_separator(self).pack(fill=tk.X, padx=th.pad_sm, pady=th.pad_xs)

        self._scroll_frame = ScrollableFrame(self, bg=th.panel_bg)
        self._scroll_frame.pack(fill=tk.BOTH, expand=True)
        self._inner = self._scroll_frame.inner

        self.show_empty()

    def set_title(self, title: str) -> None:
        self._title_var.set(title)

    def show_empty(self, message: str = "") -> None:
        """显示空状态提示。"""
        self._clear_content()
        th = current_theme()
        msg = message or t("workflow.properties.empty")
        themed_label(
            self._inner, text="◇", style="title",
            bg=th.panel_bg, fg=th.empty_state_icon,
        ).pack(pady=(th.pad_xl, th.pad_sm))
        themed_label(
            self._inner, text=msg, style="body",
            bg=th.panel_bg, fg=th.text_muted,
        ).pack()
        hint = t("workflow.properties.empty_hint")
        themed_label(
            self._inner, text=hint, style="small",
            bg=th.panel_bg, fg=th.text_muted,
        ).pack(pady=(th.pad_xs, 0))

    def show_properties(self, builder: Callable) -> None:
        """调用 builder(content_frame) 填充属性面板内容。"""
        self._clear_content()
        builder(self._inner)

    def _clear_content(self) -> None:
        for child in self._inner.winfo_children():
            child.destroy()

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.panel_bg)
        self._scroll_frame.set_bg(th.panel_bg)
        self._header.configure(bg=th.panel_bg)
