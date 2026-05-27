"""QtClickPosDialog — 固定坐标点击步骤配置对话框。"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout

from src.core.step_types import BaseStep, ClickPosStep
from src.panel.qt_backend.widgets import (
    themed_combobox, themed_checkbutton, themed_entry, themed_frame, themed_label,
)
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtClickPosDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["pos_x"] = self._add_labeled_spinbox(
            t("dialog.label.pos_x"),
            default=0, min_val=0, max_val=9999, increment=1,
        )
        self._vars["pos_y"] = self._add_labeled_spinbox(
            t("dialog.label.pos_y"),
            default=0, min_val=0, max_val=9999, increment=1,
        )
        self._vars["clicks"] = self._add_labeled_spinbox(
            t("dialog.label.click_count"),
            default=1, min_val=1, max_val=5, increment=1,
        )
        self._vars["hold_duration"] = self._add_labeled_spinbox(
            t("dialog.label.hold_duration"),
            default=0.0, min_val=0.0, max_val=30.0, increment=0.1,
        )

        btn_row = themed_frame(self)
        btn_layout = QHBoxLayout(btn_row)
        btn_layout.setContentsMargins(0, 0, 0, 0)
        themed_label(btn_row, text=t("dialog.label.mouse_button"))
        self._vars["button_combo"] = themed_combobox(
            btn_row, items=["left", "right", "middle"],
        )
        btn_layout.addWidget(self._vars["button_combo"])
        self._form_layout.addRow(btn_row)

        self._vars["use_coord_var_cb"] = themed_checkbutton(
            self, text=t("dialog.hint.use_coord_var"),
        )
        self._form_layout.addRow(self._vars["use_coord_var_cb"])

        self._vars["coord_var_name"] = self._add_labeled_entry(
            t("dialog.label.coord_var_name"), default="",
        )
        hint = themed_label(self, text=t("dialog.hint.coord_var_reference"))
        self._form_layout.addRow(hint)

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["pos_x"].setValue(action.pos_x)
        self._vars["pos_y"].setValue(action.pos_y)
        self._vars["clicks"].setValue(action.clicks)
        self._vars["hold_duration"].setValue(action.hold_duration)
        idx = self._vars["button_combo"].findText(action.button or "left")
        if idx >= 0:
            self._vars["button_combo"].setCurrentIndex(idx)
        self._vars["use_coord_var_cb"].setChecked(action.use_coord_var)
        self._vars["coord_var_name"].setText(action.coord_var_name or "")
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or ClickPosStep()
        step.pos_x = self._get_int("pos_x", min_val=0, max_val=9999, default=0)
        step.pos_y = self._get_int("pos_y", min_val=0, max_val=9999, default=0)
        step.clicks = self._get_int("clicks", min_val=1, max_val=5, default=1)
        step.hold_duration = self._get_float("hold_duration", min_val=0.0, max_val=30.0, default=0.0)
        step.button = self._vars["button_combo"].currentText()
        step.use_coord_var = self._vars["use_coord_var_cb"].isChecked()
        step.coord_var_name = self._vars["coord_var_name"].text()
        self._apply_common(step)
        return step
