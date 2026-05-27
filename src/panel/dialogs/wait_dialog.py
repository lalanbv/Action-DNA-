"""WaitDialog — 固定等待对话框。"""

from __future__ import annotations

from src.core.action import ActionType
from src.core.step_types import BaseStep, WaitStep
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.utils.i18n import t


class WaitDialog(StepDialogBase):
    """固定等待配置对话框。"""

    def _build_content(self) -> None:
        self._vars["wait_seconds"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.wait_seconds"),
            default=1.0, min_val=0.1, max_val=300, increment=0.1, row=0,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["wait_seconds"].set(action.wait_seconds)
        self._add_common_fields(self._content_frame, 1, action)

    def _get_result(self) -> BaseStep:
        step = self._action or WaitStep()
        step.wait_seconds = self._get_float("wait_seconds", min_val=0.1, max_val=300.0, default=1.0)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.WAIT, WaitDialog)
