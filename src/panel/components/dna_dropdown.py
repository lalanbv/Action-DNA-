"""DNADropdown — 统一主题下拉组件。

Canvas 绘制文本 + 箭头指示器 + 应用内 Frame Listbox 弹出。
彻底规避 ttk.Combobox 平台主题问题和 tk.Entry 状态管理缺陷。

设计原则：
- 全部视觉元素用 Canvas 绘制（文本、箭头、边框、hover 高亮）
- 弹出层为应用内 Frame（place 定位 + grab_set 限定交互域）
- 不使用 bind_all / unbind_all（避免全局事件污染）
- __slots__ 与 DNAWidget 基类协作
"""

from __future__ import annotations

import tkinter as tk
from typing import Any, Callable

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme.style_mappings import (
    derive_hover_bg as _derive_hover_bg,
    resolve_font as _resolve_font,
)
from src.panel.components.base import DNAWidget


def _draw_arrow_polygon(canvas: tk.Canvas, cx: float, cy: float, size: float, fill: str) -> int:
    """绘制向下的三角形箭头，返回 canvas item id。"""
    half = size / 2
    points = [
        cx - half, cy - half * 0.6,
        cx + half, cy - half * 0.6,
        cx, cy + half * 0.6,
    ]
    return canvas.create_polygon(points, fill=fill, outline="", smooth=False)


class DNADropdown(DNAWidget):
    """统一主题下拉组件，i18n 感知。

    options 为 [(internal_value, i18n_key), ...] 列表。
    get_value() 返回内部值而非显示文本。
    """

    __slots__ = (
        "_command", "_variable", "_placeholder", "_i18n",
        "_items", "_value_to_display", "_display_to_value",
        "_display_values", "_suppressing_var_update",
        "_internal_state", "_enabled",
        "_popup", "_listbox", "_hover_index",
        "_bg", "_fg", "_border_color", "_border_hover_color",
        "_arrow_bg", "_arrow_fg", "_arrow_active_bg",
        "_selected_bg", "_selected_fg",
        "_current_display", "_hovering", "_canvas",
        "_text_x_pad", "_arrow_zone_width",
        "_draw_pending", "_popup_open",
        "_outside_bound", "_outside_bind_id",
    )

    _ARROW_SIZE = 6
    _MIN_WIDTH = 80
    _MAX_VISIBLE_ITEMS = 10
    _ITEM_HEIGHT = 26
    _BORDER_RADIUS = 4

    def __init__(
        self,
        parent: tk.Widget,
        options: list[tuple[str, str]] | None = None,
        *,
        value: str | None = None,
        variable: tk.StringVar | None = None,
        placeholder: str = "",
        state: str = "normal",
        width: int = 20,
        command: Callable[[str], None] | None = None,
        i18n: bool = True,
        **kw: Any,
    ) -> None:
        th = current_theme()
        sm = scale_manager()

        self._command = command
        self._variable = variable
        self._placeholder = placeholder
        self._i18n = i18n
        self._items: list[tuple[str, str]] = list(options) if options else []
        self._value_to_display: dict[str, str] = {}
        self._display_to_value: dict[str, str] = {}
        self._display_values: list[str] = []
        self._suppressing_var_update = False
        self._internal_state: str = state
        self._enabled: bool = state not in ("disabled", tk.DISABLED)
        self._popup: tk.Frame | None = None
        self._listbox: tk.Listbox | None = None
        self._hover_index: int = -1
        self._current_display: str = ""
        self._hovering: bool = False
        self._draw_pending: bool = False
        self._popup_open: bool = False
        self._outside_bound: bool = False
        self._outside_bind_id: str | None = None

        self._text_x_pad = sm.s(8)
        self._arrow_zone_width = sm.s(24)

        self._bg = th.input_bg
        self._fg = th.input_fg
        self._border_color = th.border_default
        self._border_hover_color = _derive_hover_bg(th.border_default, 0.25)
        self._arrow_bg = th.input_bg
        self._arrow_fg = th.text_secondary
        self._arrow_active_bg = _derive_hover_bg(th.input_bg)
        self._selected_bg = th.accent_blue
        self._selected_fg = th.text_on_accent

        super().__init__(parent, bg=self._border_color, padx=1, pady=1)

        canvas_h = sm.s(28)
        canvas_w = sm.s(max(self._MIN_WIDTH, width * 8))
        self._canvas = tk.Canvas(
            self,
            width=canvas_w,
            height=canvas_h,
            bg=self._bg,
            highlightthickness=0,
            bd=0,
            cursor="hand2" if self._enabled else "arrow",
        )
        self._canvas.pack(fill=tk.BOTH, expand=True)

        self._rebuild_options()

        if self._variable:
            self._variable.trace_add("write", self._on_var_change)

        if value is not None:
            self.set_value(value)
        elif self._variable:
            var_val = self._variable.get()
            if var_val:
                display = self._value_to_display.get(var_val)
                self._current_display = display if display is not None else var_val
        elif placeholder:
            self._current_display = placeholder

        # 点击：Canvas + Frame 都响应
        self._canvas.bind("<ButtonPress-1>", self._on_click)
        self.bind("<ButtonPress-1>", self._on_click)
        # Hover：绑在 Frame 上，覆盖 1px 边框区域
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        # 尺寸变化时重绘
        self._canvas.bind("<Configure>", self._on_canvas_configure)

        if not self._enabled:
            self._apply_disabled_visual()

        self.after_idle(self._request_draw)

    # ── 绘制 ──────────────────────────────────────────────────

    def _request_draw(self) -> None:
        if self._draw_pending:
            return
        self._draw_pending = True
        self.after_idle(self._do_draw)

    def _do_draw(self) -> None:
        self._draw_pending = False
        self._draw()

    def _draw(self) -> None:
        if not self.winfo_exists() or not self._canvas.winfo_exists():
            return
        self._canvas.delete("all")

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 4:
            cw = self._canvas.winfo_reqwidth()
        if ch < 4:
            ch = self._canvas.winfo_reqheight()
        if cw < 4 or ch < 4:
            return

        th = current_theme()
        font = _resolve_font(th, "body")
        sm = scale_manager()
        arrow_cx = cw - self._arrow_zone_width // 2
        cy = ch // 2

        # 箭头区域背景
        arrow_bg = (
            self._arrow_active_bg
            if (self._hovering or self._popup_open) and self._enabled
            else self._arrow_bg
        )
        self._canvas.create_rectangle(
            cw - self._arrow_zone_width, 0, cw, ch,
            fill=arrow_bg, outline="",
        )

        # 箭头分隔线
        self._canvas.create_line(
            cw - self._arrow_zone_width, sm.s(2),
            cw - self._arrow_zone_width, ch - sm.s(2),
            fill=self._border_color, width=1,
        )

        # 三角形箭头（替代 unicode 字符，确保跨平台一致性）
        arrow_fg = th.text_primary if self._enabled else th.btn_disabled_fg
        arrow_size = sm.s(self._ARROW_SIZE)
        _draw_arrow_polygon(self._canvas, arrow_cx, cy + sm.s(1), arrow_size, arrow_fg)

        # 文本
        if not self._enabled:
            text_fg = th.btn_disabled_fg
        elif self._current_display == self._placeholder:
            text_fg = th.text_secondary
        else:
            text_fg = self._fg

        max_text_w = cw - self._arrow_zone_width - self._text_x_pad * 2
        self._canvas.create_text(
            self._text_x_pad, cy,
            text=self._current_display,
            fill=text_fg,
            font=font,
            anchor=tk.W,
            width=max(max_text_w, 10),
        )

    # ── 选项管理 ───────────────────────────────────────────────

    def _rebuild_options(self) -> None:
        from src.utils.i18n import t

        self._value_to_display.clear()
        self._display_to_value.clear()
        display_values: list[str] = []

        for val, key in self._items:
            display = t(key) if self._i18n else key
            self._value_to_display[val] = display
            self._display_to_value[display] = val
            display_values.append(display)

        self._display_values = display_values
        self._fit_to_content()

    def _fit_to_content(self) -> None:
        """根据最宽选项文本自适应调整 Canvas 宽度。"""
        if not self._display_values:
            return
        try:
            import tkinter.font as tkfont
            font = _resolve_font(current_theme(), "body")
            font_obj = tkfont.Font(root=self.winfo_toplevel(), font=font)
            max_w = max(font_obj.measure(t) for t in self._display_values)
            sm = scale_manager()
            needed = max_w + self._arrow_zone_width + self._text_x_pad * 2 + 4
            canvas_w = sm.s(max(self._MIN_WIDTH, needed))
            if hasattr(self, "_canvas") and self._canvas.winfo_exists():
                self._canvas.configure(width=canvas_w)
        except Exception:
            pass

    # ── 弹出列表 ───────────────────────────────────────────────

    def _show_popup(self) -> None:
        if not self._enabled:
            return
        if self._popup is not None:
            self._close_popup()
            return

        th = current_theme()
        sm = scale_manager()

        self.update_idletasks()

        n_items = len(self._display_values)
        if n_items == 0:
            return

        root = self.winfo_toplevel()
        root_x = root.winfo_rootx()
        root_y = root.winfo_rooty()

        # 相对于主窗口的坐标
        x = self.winfo_rootx() - root_x
        y = self.winfo_rooty() - root_y + self.winfo_height()
        w = max(self.winfo_width(), sm.s(self._MIN_WIDTH))

        max_visible = min(n_items, self._MAX_VISIBLE_ITEMS)
        item_h = sm.s(self._ITEM_HEIGHT)
        list_h = max_visible * item_h + sm.s(4)

        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        abs_y = y + root_y

        # 如果超出屏幕底部，向上弹出
        if abs_y + list_h > screen_h - sm.s(40):
            y = self.winfo_rooty() - root_y - list_h
            abs_y = y + root_y
            if abs_y < sm.s(10):
                list_h = max(sm.s(100), screen_h - self.winfo_rooty() - self.winfo_height() - sm.s(40))
                y = self.winfo_rooty() - root_y + self.winfo_height()

        # 如果超出屏幕右侧，向左偏移
        abs_x = x + root_x
        if abs_x + w > screen_w - sm.s(10):
            x = max(sm.s(10), screen_w - w - sm.s(10)) - root_x

        # 应用内弹出层（非独立窗口，避免 z-order 和圆角问题）
        self._popup = tk.Frame(root, bg=th.border_default, padx=1, pady=1)
        self._popup.place(x=x, y=y, width=w, height=list_h, anchor="nw")
        self._popup.lift()

        list_font = _resolve_font(th, "body")
        self._listbox = tk.Listbox(
            self._popup,
            bg=th.input_bg,
            fg=th.input_fg,
            selectbackground=th.accent_blue,
            selectforeground=th.text_on_accent,
            font=list_font,
            relief=tk.FLAT,
            bd=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
            selectborderwidth=0,
        )
        self._listbox.pack(fill=tk.BOTH, expand=True)

        for dv in self._display_values:
            self._listbox.insert(tk.END, dv)

        for i, dv in enumerate(self._display_values):
            if dv == self._current_display:
                self._listbox.selection_set(i)
                self._listbox.see(i)
                break

        self._listbox.bind("<<ListboxSelect>>", self._on_list_select)
        self._listbox.bind("<Motion>", self._on_list_motion)
        self._listbox.bind("<Leave>", self._on_list_leave)
        self._popup.bind("<Escape>", lambda _: self._close_popup())
        self._popup.bind("<ButtonPress-1>", self._on_popup_click)

        self._popup_open = True
        self._draw()
        self._listbox.focus_set()
        # 全局点击检测：点击弹窗外部时关闭
        if not self._outside_bound:
            self._outside_bind_id = self.winfo_toplevel().bind_all(
                "<ButtonPress-1>", self._on_outside_click, add="+",
            )
            self._outside_bound = True

    def _close_popup(self) -> None:
        if self._popup is None:
            return
        # 解绑全局点击检测，避免泄漏
        if self._outside_bound:
            try:
                self.winfo_toplevel().unbind(
                    "<ButtonPress-1>", self._outside_bind_id,
                )
            except tk.TclError:
                pass
            self._outside_bound = False
            self._outside_bind_id = None
        popup = self._popup
        self._popup = None
        self._listbox = None
        self._hover_index = -1
        self._popup_open = False
        try:
            popup.place_forget()
            popup.destroy()
        except tk.TclError:
            pass
        self._draw()

    # ── 事件处理 ───────────────────────────────────────────────

    def _on_click(self, _event: tk.Event | None = None) -> None:
        if self._enabled:
            self._show_popup()

    def _on_enter(self, _event: tk.Event) -> None:
        if self._enabled:
            self._hovering = True
            super().configure(bg=self._border_hover_color)
            self._draw()

    def _on_leave(self, _event: tk.Event) -> None:
        if self._enabled:
            self._hovering = False
            super().configure(bg=self._border_color)
            self._draw()

    def _on_canvas_configure(self, _event: tk.Event) -> None:
        self._request_draw()

    def _on_popup_click(self, event: tk.Event) -> None:
        """点击弹窗边框时关闭。"""
        if self._popup is None:
            return
        if event.widget is self._popup:
            self._close_popup()

    def _on_outside_click(self, event: tk.Event) -> None:
        """全局点击检测：点击弹窗外部时关闭。"""
        if self._popup is None:
            return
        widget = event.widget
        # 点击在弹窗内（Listbox 或边框）→ 不关闭
        w = widget
        while w is not None:
            if w is self._popup:
                return
            w = getattr(w, "master", None)
        # 点击在 DNADropdown 自身 → 由 _on_click 处理 toggle
        w = widget
        while w is not None:
            if w is self:
                return
            w = getattr(w, "master", None)
        self._close_popup()

    def _on_list_select(self, _event: tk.Event | None = None) -> None:
        if self._listbox is None:
            return
        sel = self._listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if 0 <= idx < len(self._items):
            val = self._items[idx][0]
            display = self._display_values[idx]

            self._current_display = display
            self._draw()

            if self._variable:
                self._suppressing_var_update = True
                try:
                    self._variable.set(val)
                finally:
                    self._suppressing_var_update = False
            if self._command:
                self._command(val)

        self._close_popup()

    def _on_list_motion(self, event: tk.Event) -> None:
        if self._listbox is None:
            return
        idx = self._listbox.nearest(event.y)
        if idx != self._hover_index:
            self._hover_index = idx
            self._listbox.selection_clear(0, tk.END)
            self._listbox.selection_set(idx)
            self._listbox.activate(idx)

    def _on_list_leave(self, _event: tk.Event) -> None:
        self._hover_index = -1

    def _on_var_change(self, *_args: Any) -> None:
        if self._suppressing_var_update or self._variable is None:
            return
        try:
            val = self._variable.get()
        except (tk.TclError, ValueError):
            return
        display = self._value_to_display.get(val)
        if display is not None:
            self._current_display = display
            self._draw()

    def _apply_disabled_visual(self) -> None:
        self._canvas.configure(cursor="arrow")
        self._draw()

    # ── 公共 API ───────────────────────────────────────────────

    def get_value(self) -> str:
        if self._current_display == self._placeholder:
            return ""
        return self._display_to_value.get(self._current_display, self._current_display)

    def set_value(self, val: str) -> None:
        display = self._value_to_display.get(val)
        self._current_display = display if display is not None else val
        self._draw()
        if self._variable:
            self._suppressing_var_update = True
            try:
                self._variable.set(val)
            finally:
                self._suppressing_var_update = False

    def get_options(self) -> list[tuple[str, str]]:
        return list(self._items)

    def set_options(self, options: list[tuple[str, str]]) -> None:
        current_val = self.get_value()
        self._items = list(options)
        self._rebuild_options()
        if current_val:
            display = self._value_to_display.get(current_val)
            if display is not None:
                self._current_display = display
                self._draw()

    def refresh_translations(self) -> None:
        current_val = self.get_value()
        self._rebuild_options()  # also calls _fit_to_content
        if current_val:
            display = self._value_to_display.get(current_val)
            if display is not None:
                self._current_display = display
                self._draw()

    def configure(self, **kw: Any) -> None:
        if "options" in kw:
            self.set_options(kw.pop("options"))
        if "value" in kw:
            self.set_value(kw.pop("value"))
        if "state" in kw:
            self._internal_state = kw.pop("state")
            self._enabled = self._internal_state not in ("disabled", tk.DISABLED)
            if self._enabled:
                self._canvas.configure(cursor="hand2")
                self._draw()
            else:
                self._apply_disabled_visual()
        if "command" in kw:
            self._command = kw.pop("command")
        if "width" in kw:
            w = kw.pop("width")
            sm = scale_manager()
            self._canvas.configure(width=sm.s(max(self._MIN_WIDTH, w * 8)))
        kw.pop("bg", None)
        kw.pop("fg", None)
        kw.pop("font", None)

    config = configure

    def cget(self, key: str) -> Any:
        if key == "value":
            return self.get_value()
        if key == "state":
            return self._internal_state
        return super().cget(key)

    @property
    def combo(self) -> tk.Canvas:
        return self._canvas

    # ── 主题 ───────────────────────────────────────────────────

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        if not self.winfo_exists():
            return

        self._bg = theme.input_bg
        self._fg = theme.input_fg
        self._border_color = theme.border_default
        self._border_hover_color = _derive_hover_bg(theme.border_default, 0.25)
        self._arrow_bg = theme.input_bg
        self._arrow_fg = theme.text_secondary
        self._arrow_active_bg = _derive_hover_bg(theme.input_bg)
        self._selected_bg = theme.accent_blue
        self._selected_fg = theme.text_on_accent

        self._canvas.configure(bg=self._bg)
        border_color = (
            self._border_hover_color if self._hovering else self._border_color
        )
        super().configure(bg=border_color)
        self._draw()
