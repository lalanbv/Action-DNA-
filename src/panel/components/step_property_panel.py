"""StepPropertyPanel — 动作链步骤属性面板（tk）

选中步骤时显示：类型标签、描述、移动到序号、关键参数、全部字段（折叠）、启用、备注。
操作按钮：上移/下移/复制/编辑（打开对话框）/删除。
属性区域超出时自动显示滚动条。规格与 Qt 端 ``action_chain_props_mixin`` 一致。
"""

import tkinter as tk
from typing import Callable

from src.core.step_types import BaseStep
from src.panel.canvas.scale import ScrollableFrame
from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.components.step_param_view import iter_all_fields, key_field_rows
from src.panel.widgets import (
    themed_button,
    themed_checkbutton,
    themed_frame,
    themed_label,
    themed_separator,
)
from src.utils.i18n import t


class StepPropertyPanel(tk.Frame):
    """动作链步骤属性面板，包含属性显示区。"""

    def __init__(
        self,
        parent: tk.Widget,
        on_move_up: Callable,
        on_move_down: Callable,
        on_edit: Callable,
        on_delete: Callable,
        on_enabled_change: Callable | None = None,
        on_duplicate: Callable | None = None,
        on_move_to_index: Callable[[int, int], None] | None = None,
        width: int | None = None,
    ) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.panel_bg)
        self.pack(fill=tk.BOTH, expand=True)
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down
        self._on_edit = on_edit
        self._on_delete = on_delete
        self._on_enabled_change = on_enabled_change
        self._on_duplicate = on_duplicate
        self._on_move_to_index = on_move_to_index
        self._current_step: BaseStep | None = None
        self._scroll: ScrollableFrame | None = None
        self._build(th)

    def _build(self, th: CanvasTheme) -> None:
        self._prop_header = themed_frame(self)
        self._prop_header.pack(fill=tk.X, padx=th.pad_sm, pady=(th.pad_sm, 0))
        themed_label(
            self._prop_header, text=t("chain.step_properties"),
            style="section", bg=th.panel_bg,
        ).pack(side=tk.LEFT)

        themed_separator(self).pack(fill=tk.X, padx=th.pad_sm, pady=th.pad_xs)

        self._scroll = ScrollableFrame(self, bg=th.panel_bg)
        self._scroll.pack(fill=tk.BOTH, expand=True)
        self._prop_area = self._scroll.inner

        themed_label(
            self._prop_area,
            text=t("workflow.properties.empty"),
            style="body", bg=th.panel_bg, fg=th.text_muted,
        ).pack(pady=th.pad_xl)

    def show_step(self, step: BaseStep, index: int, total: int) -> None:
        """显示选中步骤的属性（与 Qt 详情面板同规格）。"""
        self._clear_props()
        th = current_theme()
        self._current_step = step

        # 类型 + 序号
        type_row = themed_frame(self._prop_area)
        type_row.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)
        badge = tk.Label(
            type_row, text=step.action_type.name, bg=th.accent_blue,
            fg=th.text_on_accent, font=th.font_small, padx=th.pad_xs, pady=2,
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

        # 移动到指定序号（多于 1 步时）
        if total > 1:
            self._build_move_to(index, total, th)

        # 关键参数表
        rows = key_field_rows(step)
        if rows:
            themed_label(
                self._prop_area, text=t("chain.detail.key_fields"),
                style="small", bg=th.panel_bg, fg=th.text_muted,
            ).pack(anchor="w", padx=th.pad_xs, pady=(th.pad_xs, 0))
            for label_text, value_text in rows:
                row = themed_frame(self._prop_area)
                row.pack(fill=tk.X, padx=th.pad_xs)
                themed_label(
                    row, text=label_text, style="small",
                    bg=th.panel_bg, fg=th.text_muted, width=12,
                ).pack(side=tk.LEFT)
                themed_label(
                    row, text=value_text, style="small",
                    bg=th.panel_bg, fg=th.text_primary, wraplength=120,
                ).pack(side=tk.LEFT, padx=(th.pad_xs, 0))

        # 全部字段（默认折叠）
        all_pairs = list(iter_all_fields(step))
        if all_pairs:
            self._build_collapsible(all_pairs, th)

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

        # 操作按钮：↑ ↓ 复制 编辑 删除
        themed_separator(self._prop_area).pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)
        btn_row = themed_frame(self._prop_area)
        btn_row.pack(fill=tk.X, padx=th.pad_xs)
        themed_button(btn_row, text="↑", command=self._on_move_up, width=3).pack(side=tk.LEFT, padx=1)
        themed_button(btn_row, text="↓", command=self._on_move_down, width=3).pack(side=tk.LEFT, padx=1)
        themed_button(btn_row, text=t("common.duplicate"), command=self._on_duplicate).pack(side=tk.LEFT, padx=1)
        themed_button(btn_row, text=t("common.edit"), command=self._on_edit).pack(side=tk.LEFT, padx=1)
        themed_button(
            btn_row, text=t("common.delete"), command=self._on_delete, style="danger",
        ).pack(side=tk.LEFT, padx=1)

    def _build_move_to(self, index: int, total: int, th: CanvasTheme) -> None:
        """「移动到序号」输入 + 确定按钮。"""
        self._move_source = index  # 渲染时捕获 source，避免回调时选中已变
        row = themed_frame(self._prop_area)
        row.pack(fill=tk.X, padx=th.pad_xs, pady=(0, th.pad_xs))
        themed_label(
            row, text=t("chain.detail.move_to"), style="small",
            bg=th.panel_bg, fg=th.text_muted,
        ).pack(side=tk.LEFT)
        self._move_var = tk.StringVar(value=str(index + 1))
        entry = tk.Entry(
            row, textvariable=self._move_var, width=4,
            bg=th.input_bg, fg=th.input_fg, insertbackground=th.text_primary,
            font=th.font_body,
        )
        entry.pack(side=tk.LEFT, padx=th.pad_xs)
        themed_button(
            row, text=t("chain.detail.move_confirm"), command=self._do_move_to,
        ).pack(side=tk.LEFT)

    def _do_move_to(self) -> None:
        """读取序号输入（1-based → 0-based）并以捕获的 source 回调。"""
        if self._on_move_to_index is None:
            return
        try:
            target = int(self._move_var.get()) - 1
        except (ValueError, AttributeError):
            return
        self._on_move_to_index(self._move_source, target)

    def _build_collapsible(self, pairs: list[tuple[str, str]], th: CanvasTheme) -> None:
        """「全部字段」折叠区：默认收起，点击标题切换。"""
        n = len(pairs)
        title_text = f"{t('chain.detail.all_fields')} ({n})"

        outer = themed_frame(self._prop_area)
        outer.pack(fill=tk.X, padx=th.pad_xs, pady=(0, th.pad_xs))

        body = themed_frame(outer)
        for fname, fval in pairs:
            r = themed_frame(body)
            r.pack(fill=tk.X)
            themed_label(
                r, text=fname, style="small", bg=th.panel_bg, fg=th.text_muted, width=16,
            ).pack(side=tk.LEFT)
            themed_label(
                r, text=fval, style="small", bg=th.panel_bg, fg=th.text_primary,
            ).pack(side=tk.LEFT, padx=(th.pad_xs, 0))

        state = {"expanded": False}

        def toggle() -> None:
            if state["expanded"]:
                body.pack_forget()
                state["expanded"] = False
                btn.config(text="▷ " + title_text)
            else:
                body.pack(fill=tk.X, padx=th.pad_xs, pady=(th.pad_xs, 0))
                state["expanded"] = True
                btn.config(text="▸ " + title_text)

        btn = themed_button(outer, text="▷ " + title_text, command=toggle)
        btn.pack(anchor="w")

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
        if self._scroll is not None:
            self._scroll.set_bg(th.panel_bg)
        from src.panel.widgets import cascade_theme
        cascade_theme(self)
