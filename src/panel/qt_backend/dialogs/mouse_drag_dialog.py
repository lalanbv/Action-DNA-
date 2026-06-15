"""QtMouseDragDialog — 鼠标拖拽步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, MouseDragStep
from src.panel.qt_backend.widgets import themed_dropdown, themed_label
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtMouseDragDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        header1 = themed_label(self, text=t("dialog.label.start_pos"))
        self._form_layout.addRow(header1)
        self._vars["start_x"] = self._add_labeled_spinbox(
            "X", default=0, min_val=0, max_val=9999, increment=10,
        )
        self._vars["start_y"] = self._add_labeled_spinbox(
            "Y", default=0, min_val=0, max_val=9999, increment=10,
        )

        header2 = themed_label(self, text=t("dialog.label.end_pos"))
        self._form_layout.addRow(header2)
        self._vars["end_x"] = self._add_labeled_spinbox(
            "X", default=0, min_val=0, max_val=9999, increment=10,
        )
        self._vars["end_y"] = self._add_labeled_spinbox(
            "Y", default=0, min_val=0, max_val=9999, increment=10,
        )

        self._vars["button_combo"] = themed_dropdown(
            self,
            options=[
                ("left", "action.key.mouse_left"),
                ("middle", "action.key.mouse_middle"),
                ("right", "action.key.mouse_right"),
            ],
        )
        self._add_row(t("dialog.label.drag_button"), self._vars["button_combo"])

        self._vars["duration"] = self._add_labeled_spinbox(
            t("dialog.label.drag_duration"),
            default=0.5, min_val=0.1, max_val=5.0, increment=0.1,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["start_x"].setValue(action.start_x)
        self._vars["start_y"].setValue(action.start_y)
        self._vars["end_x"].setValue(action.end_x)
        self._vars["end_y"].setValue(action.end_y)
        idx = self._vars["button_combo"].findData(action.button or "left")
        if idx >= 0:
            self._vars["button_combo"].setCurrentIndex(idx)
        self._vars["duration"].setValue(action.duration)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or MouseDragStep()
        step.start_x = self._get_int("start_x", min_val=0, default=0)
        step.start_y = self._get_int("start_y", min_val=0, default=0)
        step.end_x = self._get_int("end_x", min_val=0, default=0)
        step.end_y = self._get_int("end_y", min_val=0, default=0)
        step.button = self._vars["button_combo"].currentData()
        step.duration = self._get_float("duration", min_val=0.1, max_val=60.0, default=0.5)
        self._apply_common(step)
        return step
