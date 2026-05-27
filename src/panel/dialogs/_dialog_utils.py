"""对话框内部共享工具函数。"""

import tkinter as tk

from src.panel.canvas.scale import scale_manager


def make_dialog(
    parent: tk.Widget,
    title: str,
    width: int = 520,
    height: int = 520,
) -> tk.Toplevel:
    """创建标准对话框窗口（DPI 感知、居中、模态）。"""
    sm = scale_manager()
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dw, dh = sm.dialog_size(
        parent, 0.55, 0.65,
        max_w=sm.s(width), max_h=sm.s(height),
    )
    dlg.geometry(f"{dw}x{dh}")
    dlg.resizable(True, True)
    dlg.transient(parent)
    dlg.grab_set()
    return dlg
