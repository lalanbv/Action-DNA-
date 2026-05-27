"""toolbar_tooltip — 主题化工具提示基类与工具栏实现。

BaseTooltip 提供 Toplevel 创建、定位、屏幕边界裁剪等公共逻辑，
ToolbarTooltip（widget 悬停绑定）和 CanvasTooltip（手动 schedule）共享基类。
"""

import tkinter as tk

from src.panel.canvas.theme import current_theme
from src.utils.text import truncate

# ── 公共常量 ───────────────────────────────────────────

_PAD_X = 8
_PAD_Y = 5
_BORDER_MARGIN = 8
_FONT_SIZE = 9
_TEXT_TRUNCATE = 80


class BaseTooltip:
    """工具提示基类 — 管理 Toplevel 生命周期与屏幕定位。"""

    def __init__(self, anchor: tk.Widget) -> None:
        self._anchor = anchor
        self._tip_window: tk.Toplevel | None = None
        self._after_id: str | None = None

    # ── 子类可覆盖 ──────────────────────────────────

    def _build_content(self, frame: tk.Frame, th) -> None:
        """在 frame 内构建提示内容，子类覆盖。"""

    def _position(self) -> tuple[int, int]:
        """返回 (root_x, root_y) 屏幕坐标，子类覆盖。"""

    # ── 公共 API ────────────────────────────────────

    def _schedule(self, delay_ms: int) -> None:
        self._cancel()
        self._after_id = self._anchor.after(delay_ms, self._display)

    def _cancel(self) -> None:
        if self._after_id is not None:
            try:
                self._anchor.after_cancel(self._after_id)
            except (tk.TclError, ValueError):
                pass
            self._after_id = None

    def _hide(self) -> None:
        if self._tip_window is not None:
            try:
                self._tip_window.destroy()
            except tk.TclError:
                pass
            self._tip_window = None

    def destroy(self) -> None:
        self._cancel()
        self._hide()

    # ── 内部 ────────────────────────────────────────

    def _display(self) -> None:
        self._after_id = None
        if not self._anchor.winfo_exists():
            return
        self._hide()

        th = current_theme()
        tw = tk.Toplevel(self._anchor)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg=th.border_default)

        frame = tk.Frame(tw, bg=th.card_bg, padx=_PAD_X, pady=_PAD_Y)
        frame.pack(fill=tk.BOTH, expand=True)

        self._build_content(frame, th)

        x, y = self._position()
        sw = self._anchor.winfo_screenwidth()
        sh = self._anchor.winfo_screenheight()
        tw.update_idletasks()
        tw_w, tw_h = tw.winfo_reqwidth(), tw.winfo_reqheight()
        if x + tw_w > sw - _BORDER_MARGIN:
            x = sw - tw_w - _BORDER_MARGIN
        if y + tw_h > sh - _BORDER_MARGIN:
            y = y - tw_h - 4
        if x < 0:
            x = 0
        if y < 0:
            y = 0
        tw.wm_geometry(f"+{x}+{y}")
        self._tip_window = tw


# ── 工具栏 Tooltip ─────────────────────────────────────

class ToolbarTooltip(BaseTooltip):
    """轻量级工具提示，鼠标悬停延迟显示，离开立即隐藏。"""

    _registry: list["ToolbarTooltip"] = []

    def __init__(
        self,
        widget: tk.Widget,
        text: str,
        shortcut: str = "",
        delay: int = 600,
    ) -> None:
        super().__init__(widget)
        self._text = text
        self._shortcut = shortcut
        self._delay = delay

        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_destroy, add="+")
        ToolbarTooltip._registry.append(self)

    def _build_content(self, frame: tk.Frame, th) -> None:
        label = tk.Label(
            frame, text=self._text, bg=th.card_bg, fg=th.text_primary,
            font=("Arial", _FONT_SIZE), anchor="w", justify="left",
        )
        label.pack(fill=tk.X)

        if self._shortcut:
            shortcut_label = tk.Label(
                frame, text=self._shortcut, bg=th.card_bg, fg=th.accent_blue,
                font=("Arial", 8), anchor="w",
            )
            shortcut_label.pack(fill=tk.X)

    def _position(self) -> tuple[int, int]:
        x = self._anchor.winfo_rootx() + 15
        y = self._anchor.winfo_rooty() + self._anchor.winfo_height() + 6
        return x, y

    # ── 事件绑定 ────────────────────────────────────

    def _on_enter(self, _event: tk.Event) -> None:
        self._schedule(self._delay)

    def _on_leave(self, _event: tk.Event) -> None:
        self._cancel()
        self._hide()

    def _on_destroy(self, _event: tk.Event) -> None:
        self.destroy()

    # ── 公共 API ────────────────────────────────────

    def update_text(self, text: str, shortcut: str = "") -> None:
        self._text = text
        if shortcut:
            self._shortcut = shortcut

    def destroy(self) -> None:
        super().destroy()
        if self in ToolbarTooltip._registry:
            ToolbarTooltip._registry.remove(self)

    @classmethod
    def cleanup_registry(cls) -> None:
        """Remove tooltips whose widgets no longer exist."""
        cls._registry = [
            t for t in cls._registry
            if t._anchor.winfo_exists()
        ]


# ── 画布 Tooltip ───────────────────────────────────────

class CanvasTooltip(BaseTooltip):
    """画布节点悬浮提示 — 手动 schedule(text, x, y)。"""

    _OFFSET_X = 16
    _OFFSET_Y = 20
    _WRAP_LENGTH = 280

    def __init__(self, canvas: tk.Canvas, delay: int = 400) -> None:
        super().__init__(canvas)
        self._delay = delay
        self._pending_text: str = ""
        self._pending_x: int = 0
        self._pending_y: int = 0

    def schedule(self, text: str, screen_x: int, screen_y: int) -> None:
        self._pending_text = text
        self._pending_x = screen_x
        self._pending_y = screen_y
        self._cancel()
        self._hide()
        self._schedule(self._delay)

    def cancel(self) -> None:
        self._cancel()
        self._hide()

    def _build_content(self, frame: tk.Frame, th) -> None:
        text = self._pending_text
        display_text = truncate(text, _TEXT_TRUNCATE)
        label = tk.Label(
            frame, text=display_text, bg=th.card_bg, fg=th.text_primary,
            font=(th.font_family, _FONT_SIZE), anchor="w", justify="left",
            wraplength=self._WRAP_LENGTH,
        )
        label.pack(fill=tk.X)

    def _position(self) -> tuple[int, int]:
        x = self._anchor.winfo_rootx() + self._pending_x + self._OFFSET_X
        y = self._anchor.winfo_rooty() + self._pending_y + self._OFFSET_Y
        return x, y
