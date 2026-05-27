"""Badge — 状态标签组件，用于显示运行状态/错误/警告等。"""

from __future__ import annotations

import tkinter as tk

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.components.base import DNAWidget


class Badge(DNAWidget):
    """紧凑的状态指示标签。

    预设样式: success / warning / error / info / neutral
    自动根据主题配色渲染圆角胶囊形标签。
    """

    __slots__ = ("_label", "_variant", "_text")

    _VARIANT_TOKENS: dict[str, dict[str, str]] = {
        "success": {"bg": "accent_green", "fg": "text_on_accent"},
        "warning": {"bg": "accent_orange", "fg": "text_on_accent"},
        "error": {"bg": "accent_red", "fg": "text_on_accent"},
        "info": {"bg": "accent_blue", "fg": "text_on_accent"},
        "neutral": {"bg": "bg_surface", "fg": "text_secondary"},
    }

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "",
        variant: str = "neutral",
        **kw,
    ) -> None:
        self._variant = variant
        self._text = text
        th = current_theme()
        sm = scale_manager()

        tokens = self._VARIANT_TOKENS.get(variant, self._VARIANT_TOKENS["neutral"])
        bg = getattr(th, tokens["bg"])
        fg = getattr(th, tokens["fg"])

        kw.setdefault("bg", bg)
        super().__init__(parent, **kw)

        self._label = tk.Label(
            self,
            text=text,
            bg=bg,
            fg=fg,
            font=th.font_small,
            padx=sm.s(8),
            pady=sm.s(2),
        )
        self._label.pack(fill=tk.BOTH, expand=True)

    def configure(self, **kw) -> None:
        if "text" in kw:
            self._text = kw.pop("text")
            self._label.configure(text=self._text)
        if "variant" in kw:
            self._variant = kw.pop("variant")
            th = current_theme()
            tokens = self._VARIANT_TOKENS.get(self._variant, self._VARIANT_TOKENS["neutral"])
            bg = getattr(th, tokens["bg"])
            fg = getattr(th, tokens["fg"])
            self._label.configure(bg=bg, fg=fg)
            super().configure(bg=bg)

    config = configure

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        super().apply_theme(theme)
        if theme is None:
            theme = current_theme()
        tokens = self._VARIANT_TOKENS.get(self._variant, self._VARIANT_TOKENS["neutral"])
        bg = getattr(theme, tokens["bg"])
        fg = getattr(theme, tokens["fg"])
        self._label.configure(bg=bg, fg=fg, font=theme.font_small)
        super().configure(bg=bg)
