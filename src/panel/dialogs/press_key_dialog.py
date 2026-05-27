"""PressKeyDialog — 按键对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, PressKeyStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.dialogs.key_picker import make_key_picker
from src.panel.widgets import themed_frame, themed_label
from src.utils.i18n import t


class PressKeyDialog(StepDialogBase):
    """按键配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        themed_label(
            self._content_frame, text=t("dialog.label.key"),
        ).grid(row=0, column=0, sticky=tk.NW, padx=th.pad_sm, pady=th.pad_xs)

        key_frame = themed_frame(self._content_frame)
        key_frame.grid(row=0, column=1, sticky=tk.EW, padx=th.pad_sm)
        self._vars["key"] = make_key_picker(key_frame, initial_value="", list_height=8)

    def _populate_fields(self, action: BaseStep) -> None:
        if action.text:
            self._vars["key"].set(f"[text] {action.text[:30]}")
        else:
            self._vars["key"].set(action.key)
        self._add_common_fields(self._content_frame, 1, action)

    def _get_result(self) -> BaseStep:
        step = self._action or PressKeyStep()
        key_val = self._vars["key"].get()
        if key_val.startswith("[text] "):
            step.text = key_val[7:]
            step.key = ""
        else:
            step.key = key_val
            step.text = ""
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.PRESS_KEY, PressKeyDialog)
