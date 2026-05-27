"""QtMouseMoveDialog — 鼠标移动步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, MouseMoveStep
from src.panel.qt_backend.widgets import themed_combobox
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtMouseMoveDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["offset_x"] = self._add_labeled_spinbox(
            t("dialog.label.offset_x"),
            default=0, min_val=-3000, max_val=3000, increment=10,
        )
        self._vars["offset_y"] = self._add_labeled_spinbox(
            t("dialog.label.offset_y"),
            default=0, min_val=-3000, max_val=3000, increment=10,
        )
        self._vars["move_speed"] = self._add_labeled_spinbox(
            t("dialog.label.move_speed"),
            default=0.5, min_val=0.1, max_val=3.0, increment=0.05,
        )
        self._vars["curve_amount"] = self._add_labeled_spinbox(
            t("dialog.label.curve_amount"),
            default=0.0, min_val=0.0, max_val=1.0, increment=0.05,
        )

        self._vars["button_combo"] = themed_combobox(
            self, items=[
                t("dialog.btn.none"), t("dialog.btn.left"),
                t("dialog.btn.middle"), t("dialog.btn.right"),
            ],
        )
        self._add_row(t("dialog.label.hold_button"), self._vars["button_combo"])

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["offset_x"].setValue(action.offset_x)
        self._vars["offset_y"].setValue(action.offset_y)
        self._vars["move_speed"].setValue(action.move_speed)
        self._vars["curve_amount"].setValue(action.curve_amount)
        self._vars["button_combo"].setCurrentIndex(0)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or MouseMoveStep()
        step.offset_x = self._get_int("offset_x", default=0)
        step.offset_y = self._get_int("offset_y", default=0)
        step.move_speed = self._get_float("move_speed", min_val=0.0, default=0.5)
        step.curve_amount = self._get_float("curve_amount", min_val=0.0, max_val=1.0, default=0.0)
        step.button = self._vars["button_combo"].currentText()
        self._apply_common(step)
        return step
