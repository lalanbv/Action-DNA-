"""DNAButton — 统一主题按钮组件。

替代 LabelButton，继承 DNAWidget 获得自动主题注册。
支持样式（primary/secondary/danger/ghost）、尺寸（sm/md/lg）、
Toggle 模式、Loading 状态、Icon 支持。
"""

from __future__ import annotations

import tkinter as tk
import tkinter.font as tkfont
from typing import Any, Callable

from src.panel.canvas.theme import CanvasTheme, current_theme
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme.style_mappings import (
    _BUTTON_STYLES,
    derive_hover_bg as _derive_hover_bg,
    resolve_font as _resolve_font,
)
from src.panel.components.base import DNAWidget


def _measure_text_px(text: str, font: tuple | str) -> int:
    """Return pixel width of *text* rendered in *font*.

    Falls back to a heuristic when tkfont is unavailable
    (e.g. before the main-loop starts).
    """
    try:
        f = tkfont.Font(font=font)
        return f.measure(text)
    except Exception:
        if isinstance(font, tuple) and len(font) >= 2:
            size = font[1]
        else:
            size = 10
        w = 0
        for ch in text:
            code = ord(ch)
            # CJK Unified / CJK Symbols / Fullwidth forms
            if 0x4E00 <= code <= 0x9FFF or 0x3000 <= code <= 0x303F or 0xFF00 <= code <= 0xFFEF:
                w += size
            else:
                w += max(int(size * 0.6), 6)
        return w


def _calc_min_width(text: str, font: tuple | str, padx: int) -> int:
    """text_px + padx*2 + frame-border(2)."""
    return _measure_text_px(text, font) + padx * 2 + 2


class DNAButton(DNAWidget):
    """统一主题按钮组件。

    外层 tk.Frame（1px 边框）+ 内层 tk.Label（按钮面），macOS 兼容。
    """

    _SIZE_CONFIG: dict[str, dict[str, Any]] = {
        "sm": {"font_style": "small", "padx": 8, "pady": 2},
        "md": {"font_style": "body", "padx": 12, "pady": 4},
        "lg": {"font_style": "section", "padx": 16, "pady": 6},
    }

    def __init__(
        self,
        parent: tk.Widget,
        text: str = "",
        command: Callable[[], None] | None = None,
        *,
        style: str = "secondary",
        size: str = "md",
        icon: str | None = None,
        toggle: bool = False,
        toggle_state: bool = False,
        loading: bool = False,
        on_toggle: Callable[[bool], None] | None = None,
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
        th = current_theme()
        sm = scale_manager()

        self._command = command
        self._on_toggle_cb = on_toggle
        self._style_name: str = style
        self._size_name: str = size
        self._icon: str | None = icon
        self._is_toggle: bool = toggle
        self._toggle_state: bool = toggle_state
        self._loading: bool = loading
        self._original_text: str = text
        self._enabled: bool = True
        self._pressed: bool = False
        self._min_width: int = 0

        size_cfg = self._SIZE_CONFIG.get(size, self._SIZE_CONFIG["md"])
        resolved_style = self._resolve_effective_style()
        style_cfg = _BUTTON_STYLES.get(resolved_style, _BUTTON_STYLES["secondary"])

        _bg = getattr(th, style_cfg["bg_prop"]) if bg is None else bg
        _fg = getattr(th, style_cfg["fg_prop"]) if fg is None else fg
        _font = font if font is not None else _resolve_font(th, size_cfg["font_style"])
        _border_color = border_color or th.btn_border
        _disabled_fg = th.btn_disabled_fg if disabledforeground is None else disabledforeground
        _disabled_bg = th.btn_disabled_bg if disabledbackground is None else disabledbackground
        _active_bg = activebackground if activebackground is not None else _derive_hover_bg(_bg)
        _active_fg = activeforeground if activeforeground is not None else _fg
        _padx = sm.s(padx if padx is not None else size_cfg["padx"])
        _pady = sm.s(pady if pady is not None else size_cfg["pady"])

        self._bg = _bg
        self._fg = _fg
        self._active_bg = _active_bg
        self._active_fg = _active_fg
        self._disabled_fg = _disabled_fg
        self._disabled_bg = _disabled_bg
        self._border_color = _border_color
        self._ghost_bg_cache: str | None = None

        initial_state = kw.pop("state", None)
        for key in ("highlightbackground", "highlightthickness",
                     "highlightcolor", "takefocus"):
            kw.pop(key, None)

        super().__init__(parent, bg=self._border_color, padx=1, pady=1, cursor=cursor)

        display_text = self._build_display_text(text)

        self._label = tk.Label(
            self, text=display_text, bg=_bg, fg=_fg, font=_font,
            padx=_padx, pady=_pady, cursor=cursor,
        )
        self._label.pack(fill=tk.BOTH, expand=True)
        self._min_width = _calc_min_width(display_text, _font, _padx)

        self._label.bind("<Enter>", self._on_enter)
        self._label.bind("<Leave>", self._on_leave)
        self._label.bind("<ButtonPress-1>", self._on_press)
        self._label.bind("<ButtonRelease-1>", self._on_release)
        tk.Frame.bind(self, "<ButtonPress-1>", self._on_press)
        tk.Frame.bind(self, "<ButtonRelease-1>", self._on_release)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

        if initial_state in ("disabled", tk.DISABLED):
            self._enabled = False
            self._apply_disabled_state()

        if self._style_name == "ghost":
            self._setup_ghost_style(th)

    # ── 尺寸计算 ──

    @property
    def min_width(self) -> int:
        """Explicitly calculated minimum pixel width (text_px + padding + border)."""
        return self._min_width

    def _recalc_min_width(self) -> None:
        """Recalculate _min_width from current label text / font / padx."""
        text = self._label.cget("text")
        font = self._label.cget("font")
        padx = self._label.cget("padx") or 0
        self._min_width = _calc_min_width(text, font, padx)

    # ── 样式解析 ──

    def _resolve_effective_style(self) -> str:
        if self._is_toggle and self._toggle_state:
            return "primary"
        return self._style_name

    def _build_display_text(self, text: str) -> str:
        if self._loading:
            return "..."
        if self._icon:
            return f"{self._icon} {text}" if text else self._icon
        return text

    def _setup_ghost_style(self, th: CanvasTheme) -> None:
        self._ghost_bg_cache = self._bg
        self._bg = th.page_bg
        self._label.configure(bg=self._bg)
        super().configure(bg=self._bg)

    # ── 事件处理 ──

    def _on_enter(self, _event: tk.Event) -> None:
        if self._enabled and not self._loading:
            self._label.configure(bg=self._active_bg, fg=self._active_fg)

    def _on_leave(self, _event: tk.Event) -> None:
        if self._enabled:
            self._label.configure(bg=self._bg, fg=self._fg)

    def _on_press(self, _event: tk.Event) -> None:
        if self._enabled:
            self._pressed = True
            self._label.configure(bg=self._active_bg)

    def _on_release(self, _event: tk.Event) -> None:
        was_pressed = self._pressed
        self._pressed = False
        if not self._enabled:
            return
        self._label.configure(bg=self._bg, fg=self._fg)
        if was_pressed:
            if self._is_toggle:
                self._toggle_state = not self._toggle_state
                self._apply_toggle_visual()
                if self._on_toggle_cb:
                    self._on_toggle_cb(self._toggle_state)
            if self._command:
                self._command()

    def _apply_toggle_visual(self) -> None:
        th = current_theme()
        effective = self._resolve_effective_style()
        cfg = _BUTTON_STYLES.get(effective, _BUTTON_STYLES["secondary"])
        self._bg = getattr(th, cfg["bg_prop"])
        self._fg = getattr(th, cfg["fg_prop"])
        self._active_bg = _derive_hover_bg(self._bg)
        self._active_fg = self._fg
        self._border_color = th.btn_border
        if self._enabled:
            self._label.configure(bg=self._bg, fg=self._fg)
        super().configure(bg=self._border_color)

    def _apply_disabled_state(self) -> None:
        if self._disabled_bg:
            self._label.configure(bg=self._disabled_bg)
        self._label.configure(fg=self._disabled_fg, cursor="arrow")
        self.configure(cursor="arrow")

    # ── 公共 API ──

    def configure(self, **kw: Any) -> None:
        if "command" in kw:
            self._command = kw.pop("command")
        if "state" in kw:
            state = kw.pop("state")
            if state in ("disabled", tk.DISABLED):
                self._enabled = False
                self._apply_disabled_state()
            else:
                self._enabled = True
                self._label.configure(bg=self._bg, fg=self._fg, cursor="hand2")
                self.configure(cursor="hand2")
        if "style" in kw:
            self._style_name = kw.pop("style")
            self.set_style(self._style_name)
        if "size" in kw:
            self._size_name = kw.pop("size")
        if "toggle" in kw:
            self._is_toggle = kw.pop("toggle")
        if "toggle_state" in kw:
            new_state = kw.pop("toggle_state")
            if new_state != self._toggle_state:
                self._toggle_state = new_state
                self._apply_toggle_visual()
        if "loading" in kw:
            loading = kw.pop("loading")
            if loading != self._loading:
                self._loading = loading
                self._label.configure(text=self._build_display_text(self._original_text))
                if loading:
                    self._apply_disabled_state()
                elif self._enabled:
                    self._label.configure(bg=self._bg, fg=self._fg, cursor="hand2")
                    self.configure(cursor="hand2")
        if "on_toggle" in kw:
            self._on_toggle_cb = kw.pop("on_toggle")
        if "icon" in kw:
            self._icon = kw.pop("icon")

        label_kw: dict[str, Any] = {}
        frame_kw: dict[str, Any] = {}

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
            self._original_text = kw.pop("text")
            label_kw["text"] = self._build_display_text(self._original_text)
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

        for skip in ("highlightbackground", "highlightthickness",
                     "highlightcolor", "takefocus", "relief", "bd",
                     "disabledforeground", "disabledbackground"):
            kw.pop(skip, None)

        if label_kw:
            self._label.configure(**label_kw)
        if frame_kw:
            super().configure(**frame_kw)
        if kw:
            self._label.configure(**kw)

        # Recalculate min width when display-affecting properties change
        if any(k in label_kw for k in ("text", "font", "padx")):
            self._recalc_min_width()

    config = configure

    def cget(self, key: str) -> Any:
        if key == "state":
            return "disabled" if not self._enabled else "normal"
        if key == "text":
            return self._original_text
        if key == "toggle_state":
            return self._toggle_state
        if key == "style":
            return self._style_name
        if key in ("bg", "fg", "font", "padx", "pady", "cursor"):
            return self._label.cget(key)
        return super().cget(key)

    def set_style(self, style_name: str) -> None:
        th = current_theme()
        cfg = _BUTTON_STYLES.get(style_name, _BUTTON_STYLES["secondary"])
        self._bg = getattr(th, cfg["bg_prop"])
        self._fg = getattr(th, cfg["fg_prop"])
        self._active_bg = _derive_hover_bg(self._bg)
        self._active_fg = self._fg
        self._border_color = th.btn_border
        if self._enabled:
            self._label.configure(bg=self._bg, fg=self._fg)
        super().configure(bg=self._border_color)

    def set_loading(self, loading: bool) -> None:
        self.configure(loading=loading)

    def get_toggle_state(self) -> bool:
        return self._toggle_state

    def set_toggle_state(self, state: bool) -> None:
        self.configure(toggle_state=state)

    def bind(self, sequence=None, func=None, add=None):
        if sequence and sequence.startswith("<Button"):
            self._label.bind(sequence, func, add)
            return super().bind(sequence, func, add)
        return super().bind(sequence, func, add)

    # ── 主题 ──

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        if not self.winfo_exists():
            return

        effective = self._resolve_effective_style()
        cfg = _BUTTON_STYLES.get(effective, _BUTTON_STYLES["secondary"])
        self._bg = getattr(theme, cfg["bg_prop"])
        self._fg = getattr(theme, cfg["fg_prop"])
        self._active_bg = _derive_hover_bg(self._bg)
        self._active_fg = self._fg
        self._border_color = theme.btn_border
        self._disabled_fg = theme.btn_disabled_fg
        self._disabled_bg = theme.btn_disabled_bg

        if self._style_name == "ghost":
            self._bg = theme.page_bg

        if self._enabled:
            self._label.configure(bg=self._bg, fg=self._fg)
        else:
            if self._disabled_bg:
                self._label.configure(bg=self._disabled_bg)
            self._label.configure(fg=self._disabled_fg)
        super().configure(bg=self._border_color)
        self._recalc_min_width()
