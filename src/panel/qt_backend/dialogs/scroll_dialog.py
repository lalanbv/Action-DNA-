"""QtScrollDialog — 滚轮步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, MouseScrollStep
from src.panel.qt_backend.widgets import themed_label
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtScrollDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["scroll_clicks"] = self._add_labeled_spinbox(
            t("dialog.label.scroll_amount"),
            default=3, min_val=-20, max_val=20, increment=1,
        )
        self._vars["scroll_delta_x"] = self._add_labeled_spinbox(
            t("dialog.label.scroll_horizontal"),
            default=0, min_val=-20, max_val=20, increment=1,
        )
        hint = themed_label(self, text=t("dialog.hint.scroll_direction"))
        self._form_layout.addRow(hint)

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["scroll_clicks"].setValue(action.scroll_clicks)
        self._vars["scroll_delta_x"].setValue(action.scroll_delta_x)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or MouseScrollStep()
        step.scroll_clicks = self._get_int("scroll_clicks", min_val=-20, max_val=20, default=3)
        step.scroll_delta_x = self._get_int("scroll_delta_x", min_val=-20, max_val=20, default=0)
        self._apply_common(step)
        return step
