"""QtClickImageDialog — 模板匹配点击步骤配置对话框。"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel

from src.core.action import DetectMode, FoundAction
from src.core.step_types import BaseStep, ClickImageStep
from src.panel.qt_backend.widgets import (
    themed_button, themed_entry, themed_frame, themed_spinbox, themed_combobox,
)
from src.utils.i18n import t

from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase
from src.panel.qt_backend.dialogs._mappings import _FOUND_ACTION_I18N, _DETECT_MODE_I18N
from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt


class QtClickImageDialog(QtStepDialogBase):
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._fa_labels: dict[FoundAction, str] = {}
        self._dm_labels: dict[DetectMode, str] = {}
        super().__init__(*args, **kwargs)

    def _build_content(self) -> None:
        self._fa_labels = {fa: t(key) for fa, key in _FOUND_ACTION_I18N.items()}
        self._dm_labels = {dm: t(key) for dm, key in _DETECT_MODE_I18N.items()}

        # 多模板图片管理器(主图 + 状态备用图,替代单行 image_path + 阈值)
        self._mt_editor = MultiTemplateEditorQt(self)
        self._add_row(t("dialog.label.template_image"), self._mt_editor)

        # Detect mode
        self._vars["detect_mode_combo"] = themed_combobox(
            self, items=list(self._dm_labels.values()),
        )
        self._add_row(t("dialog.label.detect_mode"), self._vars["detect_mode_combo"])

        # Retry settings
        self._vars["retry_count"] = self._add_labeled_spinbox(
            t("dialog.label.retry_count"),
            default=0, min_val=0, max_val=20, increment=1,
        )
        self._vars["retry_wait_min"] = self._add_labeled_spinbox(
            t("dialog.label.retry_wait_min"),
            default=0.0, min_val=0.0, max_val=30.0, increment=0.1,
        )
        self._vars["retry_wait_max"] = self._add_labeled_spinbox(
            t("dialog.label.retry_wait_max"),
            default=0.0, min_val=0.0, max_val=30.0, increment=0.1,
        )

        # Found action
        self._vars["found_action_combo"] = themed_combobox(
            self, items=list(self._fa_labels.values()),
        )
        self._vars["found_action_combo"].currentIndexChanged.connect(
            self._on_found_action_changed,
        )
        self._add_row(t("dialog.label.found_action"), self._vars["found_action_combo"])

        # Hold duration (conditional)
        self._vars["hold_duration"] = self._add_labeled_spinbox(
            t("dialog.label.hold_duration"),
            default=1.0, min_val=0.1, max_val=30.0, increment=0.1,
        )

        # Drag offsets (conditional)
        self._drag_row = themed_frame(self)
        drag_layout = QHBoxLayout(self._drag_row)
        drag_layout.setContentsMargins(0, 0, 0, 0)
        self._vars["drag_offset_x"] = themed_spinbox(
            self._drag_row, minimum=-3000, maximum=3000, value=0,
        )
        self._vars["drag_offset_y"] = themed_spinbox(
            self._drag_row, minimum=-3000, maximum=3000, value=0,
        )
        drag_layout.addWidget(QLabel("X:"))
        drag_layout.addWidget(self._vars["drag_offset_x"])
        drag_layout.addWidget(QLabel("Y:"))
        drag_layout.addWidget(self._vars["drag_offset_y"])
        self._add_row(t("dialog.label.drag_offset"), self._drag_row)

        # Coord variable name
        self._vars["save_coord_name"] = self._add_labeled_entry(
            t("dialog.label.coord_var_name"), default="",
        )

        self._on_found_action_changed()

    def _on_found_action_changed(self) -> None:
        label = self._vars["found_action_combo"].currentText()
        fa_long = self._fa_labels.get(FoundAction.LONG_PRESS, "")
        fa_drag = self._fa_labels.get(FoundAction.DRAG_TO, "")
        if label == fa_long:
            self._drag_row.hide()
        elif label == fa_drag:
            self._drag_row.show()
        else:
            self._drag_row.hide()

    def _populate_fields(self, action: BaseStep) -> None:
        self._mt_editor.set_state(
            image_path=action.image_path,
            alt_paths=action.alt_image_paths,
            alt_thresholds=action.alt_thresholds,
            mode=action.threshold_mode,
            strategy=action.match_strategy,
            global_threshold=action.threshold,
        )
        for k, v in self._dm_labels.items():
            if k == action.detect_mode:
                idx = self._vars["detect_mode_combo"].findText(v)
                if idx >= 0:
                    self._vars["detect_mode_combo"].setCurrentIndex(idx)
                break
        self._vars["retry_count"].setValue(action.retry_count)
        self._vars["retry_wait_min"].setValue(action.retry_wait_min)
        self._vars["retry_wait_max"].setValue(action.retry_wait_max)
        for k, v in self._fa_labels.items():
            if k == action.found_action:
                idx = self._vars["found_action_combo"].findText(v)
                if idx >= 0:
                    self._vars["found_action_combo"].setCurrentIndex(idx)
                break
        self._vars["hold_duration"].setValue(action.hold_duration)
        self._vars["drag_offset_x"].setValue(action.drag_offset_x)
        self._vars["drag_offset_y"].setValue(action.drag_offset_y)
        self._vars["save_coord_name"].setText(action.save_coord_name)
        self._on_found_action_changed()
        self._add_common_fields(action)

    def _get_result(self) -> BaseStep:
        step = self._action or ClickImageStep()
        (
            image_path, alt_paths, alt_thresholds,
            mode, strategy, global_threshold,
        ) = self._mt_editor.get_state()
        step.image_path = image_path
        step.alt_image_paths = alt_paths
        step.alt_thresholds = alt_thresholds
        step.threshold_mode = mode
        step.match_strategy = strategy
        step.threshold = global_threshold
        step.retry_count = self._get_int("retry_count", min_val=0, default=3)
        step.retry_wait_min = self._get_float("retry_wait_min", min_val=0.0, default=0.5)
        step.retry_wait_max = self._get_float("retry_wait_max", min_val=0.0, default=1.5)
        step.hold_duration = self._get_float("hold_duration", min_val=0.0, default=0.5)
        step.drag_offset_x = self._get_int("drag_offset_x", default=0)
        step.drag_offset_y = self._get_int("drag_offset_y", default=0)
        step.save_coord_name = self._vars["save_coord_name"].text()
        dm_label = self._vars["detect_mode_combo"].currentText()
        for k, v in self._dm_labels.items():
            if v == dm_label:
                step.detect_mode = k
                break
        fa_label = self._vars["found_action_combo"].currentText()
        for k, v in self._fa_labels.items():
            if v == fa_label:
                step.found_action = k
                break
        self._apply_common(step)
        return step
