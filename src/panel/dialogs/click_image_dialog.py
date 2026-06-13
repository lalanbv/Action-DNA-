"""ClickImageDialog — 图片点击对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType, DetectMode, FoundAction, MatchStrategy, ThresholdMode
from src.core.step_types import BaseStep, ClickImageStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.dialogs.key_picker import SyncedVar
from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
from src.panel.widgets import themed_button, themed_dropdown, themed_entry, themed_frame, themed_label, themed_spinbox
from src.utils.i18n import t


_FOUND_ACTION_OPTIONS = [
    (fa.name, i18n_key)
    for fa, i18n_key in [
        (FoundAction.LEFT_CLICK, "dialog.found_action.left_click"),
        (FoundAction.RIGHT_CLICK, "dialog.found_action.right_click"),
        (FoundAction.LEFT_DOUBLE_CLICK, "dialog.found_action.left_double_click"),
        (FoundAction.RIGHT_DOUBLE_CLICK, "dialog.found_action.right_double_click"),
        (FoundAction.LONG_PRESS, "dialog.found_action.long_press"),
        (FoundAction.DRAG_TO, "dialog.found_action.drag_to"),
        (FoundAction.ONLY_MOVE, "dialog.found_action.only_move"),
        (FoundAction.OUTPUT_COORD, "dialog.found_action.output_coord"),
    ]
]

_DETECT_MODE_OPTIONS = [
    (dm.name, i18n_key)
    for dm, i18n_key in [
        (DetectMode.WAIT_UNTIL_FOUND, "dialog.detect_mode.wait_until_found"),
        (DetectMode.SKIP_IF_NOT_FOUND, "dialog.detect_mode.skip_if_not_found"),
        (DetectMode.FAIL_IF_NOT_FOUND, "dialog.detect_mode.fail_if_not_found"),
    ]
]


class ClickImageDialog(StepDialogBase):
    """图片点击配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        row = 0

        # 多模板图片管理器(主图 + 状态备用图,替代单行 image_path + 阈值)
        themed_label(
            self._content_frame, text=t("dialog.label.template_image"),
        ).grid(row=row, column=0, sticky=tk.NW, padx=th.pad_sm, pady=th.pad_xs)
        self._mt_editor = MultiTemplateEditor(self._content_frame)
        self._mt_editor.frame.grid(row=row, column=1, sticky=tk.EW, padx=th.pad_sm)
        row += 1

        # 检测模式
        themed_label(
            self._content_frame, text=t("dialog.label.detect_mode"),
        ).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
        self._dm_dropdown = themed_dropdown(
            self._content_frame,
            options=_DETECT_MODE_OPTIONS,
            value=DetectMode.SKIP_IF_NOT_FOUND.name,
            state="readonly", width=22,
        )
        self._dm_dropdown.grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm)
        row += 1

        # 重试设置
        self._vars["retry_count"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.retry_count"),
            default=0, min_val=0, max_val=20, increment=1, row=row,
        )
        row += 1
        self._vars["retry_wait_min"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.retry_wait_min"),
            default=0.0, min_val=0.0, max_val=30.0, increment=0.1, row=row,
        )
        row += 1
        self._vars["retry_wait_max"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.retry_wait_max"),
            default=0.0, min_val=0.0, max_val=30.0, increment=0.1, row=row,
        )
        row += 1

        # 找到后动作
        themed_label(
            self._content_frame, text=t("dialog.label.found_action"),
        ).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
        self._fa_dropdown = themed_dropdown(
            self._content_frame,
            options=_FOUND_ACTION_OPTIONS,
            value=FoundAction.LEFT_CLICK.name,
            state="readonly", width=22,
            command=self._on_found_action_value,
        )
        self._fa_dropdown.grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm)
        row += 1

        # 条件字段：长按秒数（仅 LONG_PRESS）
        self._hold_frame = themed_frame(self._content_frame)
        self._hold_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW)
        themed_label(
            self._hold_frame, text=t("dialog.label.hold_duration"),
        ).pack(side=tk.LEFT, padx=(th.pad_sm, 0))
        _v_hold_raw = tk.DoubleVar(value=1.0)
        _sb_hold = themed_spinbox(
            self._hold_frame, from_=0.1, to=30.0, increment=0.1,
            textvariable=_v_hold_raw, width=8,
        )
        _sb_hold.pack(side=tk.LEFT, padx=th.pad_sm)
        self._vars["hold_duration"] = SyncedVar(_v_hold_raw, _sb_hold, True)
        row += 1

        # 条件字段：拖拽偏移（仅 DRAG_TO）
        self._drag_frame = themed_frame(self._content_frame)
        self._drag_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW)
        themed_label(
            self._drag_frame, text=t("dialog.label.drag_offset_x"),
        ).pack(side=tk.LEFT, padx=(th.pad_sm, 0))
        _v_drag_x_raw = tk.IntVar(value=0)
        _sb_drag_x = themed_spinbox(
            self._drag_frame, from_=-3000, to=3000, increment=1,
            textvariable=_v_drag_x_raw, width=6,
        )
        _sb_drag_x.pack(side=tk.LEFT, padx=th.pad_xs)
        themed_label(
            self._drag_frame, text=t("dialog.label.drag_offset_y"),
        ).pack(side=tk.LEFT, padx=(th.pad_sm, 0))
        _v_drag_y_raw = tk.IntVar(value=0)
        _sb_drag_y = themed_spinbox(
            self._drag_frame, from_=-3000, to=3000, increment=1,
            textvariable=_v_drag_y_raw, width=6,
        )
        _sb_drag_y.pack(side=tk.LEFT, padx=th.pad_xs)
        self._vars["drag_offset_x"] = SyncedVar(_v_drag_x_raw, _sb_drag_x, False)
        self._vars["drag_offset_y"] = SyncedVar(_v_drag_y_raw, _sb_drag_y, False)
        row += 1

        self._on_found_action_changed()

        # 坐标变量名
        themed_label(
            self._content_frame, text=t("dialog.label.coord_var_name"),
        ).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
        self._vars["save_coord_name"] = tk.StringVar()
        themed_entry(
            self._content_frame, textvariable=self._vars["save_coord_name"], width=20,
        ).grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm)
        row += 1
        themed_label(
            self._content_frame,
            text="  " + t("dialog.hint.coord_output_save"),
            fg=th.text_muted,
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)
        row += 1

        self._common_row = row

    def _on_found_action_value(self, val: str) -> None:
        if val == FoundAction.LONG_PRESS.name:
            self._hold_frame.grid()
            self._drag_frame.grid_remove()
        elif val == FoundAction.DRAG_TO.name:
            self._hold_frame.grid_remove()
            self._drag_frame.grid()
        else:
            self._hold_frame.grid_remove()
            self._drag_frame.grid_remove()

    def _on_found_action_changed(self) -> None:
        self._on_found_action_value(self._fa_dropdown.get_value())

    def _populate_fields(self, action: BaseStep) -> None:
        self._mt_editor.set_state(
            image_path=action.image_path,
            alt_paths=action.alt_image_paths,
            alt_thresholds=action.alt_thresholds,
            mode=action.threshold_mode,
            strategy=action.match_strategy,
            global_threshold=action.threshold,
        )
        self._dm_dropdown.set_value(action.detect_mode.name)
        self._vars["retry_count"].set(action.retry_count)
        self._vars["retry_wait_min"].set(action.retry_wait_min)
        self._vars["retry_wait_max"].set(action.retry_wait_max)
        self._fa_dropdown.set_value(action.found_action.name)
        self._vars["hold_duration"].set(action.hold_duration)
        self._vars["drag_offset_x"].set(action.drag_offset_x)
        self._vars["drag_offset_y"].set(action.drag_offset_y)
        self._vars["save_coord_name"].set(action.save_coord_name)
        self._on_found_action_changed()
        self._add_common_fields(self._content_frame, self._common_row, action)

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
        step.save_coord_name = self._vars["save_coord_name"].get()
        dm_val = self._dm_dropdown.get_value()
        fa_val = self._fa_dropdown.get_value()
        step.detect_mode = DetectMode[dm_val] if dm_val in DetectMode.__members__ else DetectMode.SKIP_IF_NOT_FOUND
        step.found_action = FoundAction[fa_val] if fa_val in FoundAction.__members__ else FoundAction.LEFT_CLICK
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.CLICK_IMAGE, ClickImageDialog)
