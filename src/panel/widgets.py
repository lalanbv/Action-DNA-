"""ThemedWidgets — 统一主题控件工厂

所有页面和对话框通过此模块创建控件，确保视觉一致性和主题切换支持。
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Any, Callable

from src.panel.canvas.theme import current_theme, CanvasTheme, theme_registry
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme.style_mappings import (
    _STYLE_FONTS, _BUTTON_STYLES, resolve_font as _resolve_font,
    derive_hover_bg as _derive_hover_bg,
)

if TYPE_CHECKING:
    from src.panel.components.themed_checkbox import ThemedCheckbox
    from src.panel.components.themed_entry import ThemedEntry
    from src.panel.components.themed_radio import ThemedRadio


class LabelButton(tk.Frame):
    """tk.Frame + tk.Label 组合按钮 — 使用外框 Frame 实现可靠边框，macOS 兼容。"""

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "",
        command: Callable[[], None] | None = None,
        bg: str | None = None,
        fg: str | None = None,
        activebackground: str | None = None,
        activeforeground: str | None = None,
        disabledforeground: str | None = None,
        disabledbackground: str | None = None,
        border_color: str | None = None,
        font: tuple | None = None,
        padx: int | None = None,
        pady: int | None = None,
        cursor: str = "hand2",
        **kw: Any,
    ) -> None:
        self._command = command
        # 从主题系统读取默认颜色，避免硬编码
        _th = current_theme()
        _bg = _th.btn_bg if bg is None else bg
        _fg = _th.text_primary if fg is None else fg
        _active_fg = _th.text_on_accent if activeforeground is None else activeforeground
        _disabled_fg = _th.btn_disabled_fg if disabledforeground is None else disabledforeground
        _disabled_bg = _th.btn_disabled_bg if disabledbackground is None else disabledbackground
        _border_color = border_color or _bg
        _font = font if font is not None else _th.font_body

        self._bg = _bg
        self._fg = _fg
        self._active_bg = activebackground if activebackground is not None else _derive_hover_bg(_bg)
        self._active_fg = _active_fg
        self._disabled_fg = _disabled_fg
        self._disabled_bg = _disabled_bg
        self._border_color = _border_color
        self._enabled = True
        self._pressed = False
        self._style_name: str | None = None
        sm = scale_manager()
        padx = sm.s(12) if padx is None else padx
        pady = sm.s(4) if pady is None else pady

        _initial_state = kw.pop("state", None)

        frame_kw: dict[str, Any] = {}
        for key in ("highlightbackground", "highlightthickness",
                     "highlightcolor", "takefocus"):
            if key in kw:
                kw.pop(key)

        super().__init__(
            parent,
            bg=self._border_color,
            padx=1,
            pady=1,
            cursor=cursor,
            **frame_kw,
        )

        self._label = tk.Label(
            self,
            text=text,
            bg=_bg,
            fg=_fg,
            font=_font,
            padx=padx,
            pady=pady,
            cursor=cursor,
        )
        self._label.pack(fill=tk.BOTH, expand=True)

        self._label.bind("<Enter>", self._on_enter)
        self._label.bind("<Leave>", self._on_leave)
        self._label.bind("<ButtonPress-1>", self._on_press)
        self._label.bind("<ButtonRelease-1>", self._on_release)
        # macOS 兼容：Frame 上也绑定按钮事件，防止事件投递到 Frame 时丢失
        tk.Frame.bind(self, "<ButtonPress-1>", self._on_press)
        tk.Frame.bind(self, "<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Destroy>", self._on_destroy)

        if _initial_state in ("disabled", tk.DISABLED):
            self._enabled = False
            if self._disabled_bg:
                self._label.configure(bg=self._disabled_bg)
            self._label.configure(fg=self._disabled_fg, cursor="arrow")
            self.configure(cursor="arrow")

        self._theme_reg_id = theme_registry().register(self)

    def _on_enter(self, _event: tk.Event) -> None:
        if self._enabled:
            self._label.configure(bg=self._active_bg, fg=self._active_fg)

    def _on_leave(self, _event: tk.Event) -> None:
        if self._enabled:
            self._label.configure(bg=self._bg, fg=self._fg)

    def _on_destroy(self, _event: tk.Event) -> None:
        theme_registry().unregister(self._theme_reg_id)

    def _on_press(self, _event: tk.Event) -> None:
        if self._enabled:
            self._pressed = True
            self._label.configure(bg=self._active_bg)

    def _on_release(self, _event: tk.Event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        if self._enabled:
            self._label.configure(bg=self._bg, fg=self._fg)
            if was_pressed and self._command:
                self._command()

    def configure(self, **kw: Any) -> None:
        if "command" in kw:
            self._command = kw.pop("command")
        if "state" in kw:
            state = kw.pop("state")
            if state in ("disabled", tk.DISABLED):
                self._enabled = False
                if self._disabled_bg:
                    self._label.configure(bg=self._disabled_bg)
                self._label.configure(fg=self._disabled_fg, cursor="arrow")
                self.configure(cursor="arrow")
            else:
                self._enabled = True
                self._label.configure(bg=self._bg, fg=self._fg, cursor="hand2")
                self.configure(cursor="hand2")
        label_kw = {}
        frame_kw = {}
        if "bg" in kw:
            self._bg = kw.pop("bg")
            self._active_bg = _derive_hover_bg(self._bg)
            if self._enabled:
                label_kw["bg"] = self._bg
        if "fg" in kw:
            self._fg = kw.pop("fg")
            if self._enabled:
                label_kw["fg"] = self._fg
        if "text" in kw:
            label_kw["text"] = kw.pop("text")
        if "font" in kw:
            label_kw["font"] = kw.pop("font")
        if "padx" in kw:
            label_kw["padx"] = kw.pop("padx")
        if "pady" in kw:
            label_kw["pady"] = kw.pop("pady")
        if "activebackground" in kw:
            self._active_bg = kw.pop("activebackground")
        if "activeforeground" in kw:
            self._active_fg = kw.pop("activeforeground")
        if "border_color" in kw:
            self._border_color = kw.pop("border_color")
            frame_kw["bg"] = self._border_color
        if "cursor" in kw:
            label_kw["cursor"] = kw.pop("cursor")

        remaining = {}
        for key, val in kw.items():
            if key in ("highlightbackground", "highlightthickness",
                       "highlightcolor", "takefocus", "relief", "bd",
                       "disabledforeground", "disabledbackground"):
                continue
            remaining[key] = val

        if label_kw:
            self._label.configure(**label_kw)
        if frame_kw:
            super().configure(**frame_kw)
        if remaining:
            self._label.configure(**remaining)

    config = configure

    def cget(self, key: str) -> Any:
        if key == "state":
            return "disabled" if not self._enabled else "normal"
        if key == "text":
            return self._label.cget("text")
        if key in ("bg", "fg", "font", "padx", "pady", "cursor"):
            return self._label.cget(key)
        return super().cget(key)

    @property
    def command(self) -> Callable[[], None] | None:
        return self._command

    def set_style(self, style_name: str) -> None:
        """按预定义样式名更新按钮外观。"""
        self._style_name = style_name
        th = current_theme()
        cfg = _BUTTON_STYLES.get(style_name, _BUTTON_STYLES["secondary"])
        bg = getattr(th, cfg["bg_prop"])
        fg = getattr(th, cfg["fg_prop"])
        self.configure(bg=bg, fg=fg)

    def bind(self, sequence=None, func=None, add=None):
        """同时绑定到外框 Frame 和内部 Label，确保事件不丢失。"""
        if sequence and sequence.startswith("<Button"):
            self._label.bind(sequence, func, add)
            return super().bind(sequence, func, add)
        return super().bind(sequence, func, add)

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        """主题切换时更新颜色（由 apply_theme_recursive 跳过递归）"""
        if theme is None:
            theme = current_theme()
        if not self.winfo_exists():
            return

        if self._style_name:
            cfg = _BUTTON_STYLES.get(self._style_name, _BUTTON_STYLES["secondary"])
            new_bg = getattr(theme, cfg["bg_prop"])
            new_fg = getattr(theme, cfg["fg_prop"])
            self._bg = new_bg
            self._fg = new_fg
            self._active_bg = _derive_hover_bg(new_bg)
            self._active_fg = new_fg
            self._border_color = theme.btn_border
            self._disabled_fg = theme.btn_disabled_fg
            self._disabled_bg = theme.btn_disabled_bg
        else:
            self._bg = theme.btn_bg
            self._fg = theme.text_primary
            self._active_bg = _derive_hover_bg(theme.btn_bg)
            self._active_fg = theme.text_on_accent
            self._border_color = theme.btn_border
            self._disabled_fg = theme.btn_disabled_fg
            self._disabled_bg = theme.btn_disabled_bg

        if self._enabled:
            self._label.configure(bg=self._bg, fg=self._fg)
        else:
            if self._disabled_bg:
                self._label.configure(bg=self._disabled_bg)
            self._label.configure(fg=self._disabled_fg)
        super().configure(bg=self._border_color)




# ── 工厂函数 ──


def themed_frame(parent: tk.Misc, **kw: Any) -> tk.Frame:
    t = current_theme()
    kw.setdefault("bg", t.page_bg)
    return tk.Frame(parent, **kw)


def _inherit_bg(parent: tk.Misc, fallback: str) -> str:
    """从父控件继承背景色，避免 Label 在非 page_bg 容器中出现文字背景色块。"""
    try:
        bg = parent.cget("bg")
        if bg and isinstance(bg, str) and bg.startswith("#"):
            return bg
    except (tk.TclError, AttributeError):
        pass
    return fallback


def themed_label(
    parent: tk.Misc, text: str = "", style: str = "body", **kw: Any
) -> tk.Label:
    t = current_theme()
    font = _resolve_font(t, style)
    kw.setdefault("bg", _inherit_bg(parent, t.page_bg))
    kw.setdefault("fg", t.text_primary)
    kw.setdefault("font", font)
    return tk.Label(parent, text=text, **kw)


def themed_button(
    parent: tk.Misc,
    text: str = "",
    command: Any = None,
    style: str = "secondary",
    **kw: Any,
) -> LabelButton:
    t = current_theme()
    sm = scale_manager()
    btn_cfg = _BUTTON_STYLES.get(style, _BUTTON_STYLES["secondary"])
    bg = getattr(t, btn_cfg["bg_prop"])
    fg = kw.pop("fg", getattr(t, btn_cfg["fg_prop"]))
    hover_bg = _derive_hover_bg(bg)
    kw.setdefault("padx", sm.s(t.pad_md))
    kw.setdefault("pady", sm.s(t.pad_xs))
    btn = LabelButton(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=hover_bg,
        activeforeground=fg,
        disabledforeground=t.btn_disabled_fg,
        disabledbackground=t.btn_disabled_bg,
        border_color=t.btn_border,
        font=t.font_body,
        **kw,
    )
    btn._style_name = style
    return btn


def themed_entry(parent: tk.Misc, **kw: Any) -> ThemedEntry:
    from src.panel.components.themed_entry import ThemedEntry as _ThemedEntry

    t = current_theme()
    kw.setdefault("bg", t.input_bg)
    kw.setdefault("fg", t.input_fg)
    kw.setdefault("insertbackground", t.text_primary)
    kw.setdefault("font", t.font_body)
    kw.setdefault("relief", "flat")
    kw.setdefault("bd", 0)
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("highlightcolor", t.accent_blue)
    kw.setdefault("highlightbackground", t.border_default)
    return _ThemedEntry(parent, **kw)


def themed_spinbox(parent: tk.Misc, **kw: Any) -> tk.Spinbox:
    t = current_theme()
    kw.setdefault("bg", t.input_bg)
    kw.setdefault("fg", t.input_fg)
    kw.setdefault("insertbackground", t.text_primary)
    kw.setdefault("font", t.font_body)
    kw.setdefault("relief", "solid")
    kw.setdefault("bd", 1)
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("highlightcolor", t.accent_blue)
    kw.setdefault("highlightbackground", t.border_default)
    button_bg = kw.pop("buttonbackground", t.bg_surface)
    return tk.Spinbox(parent, buttonbackground=button_bg, **kw)


def themed_checkbutton(
    parent: tk.Misc, text: str = "", **kw: Any
) -> ThemedCheckbox:
    from src.panel.components.themed_checkbox import ThemedCheckbox as _ThemedCheckbox

    t = current_theme()
    kw.setdefault("bg", _inherit_bg(parent, t.page_bg))
    return _ThemedCheckbox(parent, text=text, **kw)


def themed_radiobutton(
    parent: tk.Misc, text: str = "", **kw: Any
) -> ThemedRadio:
    from src.panel.components.themed_radio import ThemedRadio as _ThemedRadio

    t = current_theme()
    kw.setdefault("bg", _inherit_bg(parent, t.page_bg))
    return _ThemedRadio(parent, text=text, **kw)


def themed_labelframe(
    parent: tk.Misc, text: str = "", **kw: Any
) -> tk.LabelFrame:
    t = current_theme()
    kw.setdefault("bg", t.card_bg)
    kw.setdefault("fg", t.text_primary)
    kw.setdefault("font", t.font_section_title)
    kw.setdefault("bd", 1)
    kw.setdefault("relief", "solid")
    kw.setdefault("highlightbackground", t.border_strong)
    return tk.LabelFrame(parent, text=text, **kw)


def themed_separator(parent: tk.Misc, orient: str = "horizontal", **kw: Any) -> tk.Frame:
    t = current_theme()
    kw.setdefault("bg", t.separator_color)
    if orient == "vertical":
        kw.setdefault("width", 1)
    else:
        kw.setdefault("height", 1)
    return tk.Frame(parent, **kw)


def themed_danger_link(
    parent: tk.Misc, text: str, on_click: Callable[[], None],
) -> tk.Label:
    """创建红色危险操作链接（带 hover 变暗效果）。"""
    t = current_theme()
    sm = scale_manager()
    lbl = themed_label(
        parent, text=text,
        fg=t.accent_red, cursor="hand2",
        font=(t.font_family, sm.s(9)),
    )
    lbl.bind("<Button-1>", lambda _: on_click())
    lbl.bind("<Enter>", lambda _: lbl.configure(fg=t.accent_red_dim))
    lbl.bind("<Leave>", lambda _: lbl.configure(fg=t.accent_red))
    return lbl


# ── 主题递归应用 ──

_WIDGET_THEME_MAP: dict[str, dict[str, str]] = {
    "Frame": {"bg": "page_bg"},
    "Label": {"fg": "text_primary"},
    "Entry": {"bg": "input_bg", "fg": "input_fg", "insertbackground": "text_primary", "highlightcolor": "accent_blue", "highlightbackground": "border_default"},
    "Spinbox": {"bg": "input_bg", "fg": "input_fg"},
    "Checkbutton": {"bg": "page_bg", "fg": "text_primary", "selectcolor": "input_bg"},
    "Radiobutton": {"bg": "page_bg", "fg": "text_primary", "selectcolor": "input_bg"},
    "LabelFrame": {"bg": "card_bg", "fg": "text_primary"},
    "Toplevel": {"bg": "dialog_bg"},
}

_SKIP_WIDGETS = {"Canvas", "Treeview", "Scrollbar"}


def apply_theme_recursive(widget: tk.Widget, theme: CanvasTheme) -> None:
    """递归重新配置原生 tk 控件树的主题颜色

    跳过 Canvas/Treeview/Scrollbar。
    自定义控件（有 apply_theme 方法）调用其 apply_theme() 后跳过子树。
    """
    if not widget.winfo_exists():
        return
    if hasattr(widget, "apply_theme"):
        try:
            widget.apply_theme()
        except tk.TclError:
            pass
        return
    wclass = widget.winfo_class()
    if wclass not in _SKIP_WIDGETS and wclass in _WIDGET_THEME_MAP:
        try:
            cfg = {
                attr: getattr(theme, token)
                for attr, token in _WIDGET_THEME_MAP[wclass].items()
            }
            # Label 继承父级背景色，避免文字背景色块
            if wclass == "Label":
                parent = widget.nametowidget(widget.winfo_parent())
                cfg["bg"] = _inherit_bg(parent, theme.page_bg)
            widget.configure(**cfg)
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        apply_theme_recursive(child, theme)


def apply_to_toplevel(toplevel: tk.Toplevel) -> None:
    """一次性将当前主题应用到 Toplevel 对话框"""
    t = current_theme()
    toplevel.configure(bg=t.dialog_bg)
    apply_theme_recursive(toplevel, t)
