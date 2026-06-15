"""主控制面板 — 薄壳路由器，页面导航框架"""

import importlib
import logging
import os
import sys
import tkinter as tk
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from tkinter import ttk
from typing import Callable

from src.core.container import ServiceContainer
from src.panel.app_mixin import ServiceProviderMixin
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import (
    ThemeCallbackMixin,
    SystemThemeSync,
    current_theme,
    restore_from_config,
)
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_registry import PAGE_HOME, PAGE_ACTION_CHAIN, PAGE_WORKFLOW_EDITOR, PageRegistry, DEFERRED_PAGE_MODULES
from src.panel.tk_timer import TkTimerScheduler
from src.utils.i18n import t

logger = logging.getLogger(__name__)

import src.panel.pages.home_page  # noqa: F401 — 触发 @register_page 注册首页


class PanelApp(ServiceProviderMixin, ThemeCallbackMixin):
    """主窗口：持有共享服务，管理页面导航

    实现 ServiceProvider 协议 — 页面通过 self.app 属性访问服务。
    """

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Action<DNA>")
        self.root.resizable(True, True)

        # DI 容器
        self._container = ServiceContainer()

        # DPI 检测 & 屏幕自适应尺寸
        sm = scale_manager()
        sm.detect(self.root)
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        init_w = min(1100, max(640, int(sw * 0.72)))
        init_h = min(780, max(480, int(sh * 0.72)))
        self.root.geometry(f"{init_w}x{init_h}")
        self.root.minsize(sm.s(640), sm.s(480))

        # 主题 — 从持久化配置恢复模式（D2：委托共享 helper）
        from src.core.config import load_config
        self._cfg = load_config()
        restore_from_config(self._cfg)
        # 语言 — 从持久化配置恢复语言偏好
        from src.utils.i18n import set_language
        if self._cfg.language.language in ("zh", "en"):
            set_language(self._cfg.language.language)
        th = current_theme()
        self.root.configure(bg=th.page_bg)
        self._configure_ttk_style(th)
        self._init_theme_guard(self._on_theme_changed, tk.TclError)

        # 注册轻量服务（无 I/O 依赖）
        self._register_lightweight_services()

        # 共享服务状态
        self._monitor_poll_id: str | None = None
        self._services_ready = False
        self._pages_registered = False
        self._pulse_state: bool = False
        self._pulse_id: str | None = None
        self._executor_source_page: str | None = None
        self._last_exec_running: bool | None = None

        # 页面导航 + 缓存池
        self._current_page: BasePage | None = None
        self._current_page_id: str | None = None
        self._page_cache: OrderedDict[str, BasePage] = OrderedDict()  # LRU order, oldest first
        self._max_cache_size: int = 3
        from src.panel.widgets import themed_frame
        self._page_container = themed_frame(self.root)
        self._page_container.pack(fill=tk.BOTH, expand=True)
        self._page_container.bind("<Configure>", self._on_resize)

        # 全局状态栏 — root 窗口底部，跨页面可见
        self._build_global_bar(th, sm)

        # 定时器调度器（解耦 root.after 直接调用）
        self._timer = TkTimerScheduler(self.root)

        # 首页（不依赖重型服务）
        self.navigate_to(PAGE_HOME)

        # 系统主题同步（D1：委托共享 SystemThemeSync，注入 tk 原语）
        self._theme_sync = SystemThemeSync()
        self._theme_sync.start(_TkThemeSyncBackend(self))

        # 延迟注册其余页面模块（避免启动时加载重型依赖阻塞 UI）
        self._timer.schedule(0, self._register_deferred_pages)

        # 延迟初始化重型服务（合并为两个阶段，减少回调延迟）
        self._timer.schedule(10, self._init_services_phase1)

        # 窗口关闭时清理资源
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── ServiceProvider 协议实现（继承自 ServiceProviderMixin） ──

    # ── 服务注册（分阶段） ──

    def _register_lightweight_services(self) -> None:
        """注册不依赖重型模块的服务"""
        from src.core.events.bus import TypedEventBus
        from src.core.engine.node_registry import NodeRegistry
        from src.panel.components.toast import ToastManager

        self._container.register(TypedEventBus, TypedEventBus)
        self._container.register(NodeRegistry, NodeRegistry)
        self._container.register(
            ToastManager, lambda: ToastManager(self.root),
        )

    def _register_deferred_pages(self) -> None:
        """并行导入非首页模块，触发 @register_page 注册（幂等）。"""
        if self._pages_registered:
            return
        self._pages_registered = True

        def _safe_import(mod_name: str) -> None:
            try:
                importlib.import_module(mod_name)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.warning(t("panel.log.deferred_module_failed", mod_name=mod_name), exc_info=True)

        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(_safe_import, DEFERRED_PAGE_MODULES))

    def _init_services_phase1(self):
        """阶段 1: 轻量服务 + 并行创建重型服务"""
        from src.core.events.bus import TypedEventBus
        self._container.get(TypedEventBus)  # trigger singleton creation

        from src.utils.preload import ensure_preloaded
        ensure_preloaded(2.0)

        from src.core.vision.capture import ScreenCapture, TemplateMatcher
        from src.core.input import InputController

        self._container.register(ScreenCapture, ScreenCapture)
        self._container.register(TemplateMatcher, TemplateMatcher)
        self._container.register(InputController, InputController)

        # 并行创建独立服务（ScreenCapture、TemplateMatcher、InputController 互不依赖）
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [
                pool.submit(self._container.get, ScreenCapture),
                pool.submit(self._container.get, TemplateMatcher),
                pool.submit(self._container.get, InputController),
            ]
            for f in as_completed(futures):
                f.result()  # propagate exceptions

        self.root.after(10, self._init_services_phase3)

    def _init_services_phase3(self):
        """阶段 3: 执行器 + 快捷键 + 插件"""
        from src.core.action_executor import ActionExecutor
        from src.core.input.hotkey_manager import HotkeyManager
        from src.core.plugins.plugin_loader import PluginLoader

        capture = self.capture
        matcher = self.matcher
        input_ctrl = self.input_ctrl
        event_bus = self.event_bus
        node_registry = self.node_registry

        self._container.register(
            ActionExecutor,
            lambda: self._build_executor(capture, matcher, input_ctrl, event_bus),
        )
        self._container.register(HotkeyManager, HotkeyManager)

        # 触发执行器创建
        executor = self._container.get(ActionExecutor)
        executor.set_main_scheduler(lambda ms, cb: self._timer.schedule(ms, cb))

        # 快捷键
        hotkey_mgr = self._container.get(HotkeyManager)
        hotkey_mgr.bind_to_tkinter(self.root)
        hotkey_cfg = self._cfg.hotkey
        hotkey_mgr.register_defaults(
            on_start_stop=self._toggle_executor,
            on_pause=lambda: (
                executor.resume() if executor.is_paused
                else executor.pause()
            ),
            on_step=lambda: logger.info(t("app.log.step_not_impl")),
            on_emergency_stop=self._emergency_stop,
            config=hotkey_cfg,
        )

        # 插件加载器
        self._container.register(
            PluginLoader,
            lambda: PluginLoader(
                node_registry=node_registry,
                event_bus=event_bus,
                screen_capture=capture,
                template_matcher=matcher,
                input_controller=input_ctrl,
            ),
        )
        self._container.get(PluginLoader)  # trigger creation
        self._init_plugins()

        # 监控事件订阅
        self._setup_monitor_events()

        # 监控状态轮询
        self._start_monitor_poll()

        self._services_ready = True

    def _build_executor(self, capture, matcher, input_ctrl, event_bus):
        from src.core.action_executor import ActionExecutor
        return ActionExecutor(
            capture, matcher, input_ctrl, event_bus,
            max_consecutive_failures=self._cfg.schedule.max_consecutive_failures,
        )

    def _build_global_bar(self, th, sm) -> None:
        """构建全局状态栏（窗口底部，跨页面可见）。"""
        self._global_bar = tk.Frame(self.root, bg=th.bg_surface, height=sm.s(36))
        self._global_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._global_bar.pack_propagate(False)
        self._global_bar.bind("<Button-1>", self._on_global_bar_click)
        self._global_dot = tk.Canvas(
            self._global_bar, width=sm.s(14), height=sm.s(14),
            bg=th.bg_surface, highlightthickness=0,
        )
        self._global_dot.pack(side=tk.LEFT, padx=(sm.s(8), sm.s(4)), pady=sm.s(11))
        self._dot_oval = self._global_dot.create_oval(
            1, 1, sm.s(14) - 1, sm.s(14) - 1,
            fill=th.status_ready, outline="",
        )
        self._global_label = tk.Label(
            self._global_bar, text=t("monitor.global_bar.idle"),
            font=(th.font_family, sm.s(11)), bg=th.bg_surface, fg=th.text_muted,
            anchor=tk.W,
        )
        self._global_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self._global_label.bind("<Button-1>", self._on_global_bar_click)

    def _configure_ttk_style(self, th) -> None:
        """配置 ttk.Style 以匹配当前主题（Treeview / Combobox / Scrollbar）"""
        style = ttk.Style()
        style.theme_use("clam")

        style.configure("Treeview",
                         background=th.card_bg,
                         foreground=th.text_primary,
                         fieldbackground=th.card_bg,
                         borderwidth=0,
                         rowheight=scale_manager().s(28))
        style.configure("Treeview.Heading",
                         background=th.bg_surface,
                         foreground=th.text_primary,
                         borderwidth=1,
                         font=th.font_body)
        style.map("Treeview.Heading",
                   background=[("active", th.bg_surface_hover)],
                   foreground=[("active", th.text_on_accent)])
        style.map("Treeview",
                   background=[("selected", th.accent_blue_dim), ("!selected", th.card_bg)],
                   foreground=[("selected", th.text_on_accent)])

        style.configure("TCombobox",
                         fieldbackground=th.input_bg,
                         background=th.input_bg,
                         foreground=th.input_fg,
                         selectbackground=th.accent_blue,
                         selectforeground=th.text_on_accent,
                         borderwidth=1,
                         relief="solid")
        style.map("TCombobox",
                   fieldbackground=[("readonly", th.input_bg)],
                   foreground=[("readonly", th.input_fg)],
                   selectbackground=[("readonly", th.accent_blue)])

        style.configure("TCombobox.Listbox",
                         background=th.card_bg,
                         foreground=th.text_primary,
                         selectbackground=th.accent_blue,
                         selectforeground=th.text_on_accent)

        style.configure("TScrollbar",
                         background=th.bg_surface,
                         troughcolor=th.bg_secondary,
                         borderwidth=0,
                         arrowsize=12)
        style.map("TScrollbar",
                   background=[("active", th.bg_surface_hover)])

        style.configure("TPanedwindow",
                         background=th.separator_color,
                         sashthickness=scale_manager().s(2),
                         sashrelief=tk.FLAT,
                         borderwidth=0)
        style.map("TPanedwindow",
                   background=[("active", th.accent_blue_dim),
                               ("!active", th.separator_color)])

        sm = scale_manager()
        style.configure("TNotebook", background=th.page_bg, borderwidth=0)
        style.configure("TNotebook.Tab",
                         background=th.bg_surface, foreground=th.text_secondary,
                         padding=[sm.s(16), sm.s(6)], font=th.font_body)
        style.map("TNotebook.Tab",
                   background=[("selected", th.card_bg)],
                   foreground=[("selected", th.text_primary)],
                   expand=[("selected", [0, 0, 0, sm.s(2)])])

    def _on_theme_changed(self) -> None:
        """主题切换时重新配置全局样式

        只更新全局元素（root 背景、ttk 样式、状态栏），
        页面自身的控件由各页面注册的 apply_theme 回调负责就地更新，
        不需要销毁重建整个页面。
        """
        th = current_theme()
        sm = scale_manager()
        self.root.configure(bg=th.page_bg)
        self._configure_ttk_style(th)
        self._global_bar.configure(bg=th.bg_surface, height=sm.s(36))
        self._global_dot.configure(bg=th.bg_surface)
        self._global_label.configure(bg=th.bg_surface)
        self._global_dot.itemconfig(self._dot_oval, fill=th.status_ready)

    def _setup_monitor_events(self) -> None:
        """订阅监控事件以显示 Toast 通知。"""
        from src.core.events.events import MonitorTriggeredEvent

        self.event_bus.subscribe(
            MonitorTriggeredEvent, self._on_monitor_triggered,
        )

    def _on_monitor_triggered(self, event) -> None:
        """监控触发时显示 Toast 通知。"""
        self.toast_manager.show(
            t("monitor.toast.triggered",
              name=event.monitor_id, action=event.action_taken),
            level="warning",
        )

    def _start_monitor_poll(self) -> None:
        """每 500ms 轮询 monitor 状态并更新全局状态栏 + 页面 widget。"""
        self._poll_monitor_state()

    def _poll_monitor_state(self) -> None:
        try:
            mm = self.executor.monitor_manager if self.executor else None
            is_running = self.executor.is_running if self.executor else False
            running_changed = is_running != self._last_exec_running
            if mm is not None and is_running:
                if running_changed:
                    th = current_theme()
                    self._global_label.configure(
                        text=t("monitor.global_bar.running_bg"),
                        fg=th.status_running,
                    )
                if self._pulse_id is None:
                    self._pulse_running_indicator()
            else:
                if running_changed:
                    self._set_idle_bar()
                self._stop_pulse()

            if mm is not None:
                states = mm.get_all_states()
                if self._current_page:
                    self._current_page.update_monitors(states)

            self._last_exec_running = is_running
        except tk.TclError:
            logger.debug(t("panel.log.monitor_poll_window_closed"))
            self._stop_monitor_poll()
            return
        except Exception:  # pylint: disable=broad-exception-caught
            logger.warning(t("panel.log.monitor_poll_exception"), exc_info=True)
        poll_ms = getattr(self._cfg, "schedule", None)
        poll_ms = poll_ms.monitor_poll_ms if poll_ms else 500
        self._monitor_poll_id = self._timer.schedule(
            poll_ms, self._poll_monitor_state,
        )

    def _stop_monitor_poll(self) -> None:
        if self._monitor_poll_id is not None:
            self._timer.cancel(self._monitor_poll_id)
            self._monitor_poll_id = None
        self._stop_pulse()

    def _pulse_running_indicator(self) -> None:
        """执行器运行时全局状态栏圆点呼吸脉冲。"""
        if not self.executor or not self.executor.is_running:
            self._stop_pulse()
            return
        th = current_theme()
        self._pulse_state = not self._pulse_state
        color = th.status_running if self._pulse_state else th.bg_surface
        try:
            if self._global_dot.winfo_exists():
                self._global_dot.itemconfig(self._dot_oval, fill=color)
        except tk.TclError:
            self._stop_pulse()
            return
        self._pulse_id = self._timer.schedule(600, self._pulse_running_indicator)

    def _stop_pulse(self) -> None:
        if self._pulse_id is not None:
            self._timer.cancel(self._pulse_id)
            self._pulse_id = None
        self._pulse_state = False

    def _set_idle_bar(self) -> None:
        th = current_theme()
        if self._global_dot.winfo_exists():
            self._global_dot.itemconfig(self._dot_oval, fill=th.status_ready)
        self._global_label.configure(
            text=t("monitor.global_bar.idle"),
            fg=th.text_muted,
        )

    def _on_global_bar_click(self, _event: tk.Event | None = None) -> None:
        """点击全局状态栏导航到来源页面。"""
        if not self._services_ready or not self.executor or not self.executor.is_running:
            return
        source = self._executor_source_page or "workflow_editor"
        if self._current_page_id != source:
            self.navigate_to(source)

    def navigate_to(self, page_id: str, **kwargs):
        """导航到指定页面，支持页面缓存复用"""
        page_class = PageRegistry.resolve(page_id)

        # 记录执行器来源页面（用于全局状态栏点击导航回来源）
        if (
            self.executor
            and self.executor.is_running
            and self._current_page_id in (PAGE_WORKFLOW_EDITOR, PAGE_ACTION_CHAIN)
        ):
            self._executor_source_page = self._current_page_id

        # 导航到当前页面时（如切换语言），直接重建
        if page_id == self._current_page_id and self._current_page:
            old = self._current_page
            self._current_page = None
            self._current_page_id = None
            old.destroy()
            self._activate_page(
                page_class(self._page_container, self, **kwargs),
                page_id, build=True, **kwargs,
            )
            return

        # 缓存当前页面
        if self._current_page:
            self._cache_current_page()

        # 尝试从缓存恢复
        if page_id in self._page_cache:
            page = self._page_cache.pop(page_id)
            self._activate_page(page, page_id, **kwargs)
            return

        # 创建新页面
        self._activate_page(
            page_class(self._page_container, self, **kwargs),
            page_id, build=True, **kwargs,
        )

    def _activate_page(self, page: BasePage, page_id: str, *, build: bool = False, **kwargs) -> None:
        """激活页面：可选构建 → 显示 → 通知 → 更新标题。"""
        if build:
            page.build()
        page.frame.pack(fill=tk.BOTH, expand=True)
        if not build:
            page.apply_theme()
        page.on_enter(**kwargs)
        self._current_page = page
        self._current_page_id = page_id
        self.root.title(f"Action<DNA> — {page.title()}")

    def _cache_current_page(self) -> None:
        """将当前页面移入缓存池（LRU 策略）。"""
        if not self._current_page or not self._current_page_id:
            return
        old_page = self._current_page
        old_id = self._current_page_id
        old_page.on_leave()
        old_page.frame.pack_forget()

        self._page_cache[old_id] = old_page

        # LRU 淘汰：超出上限时销毁最旧的页面
        while len(self._page_cache) > self._max_cache_size:
            evict_id, evict_page = self._page_cache.popitem(last=False)
            if evict_page:
                evict_page.destroy()

    def clear_page_cache(self) -> None:
        """清空所有缓存的页面。"""
        for pid in list(self._page_cache):
            page = self._page_cache.pop(pid)
            page.destroy()

    # ── 公共访问器（供 HomeStateMixin 使用）──

    def get_cached_page(self, page_id: str):
        return self._page_cache.get(page_id)

    def set_executor_source(self, page_type: str) -> None:
        self._executor_source_page = page_type

    def get_executor_source(self) -> str | None:
        return self._executor_source_page

    def schedule_restart(self) -> None:
        """停止独占资源 → 启动新进程 → 终止当前进程。"""
        self._stop_services()
        try:
            from src.utils.restart import restart_app
            restart_app()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(t("panel.log.restart_failed_recover"))
            from tkinter import messagebox
            messagebox.showerror(t("app.title"), t("settings.restart_failed"))
            self._services_ready = True

    def _stop_services(self) -> None:
        """按正确顺序停止所有服务，释放独占资源防止新旧进程冲突。

        顺序：回调/轮询 → 热键 → 执行器 → 插件 → 截图 → 缓存
        热键和执行器必须在最前面释放，否则新进程无法注册同一系统热键。
        """
        self._unregister_theme_callback()
        self._theme_sync.stop()
        self._stop_monitor_poll()
        self._stop_pulse()
        if self.hotkey_manager:
            self.hotkey_manager.shutdown()
        if self.executor:
            self.executor.stop()
        if self.plugin_loader:
            self.plugin_loader.stop_watcher()
            self.plugin_loader.unload_all()
        if self.capture:
            self.capture.close()
        if self.matcher:
            self.matcher.clear_cache()
        self._services_ready = False

    def run(self):
        self.root.mainloop()

    def _on_resize(self, event: tk.Event) -> None:
        """窗口大小变化时更新断点。"""
        if event.widget is self._page_container:
            scale_manager().update_breakpoint(event.width)

    def _on_close(self) -> None:
        """窗口关闭时清理所有资源：页面 → 插件 → 执行器 → 快捷键 → 截图 → 缓存

        不在主线程 join 执行器线程，避免阻塞 tkinter 事件循环导致卡死。
        执行器线程为 daemon，进程退出时自动终止。
        """
        try:
            self._unregister_theme_callback()
            self._theme_sync.stop()
            self._stop_monitor_poll()
            if self._current_page:
                self._current_page.destroy()
                self._current_page = None
            self.clear_page_cache()
            if self.executor:
                self.executor.stop()
            if self.hotkey_manager:
                self.hotkey_manager.shutdown()
            if self.plugin_loader:
                self.plugin_loader.stop_watcher()
                self.plugin_loader.unload_all()
            if self.capture:
                self.capture.close()
            if self.matcher:
                self.matcher.clear_cache()
        finally:
            self.root.destroy()


class _TkThemeSyncBackend:
    """tkinter 主题同步原语 — marshal 用 root.after(0)，定时器用 TkTimerScheduler。

    实现 theme_sync.ThemeSyncBackend Protocol。
    """

    def __init__(self, app: "PanelApp") -> None:
        self._app = app

    def marshal_main(self, fn: Callable[[], None]) -> None:
        """回 UI 主线程：root.after(0) 在 widget 仍存活时调度。"""
        try:
            if self._app.root.winfo_exists():
                self._app.root.after(0, fn)
        except tk.TclError:
            pass

    def start_timer(self, interval_ms: int, fn: Callable[[], None]) -> str:
        return self._app._timer.schedule(interval_ms, fn)

    def stop_timer(self, handle: object) -> None:
        self._app._timer.cancel(handle)


