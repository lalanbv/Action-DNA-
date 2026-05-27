"""StepPropertyPanel — 动作链步骤属性面板

选中步骤时显示：类型标签、描述、启用开关、备注。
操作按钮：上移/下移/编辑（打开对话框）/删除。
底部：循环设置（无限循环 checkbox + 循环次数 spinbox）。
"""

import tkinter as tk
from typing import Callable

from src.core.step_types import BaseStep
from src.panel.canvas.theme import current_theme, CanvasTheme
from src.panel.widgets import (
    themed_button,
    themed_checkbutton,
    themed_frame,
    themed_label,
    themed_separator,
    themed_spinbox,
)
from src.utils.i18n import t


class StepPropertyPanel(tk.Frame):
    """动作链步骤属性面板，包含属性显示区 + 循环设置区。"""

    def __init__(
        self,
        parent: tk.Widget,
        on_move_up: Callable,
        on_move_down: Callable,
        on_edit: Callable,
        on_delete: Callable,
        on_enabled_change: Callable | None = None,
        width: int = 220,
    ) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.panel_bg, width=width)
        self.pack_propagate(False)
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._on_enabled_change = on_enabled_change
        self._current_step: BaseStep | None = None
        self._build(th)

    def _build(self, th: CanvasTheme) -> None:
        # ── 属性区域（上半）──
        self._prop_header = themed_frame(self)
        self._prop_header.pack(fill=tk.X, padx=th.pad_sm, pady=(th.pad_sm, 0))
        themed_label(
            self._prop_header, text=t("chain.step_properties"),
            style="section", bg=th.panel_bg,
        ).pack(side=tk.LEFT)

        themed_separator(self).pack(fill=tk.X, padx=th.pad_sm, pady=th.pad_xs)

        self._prop_area = themed_frame(self)
        self._prop_area.pack(fill=tk.BOTH, expand=True)

        themed_label(
            self._prop_area,
            text=t("workflow.properties.empty"),
            style="body", bg=th.panel_bg, fg=th.text_muted,
        ).pack(pady=th.pad_xl)

        # ── 循环设置区域（底部固定）──
        themed_separator(self).pack(fill=tk.X, padx=th.pad_sm, pady=th.pad_xs)

        loop_frame = themed_frame(self)
        loop_frame.pack(fill=tk.X, padx=th.pad_sm, pady=(0, th.pad_sm))
        themed_label(
            loop_frame, text=t("chain.loop_label"), style="body", bg=th.panel_bg,
        ).pack(anchor="w")

        self.var_loop = tk.BooleanVar(value=True)
        themed_checkbutton(
            loop_frame, text=t("common.infinite_loop"), variable=self.var_loop,
        ).pack(anchor="w", padx=th.pad_xs)

        count_row = themed_frame(loop_frame)
        count_row.pack(fill=tk.X, padx=th.pad_xs)
        themed_label(
            count_row, text=t("common.loop_count_label"), style="small", bg=th.panel_bg,
        ).pack(side=tk.LEFT)
        self.var_loop_count = tk.IntVar(value=0)
        themed_spinbox(count_row, from_=0, to=9999, textvariable=self.var_loop_count, width=6).pack(
            side=tk.LEFT, padx=th.pad_xs,
        )

    def show_step(self, step: BaseStep, index: int, total: int) -> None:
        """显示选中步骤的属性。"""
        self._clear_props()
        th = current_theme()

        # 类型 + 序号
        type_row = themed_frame(self._prop_area)
        type_row.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

        badge = tk.Label(
            type_row, text=step.action_type.name, bg=th.accent_blue, fg=th.text_on_accent,
            font=th.font_small, padx=th.pad_xs, pady=2,
        )
        badge.pack(side=tk.LEFT)

        themed_label(
            type_row, text=f"#{index + 1} / {total}",
            style="small", bg=th.panel_bg, fg=th.text_muted,
        ).pack(side=tk.RIGHT)

        # 描述
        desc = step.describe() if hasattr(step, "describe") else ""
        if desc:
            themed_label(
                self._prop_area, text=desc, style="body", bg=th.panel_bg,
                wraplength=180, justify=tk.LEFT,
            ).pack(fill=tk.X, padx=th.pad_xs, pady=(0, th.pad_xs))

        # 启用
        self.var_enabled = tk.BooleanVar(value=step.enabled)
        themed_checkbutton(
            self._prop_area, text=t("common.enabled"), variable=self.var_enabled,
            command=lambda: self._apply_enabled(step),
        ).pack(anchor="w", padx=th.pad_xs)

        # 备注
        themed_label(
            self._prop_area, text=t("chain.comment_label"), style="small", bg=th.panel_bg,
        ).pack(anchor="w", padx=th.pad_xs, pady=(th.pad_sm, 0))
        self.var_comment = tk.StringVar(value=step.comment)
        comment_entry = tk.Entry(
            self._prop_area, textvariable=self.var_comment,
            bg=th.input_bg, fg=th.input_fg, insertbackground=th.text_primary,
            font=th.font_body,
        )
        comment_entry.pack(fill=tk.X, padx=th.pad_xs, pady=(0, th.pad_sm))
        comment_entry.bind("<FocusOut>", lambda e: self._apply_comment(step))

        # 操作按钮
        themed_separator(self._prop_area).pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

        btn_row = themed_frame(self._prop_area)
        btn_row.pack(fill=tk.X, padx=th.pad_xs)

        themed_button(btn_row, text="↑", command=self._on_move_up, width=3).pack(side=tk.LEFT, padx=1)
        themed_button(btn_row, text="↓", command=self._on_move_down, width=3).pack(side=tk.LEFT, padx=1)
        themed_button(btn_row, text=t("common.edit"), command=self._on_edit).pack(side=tk.LEFT, padx=1)
        themed_button(
            btn_row, text=t("common.delete"), command=self._on_delete, style="danger",
        ).pack(side=tk.LEFT, padx=1)

        self._current_step = step

    def show_empty(self) -> None:
        """清空属性区，显示空提示。"""
        self._clear_props()
        th = current_theme()
        themed_label(
            self._prop_area,
            text=t("workflow.properties.empty"),
            style="body", bg=th.panel_bg, fg=th.text_muted,
        ).pack(pady=th.pad_xl)

    def _clear_props(self) -> None:
        for child in self._prop_area.winfo_children():
            child.destroy()
        self._current_step = None

    def _apply_enabled(self, step: BaseStep) -> None:
        step.enabled = self.var_enabled.get()
        if self._on_enabled_change:
            self._on_enabled_change()

    def _apply_comment(self, step: BaseStep) -> None:
        step.comment = self.var_comment.get()

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.panel_bg)
        self._prop_header.configure(bg=th.panel_bg)
        self._prop_area.configure(bg=th.panel_bg)
