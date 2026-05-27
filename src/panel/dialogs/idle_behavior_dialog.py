"""IdleBehaviorDialog — 随机idle对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, IdleBehaviorStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.widgets import themed_label
from src.utils.i18n import t


class IdleBehaviorDialog(StepDialogBase):
    """随机 idle 行为配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        self._vars["idle_duration"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.idle_duration"),
            default=3.0, min_val=0.5, max_val=60.0, increment=0.5, row=0,
        )
        self._vars["jitter_intensity"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.jitter_intensity"),
            default=3, min_val=0, max_val=20, increment=1, row=1,
        )

        self._vars["idle_actions"] = self._add_labeled_entry(
            self._content_frame, t("dialog.label.random_keys"),
            default="", row=2,
        )
        themed_label(
            self._content_frame, text="  " + t("dialog.hint.optional_keys"),
            fg=th.text_muted,
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

        self._vars["idle_action_chance"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.key_chance"),
            default=0.2, min_val=0.0, max_val=1.0, increment=0.05, row=4,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["idle_duration"].set(action.idle_duration)
        self._vars["jitter_intensity"].set(action.jitter_intensity)
        idle_entry = self._vars["idle_actions"]
        idle_entry.delete(0, tk.END)
        idle_entry.insert(0, action.idle_actions or "")
        self._vars["idle_action_chance"].set(action.idle_action_chance)
        self._add_common_fields(self._content_frame, 5, action)

    def _get_result(self) -> BaseStep:
        step = self._action or IdleBehaviorStep()
        step.idle_duration = self._get_float("idle_duration", min_val=0.5, max_val=60.0, default=3.0)
        step.jitter_intensity = self._get_int("jitter_intensity", min_val=0, max_val=20, default=3)
        step.idle_actions = self._vars["idle_actions"].get()
        step.idle_action_chance = self._get_float("idle_action_chance", min_val=0.0, max_val=1.0, default=0.2)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.IDLE_BEHAVIOR, IdleBehaviorDialog)
