"""Qt PanelApp — QMainWindow + 页面导航 + 服务容器。

与 tkinter PanelApp (app.py) 对等的 PySide6 实现。
通过 DNA_GUI_BACKEND=qt 环境变量激活。
"""

from __future__ import annotations

import importlib
import logging
from collections import OrderedDict
import os
import sys

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QStackedWidget, QWidget,
    QLabel, QStatusBar, QHBoxLayout, QVBoxLayout,
)
from PySide6.QtCore import Qt, QTimer, QSize
from PySide6.QtGui import QColor, QPainter, QFont

from src.core.container import ServiceContainer
from src.panel.app_mixin import ServiceProviderMixin
from src.panel.pages.page_registry import PAGE_HOME, PAGE_ACTION_CHAIN, PAGE_WORKFLOW_EDITOR
from src.panel.canvas.theme import (
    current_theme, current_theme_mode, ThemeCallbackMixin,
    resolved_theme_mode, set_theme_mode,
)
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.theme import theme_to_qss
from src.panel.qt_backend.timer import QtTimerScheduler
from src.utils.i18n import t

logger = logging.getLogger(__name__)


def _safe_destroy_page(widget: QWidget) -> None:
    """安全调用 destroy_page()，忽略非页面 widget。"""
    destroy = getattr(widget, "destroy_page", None)
    if callable(destroy):
        try:
            destroy()
        except Exception:
            logger.warning("destroy_page() failed", exc_info=True)

# Qt 页面模块 — 导入以触发 @register_page 装饰器注册
_QT_PAGE_MODULES: tuple[str, ...] = (
    "src.panel.qt_backend.pages.home_page",
    "src.panel.qt_backend.pages.action_chain_page",
    "src.panel.qt_backend.pages.workflow_page",
    "src.panel.qt_backend.pages.record_page",
    "src.panel.qt_backend.pages.notification_page",
    "src.panel.qt_backend.pages.schedule_page",
    "src.panel.qt_backend.pages.settings_page",
    "src.panel.qt_backend.pages.plugin_page",
)

for _mod in _QT_PAGE_MODULES:
    try:
        importlib.import_module(_mod)
    except Exception:
        logger.warning("Failed to import Qt page module: %s", _mod, exc_info=True)


class StatusDot(QWidget):
    """状态指示圆点（替代 tkinter Canvas create_oval）。"""

    def __init__(self, color: str = "#808080", size: int = 14) -> None:
        super().__init__()
        self._color = color
        self._size = size
        self.setFixedSize(size, size)

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QColor(self._color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(1, 1, self._size - 2, self._size - 2)
        painter.end()


class QtPanelApp(ServiceProviderMixin, ThemeCallbackMixin, QMainWindow):
    """PySide6 主窗口 — 与 tkinter PanelApp 对等。

    实现 ServiceProvider 协议 — 页面通过 self.app 属性访问服务。
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Action<DNA>")
        self.setMinimumSize(640, 480)

        # DI 容器
        self._container = ServiceContainer()

        # DPI 检测
        sm = qt_scale_manager()
        sm.detect()
        init_w, init_h = sm.initial_size()
        self.resize(init_w, init_h)
        min_w, min_h = sm.min_size()
        self.setMinimumSize(min_w, min_h)

        # 定时器调度器
        self._timer = QtTimerScheduler()

        # 主题
        from src.core.config import load_config
        self._cfg = load_config()
        mode = self._cfg.editor.theme_mode
        if mode in ("dark", "light", "system"):
            set_theme_mode(mode)
        else:
            set_theme_mode("system")

        # 语言
        from src.utils.i18n import set_language
        if self._cfg.language.language in ("zh", "en"):
            set_language(self._cfg.language.language)

        self._apply_theme()
        self._init_theme_guard(self._on_theme_changed, RuntimeError)
        self._register_lightweight_services()

        # 共享服务状态
        self._services_ready = False
        self._pulse_state: bool = False
        self._pulse_timer: QTimer | None = None
        self._executor_source_page: str | None = None
        self._last_exec_running: bool | None = None
        self._monitor_timer: QTimer | None = None
        self._sys_theme_timer: QTimer | None = None

        # 页面导航 — 使用 QStackedWidget
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # 页面缓存（Qt 使用 QWidget，不通过 pack/grid 显示隐藏）
        self._page_cache: OrderedDict[str, QWidget] = OrderedDict()
        self._max_cache_size: int = 3
        self._current_page_id: str | None = None

        # 全局状态栏
        self._build_global_bar()

        # 首页
        self.navigate_to(PAGE_HOME)

        # 系统主题轮询
        self._last_resolved: str = resolved_theme_mode()
        self._start_system_theme_poller()

        # 延迟初始化重型服务
        self._timer.schedule(50, self._init_services_phase1)

    # ── ServiceProvider 协议（继承自 ServiceProviderMixin，toast_manager 覆盖） ──

    @property
    def toast_manager(self):
        from src.panel.qt_backend.components.toast import QtToastManager
        mgr = self._try_get(QtToastManager)
        if mgr is None:
            mgr = QtToastManager(self)
            self._container.register_instance(QtToastManager, mgr)
        return mgr

    # ── 服务注册 ──

    def _register_lightweight_services(self) -> None:
        from src.core.events.bus import TypedEventBus
        from src.core.engine.node_registry import NodeRegistry

        self._container.register(TypedEventBus, TypedEventBus)
        self._container.register(NodeRegistry, NodeRegistry)

    def _init_services_phase1(self) -> None:
        from src.core.events.bus import TypedEventBus
        self._container.get(TypedEventBus)
        self._timer.schedule(100, self._init_services_phase2)

    def _init_services_phase2(self) -> None:
        from src.core.vision.capture import ScreenCapture, TemplateMatcher
        from src.core.input import InputController

        self._container.register(ScreenCapture, ScreenCapture)
        self._container.register(TemplateMatcher, TemplateMatcher)
        self._container.register(InputController, InputController)

        self._container.get(ScreenCapture)
        self._container.get(TemplateMatcher)
        self._container.get(InputController)

        self._timer.schedule(50, self._init_services_phase3)

    def _init_services_phase3(self) -> None:
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
            lambda: ActionExecutor(
                capture, matcher, input_ctrl, event_bus,
                max_consecutive_failures=self._cfg.schedule.max_consecutive_failures,
            ),
        )
        self._container.register(HotkeyManager, HotkeyManager)

        executor = self._container.get(ActionExecutor)
        executor.set_main_scheduler(lambda ms, cb: self._timer.schedule(ms, cb))

        # 热键管理器
        hotkey_mgr = self._container.get(HotkeyManager)
        hotkey_mgr.bind_to_qt(lambda ms, cb: self._timer.schedule(ms, cb))
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
        self._container.get(PluginLoader)
        self._init_plugins()

        self._setup_monitor_events()
        self._start_monitor_poll()

        self._services_ready = True

    def _setup_monitor_events(self) -> None:
        from src.core.events.events import MonitorTriggeredEvent
        self.event_bus.subscribe(MonitorTriggeredEvent, self._on_monitor_triggered)

    def _on_monitor_triggered(self, event) -> None:
        logger.info(t("monitor.toast.triggered", name=event.monitor_id, action=event.action_taken))
        self.toast_manager.show(
            t("monitor.toast.triggered", name=event.monitor_id, action=event.action_taken),
            level="warning",
        )

    # ── 主题 ──

    def _apply_theme(self) -> None:
        th = current_theme()
        qss = theme_to_qss(th)
        self.setStyleSheet(qss)

    def _set_status_label_color(self, color: str) -> None:
        self._status_label.setStyleSheet(f"color: {color}; background: transparent;")

    def _on_theme_changed(self) -> None:
        """主题切换时重新配置全局样式，并强制所有页面（含缓存）更新。"""
        self._apply_theme()
        self._last_resolved = resolved_theme_mode()
        th = current_theme()
        self._set_status_label_color(th.text_muted)
        self._status_dot.set_color(th.status_ready)

        # Force update cached pages too (they won't get callbacks since not visible)
        for page in self._page_cache.values():
            if hasattr(page, "apply_theme"):
                try:
                    page.apply_theme()
                except Exception:
                    pass

        # Force update status bar background
        if hasattr(self, "_status_bar") and self._status_bar is not None:
            self._status_bar.setStyleSheet(
                f"background-color: {th.bg_surface}; border-top: 1px solid {th.border_default};"
            )

    def _start_system_theme_poller(self) -> None:
        self._sys_theme_timer = QTimer(self)
        self._sys_theme_timer.setInterval(30000)
        self._sys_theme_timer.timeout.connect(self._poll_system_theme)
        self._sys_theme_timer.start()

    def _poll_system_theme(self) -> None:
        if current_theme_mode() == "system":
            resolved = resolved_theme_mode()
            if resolved != self._last_resolved:
                self._last_resolved = resolved
                set_theme_mode("system")

    # ── 全局状态栏 ──

    def _build_global_bar(self) -> None:
        th = current_theme()
        sm = qt_scale_manager()

        bar = QStatusBar()
        bar.setFixedHeight(sm.s(36))
        bar.setStyleSheet(f"background-color: {th.bg_surface}; border-top: 1px solid {th.border_default};")

        layout = QHBoxLayout()
        layout.setContentsMargins(sm.s(8), 0, sm.s(8), 0)
        layout.setSpacing(sm.s(4))

        self._status_dot = StatusDot(th.status_ready, sm.s(14))
        layout.addWidget(self._status_dot)

        self._status_label = QLabel(t("monitor.global_bar.idle"))
        self._set_status_label_color(th.text_muted)
        layout.addWidget(self._status_label, 1)

        container = QWidget()
        container.setLayout(layout)
        bar.addWidget(container, 1)
        self.setStatusBar(bar)

    def _start_monitor_poll(self) -> None:
        poll_ms = getattr(self._cfg, "schedule", None)
        poll_ms = poll_ms.monitor_poll_ms if poll_ms else 500
        self._monitor_timer = QTimer(self)
        self._monitor_timer.setInterval(poll_ms)
        self._monitor_timer.timeout.connect(self._poll_monitor_state)
        self._monitor_timer.start()

    def _poll_monitor_state(self) -> None:
        try:
            mm = self.executor.monitor_manager if self.executor else None
            is_running = self.executor.is_running if self.executor else False
            running_changed = is_running != self._last_exec_running
            if mm is not None and is_running:
                if running_changed:
                    th = current_theme()
                    self._status_label.setText(t("monitor.global_bar.running_bg"))
                    self._set_status_label_color(th.status_running)
                if self._pulse_timer is None:
                    self._pulse_running_indicator()
            else:
                if running_changed:
                    th = current_theme()
                    self._status_dot.set_color(th.status_ready)
                    self._status_label.setText(t("monitor.global_bar.idle"))
                    self._set_status_label_color(th.text_muted)
                self._stop_pulse()
            self._last_exec_running = is_running
        except Exception:
            logger.warning("监控轮询异常", exc_info=True)

    def _pulse_running_indicator(self) -> None:
        if not self.executor or not self.executor.is_running:
            self._stop_pulse()
            return
        th = current_theme()
        self._pulse_state = not self._pulse_state
        color = th.status_running if self._pulse_state else th.bg_surface
        self._status_dot.set_color(color)
        if self._pulse_timer is None:
            self._pulse_timer = QTimer(self)
            self._pulse_timer.setSingleShot(True)
            self._pulse_timer.timeout.connect(self._pulse_running_indicator)
        self._pulse_timer.start(600)

    def _stop_pulse(self) -> None:
        if self._pulse_timer is not None:
            self._pulse_timer.stop()
        self._pulse_state = False

    # ── 页面导航 ──

    def navigate_to(self, page_id: str, **kwargs) -> None:
        """导航到指定页面，使用 PageRegistry 动态解析 Qt 页面类。"""
        if not isinstance(page_id, str):
            logger.warning("navigate_to: ignoring non-string page_id=%r", page_id)
            return
        from src.panel.pages.page_registry import PageRegistry

        # 记录执行器来源页面
        if (
            self.executor
            and self.executor.is_running
            and self._current_page_id in (PAGE_WORKFLOW_EDITOR, PAGE_ACTION_CHAIN)
        ):
            self._executor_source_page = self._current_page_id

        # 如果导航到当前页面，重建
        if page_id == self._current_page_id:
            self._remove_current_page()

        # 尝试从缓存恢复
        if page_id in self._page_cache:
            self._cache_current_page()
            page = self._page_cache.pop(page_id)
            self._stack.addWidget(page)
            self._stack.setCurrentWidget(page)
            if hasattr(page, "apply_theme"):
                page.apply_theme()
            if hasattr(page, "on_enter"):
                page.on_enter(**kwargs)
            self._current_page_id = page_id
            self.setWindowTitle(f"Action<DNA> — {page_id}")
            return

        # 通过 PageRegistry 解析并创建真实页面
        self._cache_current_page()
        try:
            page_class = PageRegistry.resolve(page_id)
            page = page_class(self._stack, self, **kwargs)
            page.build()
            page.on_enter(**kwargs)
        except Exception:
            logger.warning("Failed to create Qt page '%s', using placeholder", page_id, exc_info=True)
            page = self._create_placeholder(page_id)

        self._stack.addWidget(page)
        self._stack.setCurrentWidget(page)
        self._current_page_id = page_id
        self.setWindowTitle(f"Action<DNA> — {page_id}")

    def _create_placeholder(self, page_id: str) -> QWidget:
        """创建占位页面。"""
        th = current_theme()
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 24, 24, 24)

        title = QLabel(f"📋 {page_id}")
        title.setStyleSheet(f"color: {th.text_primary}; font-size: 20px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        hint = QLabel("此页面将在后续 Phase 中实现\n当前使用 PySide6 后端")
        hint.setStyleSheet(f"color: {th.text_muted}; font-size: 12px; background: transparent;")
        layout.addWidget(hint)
        layout.addStretch()

        return page

    def _cache_current_page(self) -> None:
        if self._current_page_id is None:
            return
        old_id = self._current_page_id
        widget = self._stack.currentWidget()
        if widget is not None:
            self._stack.removeWidget(widget)
            self._page_cache[old_id] = widget

            while len(self._page_cache) > self._max_cache_size:
                evict_id, evict = self._page_cache.popitem(last=False)
                if evict is not None:
                    _safe_destroy_page(evict)
                    evict.deleteLater()

    def _remove_current_page(self) -> None:
        widget = self._stack.currentWidget()
        if widget is not None:
            self._stack.removeWidget(widget)
            _safe_destroy_page(widget)
            widget.deleteLater()
        self._current_page_id = None

    def clear_page_cache(self) -> None:
        for pid in list(self._page_cache):
            page = self._page_cache.pop(pid)
            _safe_destroy_page(page)
            page.deleteLater()

    # ── 公共访问器（供 HomeStateMixin 使用）──

    def get_cached_page(self, page_id: str):
        return self._page_cache.get(page_id)

    def set_executor_source(self, page_type: str) -> None:
        self._executor_source_page = page_type

    def get_executor_source(self) -> str | None:
        return self._executor_source_page

    # ── 生命周期 ──

    def schedule_restart(self) -> None:
        """停止独占资源 → 启动新进程 → 终止当前进程。"""
        self._stop_services()
        try:
            from src.utils.restart import restart_app
            restart_app()
        except Exception:  # pylint: disable=broad-exception-caught
            logger.exception("重启失败，尝试恢复服务")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, t("app.title"), t("settings.restart_failed"))
            self._services_ready = True

    def _stop_services(self) -> None:
        """按正确顺序停止所有服务，释放独占资源防止新旧进程冲突。

        顺序：回调/轮询 → 热键 → 执行器 → 插件 → 截图 → 缓存
        """
        self._unregister_theme_callback()
        if self._sys_theme_timer:
            self._sys_theme_timer.stop()
            self._sys_theme_timer = None
        if self._monitor_timer:
            self._monitor_timer.stop()
            self._monitor_timer = None
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

    def run(self) -> None:
        """显示窗口并启动事件循环。"""
        self.show()
        QApplication.instance().exec()

    def closeEvent(self, event) -> None:
        """窗口关闭时清理资源。"""
        try:
            self._unregister_theme_callback()
            if self._sys_theme_timer:
                self._sys_theme_timer.stop()
            if self._monitor_timer:
                self._monitor_timer.stop()
            self._stop_pulse()
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
        except Exception:
            logger.warning("关闭清理异常", exc_info=True)
        event.accept()
