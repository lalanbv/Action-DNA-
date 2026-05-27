"""MultiKeySequenceDialog — 多键序列对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, MultiKeySequenceStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.dialogs.key_picker import make_key_picker
from src.panel.widgets import themed_frame, themed_label
from src.utils.i18n import t


class MultiKeySequenceDialog(StepDialogBase):
    """多键序列配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        themed_label(
            self._content_frame, text=t("dialog.label.key_sequence"),
        ).grid(row=0, column=0, sticky=tk.NW, padx=th.pad_sm, pady=th.pad_xs)

        seq_frame = themed_frame(self._content_frame)
        seq_frame.grid(row=0, column=1, sticky=tk.EW, padx=th.pad_sm)
        self._vars["key_sequence"] = make_key_picker(
            seq_frame, initial_value="", append_mode=True,
        )

        themed_label(
            self._content_frame, text=t("dialog.hint.key_sequence_format"),
            fg=th.text_muted,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

        self._vars["key_interval_min"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.interval_min"),
            default=0.1, min_val=0.0, max_val=5.0, increment=0.05, row=2,
        )
        self._vars["key_interval_max"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.interval_max"),
            default=0.3, min_val=0.0, max_val=5.0, increment=0.05, row=3,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["key_sequence"].set(action.key_sequence)
        self._vars["key_interval_min"].set(action.key_interval_min)
        self._vars["key_interval_max"].set(action.key_interval_max)
        self._add_common_fields(self._content_frame, 4, action)

    def _get_result(self) -> BaseStep:
        step = self._action or MultiKeySequenceStep()
        step.key_sequence = self._vars["key_sequence"].get()
        step.key_interval_min = self._get_float("key_interval_min", min_val=0.0, max_val=5.0, default=0.1)
        step.key_interval_max = self._get_float("key_interval_max", min_val=0.0, max_val=5.0, default=0.3)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.MULTI_KEY_SEQUENCE, MultiKeySequenceDialog)
