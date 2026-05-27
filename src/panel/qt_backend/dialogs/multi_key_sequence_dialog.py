"""QtMultiKeySequenceDialog — 多键序列步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, MultiKeySequenceStep
from src.panel.qt_backend.widgets import themed_label
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtMultiKeySequenceDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["key_sequence"] = self._add_labeled_entry(
            t("dialog.label.key_sequence"), default="",
        )
        hint = themed_label(self, text=t("dialog.hint.key_sequence_format"))
        self._form_layout.addRow(hint)
        self._vars["key_interval_min"] = self._add_labeled_spinbox(
            t("dialog.label.interval_min"),
            default=0.1, min_val=0.0, max_val=5.0, increment=0.05,
        )
        self._vars["key_interval_max"] = self._add_labeled_spinbox(
            t("dialog.label.interval_max"),
            default=0.3, min_val=0.0, max_val=5.0, increment=0.05,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["key_sequence"].setText(action.key_sequence)
        self._vars["key_interval_min"].setValue(action.key_interval_min)
        self._vars["key_interval_max"].setValue(action.key_interval_max)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or MultiKeySequenceStep()
        step.key_sequence = self._vars["key_sequence"].text()
        step.key_interval_min = self._get_float("key_interval_min", min_val=0.0, max_val=5.0, default=0.1)
        step.key_interval_max = self._get_float("key_interval_max", min_val=0.0, max_val=5.0, default=0.3)
        self._apply_common(step)
        return step
