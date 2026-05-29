"""ThemedWidgets — 统一主题控件工厂

所有页面和对话框通过此模块创建控件，确保视觉一致性和主题切换支持。
"""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING, Any, Callable

from src.panel.canvas.theme import current_theme, CanvasTheme
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme.style_mappings import (
    _BUTTON_STYLES, resolve_font as _resolve_font,
    derive_hover_bg as _derive_hover_bg,
)

if TYPE_CHECKING:
    from src.panel.components.themed_entry import ThemedEntry
    from src.panel.components.themed_checkbox import ThemedCheckbox
    from src.panel.components.themed_radio import ThemedRadio
    from src.panel.components.dna_dropdown import DNADropdown


# LabelButton 向后兼容别名 — 惰性加载以避免循环导入
# widgets → dna_button → components/__init__ → profile_bar → widgets
LabelButton = None  # type: ignore[assignment]




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
    global LabelButton
    if LabelButton is None:
        from src.panel.components.dna_button import DNAButton
        LabelButton = DNAButton
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
        style=style,
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
    from src.panel.components.dna_toggle import DNAToggle

    t = current_theme()
    kw.setdefault("bg", _inherit_bg(parent, t.page_bg))
    return DNAToggle(parent, text=text, mode="checkbox", **kw)


def themed_radiobutton(
    parent: tk.Misc, text: str = "", **kw: Any
) -> ThemedRadio:
    from src.panel.components.dna_toggle import DNAToggle

    t = current_theme()
    kw.setdefault("bg", _inherit_bg(parent, t.page_bg))
    return DNAToggle(parent, text=text, mode="radio", **kw)


def themed_dropdown(
    parent: tk.Misc,
    options: list[tuple[str, str]] | None = None,
    **kw: Any,
) -> DNADropdown:
    from src.panel.components.dna_dropdown import DNADropdown

    return DNADropdown(parent, options=options, **kw)


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


def themed_paned_window(
    parent: tk.Misc, orient: str = tk.HORIZONTAL, **kw: Any,
) -> tk.PanedWindow:
    """创建统一风格的 PanedWindow，分隔条使用 separator_color 平坦线。"""
    t = current_theme()
    sm = scale_manager()
    kw.setdefault("opaqueresize", True)
    kw.setdefault("sashwidth", max(sm.s(6), 4))
    kw.setdefault("sashrelief", tk.FLAT)
    kw.setdefault("bd", 0)
    kw.setdefault("bg", t.separator_color)
    kw.setdefault("orient", orient)
    if "sashcursor" not in kw:
        kw["sashcursor"] = (
            "sb_h_double_arrow" if orient == tk.HORIZONTAL else "sb_v_double_arrow"
        )
    return tk.PanedWindow(parent, **kw)


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
    自定义控件（有 apply_theme 方法）调用其 apply_theme() 后停止，
    由该控件负责级联更新自身的子控件树。
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
            if wclass == "Label":
                parent = widget.nametowidget(widget.winfo_parent())
                cfg["bg"] = _inherit_bg(parent, theme.page_bg)
            widget.configure(**cfg)
        except tk.TclError:
            pass
    for child in widget.winfo_children():
        apply_theme_recursive(child, theme)


def cascade_theme(widget: tk.Widget) -> None:
    """复合控件 apply_theme 末尾调用，将主题级联到所有子控件。

    复合控件在自己的 apply_theme 中先更新自身和已知子控件的颜色，
    再调用此方法处理剩余的原生子控件。遇到有 apply_theme 的子控件
    会自动触发其 apply_theme（递归停止，由该控件接管自己的子树）。
    """
    th = current_theme()
    for child in widget.winfo_children():
        apply_theme_recursive(child, th)


def apply_to_toplevel(toplevel: tk.Toplevel) -> None:
    """一次性将当前主题应用到 Toplevel 对话框"""
    t = current_theme()
    toplevel.configure(bg=t.dialog_bg)
    apply_theme_recursive(toplevel, t)
