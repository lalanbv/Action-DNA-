"""QtPressKeyDialog — 按键步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, PressKeyStep
from src.panel.qt_backend.widgets import themed_label
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtPressKeyDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["key_entry"] = self._add_labeled_entry(
            t("dialog.label.key"), default="",
        )
        hint = themed_label(self, text=t("dialog.hint.key_format"))
        self._form_layout.addRow(hint)

    def _populate_fields(self, action: BaseStep) -> None:
        entry = self._vars["key_entry"]
        if action.text:
            entry.setText(f"[text] {action.text[:30]}")
        else:
            entry.setText(action.key)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or PressKeyStep()
        key_val = self._vars["key_entry"].text()
        if key_val.startswith("[text] "):
            step.text = key_val[7:]
            step.key = ""
        else:
            step.key = key_val
            step.text = ""
        self._apply_common(step)
        return step
