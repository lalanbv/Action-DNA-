"""ToolbarFrame + RunControls — 自适应换行工具栏

设计原则 (参考 VS Code / Apple HIG):
- 扁平无边框按钮, 悬停显示背景
- 统一图标+文本, 最小点击区域 36x28
- 语义分组 + 竖线分隔
- 每个元素独立排序、独立大小、独立自适应
- 自动换行: 窗口变窄时元素流到下一行

布局策略:
  使用 grid 放置所有元素。为了避免 grid 列宽跨行共享，
  每行占据独立的列区间：row_idx * max_cols + col_in_row。
  不同行的元素使用不同的列号，互不干扰。
"""

import tkinter as tk
from typing import Callable

from src.panel.canvas.theme import current_theme
from src.panel.canvas.theme.style_mappings import TOOLBAR_BTN_CONFIG
from src.panel.components.toolbar_tooltip import ToolbarTooltip
from src.panel.widgets import LabelButton, themed_button, themed_separator
from src.utils.i18n import t

# ── Unicode 图标常量 ──────────────────────────────────────────

ICONS: dict[str, str] = {
    "back": "←",
    "start": "▶",
    "pause": "⏸",
    "resume": "▶",
    "stop": "⏹",
    "refresh": "↻",
    "save": "⤓",
    "save_as": "⤓",
    "load": "⤋",
    "delete": "✕",
    "clear": "∅",
    "undo": "↩",
    "redo": "↪",
    "debug": "⚙",
    "settings": "⚙",
    "search": "⌕",
    "theme_dark": "☽",
    "theme_light": "☀",
    "home": "⌂",
    "record": "⏺",
    "export": "⤒",
    "import": "⤑",
    "fullscreen": "⤢",
    "pick_region": "✦",
    "reset": "↺",
    "breakpoint": "◆",
    "step_over": "→",
    "palette": "☰",
    "properties": "⚙",
    "log": "≡",
    "add": "➕",
    "remove": "➖",
}

# ── 按钮内边距 (参考 Apple HIG 28pt 触控目标) ──────────────

_PADX: int = TOOLBAR_BTN_CONFIG["padx"]  # type: ignore[assignment]
_PADY: int = TOOLBAR_BTN_CONFIG["pady"]  # type: ignore[assignment]


class ToolbarFrame(tk.Frame):
    """工具栏 — 每个元素独立排列 + 语义分组分隔 + 自动换行。

    每个按钮/标签/下拉框等都是一个独立的 grid cell，
    不再捆绑到 section Frame 中。section 仅作为逻辑分组
    用于插入竖线分隔符。
    """

    def __init__(self, parent: tk.Widget) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.toolbar_bg)
        self._sections: dict[str, str] = {}
        self._tooltips: list[ToolbarTooltip] = []
        self._last_section: str | None = None

        self._items: list[tuple[str, tk.Widget]] = []
        self._reflow_id: str | None = None
        self._is_reflowing: bool = False
        self._last_width: int = -1
        self._last_height: int = -1

        self.pack_propagate(False)
        self.configure(height=36)
        self.bind("<Configure>", self._on_configure)

    # ── 构建接口 ──────────────────────────────────────────

    def add_section(self, name: str) -> tk.Frame:
        """创建逻辑分组。返回 self 作为兼容性适配。"""
        if name in self._sections:
            return self
        if self._last_section is not None:
            sep = themed_separator(self, orient=tk.VERTICAL)
            self._items.append(("sep", sep))
        self._sections[name] = name
        self._last_section = name
        return self

    def get_section(self, name: str) -> tk.Frame | None:
        """返回 self 作为兼容性适配。"""
        if name in self._sections:
            return self
        return None

    def make_button(
        self,
        section: str,
        text: str,
        command: Callable,
        style: str = "secondary",
        *,
        icon: str | None = None,
        tooltip: str | None = None,
        shortcut_hint: str | None = None,
        **kw,
    ) -> LabelButton:
        if section not in self._sections:
            self.add_section(section)

        icon_char = ICONS.get(icon, "") if icon else ""
        display = f"{icon_char} {text}" if icon else text

        kw.setdefault("padx", _PADX)
        kw.setdefault("pady", _PADY)

        btn = themed_button(self, text=display, command=command, style=style, **kw)
        self._items.append(("item", btn))

        if tooltip:
            tip = ToolbarTooltip(btn, tooltip, shortcut=shortcut_hint or "")
            self._tooltips.append(tip)
        return btn

    def add_widget(self, section: str, widget: tk.Widget) -> None:
        """添加一个独立元素到工具栏。"""
        if section not in self._sections:
            self.add_section(section)
        self._items.append(("item", widget))

    def add_item(self, itype: str, widget: tk.Widget, *, section: str = "") -> None:
        """添加一个带类型标注的元素到工具栏。

        公共接口，供 ProfileBar / RegionBar / RunControls 等组件使用，
        避免直接访问 _items。
        """
        if section and section not in self._sections:
            self.add_section(section)
        self._items.append((itype, widget))

    def request_reflow(self) -> None:
        """请求延迟重排，供嵌入组件在尺寸变化时调用。"""
        if self._reflow_id is not None:
            self.after_cancel(self._reflow_id)
        self._reflow_id = self.after(80, self._do_reflow)

    def add_spacer(self) -> None:
        spacer = tk.Frame(self, bg=current_theme().toolbar_bg)
        self._items.append(("spacer", spacer))

    def make_toggle_button(
        self,
        section: str,
        text: str,
        command: Callable,
        active: bool = False,
        *,
        icon: str | None = None,
        tooltip: str | None = None,
        shortcut_hint: str | None = None,
        **kw,
    ) -> LabelButton:
        style = "primary" if active else "secondary"
        btn = self.make_button(
            section, text, command, style=style,
            icon=icon, tooltip=tooltip, shortcut_hint=shortcut_hint, **kw,
        )
        return btn

    @staticmethod
    def update_toggle(btn: LabelButton, active: bool) -> None:
        btn.set_style("primary" if active else "secondary")

    def set_tooltip(self, widget: tk.Widget, text: str, shortcut: str = "") -> None:
        tip = ToolbarTooltip(widget, text, shortcut=shortcut)
        self._tooltips.append(tip)

    # ── Grid 换行 ─────────────────────────────────────────

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is not self or self._is_reflowing:
            return
        w, h = event.width, event.height
        if w == self._last_width:
            return
        self._last_width = w
        self._last_height = h
        if self._reflow_id is not None:
            self.after_cancel(self._reflow_id)
        self._reflow_id = self.after(150, self._do_reflow)

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
        # 1. Prefer explicit min_width (font-measured, always reliable)
        mw = getattr(widget, "min_width", 0)
        if mw > 1:
            return mw
        # 2. Fall back to tkinter geometry
        w = widget.winfo_reqwidth()
        if w > 1:
            return w
        w = widget.winfo_width()
        if w > 1:
            return w
        return 30

    def _measure_height(self, widget: tk.Widget) -> int:
        h = widget.winfo_reqheight()
        if h > 1:
            return h
        h = widget.winfo_height()
        if h > 1:
            return h
        return 28

    def _perform_reflow(self) -> None:
        self.update_idletasks()
        available = self.winfo_width()
        if available <= 1:
            return

        # 测量宽度 + 高度
        widths: dict[int, int] = {}
        heights: dict[int, int] = {}
        for _, widget in self._items:
            if widget.winfo_exists():
                widths[id(widget)] = self._measure_width(widget)
                heights[id(widget)] = self._measure_height(widget)

        # 全部取消 place
        for _, widget in self._items:
            if widget.winfo_exists():
                widget.place_forget()

        # 计算分配方案
        row_plan: list[list[tuple[str, tk.Widget]]] = [[]]
        x = 0
        GAP = 2

        for item in self._items:
            itype, widget = item
            if not widget.winfo_exists():
                continue
            w = widths.get(id(widget), 30)
            gap = GAP if x > 0 else 0

            if itype == "spacer":
                row_plan[-1].append(item)
                row_plan.append([])
                x = 0
            elif itype == "sep" and x == 0:
                continue
            elif x + gap + w > available and x > 0:
                row_plan.append([item])
                x = w
            else:
                row_plan[-1].append(item)
                x += gap + w

        # 用 place 放置 items（避免 grid 跨行列宽共享）
        y = 0
        for row_items in row_plan:
            if not any(w.winfo_exists() for _, w in row_items):
                continue

            row_h = max(
                (heights[id(w)] for _, w in row_items if w.winfo_exists()),
                default=28,
            )

            spacer_idx = None
            for i, (itype, _) in enumerate(row_items):
                if itype == "spacer":
                    spacer_idx = i
                    break

            def _place(itype: str, widget: tk.Widget, px: int) -> int:
                w = widths.get(id(widget), 30)
                h = heights.get(id(widget), 28)
                widget.place(x=px, y=y + (row_h - h) // 2, anchor="nw")
                return w + GAP

            if spacer_idx is not None:
                # 左侧元素
                lx = 0
                for itype, widget in row_items[:spacer_idx]:
                    if widget.winfo_exists():
                        lx += _place(itype, widget, lx)

                # 右侧元素（右对齐）
                right = [(t, w) for t, w in row_items[spacer_idx + 1:]
                         if w.winfo_exists()]
                if right:
                    total_rw = sum(widths.get(id(w), 30) for _, w in right)
                    total_rw += GAP * max(0, len(right) - 1)
                    rx = max(lx, available - total_rw)
                    for itype, widget in right:
                        rx += _place(itype, widget, rx)
            else:
                lx = 0
                for itype, widget in row_items:
                    if widget.winfo_exists():
                        lx += _place(itype, widget, lx)

            y += row_h

        new_height = max(y, 36)
        if new_height != self._last_height:
            self._last_height = new_height
            self.configure(height=new_height)

    # ── 主题 ──────────────────────────────────────────────

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.toolbar_bg)
        for itype, widget in self._items:
            if not widget.winfo_exists():
                continue
            if hasattr(widget, "apply_theme"):
                try:
                    widget.apply_theme()
                except tk.TclError:
                    pass
            elif itype == "sep":
                try:
                    widget.configure(bg=th.border_default)
                except tk.TclError:
                    pass
            elif itype == "spacer":
                try:
                    widget.configure(bg=th.toolbar_bg)
                except tk.TclError:
                    pass
            else:
                try:
                    wclass = widget.winfo_class()
                    if wclass == "Label":
                        widget.configure(fg=th.text_primary, bg=th.toolbar_bg)
                except tk.TclError:
                    pass


class RunControls(tk.Frame):
    """启动/暂停/停止按钮组，封装状态机。

    通过 add_to_toolbar() 将每个按钮以 toolbar 为 parent 创建，
    作为独立 grid cell 实现逐元素自适应换行。
    """

    VALID_STATES = frozenset({"idle", "running", "paused"})

    def __init__(
        self,
        parent: tk.Widget,
        on_start: Callable,
        on_pause: Callable,
        on_resume: Callable,
        on_stop: Callable,
        *,
        show_labels: bool = True,
    ) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.toolbar_bg)
        self._on_start = on_start
        self._on_pause = on_pause
        self._on_resume = on_resume
        self._on_stop = on_stop
        self._state = "idle"
        self._show_labels = show_labels
        self.btn_start: LabelButton | None = None
        self.btn_pause: LabelButton | None = None
        self.btn_stop: LabelButton | None = None

    def _label(self, key: str, icon_key: str) -> str:
        icon = ICONS.get(icon_key, "")
        if self._show_labels:
            return f"{icon} {t(key)}" if icon else t(key)
        return icon or t(key)

    def add_to_toolbar(self, toolbar: "ToolbarFrame", section: str) -> None:
        """以 toolbar 为 parent 创建每个按钮，并作为独立 grid cell 注册。"""
        self.btn_start = themed_button(
            toolbar, text=self._label("common.start", "start"), style="primary",
            command=self._on_start,
            padx=_PADX, pady=_PADY,
        )
        toolbar.add_item("item", self.btn_start, section=section)

        self.btn_pause = themed_button(
            toolbar, text=self._label("common.pause", "pause"),
            command=self._handle_pause, state=tk.DISABLED,
            padx=_PADX, pady=_PADY,
        )
        toolbar.add_item("item", self.btn_pause, section=section)

        self.btn_stop = themed_button(
            toolbar, text=self._label("common.stop", "stop"), style="danger",
            command=self._on_stop, state=tk.DISABLED,
            padx=_PADX, pady=_PADY,
        )
        toolbar.add_item("item", self.btn_stop, section=section)

    def _handle_pause(self) -> None:
        if self._state == "paused":
            self._on_resume()
        else:
            self._on_pause()

    def set_state(self, state: str) -> None:
        if state not in self.VALID_STATES:
            raise ValueError(f"Invalid RunControls state: {state!r}")
        self._state = state
        self._update_visuals()

    def _update_visuals(self) -> None:
        is_active = self._state in ("running", "paused")

        if self.btn_start is not None:
            self.btn_start.configure(
                state=tk.DISABLED if is_active else tk.NORMAL,
            )
        if self.btn_pause is not None:
            self.btn_pause.configure(
                state=tk.NORMAL if is_active else tk.DISABLED,
                text=self._label(
                    "common.resume" if self._state == "paused" else "common.pause",
                    "pause",
                ),
            )
        if self.btn_stop is not None:
            self.btn_stop.configure(
                state=tk.NORMAL if is_active else tk.DISABLED,
            )

    @property
    def state(self) -> str:
        return self._state

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.toolbar_bg)
        for btn in (self.btn_start, self.btn_pause, self.btn_stop):
            if btn is not None and btn.winfo_exists():
                try:
                    btn.apply_theme()
                except tk.TclError:
                    pass
