"""LoopControls — 循环控制组件

提供三种模式：单次执行 / 无限循环 / 指定次数。
作为工具栏嵌入组件，与 ProfileBar、RegionBar、RunControls 平级。
"""

import tkinter as tk
from typing import TYPE_CHECKING, Callable

from src.panel.canvas.theme import current_theme
from src.panel.widgets import themed_dropdown, themed_frame, themed_label, themed_spinbox
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.panel.components.dna_dropdown import DNADropdown
    from src.panel.components.toolbar import ToolbarFrame


class LoopControls(tk.Frame):
    """循环控制组件 — 模式下拉 + 可选次数输入。

    三种模式:
      - MODE_SINGLE:  单次执行 (loop=False, loop_count=1)
      - MODE_INFINITE: 无限循环 (loop=True,  loop_count=0)
      - MODE_FINITE:   指定次数 (loop=True,  loop_count=N)
    """

    MODE_SINGLE = "single"
    MODE_INFINITE = "infinite"
    MODE_FINITE = "finite"

    _MODE_OPTIONS = [
        (MODE_SINGLE, "common.loop.single"),
        (MODE_INFINITE, "common.loop.infinite"),
        (MODE_FINITE, "common.loop.finite"),
    ]

    def __init__(
        self,
        parent: tk.Widget,
        on_change: Callable | None = None,
        **kw: object,
    ) -> None:
        th = current_theme()
        kw.setdefault("bg", th.toolbar_bg)
        super().__init__(parent, **kw)
        self._on_change = on_change

        self._mode_var = tk.StringVar(value=self.MODE_INFINITE)
        self._count_var = tk.IntVar(value=1)
        self._count_trace = self._count_var.trace_add("write", self._on_count_changed)
        self.bind("<Destroy>", self._on_destroy)

        # 模式下拉
        self._dropdown: DNADropdown = themed_dropdown(
            self,
            options=self._MODE_OPTIONS,
            value=self.MODE_INFINITE,
            state="readonly",
            width=10,
            command=self._on_mode_changed,
        )
        self._dropdown.pack(side=tk.LEFT)

        # 次数输入（默认隐藏，仅在 FINITE 模式显示）
        self._count_container = themed_frame(self)
        self._count_spinbox = themed_spinbox(
            self._count_container,
            from_=1, to=9999,
            textvariable=self._count_var,
            width=5,
        )
        self._count_spinbox.pack(side=tk.LEFT, padx=(4, 0))
        self._times_label = themed_label(
            self._count_container,
            text=t("common.loop.times"),
            style="small",
        )
        self._times_label.pack(side=tk.LEFT, padx=(2, 0))

        # 初始 min_width（toolbar 通过此属性准确测量复合组件宽度）
        self.min_width: int = 0
        self.after_idle(self._update_min_width)

    # ── 内部回调 ──────────────────────────────────────────

    def _update_min_width(self) -> None:
        """根据当前模式计算并设置 min_width，供 toolbar 准确测量。"""
        self.update_idletasks()
        dw = self._dropdown.winfo_reqwidth() if self._dropdown.winfo_exists() else 90
        mode = self._mode_var.get()
        cw = 0
        if mode == self.MODE_FINITE and self._count_container.winfo_exists():
            cw = self._count_container.winfo_reqwidth() + 4  # padx
        self.min_width = dw + cw + 2

    def _on_mode_changed(self, mode: str) -> None:
        self._mode_var.set(mode)
        if mode == self.MODE_FINITE:
            self._count_container.pack(side=tk.LEFT, padx=(4, 0))
        else:
            self._count_container.pack_forget()
        self._update_min_width()
        self._notify_toolbar()
        if self._on_change:
            self._on_change()

    def _on_count_changed(self, *_: object) -> None:
        if self._mode_var.get() == self.MODE_FINITE and self._on_change:
            self._on_change()

    def _on_destroy(self, _event: object = None) -> None:
        if self._count_trace:
            try:
                self._count_var.trace_remove("write", self._count_trace)
            except (tk.TclError, ValueError):
                pass
            self._count_trace = None

    def _notify_toolbar(self) -> None:
        """尺寸变化时通知工具栏重新布局。"""
        widget: tk.Widget | None = self.master
        while widget:
            if hasattr(widget, 'request_reflow'):
                widget.request_reflow()
                return
            widget = widget.master

    # ── 公共接口 ──────────────────────────────────────────

    @property
    def loop(self) -> bool:
        return self._mode_var.get() != self.MODE_SINGLE

    @property
    def loop_count(self) -> int:
        mode = self._mode_var.get()
        if mode == self.MODE_SINGLE:
            return 1
        elif mode == self.MODE_INFINITE:
            return 0
        else:
            try:
                return max(1, self._count_var.get())
            except tk.TclError:
                return 1

    def set_from_model(self, loop: bool, loop_count: int) -> None:
        """从数据模型恢复 UI 状态。"""
        if not loop:
            self._mode_var.set(self.MODE_SINGLE)
            self._count_container.pack_forget()
        elif loop_count == 0:
            self._mode_var.set(self.MODE_INFINITE)
            self._count_container.pack_forget()
        else:
            self._mode_var.set(self.MODE_FINITE)
            self._count_var.set(loop_count)
            self._count_container.pack(side=tk.LEFT, padx=(4, 0))
        self._dropdown.set_value(self._mode_var.get())
        self._update_min_width()
        self._notify_toolbar()

    def add_to_toolbar(self, toolbar: ToolbarFrame, section: str) -> None:
        toolbar.add_widget(section, self)

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.toolbar_bg)
        self._count_container.configure(bg=th.toolbar_bg)
        self._times_label.configure(bg=th.toolbar_bg)
        from src.panel.widgets import cascade_theme
        cascade_theme(self)
