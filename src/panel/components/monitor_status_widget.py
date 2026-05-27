"""MonitorStatusWidget — 实时 monitor 状态卡片条。

水平排列的 monitor 状态卡片，每个显示：
- 彩色左边框（绿=运行/黄=暂停/红=错误/灰=空闲）
- 状态圆点（12x12）
- Monitor 名称
- 触发次数 badge
- 上次触发时间（相对时间）
- handling 状态动态提示
"""

import time
import tkinter as tk

from src.panel.canvas.theme import current_theme
from src.panel.canvas.scale import scale_manager


_STATUS_COLORS = {
    "idle": "status_ready",
    "running": "status_running",
    "paused": "status_paused",
    "error": "status_error",
    "handling": "status_running",
}

_BORDER_WIDTH = 3


class MonitorCard(tk.Frame):
    """单个 monitor 的状态卡片。"""

    def __init__(self, parent: tk.Widget, monitor_name: str) -> None:
        th = current_theme()
        sm = scale_manager()
        super().__init__(
            parent,
            bg=th.bg_surface,
            highlightbackground=th.border_default,
            highlightthickness=1,
            padx=sm.s(8),
            pady=sm.s(5),
        )

        self._status = "idle"
        self._trigger_count = 0
        self._last_trigger_time = 0.0

        # 左侧彩色边框
        dot_color = getattr(th, _STATUS_COLORS["idle"])
        self._border_canvas = tk.Canvas(
            self, width=_BORDER_WIDTH, height=sm.s(20),
            bg=dot_color, highlightthickness=0,
        )
        self._border_canvas.pack(side=tk.LEFT, padx=(0, sm.s(4)))

        self._dot = tk.Canvas(
            self, width=sm.s(12), height=sm.s(12),
            bg=th.bg_surface, highlightthickness=0,
        )
        self._dot.pack(side=tk.LEFT, padx=(0, sm.s(4)))
        self._dot_oval = self._dot.create_oval(
            1, 1, sm.s(12) - 1, sm.s(12) - 1,
            fill=dot_color, outline="",
        )

        self._name_label = tk.Label(
            self, text=monitor_name,
            font=(th.font_family, sm.s(11)),
            bg=th.bg_surface, fg=th.text_secondary,
        )
        self._name_label.pack(side=tk.LEFT)

        self._badge = tk.Label(
            self, text="0",
            font=(th.font_family, sm.s(9)),
            bg=th.accent_blue_dim, fg=th.text_on_accent,
            padx=sm.s(4), pady=sm.s(1),
        )
        self._badge.pack(side=tk.LEFT, padx=(sm.s(6), 0))

        self._handling_label = tk.Label(
            self, text="",
            font=(th.font_family, sm.s(9)),
            bg=th.bg_surface, fg=th.status_running,
        )
        self._handling_label.pack(side=tk.LEFT, padx=(sm.s(4), 0))

        self._time_label = tk.Label(
            self, text="",
            font=(th.font_family, sm.s(9)),
            bg=th.bg_surface, fg=th.text_muted,
        )
        self._time_label.pack(side=tk.LEFT, padx=(sm.s(4), 0))

    def update_state(self, status: str, trigger_count: int, last_trigger_time: float) -> None:
        th = current_theme()

        self._status = status
        self._trigger_count = trigger_count
        self._last_trigger_time = last_trigger_time

        color_key = _STATUS_COLORS.get(status, "status_ready")
        dot_color = getattr(th, color_key)
        if self._dot.winfo_exists():
            self._dot.itemconfig(self._dot_oval, fill=dot_color)
        if self._border_canvas.winfo_exists():
            self._border_canvas.configure(bg=dot_color)

        if self._badge.winfo_exists():
            self._badge.configure(text=str(trigger_count))

        if self._handling_label.winfo_exists():
            self._handling_label.configure(
                text="●" if status == "handling" else ""
            )

        if self._time_label.winfo_exists():
            if last_trigger_time > 0:
                elapsed = time.monotonic() - last_trigger_time
                self._time_label.configure(text=self._format_elapsed(elapsed))
            else:
                self._time_label.configure(text="")

    @staticmethod
    def _format_elapsed(seconds: float) -> str:
        if seconds < 60:
            return f"{int(seconds)}s ago"
        if seconds < 3600:
            return f"{int(seconds / 60)}m ago"
        return f"{int(seconds / 3600)}h ago"

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.bg_surface, highlightbackground=th.border_default)
        if self._dot.winfo_exists():
            self._dot.configure(bg=th.bg_surface)
            color_key = _STATUS_COLORS.get(self._status, "status_ready")
            self._dot.itemconfig(self._dot_oval, fill=getattr(th, color_key))
        if self._border_canvas.winfo_exists():
            color_key = _STATUS_COLORS.get(self._status, "status_ready")
            self._border_canvas.configure(bg=getattr(th, color_key))
        if self._name_label.winfo_exists():
            self._name_label.configure(bg=th.bg_surface, fg=th.text_secondary)
        if self._badge.winfo_exists():
            self._badge.configure(bg=th.accent_blue_dim, fg=th.text_on_accent)
        if self._handling_label.winfo_exists():
            self._handling_label.configure(bg=th.bg_surface, fg=th.status_running)
        if self._time_label.winfo_exists():
            self._time_label.configure(bg=th.bg_surface, fg=th.text_muted)


class MonitorStatusWidget(tk.Frame):
    """水平排列的 monitor 状态卡片条。"""

    def __init__(self, parent: tk.Widget) -> None:
        th = current_theme()
        super().__init__(parent, bg=th.bg_primary)
        self._cards: dict[str, MonitorCard] = {}

    def update_monitors(self, states: list) -> None:
        """更新所有 monitor 卡片。states 为 MonitorState 列表。"""
        current_ids = set()

        for state in states:
            mid = state.monitor_id
            current_ids.add(mid)

            if mid not in self._cards:
                card = MonitorCard(self, state.config_name)
                card.pack(side=tk.LEFT, padx=(0, 4))
                self._cards[mid] = card

            self._cards[mid].update_state(
                status=state.status,
                trigger_count=state.trigger_count,
                last_trigger_time=state.last_trigger_time,
            )

        for mid in list(self._cards.keys()):
            if mid not in current_ids:
                card = self._cards.pop(mid)
                card.destroy()

    def apply_theme(self) -> None:
        th = current_theme()
        self.configure(bg=th.bg_primary)
        for card in self._cards.values():
            card.apply_theme()
