"""QtKeyComboDialog — 组合键步骤配置对话框。"""

from __future__ import annotations

from src.core.step_types import BaseStep, KeyComboStep
from src.panel.qt_backend.widgets import themed_combobox, themed_label
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase


class QtKeyComboDialog(QtStepDialogBase):
    def _build_content(self) -> None:
        self._vars["combo_keys"] = self._add_labeled_entry(
            t("dialog.label.combo_keys"), default="",
        )
        hint = themed_label(self, text=t("dialog.hint.combo_key_format"))
        self._form_layout.addRow(hint)

        self._mode_labels = {
            "hold_tap": t("common.mode.hold_tap"),
            "sequence": t("common.mode.sequence"),
            "all_hold": t("common.mode.all_hold"),
        }
        self._vars["combo_mode_combo"] = themed_combobox(
            self, items=list(self._mode_labels.values()),
        )
        self._add_row(t("dialog.label.combo_mode"), self._vars["combo_mode_combo"])

        self._vars["hold_duration"] = self._add_labeled_spinbox(
            t("dialog.label.hold_duration"),
            default=1.0, min_val=0.1, max_val=30.0, increment=0.1,
        )

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["combo_keys"].setText(action.combo_keys)
        for k, v in self._mode_labels.items():
            if k == action.combo_mode:
                idx = self._vars["combo_mode_combo"].findText(v)
                if idx >= 0:
                    self._vars["combo_mode_combo"].setCurrentIndex(idx)
                break
        self._vars["hold_duration"].setValue(action.hold_duration)
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or KeyComboStep()
        step.combo_keys = self._vars["combo_keys"].text()
        label = self._vars["combo_mode_combo"].currentText()
        for k, v in self._mode_labels.items():
            if v == label:
                step.combo_mode = k
                break
        step.hold_duration = self._get_float("hold_duration", min_val=0.0, max_val=60.0, default=0.5)
        self._apply_common(step)
        return step
