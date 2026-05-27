"""FloatingZoomControls — 底部居中浮动缩放工具栏

风格: 毛玻璃半透明 + 圆角 + 阴影边框
布局: [-] 100% [+] [适应] [1:1]
百分比可点击弹出预设: 25%, 50%, 75%, 100%, 150%, 200%

使用 tk.Label 模拟按钮，因为 macOS tk.Button 不支持自定义 bg/fg。
"""

import tkinter as tk

from src.panel.canvas.theme import current_theme
from src.panel.canvas.scale import scale_manager
from src.utils.i18n import t


class FloatingZoomControls:
    """浮动缩放控件栏"""

    __slots__ = (
        "_parent", "_on_zoom_in", "_on_zoom_out", "_on_zoom_reset",
        "_on_zoom_to_fit", "_on_zoom_to", "_get_zoom",
        "_frame", "_zoom_label", "_preset_win", "_buttons",
        "_reposition_after_id", "_configure_bind_id", "_shadow",
    )

    def __init__(
        self,
        parent: tk.Widget,
        on_zoom_in: callable,
        on_zoom_out: callable,
        on_zoom_reset: callable,
        on_zoom_to_fit: callable,
        on_zoom_to: callable,
        get_zoom: callable,
    ) -> None:
        self._parent = parent
        self._on_zoom_in = on_zoom_in
        self._on_zoom_out = on_zoom_out
        self._on_zoom_reset = on_zoom_reset
        self._on_zoom_to_fit = on_zoom_to_fit
        self._on_zoom_to = on_zoom_to
        self._get_zoom = get_zoom
        self._preset_win: tk.Toplevel | None = None
        self._frame: tk.Frame | None = None
        self._buttons: list[tk.Label] = []
        self._reposition_after_id: str | None = None

        self._build()
        self._do_reposition()
        self._configure_bind_id = parent.bind("<Configure>", lambda _: self._schedule_reposition())

    # ── 构建 ────────────────────────────────────────────────

    @staticmethod
    def _bar_colors(theme) -> dict:
        return {
            "frame_bg": theme.btn_bg,
            "frame_border": theme.border_strong,
            "btn_bg": theme.btn_bg,
            "btn_fg": theme.text_primary,
            "btn_active_bg": theme.btn_bg_hover,
        }

    def _make_btn(
        self, parent: tk.Widget, text: str, command: callable,
        bg: str, fg: str, hover_bg: str, font: tuple, padx: int = 8,
    ) -> tk.Label:
        lbl = tk.Label(
            parent, text=text, bg=bg, fg=fg,
            font=font, cursor="hand2", padx=padx, pady=2,
        )
        lbl.bind("<Button-1>", lambda _: command())
        lbl.bind("<Enter>", lambda _: lbl.configure(bg=hover_bg))
        lbl.bind("<Leave>", lambda _: lbl.configure(bg=bg))
        return lbl

    def _build(self) -> None:
        theme = current_theme()
        c = self._bar_colors(theme)

        # 阴影层
        self._shadow = tk.Frame(
            self._parent,
            bg=theme.shadow_color,
            highlightthickness=0,
            bd=0,
        )

        self._frame = tk.Frame(
            self._parent,
            bg=c["frame_bg"],
            highlightbackground=c["frame_border"],
            highlightthickness=1,
            bd=0,
        )

        sm = scale_manager()
        btn_font = (theme.font_family, sm.s(11))
        small_font = (theme.font_family, sm.s(9))

        btn_out = self._make_btn(
            self._frame, "−", self._on_zoom_out,
            c["btn_bg"], c["btn_fg"], c["btn_active_bg"], btn_font,
        )
        btn_out.pack(side=tk.LEFT)
        self._buttons.append(btn_out)

        self._zoom_label = tk.Label(
            self._frame,
            text="100%",
            bg=c["frame_bg"],
            fg=c["btn_fg"],
            font=(theme.font_family, sm.s(10), "bold"),
            cursor="hand2",
            padx=6,
            pady=2,
        )
        self._zoom_label.pack(side=tk.LEFT)
        self._zoom_label.bind("<Button-1>", lambda _: self._toggle_presets())

        btn_in = self._make_btn(
            self._frame, "+", self._on_zoom_in,
            c["btn_bg"], c["btn_fg"], c["btn_active_bg"], btn_font,
        )
        btn_in.pack(side=tk.LEFT)
        self._buttons.append(btn_in)

        sep = tk.Frame(self._frame, bg=theme.border_default, width=1)
        sep.pack(side=tk.LEFT, fill=tk.Y, padx=4, pady=4)

        btn_fit = self._make_btn(
            self._frame, t("zoom.fit"), self._on_zoom_to_fit,
            c["btn_bg"], c["btn_fg"], c["btn_active_bg"], small_font, padx=6,
        )
        btn_fit.pack(side=tk.LEFT)
        self._buttons.append(btn_fit)

        btn_reset = self._make_btn(
            self._frame, "1:1", self._on_zoom_reset,
            c["btn_bg"], c["btn_fg"], c["btn_active_bg"], small_font, padx=6,
        )
        btn_reset.pack(side=tk.LEFT)
        self._buttons.append(btn_reset)

    # ── 预设弹窗 ────────────────────────────────────────────

    def _toggle_presets(self) -> None:
        if self._preset_win and self._preset_win.winfo_exists():
            self._preset_win.destroy()
            self._preset_win = None
            return

        theme = current_theme()
        c = self._bar_colors(theme)
        sm = scale_manager()

        win = tk.Toplevel(self._parent)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        self._preset_win = win

        lx = self._zoom_label.winfo_rootx()
        ly = self._zoom_label.winfo_rooty() - 2
        win.geometry(f"+{lx}+{ly}")

        frame = tk.Frame(
            win, bg=c["frame_bg"],
            highlightbackground=c["frame_border"],
            highlightthickness=1,
        )
        frame.pack()

        presets = [0.25, 0.50, 0.75, 1.00, 1.50, 2.00]

        for val in presets:
            text = f"{int(val * 100)}%"
            lbl = tk.Label(
                frame,
                text=text,
                bg=c["btn_bg"],
                fg=c["btn_fg"],
                cursor="hand2",
                font=(theme.font_family, sm.s(9)),
                padx=12,
                pady=3,
            )
            lbl.pack(fill=tk.X)
            lbl.bind("<Button-1>", lambda _, v=val: self._select_preset(v))
            lbl.bind("<Enter>", lambda _, l=lbl: l.configure(bg=c["btn_active_bg"]))
            lbl.bind("<Leave>", lambda _, l=lbl: l.configure(bg=c["btn_bg"]))

        win.bind("<FocusOut>", lambda _: self._close_presets())
        win.bind("<Escape>", lambda _: self._close_presets())
        win.focus_set()

    def _select_preset(self, val: float) -> None:
        self._close_presets()
        self._on_zoom_to(val)

    def _close_presets(self) -> None:
        if self._preset_win and self._preset_win.winfo_exists():
            self._preset_win.destroy()
        self._preset_win = None

    # ── 定位 ────────────────────────────────────────────────

    def _schedule_reposition(self) -> None:
        if self._reposition_after_id is not None:
            return
        self._reposition_after_id = self._parent.after_idle(self._do_reposition)

    def _do_reposition(self) -> None:
        self._reposition_after_id = None
        if not self._frame or not self._frame.winfo_exists():
            return
        pw = self._parent.winfo_width()
        ph = self._parent.winfo_height()
        fw = self._frame.winfo_reqwidth()
        fh = self._frame.winfo_reqheight()
        x = max((pw - fw) // 2, 0)
        y = max(ph - fh - 8, 0)
        # 阴影偏移
        if hasattr(self, "_shadow") and self._shadow.winfo_exists():
            self._shadow.place(x=x + 2, y=y + 2, width=fw, height=fh)
        self._frame.place(x=x, y=y)

    # ── 外部接口 ────────────────────────────────────────────

    def update_zoom_display(self) -> None:
        zoom = self._get_zoom()
        if self._zoom_label and self._zoom_label.winfo_exists():
            self._zoom_label.configure(text=f"{zoom:.0%}")

    def apply_theme(self) -> None:
        if not self._frame or not self._frame.winfo_exists():
            return
        theme = current_theme()
        if hasattr(self, "_shadow") and self._shadow.winfo_exists():
            self._shadow.configure(bg=theme.shadow_color)
        c = self._bar_colors(theme)
        self._frame.configure(bg=c["frame_bg"], highlightbackground=c["frame_border"])
        for btn in self._buttons:
            if btn.winfo_exists():
                btn.configure(bg=c["btn_bg"], fg=c["btn_fg"])
                btn.bind("<Enter>", lambda _: btn.configure(bg=c["btn_active_bg"]))
                btn.bind("<Leave>", lambda _: btn.configure(bg=c["btn_bg"]))
        if self._zoom_label and self._zoom_label.winfo_exists():
            self._zoom_label.configure(bg=c["frame_bg"], fg=c["btn_fg"])
        for child in self._frame.winfo_children():
            if isinstance(child, tk.Frame) and child not in self._buttons:
                child.configure(bg=theme.border_default)

    def destroy(self) -> None:
        self._close_presets()
        if self._reposition_after_id is not None:
            try:
                self._parent.after_cancel(self._reposition_after_id)
            except Exception:
                pass
            self._reposition_after_id = None
        try:
            self._parent.unbind("<Configure>", self._configure_bind_id)
        except Exception:
            pass
        if hasattr(self, "_shadow") and self._shadow.winfo_exists():
            self._shadow.destroy()
        if self._frame and self._frame.winfo_exists():
            self._frame.destroy()
        self._frame = None
