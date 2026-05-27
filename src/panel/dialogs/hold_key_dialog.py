"""HoldKeyDialog — 长按按键对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, HoldKeyStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.dialogs.key_picker import make_key_picker
from src.panel.widgets import themed_frame, themed_label
from src.utils.i18n import t


class HoldKeyDialog(StepDialogBase):
    """长按按键配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        themed_label(
            self._content_frame, text=t("dialog.label.key"),
        ).grid(row=0, column=0, sticky=tk.NW, padx=th.pad_sm, pady=th.pad_xs)

        key_frame = themed_frame(self._content_frame)
        key_frame.grid(row=0, column=1, sticky=tk.EW, padx=th.pad_sm)
        self._vars["keys_hold"] = make_key_picker(key_frame, initial_value="")

        self._vars["hold_duration"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.hold_duration"),
            default=1.0, min_val=0.1, max_val=60.0, increment=0.1, row=1,
        )

        themed_label(
            self._content_frame, text=t("dialog.hint.multi_key_hold"),
            fg=th.text_muted,
        ).grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["keys_hold"].set(action.keys_hold or action.key)
        self._vars["hold_duration"].set(action.hold_duration)
        self._add_common_fields(self._content_frame, 3, action)

    def _get_result(self) -> BaseStep:
        step = self._action or HoldKeyStep()
        step.keys_hold = self._vars["keys_hold"].get()
        step.hold_duration = self._get_float("hold_duration", min_val=0.1, max_val=60.0, default=1.0)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.HOLD_KEY, HoldKeyDialog)
