"""统一监控管理器 — 集中管理所有 BackgroundMonitor 实例。

替代 ActionExecutor._monitors: list[BackgroundMonitor] 的分散管理模式，
提供统一生命周期、健康追踪、状态快照和事件发布。
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable, Literal

from src.core.events.events import MonitorStateChangedEvent
from src.core.monitor import BackgroundMonitor, MonitorConfig

if TYPE_CHECKING:
    from src.core.events.bus import TypedEventBus
    from src.core.shared_frame_provider import SharedFrameProvider
    from src.core.vision import ScreenCapture, TemplateMatcher

    from src.core.input import InputController


@dataclass(frozen=True)
class MonitorState:
    """单个 monitor 的不可变运行时状态快照。"""

    monitor_id: str
    config_name: str
    status: Literal["idle", "running", "paused", "error"]
    trigger_count: int
    last_trigger_time: float  # monotonic, 0.0=从未触发
    consecutive_count: int
    error_count: int
    last_error: str
    last_check_time: float  # monotonic, 0.0=从未检查

    @property
    def has_ever_triggered(self) -> bool:
        return self.last_trigger_time > 0.0

    @property
    def has_ever_checked(self) -> bool:
        return self.last_check_time > 0.0

    @property
    def seconds_since_trigger(self) -> float:
        if not self.has_ever_triggered:
            return float("inf")
        return time.monotonic() - self.last_trigger_time


def _make_idle_state(monitor_id: str, config_name: str) -> MonitorState:
    return MonitorState(
        monitor_id=monitor_id,
        config_name=config_name,
        status="idle",
        trigger_count=0,
        last_trigger_time=0.0,
        consecutive_count=0,
        error_count=0,
        last_error="",
        last_check_time=0.0,
    )


class MonitorManager:
    """集中管理所有 BackgroundMonitor 实例。

    职责：
    - 统一生命周期管理（register/start/stop/pause/resume）
    - 状态快照查询（get_state/get_all_states）
    - 事件发布协调（通过 TypedEventBus）
    - handler 活跃标志（用于协调抢占）
    """

    def __init__(
        self,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
        input_ctrl: InputController,
        event_bus: TypedEventBus,
    ) -> None:
        self._capture = capture
        self._matcher = matcher
        self._input = input_ctrl
        self._event_bus = event_bus
        self._frame_provider: SharedFrameProvider | None = None

        self._monitors: dict[str, BackgroundMonitor] = {}
        self._configs: dict[str, MonitorConfig] = {}
        self._states: dict[str, MonitorState] = {}
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

        self._lock = threading.Lock()
        self._handler_count = 0
        self._handler_done_event = threading.Event()
        self._handler_done_event.set()
        self._running = False

    def set_frame_provider(self, provider: SharedFrameProvider) -> None:
        self._frame_provider = provider

    # ---- 生命周期 ----

    def register(self, config: MonitorConfig) -> str:
        """注册一个 monitor 配置，返回唯一 monitor_id。"""
        monitor_id = uuid.uuid4().hex[:8]
        with self._lock:
            self._configs[monitor_id] = config
            self._states[monitor_id] = _make_idle_state(monitor_id, config.name)

            monitor = BackgroundMonitor(
                config=config,
                capture=self._capture,
                matcher=self._matcher,
                input_ctrl=self._input,
                stop_event=self._stop_event,
                pause_event=self._pause_event,
                event_bus=self._event_bus,
                frame_provider=self._frame_provider,
                state_callback=self._make_state_callback(monitor_id),
                handler_enter_callback=self._on_handler_enter,
                handler_exit_callback=self._on_handler_exit,
            )
            self._monitors[monitor_id] = monitor
        return monitor_id

    def unregister(self, monitor_id: str) -> None:
        """移除一个 monitor（必须先停止）。"""
        with self._lock:
            monitor = self._monitors.get(monitor_id)
            if monitor and monitor.is_running:
                msg = f"Cannot unregister running monitor: {monitor_id}"
                raise RuntimeError(msg)
            self._monitors.pop(monitor_id, None)
            self._configs.pop(monitor_id, None)
            self._states.pop(monitor_id, None)

    def start_all(self) -> None:
        """启动所有已注册且 enabled 的 monitor。"""
        self._stop_event.clear()
        self._pause_event.clear()
        old_statuses, to_act = self._bulk_transition(
            "running",
            predicate=lambda mid: self._configs[mid].enabled,
            collect_monitor=True,
        )
        for mid, monitor in to_act:
            monitor.start()
        self._running = True
        self._publish_state_changes(old_statuses)

    def stop_all(self) -> None:
        """停止所有 monitor。"""
        self._stop_event.set()
        old_statuses, to_act = self._bulk_transition(
            "idle", predicate=None, collect_monitor=True,
        )
        for mid, monitor in to_act:
            monitor.stop()
        self._running = False
        self._publish_state_changes(old_statuses)

    def pause_all(self) -> None:
        """暂停所有 monitor。"""
        self._pause_event.set()
        old_statuses, _ = self._bulk_transition(
            "paused",
            predicate=lambda mid: self._states[mid].status == "running",
            collect_monitor=False,
        )
        self._publish_state_changes(old_statuses)

    def resume_all(self) -> None:
        """恢复所有暂停的 monitor。"""
        self._pause_event.clear()
        old_statuses, _ = self._bulk_transition(
            "running",
            predicate=lambda mid: self._states[mid].status == "paused",
            collect_monitor=False,
        )
        self._publish_state_changes(old_statuses)

    # ---- 状态查询 ----

    def get_state(self, monitor_id: str) -> MonitorState:
        """获取单个 monitor 的状态快照。"""
        with self._lock:
            state = self._states.get(monitor_id)
            if state is None:
                msg = f"Unknown monitor: {monitor_id}"
                raise KeyError(msg)
            return state

    def get_all_states(self) -> list[MonitorState]:
        """获取所有 monitor 的状态快照列表。"""
        with self._lock:
            return list(self._states.values())

    def get_config(self, monitor_id: str) -> MonitorConfig:
        with self._lock:
            cfg = self._configs.get(monitor_id)
            if cfg is None:
                msg = f"Unknown monitor: {monitor_id}"
                raise KeyError(msg)
            return cfg

    def get_all_configs(self) -> list[tuple[str, MonitorConfig]]:
        with self._lock:
            return list(self._configs.items())

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_handler_active(self) -> bool:
        """是否有 monitor handler 正在执行（用于协调抢占）。"""
        with self._lock:
            return self._handler_count > 0

    @property
    def monitor_count(self) -> int:
        with self._lock:
            return len(self._monitors)

    # ---- 内部回调 ----

    def _make_state_callback(self, monitor_id: str):
        """为特定 monitor 创建状态更新回调。"""

        def callback(state: MonitorState) -> None:
            with self._lock:
                old = self._states.get(monitor_id)
                self._states[monitor_id] = state
            if old and old.status != state.status:
                self._publish_state_change_event(
                    monitor_id, old.status, state.status
                )

        return callback

    def _on_handler_enter(self) -> None:
        with self._lock:
            self._handler_count += 1
            if self._handler_count == 1:
                self._handler_done_event.clear()

    def _on_handler_exit(self) -> None:
        with self._lock:
            self._handler_count = max(0, self._handler_count - 1)
            if self._handler_count == 0:
                self._handler_done_event.set()

    def wait_for_handlers(self, timeout: float) -> bool:
        """等待所有 handler 完成，返回是否在超时前完成。"""
        return self._handler_done_event.wait(timeout=timeout)

    def _publish_state_change_event(
        self, monitor_id: str, old_status: str, new_status: str
    ) -> None:
        with self._lock:
            state = self._states.get(monitor_id)
        if state is None:
            return
        self._event_bus.publish(
            MonitorStateChangedEvent(
                monitor_id=monitor_id,
                old_status=old_status,
                new_status=new_status,
                trigger_count=state.trigger_count,
            )
        )

    def _bulk_transition(
        self,
        new_status: str,
        predicate: Callable[[str], bool] | None,
        collect_monitor: bool,
    ) -> tuple[dict[str, str], list[tuple[str, BackgroundMonitor]]]:
        """批量状态转换：锁定 → 过滤 → 更新状态 → 返回操作列表。

        Args:
            new_status: 目标状态
            predicate: 过滤函数 (mid -> bool)，None 表示全选
            collect_monitor: 是否收集 monitor 实例（start/stop 需要）

        Returns:
            (old_statuses, action_list) — action_list 仅在 collect_monitor=True 时有内容
        """
        old_statuses: dict[str, str] = {}
        to_act: list[tuple[str, BackgroundMonitor]] = []
        with self._lock:
            for mid, monitor in self._monitors.items():
                if predicate is not None and not predicate(mid):
                    continue
                old_statuses[mid] = self._states[mid].status
                self._states[mid] = _update_state_status(self._states[mid], new_status)
                if collect_monitor:
                    to_act.append((mid, monitor))
        return old_statuses, to_act

    def _publish_state_changes(self, old_statuses: dict[str, str]) -> None:
        """批量发布状态变更（start/stop/pause/resume 后调用）。"""
        with self._lock:
            snapshot = list(self._states.values())
        for state in snapshot:
            old = old_statuses.get(state.monitor_id, "idle")
            if old == state.status:
                continue
            try:
                self._event_bus.publish(
                    MonitorStateChangedEvent(
                        monitor_id=state.monitor_id,
                        old_status=old,
                        new_status=state.status,
                        trigger_count=state.trigger_count,
                    )
                )
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "发布监控状态变更失败: %s", state.monitor_id,
                )


def _update_state_status(state: MonitorState, new_status: str) -> MonitorState:
    return replace(state, status=new_status)
