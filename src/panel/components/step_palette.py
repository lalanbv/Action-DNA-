"""StepPalette — 动作链左侧动作面板共享组件

提供 13 种动作类型按钮（带颜色标识条），点击打开对应步骤添加对话框。
使用 palette_data.ACTION_PALETTE 作为统一数据源。
内容超出时自动显示滚动条。
"""

import tkinter as tk
from typing import Callable

from src.core.action import ActionType
from src.panel.canvas.scale import ScrollableFrame
from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.components.palette_data import ACTION_PALETTE, action_accent
from src.panel.components.dna_button import DNAButton as LabelButton
from src.panel.widgets import themed_frame, themed_label
from src.utils.i18n import t


class StepPalette(tk.Frame):
    """动作链左侧动作面板：使用统一 palette_data 的类型按钮。"""

    def __init__(
        self,
        parent: tk.Widget,
        on_add_step: Callable[[ActionType, str], None],
        width: int | None = None,
    ) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.panel_bg)
        self.pack(fill=tk.BOTH, expand=True)
        self._on_add_step = on_add_step
        self._rows: list[tuple[tk.Frame, LabelButton, tk.Frame, str]] = []
        self._scroll: ScrollableFrame | None = None
        self._build(th)

    def _build(self, th: CanvasTheme) -> None:
        header = themed_frame(self)
        header.pack(fill=tk.X, padx=th.pad_xs, pady=(th.pad_sm, 0))
        themed_label(
            header, text=t("chain.add_step"), style="section", bg=th.panel_bg,
        ).pack()

        self._scroll = ScrollableFrame(self, bg=th.panel_bg)
        self._scroll.pack(fill=tk.BOTH, expand=True)

        for action_type, i18n_key in ACTION_PALETTE:
            accent_token = action_accent(action_type)
            accent = getattr(th, accent_token, th.accent_blue)
            title = t(i18n_key)
            label_text = title.lstrip("+ ")

            row = tk.Frame(
                self._scroll.inner, bg=th.card_bg,
                highlightbackground=th.border_default,
                highlightthickness=1,
            )
            row.pack(fill=tk.X, padx=th.pad_xs, pady=1)

            strip = tk.Frame(row, bg=accent, width=4)
            strip.pack(side=tk.LEFT, fill=tk.Y)
            strip.pack_propagate(False)

            btn = LabelButton(
                row,
                text=label_text,
                command=lambda at=action_type, ti=title: self._on_add_step(at, ti),
                bg=th.card_bg,
                fg=th.text_primary,
                font=th.font_small,
                border_color=th.card_bg,
                padx=th.pad_xs,
                pady=th.pad_xs,
            )
            btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

            self._rows.append((row, btn, strip, accent_token))

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.panel_bg)
        if self._scroll is not None:
            self._scroll.set_bg(th.panel_bg)
        for row, btn, strip, accent_token in self._rows:
            accent = getattr(th, accent_token, th.accent_blue)
            row.configure(bg=th.card_bg, highlightbackground=th.border_default)
            btn.configure(bg=th.card_bg, fg=th.text_primary, font=th.font_small,
                          border_color=th.card_bg)
            strip.configure(bg=accent)
        from src.panel.widgets import cascade_theme
        cascade_theme(self)
