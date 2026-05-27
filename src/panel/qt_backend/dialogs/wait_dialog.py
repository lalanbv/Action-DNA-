"""QtWaitDialog — 等待步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, WaitStep
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtWaitDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["wait_seconds"] = self._add_labeled_spinbox(
            t("dialog.label.wait_seconds"),
            default=1.0, min_val=0.1, max_val=300, increment=0.1,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["wait_seconds"].setValue(action.wait_seconds)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or WaitStep()
        step.wait_seconds = self._get_float("wait_seconds", min_val=0.1, max_val=300.0, default=1.0)
        self._apply_common(step)
        return step
