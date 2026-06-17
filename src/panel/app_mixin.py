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

    def _safe_get_service(self, svc_type: type):
        """安全获取服务: 工厂实例化失败时返回 None 而非抛异常。

        用于分阶段服务初始化的降级路径 —— 某个重型服务(如 Windows exe 下的
        ScreenCapture)工厂抛异常时,不应拖垮整个初始化链。``try_get`` 仅在「未注册」
        时返回 None;已注册但工厂失败仍会抛。此包装确保降级场景下拿到 None,
        让后续阶段(executor 注册)能继续。
        """
        try:
            return self._container.try_get(svc_type)
        except Exception:  # noqa: BLE001 — 降级: 工厂失败返回 None
            logger.debug(
                "服务获取失败(降级为 None): %s",
                getattr(svc_type, "__name__", svc_type),
                exc_info=True,
            )
            return None

    @property
    def event_bus(self):
        from src.core.events.bus import TypedEventBus
        return self._container.try_get(TypedEventBus)

    @property
    def executor(self):
        from src.core.action_executor import ActionExecutor
        return self._container.try_get(ActionExecutor)

    @property
    def ring_log(self):
        """共享执行日志缓冲(单例)。tkinter/Qt 双后端与所有页面共用同一实例。"""
        from src.core.debug.ring_buffer_log import RingBufferLog
        return self._container.try_get(RingBufferLog)

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
