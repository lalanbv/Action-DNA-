"""WaitRandomDialog — 随机等待对话框。"""

from __future__ import annotations

from src.core.action import ActionType
from src.core.step_types import BaseStep, WaitRandomStep
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.utils.i18n import t


class WaitRandomDialog(StepDialogBase):
    """随机等待配置对话框。"""

    def _build_content(self) -> None:
        self._vars["wait_min"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.wait_min"),
            default=0.5, min_val=0.0, max_val=300, increment=0.1, row=0,
        )
        self._vars["wait_max"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.wait_max"),
            default=2.0, min_val=0.0, max_val=300, increment=0.1, row=1,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["wait_min"].set(action.wait_min)
        self._vars["wait_max"].set(action.wait_max)
        self._add_common_fields(self._content_frame, 2, action)

    def _get_result(self) -> BaseStep:
        step = self._action or WaitRandomStep()
        step.wait_min = self._get_float("wait_min", min_val=0.0, max_val=300.0, default=0.5)
        step.wait_max = self._get_float("wait_max", min_val=0.0, max_val=300.0, default=2.0)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.WAIT_RANDOM, WaitRandomDialog)
