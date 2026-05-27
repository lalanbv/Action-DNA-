"""BaseController — 控制器共享基础设施。

提取 ActionChainController 和 WorkflowController 共用的：
- __init__ (7 参数初始化 + 事件订阅)
- 执行控制 (start/stop/pause/resume)
- 配置文件操作 (list/load/save/delete)
- 区域操作 (set_region/set_fullscreen)
- 监控器管理 (add/remove/update/get)
- 事件回调 (_on_finished/_on_started/_on_stopped/_on_paused/_on_resumed)
- 生命周期 (destroy)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

from src.core.action_executor import ActionExecutor
from src.core.events import TypedEventBus
from src.core.events.event_names import EventName
from src.core.logger import log
from src.core.monitor import MonitorConfig
from src.core.vision import ScreenCapture, TemplateMatcher
from src.panel.models.chain_model import ChainModel, ExecutorState
from src.panel.profile_manager import ProfileManager
from src.utils.i18n import t


class BaseController(ABC):
    """控制器共享基类 — 子类仅需实现 _event_subscriptions() 和特有方法。"""

    def __init__(
        self,
        model: ChainModel,
        executor: ActionExecutor,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
        profile_mgr: ProfileManager,
        event_bus: TypedEventBus,
        main_thread_schedule,
    ) -> None:
        self.model = model
        self._executor = executor
        self._capture = capture
        self._matcher = matcher
        self._profile_mgr = profile_mgr
        self._bus = event_bus
        self._schedule_main = main_thread_schedule

        self._subscriptions: list[tuple[str, Callable]] = []
        for event, callback in self._event_subscriptions():
            self._bus.on(event, callback)
            self._subscriptions.append((event, callback))

    @abstractmethod
    def _event_subscriptions(self) -> list[tuple[str, Callable]]:
        """返回子类需要订阅的 (event_name, callback) 列表。"""

    # ── 保护 ──────────────────────────────────────────────

    def _require_idle(self) -> None:
        if self._executor.is_running:
            raise RuntimeError("执行器运行中，无法修改")

    # ── 监控器管理 ──────────────────────────────────────────

    def add_monitor(self, monitor: MonitorConfig) -> None:
        self.model.add_monitor(monitor)

    def remove_monitor(self, index: int) -> None:
        self.model.remove_monitor(index)

    def update_monitor(self, index: int, monitor: MonitorConfig) -> None:
        self.model.update_monitor(index, monitor)

    def get_monitors(self) -> list[MonitorConfig]:
        return self.model.get_monitors()

    # ── 执行控制 ──────────────────────────────────────────

    @abstractmethod
    def start_chain(self) -> None:
        """启动执行（子类决定前置校验）。"""

    def stop_chain(self) -> None:
        if not self._executor.is_running:
            return
        self._executor.stop()

    def pause_chain(self) -> None:
        if not self._executor.is_running or self._executor.is_paused:
            return
        self._executor.pause()

    def resume_chain(self) -> None:
        if not self._executor.is_paused:
            return
        self._executor.resume()

    # ── 配置文件 ──────────────────────────────────────────

    def list_profiles(self) -> list[str]:
        return self._profile_mgr.list_profiles()

    def load_profile(self, name: str) -> None:
        self._require_idle()
        if not self._profile_mgr.exists(name):
            raise FileNotFoundError(t("profile.error.file_not_found", path=name))
        graph = self._profile_mgr.load(name)
        self._matcher.clear_cache()
        self.model.load_graph(graph, name)
        log.info("已加载配置: %s", name)

    def save_profile(self, name: str | None = None) -> str | None:
        name = name or self.model.current_profile_name
        if not name:
            return None
        self._profile_mgr.save(name, self.model.graph)
        self.model.current_profile_name = name
        self.model.mark_clean()
        log.info("配置已保存: %s", name)
        return name

    def delete_profile(self, name: str) -> None:
        self._profile_mgr.delete(name)
        if self.model.current_profile_name == name:
            self.model.current_profile_name = None
        log.info("已删除配置: %s", name)

    # ── 区域 ──────────────────────────────────────────────

    def set_region(self, left: int, top: int, width: int, height: int) -> None:
        self._capture.set_region(left, top, width, height)
        self.model.set_region("custom", (left, top, width, height))

    def set_fullscreen(self) -> None:
        self._capture.set_fullscreen()
        self.model.set_region("fullscreen")

    # ── 执行器事件回调（共享）──────────────────────────────

    def _on_finished(self, **kwargs):
        self.model.set_executor_state(ExecutorState.IDLE)

    def _on_started(self, **kwargs):
        self.model.set_executor_state(ExecutorState.RUNNING)

    def _on_stopped(self, **kwargs):
        self.model.set_executor_state(ExecutorState.IDLE)

    def _on_paused(self, **kwargs):
        self.model.set_executor_state(ExecutorState.PAUSED)

    def _on_resumed(self, **kwargs):
        self.model.set_executor_state(ExecutorState.RUNNING)

    # ── 生命周期 ──────────────────────────────────────────────

    def destroy(self) -> None:
        """取消所有事件订阅，防止页面销毁后回调泄漏"""
        for event, callback in self._subscriptions:
            self._bus.off(event, callback)
        self._subscriptions.clear()
