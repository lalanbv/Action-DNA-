"""ServiceProviderMixin — tkinter / Qt 后端共享的 ServiceProvider 实现。

宿主类需提供:
  - self._container: ServiceContainer
"""

from __future__ import annotations

import logging
import os
import sys

from src.utils.i18n import t

logger = logging.getLogger(__name__)


class ServiceProviderMixin:
    """ServiceProvider 协议共享实现。

    不定义 __init__，仅通过 self._container 访问服务容器。
    """

    # ── ServiceProvider properties ──

    def get(self, service_type: type) -> object:
        return self._container.get(service_type)

    def _try_get(self, svc_type: type):
        return self._container.try_get(svc_type)

    @property
    def event_bus(self):
        from src.core.events.bus import TypedEventBus
        return self._container.try_get(TypedEventBus)

    @property
    def executor(self):
        from src.core.action_executor import ActionExecutor
        return self._container.try_get(ActionExecutor)

    @property
    def capture(self):
        from src.core.vision.capture import ScreenCapture
        return self._container.try_get(ScreenCapture)

    @property
    def matcher(self):
        from src.core.vision.capture import TemplateMatcher
        return self._container.try_get(TemplateMatcher)

    @property
    def hotkey_manager(self):
        from src.core.input.hotkey_manager import HotkeyManager
        return self._container.try_get(HotkeyManager)

    @property
    def toast_manager(self):
        from src.panel.components.toast import ToastManager
        return self._container.try_get(ToastManager)

    @property
    def plugin_loader(self):
        from src.core.plugins.plugin_loader import PluginLoader
        return self._container.try_get(PluginLoader)

    @property
    def input_ctrl(self):
        from src.core.input import InputController
        return self._container.try_get(InputController)

    @property
    def node_registry(self):
        from src.core.engine.node_registry import NodeRegistry
        return self._container.try_get(NodeRegistry)

    # ── Plugin initialization ──

    def _init_plugins(self) -> None:
        """扫描并加载内置插件。"""
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.plugin_loader.add_scan_dir(os.path.join(base, "src", "plugins", "builtin"))
        self.plugin_loader.add_scan_dir("plugins")
        self.plugin_loader.scan()
        loaded, failed = self.plugin_loader.load_all()
        if loaded:
            logger.info(t("app.log.plugins_loaded", count=len(loaded)))
        if failed:
            logger.warning(t("app.log.plugin_failed", failed=failed))

    # ── Executor controls ──

    def _toggle_executor(self) -> None:
        """启动/停止执行器。快捷键仅用于停止正在运行的执行。"""
        if self.executor.is_running:
            self.executor.stop()
            logger.info(t("app.log.hotkey_stop"))
        else:
            logger.info(t("app.log.hotkey_start_hint"))

    def _emergency_stop(self) -> None:
        """紧急停止。"""
        if self.executor.is_running:
            self.executor.stop()
        logger.info(t("app.log.emergency_stop"))
