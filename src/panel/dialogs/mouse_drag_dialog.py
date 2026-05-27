"""MouseDragDialog — 鼠标拖拽对话框（从起点拖到终点）。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, MouseDragStep
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.widgets import themed_button, themed_frame, themed_label
from src.utils.i18n import t


class MouseDragDialog(StepDialogBase):
    """鼠标拖拽配置对话框。从起点按住鼠标键拖到终点。"""

    def _build_content(self) -> None:
        th = current_theme()

        themed_label(
            self._content_frame, text=t("dialog.label.start_pos"),
            font=th.font_small,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg, pady=(th.pad_md, 0))

        self._vars["start_x"] = self._add_labeled_spinbox(
            self._content_frame, "X",
            default=0, min_val=0, max_val=9999, increment=10, row=1,
        )
        self._vars["start_y"] = self._add_labeled_spinbox(
            self._content_frame, "Y",
            default=0, min_val=0, max_val=9999, increment=10, row=2,
        )

        themed_label(
            self._content_frame, text=t("dialog.label.end_pos"),
            font=th.font_small,
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg, pady=(th.pad_md, 0))

        self._vars["end_x"] = self._add_labeled_spinbox(
            self._content_frame, "X",
            default=0, min_val=0, max_val=9999, increment=10, row=4,
        )
        self._vars["end_y"] = self._add_labeled_spinbox(
            self._content_frame, "Y",
            default=0, min_val=0, max_val=9999, increment=10, row=5,
        )

        button_row = 6
        themed_label(
            self._content_frame, text=t("dialog.label.drag_button"),
        ).grid(row=button_row, column=0, sticky=tk.W, padx=th.pad_lg, pady=th.pad_xs)
        self._vars["button"] = tk.StringVar(value="left")
        btn_frame = themed_frame(self._content_frame)
        btn_frame.grid(row=button_row, column=1, sticky=tk.EW, padx=th.pad_lg, pady=th.pad_xs)
        sm = scale_manager()
        for text_key, val in [
            ("dialog.btn.left", "left"),
            ("dialog.btn.middle", "middle"),
            ("dialog.btn.right", "right"),
        ]:
            tk.Radiobutton(
                btn_frame, text=t(text_key), variable=self._vars["button"],
                value=val, bg=th.bg_surface, fg=th.text_primary,
                selectcolor=th.bg_surface_dark, activebackground=th.bg_surface,
                font=(th.font_family, sm.s(9)),
            ).pack(side=tk.LEFT, padx=2)

        self._vars["duration"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.drag_duration"),
            default=0.5, min_val=0.1, max_val=5.0, increment=0.1, row=7,
        )

        test_f = themed_frame(self._content_frame)
        test_f.grid(row=8, column=0, columnspan=2, pady=th.pad_sm)
        themed_button(test_f, text=t("dialog.btn.test_drag"), command=self._do_test).pack()

        self._test_row = 9

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["start_x"].set(action.start_x)
        self._vars["start_y"].set(action.start_y)
        self._vars["end_x"].set(action.end_x)
        self._vars["end_y"].set(action.end_y)
        self._vars["button"].set(action.button)
        self._vars["duration"].set(action.duration)

        self._add_common_fields(self._content_frame, self._test_row, action)

    def _get_result(self) -> BaseStep:
        step = self._action or MouseDragStep()
        step.start_x = self._get_int("start_x", min_val=0, default=0)
        step.start_y = self._get_int("start_y", min_val=0, default=0)
        step.end_x = self._get_int("end_x", min_val=0, default=0)
        step.end_y = self._get_int("end_y", min_val=0, default=0)
        step.button = self._vars["button"].get()
        step.duration = self._get_float("duration", min_val=0.1, max_val=60.0, default=0.5)
        self._apply_common(step)
        return step

    def _do_test(self) -> None:
        sx = self._get_int("start_x", min_val=0, default=0)
        sy = self._get_int("start_y", min_val=0, default=0)
        ex = self._get_int("end_x", min_val=0, default=0)
        ey = self._get_int("end_y", min_val=0, default=0)
        dur = self._get_float("duration", min_val=0.1, max_val=60.0, default=0.5)

        from src.core.input import InputController
        inp = InputController()
        self.withdraw()
        self.after(300, lambda: (
            inp.drag_to(sx, sy, ex, ey, duration=dur),
            self.deiconify(),
        ))


DialogRegistry.register(ActionType.MOUSE_DRAG, MouseDragDialog)
