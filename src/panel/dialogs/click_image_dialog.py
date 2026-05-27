"""ClickImageDialog — 图片点击对话框。"""

from __future__ import annotations

import os

import tkinter as tk
from tkinter import filedialog, ttk

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None  # type: ignore[assignment,misc]
    ImageTk = None  # type: ignore[assignment]

from src.core.action import ActionType, DetectMode, FoundAction
from src.core.step_types import BaseStep, ClickImageStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.dialogs.key_picker import SyncedVar
from src.panel.widgets import themed_button, themed_entry, themed_frame, themed_label, themed_spinbox
from src.utils.i18n import t


_FOUND_ACTION_I18N = {
    FoundAction.LEFT_CLICK: "dialog.found_action.left_click",
    FoundAction.RIGHT_CLICK: "dialog.found_action.right_click",
    FoundAction.LEFT_DOUBLE_CLICK: "dialog.found_action.left_double_click",
    FoundAction.RIGHT_DOUBLE_CLICK: "dialog.found_action.right_double_click",
    FoundAction.LONG_PRESS: "dialog.found_action.long_press",
    FoundAction.DRAG_TO: "dialog.found_action.drag_to",
    FoundAction.ONLY_MOVE: "dialog.found_action.only_move",
    FoundAction.OUTPUT_COORD: "dialog.found_action.output_coord",
}

_DETECT_MODE_I18N = {
    DetectMode.WAIT_UNTIL_FOUND: "dialog.detect_mode.wait_until_found",
    DetectMode.SKIP_IF_NOT_FOUND: "dialog.detect_mode.skip_if_not_found",
    DetectMode.FAIL_IF_NOT_FOUND: "dialog.detect_mode.fail_if_not_found",
}


def _found_action_labels() -> dict[FoundAction, str]:
    return {fa: t(key) for fa, key in _FOUND_ACTION_I18N.items()}


def _found_action_from_label(label: str) -> FoundAction | None:
    for fa, lbl in _found_action_labels().items():
        if lbl == label:
            return fa
    return None


def _detect_mode_labels() -> dict[DetectMode, str]:
    return {dm: t(key) for dm, key in _DETECT_MODE_I18N.items()}


class ClickImageDialog(StepDialogBase):
    """图片点击配置对话框。"""

    def __init__(self, *args: object, **kwargs: object) -> None:
        self._photo_ref: list[object] = [None]
        self._fa_labels: dict[FoundAction, str] = {}
        self._dm_labels: dict[DetectMode, str] = {}
        super().__init__(*args, **kwargs)

    def _build_content(self) -> None:
        th = current_theme()
        self._fa_labels = _found_action_labels()
        self._dm_labels = _detect_mode_labels()
        row = 0

        # 图片路径 + 预览
        themed_label(
            self._content_frame, text=t("dialog.label.template_image"),
        ).grid(row=row, column=0, sticky=tk.NW, padx=th.pad_sm, pady=th.pad_xs)
        img_frame = themed_frame(self._content_frame)
        img_frame.grid(row=row, column=1, sticky=tk.EW, padx=th.pad_sm)

        self._vars["image_path"] = tk.StringVar()
        themed_entry(img_frame, textvariable=self._vars["image_path"], width=32).pack(
            side=tk.TOP, fill=tk.X,
        )
        btn_frame = themed_frame(img_frame)
        btn_frame.pack(side=tk.TOP, fill=tk.X, pady=th.pad_xs)
        self._preview_label = themed_label(btn_frame, text=t("dialog.hint.no_image"))
        self._preview_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        themed_button(
            btn_frame, text=t("dialog.btn.select_image"), command=self._browse,
        ).pack(side=tk.RIGHT, padx=th.pad_xs)
        self._vars["image_path"].trace_add("write", self._update_preview)
        row += 1

        # 阈值
        self._vars["threshold"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.confidence"),
            default=0.8, min_val=0.1, max_val=1.0, increment=0.05, row=row,
        )
        row += 1

        # 检测模式
        themed_label(
            self._content_frame, text=t("dialog.label.detect_mode"),
        ).grid(row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
        self._vars["detect_mode"] = tk.StringVar(
            value=self._dm_labels.get(DetectMode.SKIP_IF_NOT_FOUND, ""),
        )
        ttk.Combobox(
            self._content_frame, textvariable=self._vars["detect_mode"],
            state="readonly", width=22,
            values=list(self._dm_labels.values()),
        ).grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm)
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
        self._vars["found_action"] = tk.StringVar(
            value=self._fa_labels.get(FoundAction.LEFT_CLICK, ""),
        )
        fa_cb = ttk.Combobox(
            self._content_frame, textvariable=self._vars["found_action"],
            state="readonly", width=22,
            values=list(self._fa_labels.values()),
        )
        fa_cb.grid(row=row, column=1, sticky=tk.W, padx=th.pad_sm)
        fa_cb.bind("<<ComboboxSelected>>", self._on_found_action_changed)
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

    def _on_found_action_changed(self, *_: object) -> None:
        label = self._vars["found_action"].get()
        fa_long = self._fa_labels.get(FoundAction.LONG_PRESS, "")
        fa_drag = self._fa_labels.get(FoundAction.DRAG_TO, "")
        if label == fa_long:
            self._hold_frame.grid()
            self._drag_frame.grid_remove()
        elif label == fa_drag:
            self._hold_frame.grid_remove()
            self._drag_frame.grid()
        else:
            self._hold_frame.grid_remove()
            self._drag_frame.grid_remove()

    def _browse(self) -> None:
        p = filedialog.askopenfilename(
            title=t("dialog.title.select_template_image"),
            filetypes=[
                (t("dialog.filetype.image"), "*.png *.jpg *.jpeg *.bmp"),
                (t("dialog.filetype.all"), "*.*"),
            ],
        )
        if p:
            self._vars["image_path"].set(p)

    def _update_preview(self, *_: object) -> None:
        path = self._vars["image_path"].get()
        if not path or not os.path.exists(path):
            self._preview_label.configure(image="", text=t("dialog.hint.no_image"))
            return
        if Image is None:
            self._preview_label.configure(image="", text=t("dialog.hint.preview_failed"))
            return
        try:
            img = Image.open(path)
            img.thumbnail((160, 100))
            self._photo_ref[0] = ImageTk.PhotoImage(img)
            self._preview_label.configure(image=self._photo_ref[0], text="")
        except (OSError, ValueError):
            self._preview_label.configure(
                image="", text=t("dialog.hint.preview_failed"),
            )

    def _populate_fields(self, action: BaseStep) -> None:
        self._fa_labels = _found_action_labels()
        self._dm_labels = _detect_mode_labels()
        self._vars["image_path"].set(action.image_path)
        self._vars["threshold"].set(action.threshold)
        for k, v in self._dm_labels.items():
            if k == action.detect_mode:
                self._vars["detect_mode"].set(v)
                break
        self._vars["retry_count"].set(action.retry_count)
        self._vars["retry_wait_min"].set(action.retry_wait_min)
        self._vars["retry_wait_max"].set(action.retry_wait_max)
        for k, v in self._fa_labels.items():
            if k == action.found_action:
                self._vars["found_action"].set(v)
                break
        self._vars["hold_duration"].set(action.hold_duration)
        self._vars["drag_offset_x"].set(action.drag_offset_x)
        self._vars["drag_offset_y"].set(action.drag_offset_y)
        self._vars["save_coord_name"].set(action.save_coord_name)
        self._on_found_action_changed()
        self._update_preview()
        self._add_common_fields(self._content_frame, self._common_row, action)

    def _get_result(self) -> BaseStep:
        step = self._action or ClickImageStep()
        step.image_path = self._vars["image_path"].get()
        step.threshold = self._get_float("threshold", min_val=0.0, max_val=1.0, default=0.8)
        step.retry_count = self._get_int("retry_count", min_val=0, default=3)
        step.retry_wait_min = self._get_float("retry_wait_min", min_val=0.0, default=0.5)
        step.retry_wait_max = self._get_float("retry_wait_max", min_val=0.0, default=1.5)
        step.hold_duration = self._get_float("hold_duration", min_val=0.0, default=0.5)
        step.drag_offset_x = self._get_int("drag_offset_x", default=0)
        step.drag_offset_y = self._get_int("drag_offset_y", default=0)
        step.save_coord_name = self._vars["save_coord_name"].get()
        dm_label = self._vars["detect_mode"].get()
        for k, v in self._dm_labels.items():
            if v == dm_label:
                step.detect_mode = k
                break
        fa_label = self._vars["found_action"].get()
        for k, v in self._fa_labels.items():
            if v == fa_label:
                step.found_action = k
                break
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.CLICK_IMAGE, ClickImageDialog)
