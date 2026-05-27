"""DNAWidget — 自定义控件基类，集成 ThemeRegistry 自动主题更新。"""

from __future__ import annotations

import tkinter as tk

from src.panel.canvas.theme import CanvasTheme, theme_registry


class DNAWidget(tk.Frame):
    """所有自定义 UI 控件的基类。

    - 自动注册到 ThemeRegistry，主题切换时自动调用 apply_theme()
    - 销毁时自动注销，防止内存泄漏
    - 子类只需实现 apply_theme(theme) 方法
    """

    __slots__ = ("_theme_reg_id",)

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)
        self._theme_reg_id: int = theme_registry().register(self)
        self.bind("<Destroy>", self._on_destroy)

    def _on_destroy(self, _event: tk.Event) -> None:
        theme_registry().unregister(self._theme_reg_id)

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        """子类覆盖此方法以响应主题切换。"""
        if theme is None:
            from src.panel.canvas.theme import current_theme
            theme = current_theme()
        if not self.winfo_exists():
            return
