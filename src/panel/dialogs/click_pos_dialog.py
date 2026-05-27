"""ClickPosDialog — 点击坐标对话框。"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from src.core.action import ActionType
from src.core.step_types import BaseStep, ClickPosStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.widgets import themed_checkbutton, themed_frame, themed_label
from src.utils.i18n import t


class ClickPosDialog(StepDialogBase):
    """点击坐标配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        self._vars["pos_x"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.pos_x"),
            default=0, min_val=0, max_val=9999, increment=1, row=0,
        )
        self._vars["pos_y"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.pos_y"),
            default=0, min_val=0, max_val=9999, increment=1, row=1,
        )

        self._vars["clicks"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.click_count"),
            default=1, min_val=1, max_val=5, increment=1, row=2,
        )

        self._vars["hold_duration"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.hold_duration"),
            default=0.0, min_val=0.0, max_val=30.0, increment=0.1, row=3,
        )

        btn_frame = themed_frame(self._content_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, sticky="ew", pady=th.pad_xs)
        themed_label(btn_frame, text=t("dialog.label.mouse_button")).pack(side=tk.LEFT, padx=(0, th.pad_sm))
        self._vars["button"] = tk.StringVar(value="left")
        ttk.Combobox(
            btn_frame, textvariable=self._vars["button"],
            values=["left", "right", "middle"], state="readonly", width=8,
        ).pack(side=tk.LEFT)

        self._vars["use_coord_var"] = tk.BooleanVar(value=False)
        themed_checkbutton(
            self._content_frame, text=t("dialog.hint.use_coord_var"),
            variable=self._vars["use_coord_var"],
        ).grid(row=5, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)

        self._vars["coord_var_name"] = self._add_labeled_entry(
            self._content_frame, t("dialog.label.coord_var_name"),
            default="", row=6,
        )

        themed_label(
            self._content_frame, text=t("dialog.hint.coord_var_reference"),
            fg=th.text_muted,
        ).grid(row=7, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["pos_x"].set(action.pos_x)
        self._vars["pos_y"].set(action.pos_y)
        self._vars["clicks"].set(action.clicks)
        self._vars["hold_duration"].set(action.hold_duration)
        self._vars["button"].set(action.button or "left")
        self._vars["use_coord_var"].set(action.use_coord_var)
        coord_entry = self._vars["coord_var_name"]
        coord_entry.delete(0, tk.END)
        coord_entry.insert(0, action.coord_var_name or "")
        self._add_common_fields(self._content_frame, 8, action)

    def _get_result(self) -> BaseStep:
        step = self._action or ClickPosStep()
        step.pos_x = self._get_int("pos_x", min_val=0, max_val=9999, default=0)
        step.pos_y = self._get_int("pos_y", min_val=0, max_val=9999, default=0)
        step.clicks = self._get_int("clicks", min_val=1, max_val=5, default=1)
        step.hold_duration = self._get_float("hold_duration", min_val=0.0, max_val=30.0, default=0.0, decimal_places=2)
        step.button = self._vars["button"].get()
        step.use_coord_var = self._vars["use_coord_var"].get()
        step.coord_var_name = self._vars["coord_var_name"].get()
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.CLICK_POS, ClickPosDialog)
