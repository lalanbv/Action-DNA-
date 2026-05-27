"""StartTimerDialog — 启动计时器对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, StartTimerStep
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.utils.i18n import t


class StartTimerDialog(StepDialogBase):
    """启动计时器配置对话框。"""

    def _build_content(self) -> None:
        self._vars["timer_name"] = self._add_labeled_entry(
            self._content_frame, t("dialog.label.timer_name"),
            default="", row=0,
        )
        self._vars["timer_timeout"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.timeout_seconds"),
            default=0.0, min_val=0.0, max_val=3600.0, increment=0.5, row=1,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        entry = self._vars["timer_name"]
        entry.delete(0, tk.END)
        entry.insert(0, action.timer_name or "")
        self._vars["timer_timeout"].set(action.timer_timeout)
        self._add_common_fields(self._content_frame, 2, action)

    def _get_result(self) -> BaseStep:
        step = self._action or StartTimerStep()
        step.timer_name = self._vars["timer_name"].get().strip()
        step.timer_timeout = self._get_float("timer_timeout", min_val=0.0, max_val=3600.0, default=0.0)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.START_TIMER, StartTimerDialog)
