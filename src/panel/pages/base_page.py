"""页面基类 — 所有功能页面的抽象父类"""

import tkinter as tk
from tkinter import messagebox

from typing import Callable

from src.core.debug.ring_buffer_log import LogEventType
from src.panel.canvas.scale import scale_manager, Breakpoint
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.canvas.theme import current_theme, ThemeCallbackMixin
from src.panel.components.toolbar import ToolbarFrame
from src.panel.tk_timer import TkTimerScheduler
from src.panel.widgets import apply_theme_recursive, themed_label
from src.utils.i18n import t


class BasePage(ThemeCallbackMixin):
    """页面基类，子类需实现 build() 和 title()"""

    def __init__(self, parent: tk.Widget, app, **kwargs):
        self.parent = parent
        self.app = app
        self._init_kwargs = kwargs
        th = current_theme()
        self.frame = tk.Frame(parent, bg=th.page_bg)
        self._timer = TkTimerScheduler(self.frame)
        self._timer_ids: list[str] = []
        self._subscriptions: list[tuple[str, Callable]] = []
        self._init_theme_guard(self.apply_theme, tk.TclError)
        self._breakpoint = scale_manager().breakpoint()
        self._configure_bind_id = self.frame.bind("<Configure>", self._on_configure)

    def build(self):
        raise NotImplementedError

    def title(self) -> str:
        return "Action<DNA>"

    def on_enter(self, **kwargs) -> None:
        """页面进入前台时调用（首次创建后 + 从缓存恢复时）。"""

    def on_leave(self) -> None:
        """页面离开前台时调用（导航到其他页面时）。"""

    def update_monitors(self, states: list) -> None:
        """推送监控状态更新。默认委托给 _monitor_widget（如果存在）。"""
        widget = getattr(self, "_monitor_widget", None)
        if widget is not None:
            widget.update_monitors(states)

    def on_breakpoint_changed(self, old: Breakpoint, new: Breakpoint) -> None:
        """断点变化时子类可覆盖以响应布局重排"""

    def apply_theme(self):
        if not self.frame.winfo_exists():
            return
        th = current_theme()
        try:
            self.frame.configure(bg=th.page_bg)
        except tk.TclError:
            return
        apply_theme_recursive(self.frame, th)
        if hasattr(self, "_toolbar") and self._toolbar.winfo_exists():
            self._toolbar.apply_theme()

    def _build_toolbar_base(self, page_title_key: str) -> ToolbarFrame:
        """Create a standard toolbar with back button and page title.

        Returns the ToolbarFrame so subclasses can add more buttons/sections.
        Stores it as ``self._toolbar``.
        """
        th = current_theme()
        toolbar = ToolbarFrame(self.frame)
        toolbar.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)
        self._toolbar = toolbar

        toolbar.make_button(
            "nav", text=t("common.back"), icon="back",
            command=lambda: self.app.navigate_to(PAGE_HOME),
            tooltip=t("common.back"), shortcut_hint="Esc",
        )
        toolbar.add_widget(
            "nav", themed_label(toolbar, text=t(page_title_key), style="section"),
        )
        return toolbar

    def destroy(self):
        """销毁页面，取消所有定时器和事件订阅"""
        from src.panel.components.toolbar_tooltip import ToolbarTooltip
        ToolbarTooltip.cleanup_registry()
        self._unregister_theme_callback()
        if self.frame.winfo_exists():
            self.frame.unbind("<Configure>", self._configure_bind_id)
        for tid in self._timer_ids:
            self._timer.cancel(tid)
        for event, callback in self._subscriptions:
            self.app.event_bus.off(event, callback)
        self.frame.destroy()

    def schedule(self, ms: int, callback) -> str:
        tid = self._timer.schedule(ms, callback)
        self._timer_ids.append(tid)
        return tid

    def subscribe(self, event: str, callback: Callable) -> None:
        """订阅事件，页面销毁时自动取消。

        回调通过 TimerScheduler.schedule_idle 调度到主线程，
        防止工作线程直接更新 GUI 控件。
        """

        def _safe_callback(**kwargs):
            if not self._timer.is_alive():
                return

            def _run() -> None:
                if self._timer.is_alive():
                    callback(**kwargs)

            self._timer.schedule_idle(_run)

        self.app.event_bus.on(event, _safe_callback)
        self._subscriptions.append((event, _safe_callback))

    def _append_log(self, msg: str) -> None:
        ring = getattr(self, "_ring_log", None)
        if ring is not None:
            ring.append(message=msg, event_type=LogEventType.CUSTOM)

    def _resolve_import_conflict(
        self,
        *,
        has_content: bool,
        is_dirty: bool,
        save_callback: Callable[[], None],
    ) -> bool:
        """解决导入冲突的用户对话框。

        Returns True if import should proceed, False if user cancelled.
        """
        if not has_content:
            return True

        if is_dirty:
            answer = messagebox.askyesnocancel(
                t("record.export.unsaved_title"),
                t("record.export.unsaved_message"),
            )
            if answer is None:
                return False
            if answer:
                save_callback()
        else:
            answer = messagebox.askyesno(
                t("record.export.new_title"),
                t("record.export.new_message"),
            )
            if not answer:
                return False

        return True

    def _show_running_warning(self, message: str) -> None:
        """显示「运行中」提示。子类可覆盖以自定义通知方式。"""
        if self.app.toast_manager:
            self.app.toast_manager.show(message, level="warning")

    def _go_home(self) -> None:
        """返回首页；若执行器正在运行则提示。"""
        if self.app.executor and self.app.executor.is_running:
            self._show_running_warning(t("workflow.msg.running_in_background"))
        self.app.navigate_to(PAGE_HOME)

    def _on_configure(self, event: tk.Event) -> None:
        if event.widget is not self.frame:
            return
        sm = scale_manager()
        sm.update_breakpoint(event.width)
        new_bp = sm.breakpoint()
        if new_bp != self._breakpoint:
            old = self._breakpoint
            self._breakpoint = new_bp
            self.on_breakpoint_changed(old, new_bp)

    def _pick_region(
        self,
        callback: Callable,
        on_cancel: Callable | None = None,
        capture: object | None = None,
    ) -> None:
        """通用区域框选流程：最小化窗口 → 延迟 → 打开 RegionPicker → 恢复窗口。

        callback 签名: (left, top, width, height) -> None
        on_cancel 签名: () -> None（可选，取消框选时的回调）
        capture: 可选的 ScreenCapture 实例，传入时使用新调用方式
        """
        self.app.root.iconify()
        if hasattr(self.app.root, "update"):
            self.app.root.update()

        def _do_pick():
            from src.panel.region_picker import RegionPicker

            try:
                if capture is not None:
                    RegionPicker(capture, callback, on_cancel=on_cancel)
                else:
                    RegionPicker(callback)
            finally:
                self.app.root.deiconify()

        self.schedule(300, _do_pick)
