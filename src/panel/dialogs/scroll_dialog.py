"""ScrollDialog — 滚轮对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, MouseScrollStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.widgets import themed_label
from src.utils.i18n import t


class ScrollDialog(StepDialogBase):
    """滚轮配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        self._vars["scroll_clicks"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.scroll_amount"),
            default=3, min_val=-20, max_val=20, increment=1, row=0,
        )
        self._vars["scroll_delta_x"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.scroll_horizontal"),
            default=0, min_val=-20, max_val=20, increment=1, row=1,
        )
        themed_label(
            self._content_frame, text="  " + t("dialog.hint.scroll_direction"),
            fg=th.text_muted,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["scroll_clicks"].set(action.scroll_clicks)
        self._vars["scroll_delta_x"].set(action.scroll_delta_x)
        self._add_common_fields(self._content_frame, 3, action)

    def _get_result(self) -> BaseStep:
        step = self._action or MouseScrollStep()
        step.scroll_clicks = self._get_int("scroll_clicks", min_val=-20, max_val=20, default=3)
        step.scroll_delta_x = self._get_int("scroll_delta_x", min_val=-20, max_val=20, default=0)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.MOUSE_SCROLL, ScrollDialog)
