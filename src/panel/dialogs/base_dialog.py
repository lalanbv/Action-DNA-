"""StepDialogBase — 步骤配置对话框抽象基类。"""

from __future__ import annotations

import tkinter as tk
from abc import ABC, abstractmethod
from tkinter import messagebox
from typing import Callable

from src.core.step_types import BaseStep
from src.panel.canvas.scale import scale_manager, ScrollableFrame
from src.panel.canvas.theme import current_theme
from src.panel.canvas.theme.theme_manager import ThemeCallbackMixin
from src.panel.dialogs.key_picker import SyncedVar
from src.utils.float_utils import safe_float, safe_int
from src.panel.widgets import (
    apply_to_toplevel,
    themed_button,
    themed_checkbutton,
    themed_entry,
    themed_frame,
    themed_label,
    themed_spinbox,
)
from src.utils.i18n import t


class StepDialogBase(tk.Toplevel, ABC, ThemeCallbackMixin):
    """步骤配置对话框抽象基类。

    子类实现 _build_content()、_get_result()，可选覆盖
    _validate_inputs() 和 _populate_fields()。

    主题（B4 修复）：打开期间若用户切换深/浅色，对话框通过
    :class:`ThemeCallbackMixin` 注册回调，重应用当前主题
    (:func:`apply_to_toplevel`)；关闭时注销回调防泄漏。
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        action: BaseStep | None = None,
        callback: Callable[[BaseStep], None] | None = None,
        width: int = 520,
        height: int = 520,
    ) -> None:
        super().__init__(parent)
        th = current_theme()
        self.title(title)
        self._action = action
        self._callback = callback
        self._vars: dict[str, tk.Variable] = {}
        self.configure(bg=th.dialog_bg)

        sm = scale_manager()
        dw, dh = sm.dialog_size(parent, 0.55, 0.65, max_w=sm.s(width), max_h=sm.s(height))
        self.geometry(f"{dw}x{dh}")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self._center_on_parent(parent)

        self._scroll_frame = ScrollableFrame(self, bg=th.dialog_bg)
        self._scroll_frame.pack(fill=tk.BOTH, expand=True)
        self._content_frame = self._scroll_frame.inner

        self._build_content()

        btn_frame = themed_frame(self)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=th.pad_md, pady=(0, th.pad_sm))
        themed_button(
            btn_frame, text=t("common.ok"), command=self._on_confirm, style="primary",
        ).pack(side=tk.RIGHT, padx=th.pad_xs)
        themed_button(
            btn_frame, text=t("common.cancel"), command=self.destroy,
        ).pack(side=tk.RIGHT, padx=th.pad_xs)

        if action:
            self._populate_fields(action)

        # B4：注册主题回调 —— 打开期间切换深/浅色时重应用主题到本 Toplevel。
        self._init_theme_guard(self._reapply_theme)

    def _reapply_theme(self) -> None:
        """主题切换回调：把当前主题重新应用到本对话框及其子控件树。"""
        if self.winfo_exists():
            apply_to_toplevel(self)

    def destroy(self) -> None:
        """注销主题回调后再销毁（B4：防泄漏 + 防销毁后回调报错）。"""
        self._unregister_theme_callback()
        super().destroy()

    @abstractmethod
    def _build_content(self) -> None:
        """构建对话框内容区域。"""

    @abstractmethod
    def _get_result(self) -> BaseStep:
        """从字段提取配置结果。"""

    def _validate_inputs(self) -> list[str]:
        """验证输入，返回错误列表。"""
        return []

    def _populate_fields(self, action: BaseStep) -> None:
        """用现有配置填充字段（编辑模式）。"""

    def _on_confirm(self) -> None:
        errors = self._validate_inputs()
        if errors:
            messagebox.showerror(
                t("dialog.validation.title"),
                "\n".join(f"  - {e}" for e in errors),
                parent=self,
            )
            return
        result = self._get_result()
        if self._callback:
            try:
                self._callback(result)
            except RuntimeError as exc:
                messagebox.showerror(
                    t("dialog.validation.title"),
                    str(exc),
                    parent=self,
                )
                return
        self.destroy()

    def _center_on_parent(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")

    def _add_labeled_entry(
        self, parent: tk.Widget, label: str, default: str = "", row: int = 0,
    ) -> tk.Entry:
        sm = scale_manager()
        themed_label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=sm.s(3))
        entry = themed_entry(parent)
        entry.insert(0, default)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=(sm.s(10), 0), pady=sm.s(3))
        parent.columnconfigure(1, weight=1)
        return entry

    def _add_labeled_spinbox(
        self,
        parent: tk.Widget,
        label: str,
        default: float = 0.0,
        min_val: float = 0.0,
        max_val: float = 9999.0,
        increment: float = 0.1,
        row: int = 0,
    ) -> SyncedVar:
        sm = scale_manager()
        themed_label(parent, text=label).grid(row=row, column=0, sticky=tk.W, pady=sm.s(3))
        var = tk.StringVar(value=str(default))
        spinbox = themed_spinbox(
            parent, from_=min_val, to=max_val, increment=increment,
            textvariable=var,
        )
        spinbox.grid(row=row, column=1, sticky=tk.EW, padx=(sm.s(10), 0), pady=sm.s(3))
        parent.columnconfigure(1, weight=1)

        synced = SyncedVar(var, spinbox, as_float=True)

        def _clamp_on_leave(_event):
            clamped = safe_float(synced.get(), min_val=min_val, max_val=max_val, default=default, decimal_places=4)
            current = var.get()
            if current != str(clamped):
                var.set(str(clamped))
        spinbox.bind("<FocusOut>", _clamp_on_leave)
        return synced

    def _add_common_fields(self, parent: tk.Widget, row: int, step: BaseStep) -> int:
        """添加注释和启用步骤通用字段，返回下一行行号。"""
        th = current_theme()
        v_comment = tk.StringVar(value=step.comment)
        themed_label(parent, text=t("dialog.label.comment")).grid(
            row=row, column=0, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs,
        )
        themed_entry(parent, textvariable=v_comment, width=30).grid(
            row=row, column=1, sticky=tk.EW, padx=th.pad_sm,
        )
        self._vars["comment"] = v_comment
        row += 1

        v_enabled = tk.BooleanVar(value=step.enabled)
        themed_checkbutton(
            parent, text=t("dialog.label.enable_step"), variable=v_enabled,
        ).grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=th.pad_sm, pady=th.pad_xs)
        self._vars["enabled"] = v_enabled
        row += 1
        return row

    def _apply_common(self, step: BaseStep) -> None:
        step.comment = self._vars["comment"].get()
        step.enabled = self._vars["enabled"].get()

    def _get_float(
        self,
        name: str,
        *,
        min_val: float | None = None,
        max_val: float | None = None,
        default: float = 0.0,
        decimal_places: int | None = None,
    ) -> float:
        """从 self._vars[name] 安全读取浮点值（带钳制和舍入）。"""
        return safe_float(
            self._vars[name].get(),
            min_val=min_val, max_val=max_val,
            default=default, decimal_places=decimal_places,
        )

    def _get_int(
        self,
        name: str,
        *,
        min_val: int | None = None,
        max_val: int | None = None,
        default: int = 0,
    ) -> int:
        """从 self._vars[name] 安全读取整数值（带钳制）。"""
        return safe_int(
            self._vars[name].get(),
            min_val=min_val, max_val=max_val, default=default,
        )
