"""MouseMoveDialog — 鼠标移动/拖拽对话框（含路径预览）。"""

from __future__ import annotations

import math
import tkinter as tk

from src.core.action import ActionType
from src.core.step_types import BaseStep, MouseMoveStep
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme
from src.panel.dialogs.base_dialog import StepDialogBase
from src.panel.dialogs.dialog_registry import DialogRegistry
from src.panel.widgets import themed_button, themed_frame, themed_label
from src.utils.i18n import t


class MouseMoveDialog(StepDialogBase):
    """鼠标移动/拖拽配置对话框。支持无按键移动和按住按键拖拽。"""

    def _build_content(self) -> None:
        self._vars["offset_x"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.offset_x"),
            default=0, min_val=-3000, max_val=3000, increment=10, row=0,
        )
        th = current_theme()
        themed_label(
            self._content_frame, text="  " + t("dialog.hint.horizontal_direction"),
            fg=th.text_muted,
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

        self._vars["offset_y"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.offset_y"),
            default=0, min_val=-3000, max_val=3000, increment=10, row=2,
        )
        themed_label(
            self._content_frame, text="  " + t("dialog.hint.vertical_direction"),
            fg=th.text_muted,
        ).grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

        self._vars["move_speed"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.move_speed"),
            default=0.5, min_val=0.1, max_val=3.0, increment=0.05, row=4,
        )

        self._vars["curve_amount"] = self._add_labeled_spinbox(
            self._content_frame, t("dialog.label.curve_amount"),
            default=0.0, min_val=0.0, max_val=1.0, increment=0.05, row=5,
        )
        themed_label(
            self._content_frame, text="  " + t("dialog.hint.curve_description"),
            fg=th.text_muted,
        ).grid(row=6, column=0, columnspan=2, sticky=tk.W, padx=th.pad_lg)

        button_row = 7
        themed_label(
            self._content_frame, text=t("dialog.label.hold_button"),
        ).grid(row=button_row, column=0, sticky=tk.W, padx=th.pad_lg, pady=th.pad_xs)
        self._vars["button"] = tk.StringVar(value="")
        btn_frame = themed_frame(self._content_frame)
        btn_frame.grid(row=button_row, column=1, sticky=tk.EW, padx=th.pad_lg, pady=th.pad_xs)
        sm = scale_manager()
        for text_key, val in [
            ("dialog.btn.none", ""),
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

        self._path_row = 8

        test_f = themed_frame(self._content_frame)
        test_f.grid(row=9, column=0, columnspan=2, pady=th.pad_sm)
        themed_button(test_f, text=t("dialog.btn.test_move"), command=self._do_test).pack()

        self._test_row = 10

    def _populate_fields(self, action: BaseStep) -> None:
        self._vars["offset_x"].set(action.offset_x)
        self._vars["offset_y"].set(action.offset_y)
        self._vars["move_speed"].set(action.move_speed)
        self._vars["curve_amount"].set(action.curve_amount)
        self._vars["button"].set(action.button)

        if action.path_points:
            self._build_path_preview(action.path_points)

        self._add_common_fields(self._content_frame, self._test_row, action)

    def _build_path_preview(
        self, points: list[tuple[int, int, float]],
    ) -> None:
        th = current_theme()
        canvas_w, canvas_h = 280, 160

        frame = themed_frame(self._content_frame)
        frame.grid(
            row=self._path_row, column=0, columnspan=2,
            sticky=tk.EW, padx=th.pad_md, pady=th.pad_xs,
        )

        total_dist = 0.0
        for i in range(1, len(points)):
            total_dist += math.hypot(
                points[i][0] - points[i - 1][0],
                points[i][1] - points[i - 1][1],
            )
        duration = points[-1][2] if points else 0
        avg_speed = total_dist / max(duration, 0.001)

        stats = (
            f"路径: {len(points)} 点 | "
            f"距离: {total_dist:.0f}px | "
            f"时长: {duration:.2f}s | "
            f"均速: {avg_speed:.0f}px/s"
        )
        themed_label(frame, text=stats, fg=th.text_muted).pack(anchor="w")

        canvas = tk.Canvas(
            frame, width=canvas_w, height=canvas_h,
            bg=th.bg_surface, highlightthickness=1,
            highlightbackground=th.border_default,
        )
        canvas.pack(pady=th.pad_xs)

        if not points:
            return

        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        range_x = max(max_x - min_x, 1)
        range_y = max(max_y - min_y, 1)

        scale = min((canvas_w - 20) / range_x, (canvas_h - 20) / range_y)

        def to_canvas(px: int, py: int) -> tuple[float, float]:
            return 10 + (px - min_x) * scale, 10 + (py - min_y) * scale

        th = current_theme()
        line_color = th.accent_mauve if self._vars["button"].get() else th.accent_teal
        for i in range(1, len(points)):
            x1, y1 = to_canvas(points[i - 1][0], points[i - 1][1])
            x2, y2 = to_canvas(points[i][0], points[i][1])
            canvas.create_line(x1, y1, x2, y2, fill=line_color, width=2)

        sx, sy = to_canvas(points[0][0], points[0][1])
        canvas.create_oval(sx - 4, sy - 4, sx + 4, sy + 4, fill=th.accent_green, outline="")

        ex, ey = to_canvas(points[-1][0], points[-1][1])
        canvas.create_oval(ex - 4, ey - 4, ex + 4, ey + 4, fill=th.accent_red, outline="")

    def _get_result(self) -> BaseStep:
        step = self._action or MouseMoveStep()
        step.offset_x = self._get_int("offset_x", default=0)
        step.offset_y = self._get_int("offset_y", default=0)
        step.move_speed = self._get_float("move_speed", min_val=0.0, default=0.5)
        step.curve_amount = self._get_float("curve_amount", min_val=0.0, max_val=1.0, default=0.0)
        step.button = self._vars["button"].get()
        self._apply_common(step)
        return step

    def _do_test(self) -> None:
        action = self._action
        if action and action.path_points:
            from src.core.input import InputController
            inp = InputController()
            time_scale = self._get_float("move_speed", min_val=0.0, default=0.5) / max(
                action.recorded_duration, 0.01,
            )
            self.withdraw()
            self.after(300, lambda: (
                inp.replay_path(action.path_points, time_scale=time_scale),
                self.deiconify(),
            ))
            return

        dx = self._get_int("offset_x", default=0)
        dy = self._get_int("offset_y", default=0)
        spd = self._get_float("move_speed", min_val=0.0, default=0.5)
        curve = self._get_float("curve_amount", min_val=0.0, max_val=1.0, default=0.0)
        if dx == 0 and dy == 0:
            return
        from src.core.input import InputController
        inp = InputController()
        self.withdraw()
        self.after(300, lambda: (
            inp.move_relative_bezier(dx, dy, duration=spd, curve_intensity=curve),
            self.deiconify(),
        ))


DialogRegistry.register(ActionType.MOUSE_MOVE, MouseMoveDialog)
