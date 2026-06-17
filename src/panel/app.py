"""主控制面板 — 薄壳路由器，页面导航框架"""

import gc
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


def _log_tk_callback_exception(exc, val, tb) -> None:
    """安全地记录 Tk 回调中未捕获的异常 —— 替代 Tk 默认 report_callback_exception。

    背景：默认 ``Tk.report_callback_exception`` 用 ``print(..., file=sys.stderr)``
    + ``traceback.print_exception`` 输出。在 PyInstaller ``console=False``（windowed）
    打包模式下 ``sys.stderr`` 是无效句柄，write 会抛 ``OSError: [Errno 22] Invalid
    argument``；而 report_callback_exception 自身位于 Tk mainloop 的异常报告路径
    (``_report_exception`` → ``report_callback_exception``) 上，其抛出的 OSError
    会穿透 mainloop 成为顶层崩溃，并连带触发 main() 的 ``input()`` → ``EOFError``。

    修复：改走 logging 落盘 —— FileHandler 写 ``assets/logs/<date>.log`` 恒成立；
    其 StreamHandler 绑定的 ``sys.stdout`` 即使无效，也由 logging 内部 handleError
    静默吞掉，绝不抛出。本函数自身再裹一层 try/except，确保回调异常报告路径
    任何情况下都不会成为新的崩溃源。绝不直接触碰 ``sys.stderr``。
    """
    try:
        logger.error("Tk 回调中未捕获异常", exc_info=(exc, val, tb))
    except Exception:  # noqa: BLE001 — 回调异常报告路径绝不能再抛
        pass


class _SafeTkRoot(tk.Tk):
    """Tk root 子类 —— 用安全异常报告覆盖默认 report_callback_exception。

    详见 :func:`_log_tk_callback_exception`：默认实现向 ``sys.stderr`` 写入，
    在 windowed 打包模式下会引发 OSError 级联崩溃。子类化 tk.Tk 是 tkinter
    覆盖该回调的惯用、可靠方式（实例属性覆盖亦可，子类更清晰）。
    """

    def report_callback_exception(self, exc, val, tb) -> None:  # noqa: D401
        _log_tk_callback_exception(exc, val, tb)


class PanelApp(ServiceProviderMixin, ThemeCallbackMixin):
    """主窗口：持有共享服务，管理页面导航

    实现 ServiceProvider 协议 — 页面通过 self.app 属性访问服务。
    """

    def __init__(self):
        # 用 _SafeTkRoot（tk.Tk 子类）覆盖默认 report_callback_exception ——
        # 默认实现向 sys.stderr 写入，windowed 打包下会引发 OSError 级联崩溃。
        self.root = _SafeTkRoot()
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
        self._restart_scheduled: bool = False
        # 关闭重入保护：WM_DELETE_WINDOW 可能被重复触发，已开始关闭则短路。
        self._closing: bool = False
        self._executor_source_page: str | None = None
        self._last_exec_running: bool | None = None
        self._exec_log_bridge = None  # EventBus→RingBufferLog 执行日志桥接器(phase3 创建)

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

        # GC 线程安全防护：禁用自动循环 GC，改由主线程周期性 gc.collect()。
        # 根因：CPython 自动循环 GC 可在任意后台线程（如 monitor 检测线程）经
        # _Py_HandlePending 触发；若此时回收含 Tkapp（Tk root 解释器）的不可达
        # 引用环（页面导航「销毁旧页面/建新页面」会产生 widget↔controller↔callback
        # 环），会在非创建线程 dealloc Tk 解释器 → Tcl_AsyncDelete → Tcl_Panic
        # → SIGTRAP 硬崩溃（crash report: Thread "monitor-*" 的 gc_collect_main
        # → Tkapp_Dealloc）。Tcl/Tk 解释器线程亲和，必须在创建线程释放。
        # 禁用自动 GC 后，引用计数归零的对象仍即时释放，仅循环垃圾改由主线程
        # （Tk 创建线程，after 回调必在此运行）周期回收 → dealloc 安全。
        gc.disable()

        def _gc_collect_main() -> None:
            """主线程周期性回收循环垃圾（自调度，配合上面的 gc.disable）。

            在 Tk mainloop 的 after 回调中运行 → 必为主线程，Tk 对象在此线程
            创建故 dealloc 安全。after 为一次性，故每次执行后重新自调度。
            _closing 后停止自调度：窗口正在关闭时若继续挂 after，destroy 拆除
            Tcl 解释器期间回调仍可能触发 → 在已删 Tcl 命令上操作崩溃。
            """
            try:
                gc.collect()
            except Exception:  # noqa: BLE001 — GC 失败不应中断 Tk 主循环
                logger.debug("gc.collect() on main thread failed", exc_info=True)
            finally:
                if not self._closing:
                    self._gc_collect_id = self._timer.schedule(2000, _gc_collect_main)

        self._gc_collect_id = self._timer.schedule(2000, _gc_collect_main)

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
        from src.core.debug.ring_buffer_log import RingBufferLog
        from src.core.events.bus import TypedEventBus
        from src.core.engine.node_registry import NodeRegistry
        from src.panel.components.toast import ToastManager

        self._container.register(TypedEventBus, TypedEventBus)
        self._container.register(NodeRegistry, NodeRegistry)
        self._container.register(RingBufferLog, RingBufferLog)
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
        """阶段 1: 轻量服务 + 并行创建重型服务。

        关键: 任一重型服务实例化失败都不能阻断 phase3(executor 注册)。
        否则页面拿到 None executor,「点启动完全无反应」且无报错(exe 无控制台)。
        因此整体 try/except 兜底,finally 中无条件调度 phase3。
        """
        try:
            from src.core.events.bus import TypedEventBus
            self._container.get(TypedEventBus)  # trigger singleton creation

            from src.utils.preload import ensure_preloaded
            ensure_preloaded(2.0)

            from src.core.vision.capture import ScreenCapture, TemplateMatcher
            from src.core.input import InputController

            self._container.register(ScreenCapture, ScreenCapture)
            self._container.register(TemplateMatcher, TemplateMatcher)
            self._container.register(InputController, InputController)

            # 并行创建独立服务;每个失败单独记录,不拖垮其它,也不阻断 phase3。
            with ThreadPoolExecutor(max_workers=3) as pool:
                futures = {
                    pool.submit(self._container.get, ScreenCapture): "ScreenCapture",
                    pool.submit(self._container.get, TemplateMatcher): "TemplateMatcher",
                    pool.submit(self._container.get, InputController): "InputController",
                }
                for f in as_completed(futures):
                    name = futures[f]
                    try:
                        f.result()
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "服务初始化失败(降级为 None,不影响 executor 注册): %s", name
                        )
        except Exception:  # noqa: BLE001 — 阶段失败降级,不阻断初始化链
            logger.exception("服务初始化 phase1 失败(降级继续)")
        finally:
            self.root.after(10, self._init_services_phase3)

    def _init_services_phase3(self):
        """阶段 3: 执行器 + 快捷键 + 插件。

        本阶段是「executor 能否注册」的关键。即使前置服务部分失败(capture 等为 None),
        也要注册 executor —— ActionExecutor 构造只存储引用,容忍 None;Wait/PressKey 等
        不依赖视觉的步骤仍可执行。热键/插件/监控为非致命增强,各自隔离失败。
        """
        try:
            from src.core.action_executor import ActionExecutor
            from src.core.input.hotkey_manager import HotkeyManager
            from src.core.plugins.plugin_loader import PluginLoader
            from src.core.vision.capture import ScreenCapture, TemplateMatcher
            from src.core.input import InputController

            # 防御性获取: 某服务工厂失败时返回 None,不抛、不中断 executor 注册。
            capture = self._safe_get_service(ScreenCapture)
            matcher = self._safe_get_service(TemplateMatcher)
            input_ctrl = self._safe_get_service(InputController)
            event_bus = self.event_bus

            # executor 必须注册:即使 capture/matcher/input 为 None(降级模式)。
            # 这正是修复「点启动完全无反应」的核心 —— 保证 executor 永不为 None。
            self._container.register(
                ActionExecutor,
                lambda: self._build_executor(capture, matcher, input_ctrl, event_bus),
            )
            try:
                executor = self._container.get(ActionExecutor)
                executor.set_main_scheduler(lambda ms, cb: self._timer.schedule(ms, cb))
            except Exception:  # noqa: BLE001
                logger.exception("ActionExecutor 创建失败(启动按钮将给出清晰错误而非静默)")
                executor = None

            # 执行日志桥接器:把 executor 生命周期事件翻译进共享 ring_log,
            # 使执行日志面板能显示 启动/停止/暂停/恢复/结束/安全停止/轮次 等事件。
            # 与节点级 LoggingLayer(在执行线程内直接写)互补。失败不阻断核心执行。
            try:
                from src.panel.components.execution_log_bridge import ExecutionLogBridge
                self._exec_log_bridge = ExecutionLogBridge(event_bus, self.ring_log)
            except Exception:  # noqa: BLE001
                logger.exception("执行日志桥接器初始化失败(非致命,跳过)")
                self._exec_log_bridge = None

            # 热键为增强功能,失败不阻断核心执行
            try:
                self._container.register(HotkeyManager, HotkeyManager)
                hotkey_mgr = self._container.get(HotkeyManager)
                hotkey_mgr.bind_to_tkinter(self.root)
                hotkey_cfg = self._cfg.hotkey

                def _toggle_pause() -> None:
                    # executor 降级时可能为 None(phase3 创建失败),此处防御。
                    if executor is None:
                        return
                    if executor.is_paused:
                        executor.resume()
                    else:
                        executor.pause()

                hotkey_mgr.register_defaults(
                    on_start_stop=self._toggle_executor,
                    on_pause=_toggle_pause,
                    on_step=lambda: logger.info(t("app.log.step_not_impl")),
                    on_emergency_stop=self._emergency_stop,
                    config=hotkey_cfg,
                )
            except Exception:  # noqa: BLE001
                logger.exception("热键管理器初始化失败(非致命,跳过)")

            # 插件加载器为增强功能,失败不阻断核心执行
            try:
                node_registry = self.node_registry
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
            except Exception:  # noqa: BLE001
                logger.exception("插件加载器初始化失败(非致命,跳过)")

            # 监控为增强功能,失败不阻断核心执行
            try:
                self._setup_monitor_events()
                self._start_monitor_poll()
            except Exception:  # noqa: BLE001
                logger.exception("监控初始化失败(非致命,跳过)")
        except Exception:  # noqa: BLE001
            logger.exception("服务初始化 phase3 失败(核心已尽力注册 executor)")
        finally:
            self._services_ready = True
            # 服务就绪后清空页面缓存: 页面可能在服务就绪前构建并缓存了 None executor,
            # 清缓存迫使下次导航重建页面,拿到已注册的真实 executor。
            try:
                self.clear_page_cache()
            except Exception:  # noqa: BLE001
                logger.debug("clear_page_cache 失败(忽略)", exc_info=True)

    def _build_executor(self, capture, matcher, input_ctrl, event_bus):
        from src.core.action_executor import ActionExecutor
        return ActionExecutor(
            capture, matcher, input_ctrl, event_bus,
            max_consecutive_failures=self._cfg.schedule.max_consecutive_failures,
            ring_log=self.ring_log,
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
        """停止独占资源 → 启动新进程 → 终止当前进程。

        防重入：若已调度过重启，直接返回（与 Qt 后端对等）。避免任何路径
        在新进程启动前反复触发 restart，造成重启风暴。
        """
        if getattr(self, "_restart_scheduled", False):
            logger.debug(t("panel.log.schedule_restart_ignored"))
            return
        self._restart_scheduled = True
        self._stop_services()
        try:
            from src.utils.restart import restart_app
            restart_app()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception(t("panel.log.restart_failed_recover"))
            # 重启失败需重置标记，否则后续无法再次尝试
            self._restart_scheduled = False
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
        if self._exec_log_bridge is not None:
            self._exec_log_bridge.destroy()
            self._exec_log_bridge = None
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
        # 确保窗口可见并置顶激活（对等 Qt 后端的 raise_/activateWindow）。
        # 重启后的新进程窗口在 macOS 上可能不自动获得焦点，lift + attributes
        # 短暂置顶可让用户立即看到窗口。
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(100, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass
        self.root.mainloop()

    def _on_resize(self, event: tk.Event) -> None:
        """窗口大小变化时更新断点。"""
        if event.widget is self._page_container:
            scale_manager().update_breakpoint(event.width)

    def _stop_gc_collect(self) -> None:
        """取消主线程周期性 GC 的自调度 after 回调。

        ``_gc_collect_main`` 每次执行后会重新 schedule 自身，此前窗口关闭路径
        从不取消它 —— destroy 拆除 Tcl 解释器期间该 after 仍可能触发，在已删
        的 Tcl 命令上操作 → ``TclError: can't delete Tcl command``。关闭时显式
        取消，并配合 ``_gc_collect_main`` 在 ``_closing`` 后停止自调度。
        """
        gc_id = getattr(self, "_gc_collect_id", None)
        if gc_id is not None:
            try:
                self._timer.cancel(gc_id)
            except tk.TclError:
                pass
            self._gc_collect_id = None

    def _on_close(self) -> None:
        """窗口关闭时清理所有资源：页面 → 插件 → 执行器 → 快捷键 → 截图 → 缓存。

        不在主线程 join 执行器线程，避免阻塞 tkinter 事件循环导致卡死。
        执行器线程为 daemon，进程退出时自动终止。

        防御要点（修 windowed 打包下的 TclError → OSError → EOFError 级联崩溃）：
        - **重入保护**（``_closing``）：WM_DELETE_WINDOW 可能被重复触发，
          已开始关闭则直接返回，避免双重 destroy。
        - **取消 GC after**：见 :meth:`_stop_gc_collect`，杜绝 destroy 期间
          的 Tcl 命令竞态。
        - **清理体整体 try/except**：任一服务清理失败仅记日志，绝不阻断窗口销毁。
        - **quit() + destroy() 双防御**：先 ``quit()`` 退出 mainloop 再 ``destroy()``，
          两者均吞 ``TclError`` —— Tcl 解释器拆除期内的命令删除失败属预期
          （命令可能已被删/解释器正在销毁），窗口本就要销毁，无需也无法恢复。
          关键：destroy 的异常绝不能穿透回 mainloop（否则触发 report_callback_exception
          → 向无效 stderr 写 → OSError 级联）。
        """
        if getattr(self, "_closing", False):
            return
        self._closing = True
        try:
            self._unregister_theme_callback()
            self._theme_sync.stop()
            self._stop_monitor_poll()
            self._stop_gc_collect()
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
        except Exception:  # noqa: BLE001 — 关闭路径绝不能向 mainloop 抛异常
            logger.exception("窗口关闭清理时发生异常（已忽略，继续销毁窗口）")
        finally:
            # 先 quit() 退出主循环，再 destroy()；两者均防御 TclError。
            # bound method 直接调用，任一失败都吞掉，确保 _on_close 不抛出。
            for _teardown in (self.root.quit, self.root.destroy):
                try:
                    _teardown()
                except tk.TclError:
                    pass


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


