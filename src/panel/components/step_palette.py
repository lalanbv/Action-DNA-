"""StepPalette — 动作链左侧动作面板共享组件

提供 13 种动作类型按钮（带颜色标识条），点击打开对应步骤添加对话框。
使用 LabelButton 确保 macOS 点击兼容。
"""

import tkinter as tk
from typing import Callable

from src.core.action import ActionType
from src.panel.canvas.theme import current_theme, CanvasTheme
from src.panel.widgets import LabelButton, themed_frame, themed_label
from src.utils.i18n import t


# (i18n_key, action_type, accent_color_field)
_PALETTE_ITEMS: list[tuple[str, ActionType, str]] = [
    ("action_type.click_image", ActionType.CLICK_IMAGE, "accent_blue"),
    ("action_type.hold_key", ActionType.HOLD_KEY, "accent_mauve"),
    ("action_type.mouse_move", ActionType.MOUSE_MOVE, "accent_teal"),
    ("action_type.mouse_drag", ActionType.MOUSE_DRAG, "accent_orange"),
    ("action_type.wait_random", ActionType.WAIT_RANDOM, "accent_green"),
    ("action_type.multi_key", ActionType.MULTI_KEY_SEQUENCE, "accent_teal"),
    ("action_type.idle", ActionType.IDLE_BEHAVIOR, "accent_gray"),
    ("action_type.key_combo", ActionType.KEY_COMBO, "accent_mauve"),
    ("action_type.wait", ActionType.WAIT, "accent_green"),
    ("action_type.press_key", ActionType.PRESS_KEY, "accent_orange"),
    ("action_type.click_pos", ActionType.CLICK_POS, "accent_red"),
    ("action_type.scroll", ActionType.MOUSE_SCROLL, "accent_orange"),
    ("action_type.start_timer", ActionType.START_TIMER, "accent_teal"),
]


class StepPalette(tk.Frame):
    """动作链左侧动作面板：13 个类型按钮。"""

    def __init__(
        self,
        parent: tk.Widget,
        on_add_step: Callable[[ActionType, str], None],
        width: int = 90,
    ) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.panel_bg, width=width)
        self.pack(fill=tk.BOTH, expand=True)
        self.pack_propagate(False)
        self._on_add_step = on_add_step
        self._rows: list[tuple[tk.Frame, LabelButton, tk.Frame, str]] = []
        self._build(th)

    def _build(self, th: CanvasTheme) -> None:
        header = themed_frame(self)
        header.pack(fill=tk.X, padx=th.pad_xs, pady=(th.pad_sm, 0))
        themed_label(
            header, text=t("chain.add_step"), style="section", bg=th.panel_bg,
        ).pack()

        for i18n_key, action_type, color_field in _PALETTE_ITEMS:
            accent = getattr(th, color_field, th.accent_blue)
            title = t(i18n_key)
            label_text = title.lstrip("+ ")

            row = tk.Frame(self, bg=th.card_bg, highlightbackground=th.border_default,
                           highlightthickness=1)
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

            self._rows.append((row, btn, strip, color_field))

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.panel_bg)
        for row, btn, strip, color_field in self._rows:
            accent = getattr(th, color_field, th.accent_blue)
            row.configure(bg=th.card_bg, highlightbackground=th.border_default)
            btn.configure(bg=th.card_bg, fg=th.text_primary, font=th.font_small)
            strip.configure(bg=accent)
