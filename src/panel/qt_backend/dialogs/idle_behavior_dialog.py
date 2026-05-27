"""QtIdleBehaviorDialog — 空闲行为步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, IdleBehaviorStep
from src.panel.qt_backend.widgets import themed_label
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtIdleBehaviorDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["idle_duration"] = self._add_labeled_spinbox(
            t("dialog.label.idle_duration"),
            default=3.0, min_val=0.5, max_val=60.0, increment=0.5,
        )
        self._vars["jitter_intensity"] = self._add_labeled_spinbox(
            t("dialog.label.jitter_intensity"),
            default=3, min_val=0, max_val=20, increment=1,
        )
        self._vars["idle_actions"] = self._add_labeled_entry(
            t("dialog.label.random_keys"), default="",
        )
        self._vars["idle_action_chance"] = self._add_labeled_spinbox(
            t("dialog.label.key_chance"),
            default=0.2, min_val=0.0, max_val=1.0, increment=0.05,
        )
        hint = themed_label(self, text=t("dialog.hint.optional_keys"))
        self._form_layout.addRow(hint)

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["idle_duration"].setValue(action.idle_duration)
        self._vars["jitter_intensity"].setValue(action.jitter_intensity)
        self._vars["idle_actions"].setText(action.idle_actions or "")
        self._vars["idle_action_chance"].setValue(action.idle_action_chance)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or IdleBehaviorStep()
        step.idle_duration = self._get_float("idle_duration", min_val=0.5, max_val=60.0, default=3.0)
        step.jitter_intensity = self._get_int("jitter_intensity", min_val=0, max_val=20, default=3)
        step.idle_actions = self._vars["idle_actions"].text()
        step.idle_action_chance = self._get_float("idle_action_chance", min_val=0.0, max_val=1.0, default=0.2)
        self._apply_common(step)
        return step
