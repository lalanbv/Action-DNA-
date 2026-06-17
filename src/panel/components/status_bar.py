"""StatusBar — 底部状态栏共享组件

多行自适应换行：每个信息段（状态圆点、文本、快捷键等）作为独立
grid cell，窗口变窄时自动换行到下一行。一行能放下则不换行。
"""

import tkinter as tk

from src.panel.canvas.theme import current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.widgets import themed_label


class StatusBar(tk.Frame):
    """底部状态栏：独立信息段 + 自适应多行换行。

    每个信息段通过 add_segment() 添加，成为独立的 grid cell。
    支持 set_left / set_center / set_right 兼容接口。
    """

    def __init__(self, parent: tk.Widget) -> None:
        th = current_theme()
        sm = scale_manager()
        super().__init__(parent, bg=th.toolbar_bg)

        # 内部分隔线（顶部 1px）
        self._top_line = tk.Frame(self, bg=th.border_default, height=sm.s(1))
        self._top_line.pack(fill=tk.X, side=tk.TOP)
        self._top_line.pack_propagate(False)

        # 内容容器
        self._content = tk.Frame(self, bg=th.toolbar_bg)
        self._content.pack(fill=tk.BOTH, expand=True)

        # 状态圆点
        self._dot_color = th.status_ready
        self._dot_canvas = tk.Canvas(
            self._content, width=sm.s(10), height=sm.s(10),
            bg=th.toolbar_bg, highlightthickness=0,
        )
        self._dot_oval = self._dot_canvas.create_oval(
            1, 1, sm.s(10) - 1, sm.s(10) - 1,
            fill=self._dot_color, outline="",
        )

        # 信息段列表: ("type", widget)
        self._segments: list[tuple[str, tk.Widget]] = []
        self._segment_labels: dict[str, tk.Label] = {}

        # 默认段: 左、中、右 + 圆点
        self._left = themed_label(self._content, style="small", bg=th.toolbar_bg)
        self._center = themed_label(self._content, style="small", bg=th.toolbar_bg)
        self._right = themed_label(self._content, style="small", bg=th.toolbar_bg)

        # 构建段列表
        self._segments.append(("dot", self._dot_canvas))
        self._segments.append(("label", self._left))
        self._segments.append(("center", self._center))
        self._segments.append(("label", self._right))

        self._segment_labels["left"] = self._left
        self._segment_labels["center"] = self._center
        self._segment_labels["right"] = self._right

        self._reflow_id: str | None = None
        self._is_reflowing: bool = False
        self._last_width: int = -1
        self._content.bind("<Configure>", self._on_configure)

    def add_segment(self, name: str, text: str = "") -> tk.Label:
        """添加一个独立信息段。"""
        th = current_theme()
        label = themed_label(self._content, text=text, style="small", bg=th.toolbar_bg)
        self._segments.append(("label", label))
        self._segment_labels[name] = label
        return label

    def insert_segment(self, index: int, name: str, text: str = "") -> tk.Label:
        """在指定位置插入一个独立信息段(控制显示顺序)。

        插入后触发重排。常用于把执行进度段排在圆点(index=1)之后。
        """
        th = current_theme()
        label = themed_label(self._content, text=text, style="small", bg=th.toolbar_bg)
        self._segments.insert(index, ("label", label))
        self._segment_labels[name] = label
        # 失效缓存宽度,触发下次 _perform_reflow 重排
        self._last_width = -1
        return label

    def set_segment(self, name: str, text: str) -> None:
        """更新指定信息段文本。"""
        if name in self._segment_labels:
            self._segment_labels[name].configure(text=text)

    # ── 兼容接口 ──

    def set_left(self, text: str) -> None:
        self._left.configure(text=text)

    def set_center(self, text: str) -> None:
        self._center.configure(text=text)

    def set_right(self, text: str) -> None:
        self._right.configure(text=text)

    def set_status_dot(self, state: str) -> None:
        """state: 'idle' | 'running' | 'paused' | 'error'"""
        th = current_theme()
        colors = {
            "idle": th.status_ready,
            "running": th.status_running,
            "paused": th.status_paused,
            "error": th.status_error,
        }
        self._dot_color = colors.get(state, th.status_ready)
        if self._dot_canvas and self._dot_canvas.winfo_exists():
            self._dot_canvas.itemconfig(self._dot_oval, fill=self._dot_color)

    def set_hotkey_info(self, hotkey_manager) -> None:
        """在右侧显示快捷键状态信息。"""
        if not hotkey_manager:
            return
        hm = hotkey_manager
        from src.utils.i18n import t
        if hm.keyboard_available:
            status = t("hotkey.available")
        else:
            status = t("hotkey.fallback")
        keys = [
            b.key_combination for b in hm.get_all_bindings() if b.enabled
        ]
        if keys:
            status += " | " + ", ".join(keys)
        self.set_right(status)

    # ── 自动换行 ──────────────────────────────────────────

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is not self._content or self._is_reflowing:
            return
        w = event.width
        if w == self._last_width:
            return
        self._last_width = w
        if self._reflow_id is not None:
            self.after_cancel(self._reflow_id)
        self._reflow_id = self.after(100, self._do_reflow)

    def _do_reflow(self) -> None:
        self._reflow_id = None
        if self._is_reflowing:
            return
        self._is_reflowing = True
        try:
            self._perform_reflow()
        finally:
            self._is_reflowing = False

    def _measure_width(self, widget: tk.Widget) -> int:
        w = widget.winfo_reqwidth()
        if w > 1:
            return w
        w = widget.winfo_width()
        if w > 1:
            return w
        return 20

    def _perform_reflow(self) -> None:
        self.update_idletasks()
        available = self._content.winfo_width()
        if available <= 1:
            return

        sm = scale_manager()
        pad = sm.s(6)

        # 测量
        widths: dict[int, int] = {}
        for _, widget in self._segments:
            if widget.winfo_exists():
                widths[id(widget)] = self._measure_width(widget) + pad

        # 全部移出 grid
        for _, widget in self._segments:
            if widget.winfo_exists():
                widget.grid_forget()

        # 清除 grid 配置
        for i in range(self._content.grid_size()[1]):
            self._content.grid_rowconfigure(i, weight=0)
        for j in range(self._content.grid_size()[0]):
            self._content.grid_columnconfigure(j, weight=0)

        # 计算 row plan
        row_plan: list[list[tuple[str, tk.Widget]]] = [[]]
        x = 0
        for item in self._segments:
            itype, widget = item
            if not widget.winfo_exists():
                continue
            w = widths.get(id(widget), 20)
            if x + w > available and x > 0:
                row_plan.append([item])
                x = w
            else:
                row_plan[-1].append(item)
                x += w

        # 放置
        for row_idx, row_items in enumerate(row_plan):
            for col_idx, (_, widget) in enumerate(row_items):
                widget.grid(row=row_idx, column=col_idx, sticky="w", padx=(0, sm.s(4)))
            self._content.grid_rowconfigure(row_idx, weight=0)

    # ── 主题 ──────────────────────────────────────────────

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.toolbar_bg)
        if hasattr(self, "_top_line") and self._top_line.winfo_exists():
            self._top_line.configure(bg=th.border_default)
        if hasattr(self, "_content") and self._content.winfo_exists():
            self._content.configure(bg=th.toolbar_bg)
        for lbl in self._segment_labels.values():
            if lbl.winfo_exists():
                lbl.configure(bg=th.toolbar_bg, fg=th.text_muted)
        if self._dot_canvas and self._dot_canvas.winfo_exists():
            self._dot_canvas.configure(bg=th.toolbar_bg)
            self._dot_canvas.itemconfig(self._dot_oval, fill=self._dot_color)
