"""ToastManager — 应用内轻量通知弹窗。

出现在主窗口右上角，自动消失（默认 3s），支持堆叠。
级别颜色：info=蓝/success=绿/warning=黄/error=红。
"""

import tkinter as tk

from src.panel.canvas.theme import current_theme
from src.panel.canvas.scale import scale_manager

_LEVEL_COLORS = {
    "info": "accent_blue",
    "success": "accent_green",
    "warning": "accent_orange",
    "error": "accent_red",
}

_TOAST_DURATION_MS = 3000


class ToastNotification(tk.Toplevel):
    """单条 toast 通知。"""

    def __init__(
        self,
        parent: tk.Tk,
        message: str,
        level: str = "info",
        duration_ms: int = _TOAST_DURATION_MS,
    ) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = scale_manager()

        self.overrideredirect(True)
        self.attributes("-topmost", True)

        accent = getattr(th, _LEVEL_COLORS.get(level, "accent_blue"), th.accent_blue)

        outer = tk.Frame(self, bg=accent, padx=1, pady=1)
        outer.pack(fill=tk.BOTH, expand=True)

        inner = tk.Frame(outer, bg=th.bg_surface, padx=sm.s(10), pady=sm.s(6))
        inner.pack(fill=tk.BOTH, expand=True)

        bar = tk.Frame(inner, bg=accent, width=sm.s(3))
        bar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, sm.s(8)))

        label = tk.Label(
            inner, text=message,
            font=(th.font_family, sm.s(10)),
            bg=th.bg_surface, fg=th.text_primary,
            wraplength=sm.s(280),
            justify=tk.LEFT,
            anchor=tk.W,
        )
        label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.update_idletasks()
        parent.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width() - self.winfo_width() - sm.s(16)
        py = parent.winfo_y() + sm.s(40)
        self.geometry(f"+{px}+{py}")

        self.after(duration_ms, self._fade_out)

    def _fade_out(self) -> None:
        try:
            self.destroy()
        except tk.TclError:
            pass


class ToastManager:
    """管理 toast 通知的堆叠显示。"""

    def __init__(self, root: tk.Tk) -> None:
        self._root = root
        self._active: list[ToastNotification] = []
        self._stack_offset = 0

    def show(self, message: str, level: str = "info", duration_ms: int = _TOAST_DURATION_MS) -> None:
        toast = ToastNotification(self._root, message, level, duration_ms)
        sm = scale_manager()

        if self._active:
            last = self._active[-1]
            try:
                x = last.winfo_x()
                y = last.winfo_y() + last.winfo_height() + sm.s(4)
                toast.geometry(f"+{x}+{y}")
            except tk.TclError:
                pass

        self._active.append(toast)
        self._stack_offset += 1

        def on_destroy(event=None):
            if toast in self._active:
                self._active.remove(toast)
                self._stack_offset = max(0, self._stack_offset - 1)

        toast.bind("<Destroy>", on_destroy)
