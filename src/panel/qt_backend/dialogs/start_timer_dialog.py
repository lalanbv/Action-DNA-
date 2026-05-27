"""QtStartTimerDialog — 启动计时器步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, StartTimerStep
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtStartTimerDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["timer_name"] = self._add_labeled_entry(
            t("dialog.label.timer_name"), default="",
        )
        self._vars["timer_timeout"] = self._add_labeled_spinbox(
            t("dialog.label.timeout_seconds"),
            default=0.0, min_val=0.0, max_val=3600.0, increment=0.5,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["timer_name"].setText(action.timer_name or "")
        self._vars["timer_timeout"].setValue(action.timer_timeout)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or StartTimerStep()
        step.timer_name = self._vars["timer_name"].text().strip()
        step.timer_timeout = self._get_float("timer_timeout", min_val=0.0, max_val=3600.0, default=0.0)
        self._apply_common(step)
        return step
