"""ScaleManager — 自适应缩放 + 响应式断点 + 滚动容器

核心架构：
- ScaleManager 单例：DPI 感知缩放因子，所有尺寸的单一真相来源
- Breakpoint 枚举：窗口宽度断点（COMPACT / NORMAL / WIDE）
- ScrollableFrame：可复用的垂直滚动容器
"""

import tkinter as tk
from enum import Enum
from tkinter import ttk

from src.utils.platform import IS_MACOS, IS_LINUX


class Breakpoint(Enum):
    COMPACT = "compact"  # 窗口宽度 < 900px
    NORMAL = "normal"  # 900-1200px
    WIDE = "wide"  # > 1200px


# 断点阈值
_COMPACT_THRESHOLD = 900
_WIDE_THRESHOLD = 1200

# 参考 DPI
_BASE_DPI = 96.0


class ScaleManager:
    """DPI 感知缩放管理器 — 单例模式

    使用方式：
        sm = scale_manager()
        sm.detect(root)          # 在 app 启动时调用一次
        pixel = sm.s(24)         # 24 * scale_factor
        font_sz = sm.s_font(10)  # max(8, int(10 * scale_factor))
        bp = sm.breakpoint()     # Breakpoint.NORMAL
    """

    def __init__(self) -> None:
        self._scale_factor: float = 1.0
        self._breakpoint: Breakpoint = Breakpoint.NORMAL

    def detect(self, root: tk.Tk) -> None:
        """从 root 窗口检测 DPI 缩放因子，启动时调用一次。

        macOS Retina → ~2.0, Windows 125% → ~1.25, 标准 → 1.0
        """
        try:
            root.update_idletasks()
            dpi = root.winfo_fpixels("1i")
            self._scale_factor = dpi / _BASE_DPI
        except Exception:
            self._scale_factor = 1.0

        # macOS Retina 特殊处理：tkinter 报告的 dpi 可能不是 2.0
        if IS_MACOS:
            try:
                scaling = root.tk.call("tk", "scaling")
                if scaling > 1.5 and self._scale_factor < 1.5:
                    self._scale_factor = scaling
            except Exception:
                pass

    @property
    def scale_factor(self) -> float:
        return self._scale_factor

    def s(self, value: int) -> int:
        """缩放像素值。标准 DPI 返回原值。"""
        return int(value * self._scale_factor)

    def s_font(self, base_size: int) -> int:
        """返回字体大小（不额外缩放）。

        tkinter 通过 tk.scaling 已经处理 DPI 感知的字体渲染，
        如果这里再乘 scale_factor 会导致双重缩放，字体模糊。
        仅保证最小 8pt。
        """
        return max(8, base_size)

    def breakpoint(self) -> Breakpoint:
        return self._breakpoint

    def update_breakpoint(self, width: int) -> None:
        """根据窗口宽度更新断点，由 <Configure> 事件调用。"""
        if width < _COMPACT_THRESHOLD:
            self._breakpoint = Breakpoint.COMPACT
        elif width > _WIDE_THRESHOLD:
            self._breakpoint = Breakpoint.WIDE
        else:
            self._breakpoint = Breakpoint.NORMAL

    def dialog_size(
        self,
        parent: tk.Widget,
        w_ratio: float,
        h_ratio: float,
        max_w: int = 600,
        max_h: int = 600,
    ) -> tuple[int, int]:
        """计算对话框尺寸：基于父窗口比例，上限为 max_w/max_h。"""
        try:
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            if pw < 100 or ph < 100:
                pw = parent.winfo_screenwidth()
                ph = parent.winfo_screenheight()
        except Exception:
            pw, ph = 800, 600

        w = min(max_w, max(300, int(pw * w_ratio)))
        h = min(max_h, max(200, int(ph * h_ratio)))
        return w, h


class ScrollableFrame(tk.Frame):
    """可复用的垂直滚动容器。

    用法：
        sf = ScrollableFrame(parent, bg=theme.page_bg)
        sf.pack(fill=tk.BOTH, expand=True)
        themed_label(sf.inner, text="Hello")
    """

    def __init__(self, parent: tk.Widget, **kw) -> None:
        super().__init__(parent, **kw)

        self._canvas = tk.Canvas(self, highlightthickness=0, bd=0)
        self._v_scroll = ttk.Scrollbar(
            self, orient=tk.VERTICAL, command=self._canvas.yview
        )

        self._canvas.configure(yscrollcommand=self._v_scroll.set)
        self._v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._inner = tk.Frame(self._canvas, **kw)
        self._window_id = self._canvas.create_window(
            (0, 0), window=self._inner, anchor=tk.NW
        )

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_mousewheel()

    @property
    def inner(self) -> tk.Frame:
        return self._inner

    def _on_inner_configure(self, event: tk.Event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        self._canvas.itemconfigure(self._window_id, width=event.width)

    def _bind_mousewheel(self) -> None:
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event: tk.Event) -> None:
        if IS_LINUX:
            self.bind_all("<Button-4>", self._on_mousewheel_linux)
            self.bind_all("<Button-5>", self._on_mousewheel_linux)
        else:
            self.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_leave(self, _event: tk.Event) -> None:
        if IS_LINUX:
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        else:
            self.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if IS_MACOS:
            self._canvas.yview_scroll(-event.delta, "units")
        else:
            self._canvas.yview_scroll(-event.delta // 120, "units")

    def _on_mousewheel_linux(self, event: tk.Event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")

    def set_bg(self, color: str) -> None:
        """主题切换时更新背景色。"""
        self.configure(bg=color)
        self._canvas.configure(bg=color)
        self._inner.configure(bg=color)


# ── 模块级单例 ──────────────────────────────────────────────

_manager = ScaleManager()


def scale_manager() -> ScaleManager:
    return _manager
