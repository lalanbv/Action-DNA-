"""ResizableDialog — 通用可调整大小对话框基类

替代页面中散布的原始 tk.Toplevel 对话框。
提供 DPI 感知尺寸、父窗口居中、OK/Cancel 按钮和主题支持。
"""

import tkinter as tk
from abc import ABC, abstractmethod

from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme
from src.panel.widgets import themed_button, themed_frame
from src.utils.i18n import t


class ResizableDialog(tk.Toplevel, ABC):
    """通用可调整大小对话框基类。

    子类实现 _build_content(content_frame) 构建内容区域。
    可选覆盖 _on_confirm() 自定义确认逻辑。

    Args:
        parent: 父窗口
        title: 对话框标题
        width: 基准宽度（base px）
        height: 基准高度（base px）
    """

    def __init__(
        self,
        parent: tk.Widget,
        title: str,
        width: int = 450,
        height: int = 400,
    ) -> None:
        super().__init__(parent)
        th = current_theme()
        self.title(title)
        self.configure(bg=th.dialog_bg)

        sm = scale_manager()
        dw, dh = sm.dialog_size(
            parent, 0.55, 0.65,
            max_w=sm.s(width), max_h=sm.s(height),
        )
        self.geometry(f"{dw}x{dh}")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()
        self._center_on_parent(parent)

        self._content_frame = themed_frame(self)
        self._content_frame.pack(fill=tk.BOTH, expand=True, padx=th.pad_md, pady=th.pad_md)

        self._build_content(self._content_frame)

        btn_frame = themed_frame(self)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=th.pad_md, pady=(0, th.pad_sm))
        themed_button(
            btn_frame, text=t("common.ok"), command=self._on_confirm, style="primary",
        ).pack(side=tk.RIGHT, padx=th.pad_xs)
        themed_button(
            btn_frame, text=t("common.cancel"), command=self.destroy,
        ).pack(side=tk.RIGHT, padx=th.pad_xs)

    @abstractmethod
    def _build_content(self, content_frame: tk.Frame) -> None:
        """构建对话框内容区域。"""

    def _on_confirm(self) -> None:
        """确认按钮回调。子类可覆盖以添加验证逻辑。"""
        self.destroy()

    def _center_on_parent(self, parent: tk.Widget) -> None:
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px + (pw - w) // 2}+{py + (ph - h) // 2}")
