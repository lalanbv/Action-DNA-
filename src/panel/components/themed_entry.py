"""ThemedEntry — 带聚焦边框动画的 Entry 控件。

替代原生 tk.Entry，外层 Frame 充当可动画边框。
API 与 tk.Entry 完全兼容。
"""

from __future__ import annotations

import tkinter as tk
from typing import Any

from src.panel.canvas.theme import CanvasTheme, current_theme, mix_colors, theme_registry



class ThemedEntry(tk.Frame):
    """带聚焦边框动画的 Entry。"""

    _ANIM_STEPS = 6
    _ANIM_INTERVAL = 16  # ~60fps

    def __init__(self, parent: tk.Widget, **kw: Any) -> None:
        th = current_theme()
        self._border_default = th.border_default
        self._border_focus = th.accent_blue
        self._current_border = self._border_default
        self._anim_id: str | None = None

        border_w = kw.pop("highlightthickness", 1)
        entry_kw = {
            "bg": kw.pop("bg", th.input_bg),
            "fg": kw.pop("fg", th.input_fg),
            "insertbackground": kw.pop("insertbackground", th.text_primary),
            "font": kw.pop("font", th.font_body),
            "relief": kw.pop("relief", "flat"),
            "bd": kw.pop("bd", 0),
            "highlightthickness": 0,
        }

        for key in ("textvariable", "width", "show", "state", "readonlybackground",
                     "disabledbackground", "disabledforeground", "exportselection",
                     "justify", "xscrollcommand"):
            if key in kw:
                entry_kw[key] = kw.pop(key)

        super().__init__(parent, bg=self._border_default, padx=border_w, pady=border_w)
        self._entry = tk.Entry(self, **entry_kw)
        self._entry.pack(fill=tk.BOTH, expand=True)

        self._entry.bind("<FocusIn>", self._on_focus_in)
        self._entry.bind("<FocusOut>", self._on_focus_out)
        self.bind("<Destroy>", self._on_destroy)

        self._theme_reg_id = theme_registry().register(self)

    def _cancel_anim(self) -> None:
        if self._anim_id is not None:
            self.after_cancel(self._anim_id)
            self._anim_id = None

    def _animate_border(self, target: str) -> None:
        self._cancel_anim()
        start = self._current_border
        counter = [0]
        steps = self._ANIM_STEPS
        interval = self._ANIM_INTERVAL

        def step() -> None:
            counter[0] += 1
            t = min(counter[0] / steps, 1.0)
            color = mix_colors(start, target, t)
            if self.winfo_exists():
                self.configure(bg=color)
            self._current_border = color
            if counter[0] < steps and self.winfo_exists():
                self._anim_id = self.after(interval, step)
            else:
                self._current_border = target
                self._anim_id = None

        step()

    def _on_focus_in(self, _event: tk.Event) -> None:
        self._animate_border(self._border_focus)

    def _on_focus_out(self, _event: tk.Event) -> None:
        self._animate_border(self._border_default)

    def _on_destroy(self, _event: tk.Event) -> None:
        self._cancel_anim()
        theme_registry().unregister(self._theme_reg_id)

    def apply_theme(self, theme: CanvasTheme | None = None) -> None:
        if theme is None:
            theme = current_theme()
        if not self.winfo_exists():
            return
        self._border_default = theme.border_default
        self._border_focus = theme.accent_blue
        self._entry.configure(bg=theme.input_bg, fg=theme.input_fg,
                              insertbackground=theme.text_primary)
        if self._current_border not in (self._border_focus, self._border_default):
            self._current_border = self._border_default
        self.configure(bg=self._current_border)

    # ── tk.Entry API 透传 ──

    def insert(self, index: Any, text: str) -> None:
        self._entry.insert(index, text)

    def delete(self, first: Any, last: Any = None) -> None:
        self._entry.delete(first, last)

    def get(self) -> str:
        return self._entry.get()

    def configure(self, **kw: Any) -> None:
        entry_kw: dict[str, Any] = {}
        frame_kw: dict[str, Any] = {}
        for key in ("textvariable", "width", "show", "state", "font", "fg", "bg",
                     "insertbackground", "readonlybackground", "disabledbackground",
                     "disabledforeground", "justify", "exportselection"):
            if key in kw:
                entry_kw[key] = kw.pop(key)
        if "highlightcolor" in kw:
            self._border_focus = kw.pop("highlightcolor")
        if "highlightbackground" in kw:
            self._border_default = kw.pop("highlightbackground")
            frame_kw["bg"] = self._border_default
        if kw:
            frame_kw.update(kw)
        if entry_kw:
            self._entry.configure(**entry_kw)
        if frame_kw:
            super().configure(**frame_kw)

    config = configure

    def cget(self, key: str) -> Any:
        entry_keys = {"textvariable", "width", "show", "state", "font", "fg", "bg",
                      "insertbackground", "readonlybackground", "disabledbackground",
                      "disabledforeground", "justify", "exportselection"}
        if key in entry_keys:
            return self._entry.cget(key)
        if key == "highlightcolor":
            return self._border_focus
        if key == "highlightbackground":
            return self._border_default
        return super().cget(key)

    def bind(self, sequence=None, func=None, add=None):
        return self._entry.bind(sequence, func, add)

    def focus_set(self) -> None:
        self._entry.focus_set()
