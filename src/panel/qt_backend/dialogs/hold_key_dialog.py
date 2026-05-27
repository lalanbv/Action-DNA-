"""QtHoldKeyDialog — 长按按键步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, HoldKeyStep
from src.panel.qt_backend.widgets import themed_label
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtHoldKeyDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["keys_hold"] = self._add_labeled_entry(
            t("dialog.label.key"), default="",
        )
        self._vars["hold_duration"] = self._add_labeled_spinbox(
            t("dialog.label.hold_duration"),
            default=1.0, min_val=0.1, max_val=60.0, increment=0.1,
        )
        hint = themed_label(self, text=t("dialog.hint.multi_key_hold"))
        self._form_layout.addRow(hint)

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["keys_hold"].setText(action.keys_hold or action.key)
        self._vars["hold_duration"].setValue(action.hold_duration)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or HoldKeyStep()
        step.keys_hold = self._vars["keys_hold"].text()
        step.hold_duration = self._get_float("hold_duration", min_val=0.1, max_val=60.0, default=1.0)
        self._apply_common(step)
        return step
