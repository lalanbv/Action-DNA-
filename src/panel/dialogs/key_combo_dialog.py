"""KeyComboDialog — 组合按键对话框。"""

from __future__ import annotations

import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, KeyComboStep
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.dialogs.key_picker import SyncedVar, make_key_picker
from src.panel.widgets import themed_dropdown, themed_frame, themed_label, themed_spinbox
from src.utils.i18n import t

_COMBO_MODE_OPTIONS = [
    ("hold_tap", "common.mode.hold_tap"),
    ("sequence", "common.mode.sequence"),
    ("all_hold", "common.mode.all_hold"),
]


class KeyComboDialog(StepDialogBase):
    """组合按键配置对话框。"""

    def _build_content(self) -> None:
        th = current_theme()
        themed_label(
            self._content_frame, text=t("dialog.label.combo_keys"),
        ).grid(row=0, column=0, sticky=tk.NW, padx=th.pad_sm, pady=th.pad_xs)

        key_frame = themed_frame(self._content_frame)
        key_frame.grid(row=0, column=1, sticky=tk.EW, padx=th.pad_sm)
        self._vars["combo_keys"] = make_key_picker(
            key_frame, initial_value="", append_mode=True,
        )

        themed_label(
            self._content_frame, text=t("dialog.hint.combo_key_order"),
            fg=th.text_muted,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

        themed_label(
            self._content_frame, text=t("dialog.label.combo_mode"),
        ).grid(row=2, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)

        self._mode_dropdown = themed_dropdown(
            self._content_frame,
            options=_COMBO_MODE_OPTIONS,
            value="hold_tap", state="readonly", width=16,
            command=self._on_mode_changed,
        )
        self._mode_dropdown.grid(row=2, column=1, sticky=tk.W, padx=th.pad_sm)

        # hold_duration 仅 all_hold 模式显示
        self._hold_frame = themed_frame(self._content_frame)
        self._hold_frame.grid(row=3, column=0, columnspan=2, sticky=tk.EW)
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

        self._on_mode_changed()

        self._common_row = 4

    def _on_mode_changed(self, val: str = "") -> None:
        if val == "all_hold":
            self._hold_frame.grid()
        else:
            self._hold_frame.grid_remove()

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["combo_keys"].set(action.combo_keys)
        self._mode_dropdown.set_value(action.combo_mode)
        self._vars["hold_duration"].set(action.hold_duration)
        self._on_mode_changed(action.combo_mode)
        self._add_common_fields(self._content_frame, self._common_row, action)

    def _get_result(self) -> BaseStep:
        step = self._action or KeyComboStep()
        step.combo_keys = self._vars["combo_keys"].get()
        step.combo_mode = self._mode_dropdown.get_value()
        step.hold_duration = self._get_float("hold_duration", min_val=0.0, max_val=60.0, default=0.5)
        self._apply_common(step)
        return step


DialogRegistry.register(ActionType.KEY_COMBO, KeyComboDialog)
