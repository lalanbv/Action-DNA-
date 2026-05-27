"""MinimapSettings — 小地图设置面板

齿轮图标弹出设置: 显示连线、显示节点标签、显示禁用节点、尺寸
"""

import tkinter as tk
from typing import Callable

from src.panel.canvas.theme import current_theme
from src.panel.canvas.scale import scale_manager
from src.utils.i18n import t


class MinimapSettings:
    """小地图设置面板"""

    __slots__ = (
        "_minimap_canvas", "_on_change",
        "_settings_win",
        "show_edges", "show_labels", "show_disabled", "size_mode",
    )

    def __init__(self, minimap_canvas: tk.Canvas, on_change: Callable[[], None]) -> None:
        self._minimap_canvas = minimap_canvas
        self._on_change = on_change
        self._settings_win: tk.Toplevel | None = None

        self.show_edges = True
        self.show_labels = True
        self.show_disabled = True
        self.size_mode: str = "medium"  # small / medium / large

    def toggle(self) -> None:
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.destroy()
            self._settings_win = None
            return

        theme = current_theme()
        sm = scale_manager()
        win = tk.Toplevel(self._minimap_canvas)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        # 防止主窗口抢占焦点导致弹窗被遮住
        win.grab_set()
        self._settings_win = win

        # 弹窗定位：齿轮按钮下方、左对齐 minimap 右边缘
        self._minimap_canvas.update_idletasks()
        mc_x = self._minimap_canvas.winfo_rootx()
        mc_y = self._minimap_canvas.winfo_rooty()
        mc_w = self._minimap_canvas.winfo_width()
        mc_h = self._minimap_canvas.winfo_height()
        popup_w = 180
        # 右对齐到 minimap 右边缘
        gx = mc_x + mc_w - popup_w
        # 弹出在 minimap 上方；若上方空间不足则放在下方
        gy = mc_y - 160
        if gy < 0:
            gy = mc_y + mc_h + 4
        screen_w = win.winfo_screenwidth()
        if gx + popup_w > screen_w:
            gx = screen_w - popup_w - 4
        if gx < 0:
            gx = 4
        win.geometry(f"+{gx}+{gy}")

        frame = tk.Frame(
            win, bg=theme.bg_surface,
            highlightbackground=theme.border_default, highlightthickness=1,
        )
        frame.pack(padx=1, pady=1)

        # 标题栏 + 关闭按钮
        header = tk.Frame(frame, bg=theme.panel_header_bg)
        header.pack(fill=tk.X)

        tk.Label(
            header, text=t("minimap.settings"),
            bg=theme.panel_header_bg, fg=theme.text_primary,
            font=(theme.font_family, sm.s(9), "bold"),
            padx=8, pady=4, anchor="w",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

        close_btn = tk.Label(
            header, text="✕",
            bg=theme.panel_header_bg, fg=theme.text_muted,
            font=(theme.font_family, sm.s(10), "bold"),
            cursor="hand2", padx=6, pady=2,
        )
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda _: self._close())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg=theme.accent_red))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg=theme.text_muted))

        self._add_check(frame, t("minimap.show_edges"), "show_edges", theme)
        self._add_check(frame, t("minimap.show_labels"), "show_labels", theme)
        self._add_check(frame, t("minimap.show_disabled"), "show_disabled", theme)

        sep = tk.Frame(frame, bg=theme.border_default, height=1)
        sep.pack(fill=tk.X, padx=4, pady=4)

        tk.Label(
            frame, text=t("minimap.size"),
            bg=theme.bg_surface, fg=theme.text_secondary,
            font=(theme.font_family, sm.s(8)), padx=8, anchor="w",
        ).pack(fill=tk.X)

        size_frame = tk.Frame(frame, bg=theme.bg_surface)
        size_frame.pack(fill=tk.X, padx=8, pady=(0, 6))

        # 用 Label 代替 Button：macOS 原生 Button 忽略 bg/fg，Label 无此限制
        for mode, label in [("small", "S"), ("medium", "M"), ("large", "L")]:
            is_active = self.size_mode == mode
            bg = theme.accent_blue if is_active else theme.btn_bg
            fg = theme.text_on_accent if is_active else theme.text_primary
            hover_bg = theme.accent_blue_dim if is_active else theme.btn_bg_hover
            border_c = theme.accent_blue if is_active else theme.border_default
            lbl = tk.Label(
                size_frame, text=label,
                bg=bg, fg=fg,
                font=(theme.font_family, sm.s(9), "bold"),
                cursor="hand2",
                padx=12, pady=4,
                relief="solid",
                bd=1,
                highlightbackground=border_c,
            )
            lbl.pack(side=tk.LEFT, padx=3, expand=True, fill=tk.BOTH, ipady=2)
            lbl.bind("<Button-1>", lambda e, m=mode: self._set_size(m))
            lbl.bind("<Enter>", lambda e, l=lbl, h=hover_bg: l.configure(bg=h))
            lbl.bind("<Leave>", lambda e, l=lbl, b=bg: l.configure(bg=b))

        win.bind("<Escape>", lambda _: self._close())
        win.focus_set()

    def _add_check(self, parent: tk.Frame, text: str, attr: str, theme) -> None:
        sm = scale_manager()
        var = tk.BooleanVar(value=getattr(self, attr))
        cb = tk.Checkbutton(
            parent, text=text, variable=var,
            bg=theme.bg_surface, fg=theme.text_primary,
            selectcolor=theme.bg_surface_dark,
            activebackground=theme.bg_surface,
            activeforeground=theme.text_primary,
            font=(theme.font_family, sm.s(9)),
            bd=0, highlightthickness=0,
            command=lambda: self._toggle_attr(attr, var.get()),
        )
        cb.pack(anchor="w", padx=8, pady=2)

    def _toggle_attr(self, attr: str, value: bool) -> None:
        setattr(self, attr, value)
        self._on_change()

    def _set_size(self, mode: str) -> None:
        self.size_mode = mode
        self._close()
        self._on_change()

    def _close(self) -> None:
        if self._settings_win and self._settings_win.winfo_exists():
            self._settings_win.grab_release()
            self._settings_win.destroy()
        self._settings_win = None

    def destroy(self) -> None:
        self._close()
