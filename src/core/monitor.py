"""后台监控器 — 运行时检测意外弹窗并自动处理。

重构版本：
- 支持通过 SharedFrameProvider 获取线程安全截图
- 通过 state_callback 推送不可变状态快照
- 通过 handler_enter/exit_callback 协调抢占
- 保留旧的直接 ScreenCapture 路径作为降级
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

import numpy as np

from src.core.action import FoundAction
from src.core.events.events import MonitorTriggeredEvent
from src.core.logger import log
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.events.bus import TypedEventBus
    from src.core.input import InputController
    from src.core.monitor_manager import MonitorState
    from src.core.shared_frame_provider import SharedFrameProvider
    from src.core.vision import ScreenCapture, TemplateMatcher


@dataclass
class MonitorConfig:
    """后台监控器配置"""

    name: str = ""
    enabled: bool = True
    # 检测目标
    image_path: str = ""        # 要监控的模板图片
    threshold: float = 0.8
    check_interval: float = 1.0  # 检测间隔（秒）
    # 处理动作
    handler_action: FoundAction = FoundAction.LEFT_CLICK
    handler_image_path: str = ""  # 可选：点击另一张图片（如关闭按钮）
    # 限制
    priority: int = 0            # 优先级（高先检查）
    max_consecutive: int = 3     # 连续触发上限
    cooldown: float = 2.0        # 触发后冷却（秒）

    def __post_init__(self) -> None:
        if not self.name:
            self.name = t("common.unnamed_monitor")

    def describe(self) -> str:
        name = self.image_path.rsplit("/", 1)[-1] if self.image_path else t("common.not_set")
        status = t("common.enabled") if self.enabled else t("monitor.disabled")
        return t("monitor.describe", name=self.name, target=name, action=self.handler_action.value, status=status)


class BackgroundMonitor:
    """后台监控线程 — 独立运行，检测并处理意外弹窗。

    不修改主流程的程序计数器，仅在检测到目标时执行处理动作。
    通过 state_callback 向 MonitorManager 推送不可变状态快照。
    通过 handler_enter/exit_callback 标记 handler 活跃状态。
    """

    def __init__(
        self,
        config: MonitorConfig,
        capture: ScreenCapture,
        matcher: TemplateMatcher,
        input_ctrl: InputController,
        stop_event: threading.Event,
        pause_event: threading.Event,
        event_bus: TypedEventBus | None = None,
        frame_provider: SharedFrameProvider | None = None,
        state_callback: Callable[[MonitorState], None] | None = None,
        handler_enter_callback: Callable[[], None] | None = None,
        handler_exit_callback: Callable[[], None] | None = None,
    ):
        self._config = config
        self._capture = capture
        self._matcher = matcher
        self._input = input_ctrl
        self._stop_event = stop_event
        self._pause_event = pause_event
        self._event_bus = event_bus
        self._frame_provider = frame_provider
        self._state_callback = state_callback
        self._handler_enter = handler_enter_callback
        self._handler_exit = handler_exit_callback

        self._thread: threading.Thread | None = None
        self._last_trigger_time: float = 0.0
        self._consecutive_count: int = 0
        self._trigger_count: int = 0
        self._error_count: int = 0
        self._last_error: str = ""
        self._last_check_time: float = 0.0
        self._status: str = "idle"
        self._state_lock = threading.Lock()

    def start(self) -> None:
        """启动监控线程"""
        if self._thread is not None and self._thread.is_alive():
            return
        self._consecutive_count = 0
        self._last_trigger_time = 0.0
        self._trigger_count = 0
        self._error_count = 0
        self._last_error = ""
        self._status = "running"
        self._thread = threading.Thread(
            target=self._run, name=f"monitor-{self._config.name}", daemon=True
        )
        self._thread.start()
        log.info(t("monitor.log.started") + f": {self._config.name}")
        self._push_state()

    def stop(self) -> None:
        """停止监控线程"""
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=3.0)
        self._thread = None
        self._consecutive_count = 0
        self._status = "idle"
        self._push_state()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_handler_active(self) -> bool:
        with self._state_lock:
            return self._status == "handling"

    # ---- 内部方法 ----

    def _run(self) -> None:
        """监控主循环"""
        while not self._stop_event.is_set():
            if self._pause_event.is_set() and not self._stop_event.is_set():
                with self._state_lock:
                    self._status = "paused"
                self._push_state()
                self._pause_event.wait(timeout=0.1)
                continue
            if self._stop_event.is_set():
                return

            try:
                self._check()
            except Exception:
                log.exception(t("monitor.log.check_error") + f": {self._config.name}")
                with self._state_lock:
                    self._error_count += 1
                    self._last_error = "check error"

            self._stop_event.wait(self._config.check_interval)

    def _check(self) -> None:
        """执行一次检测"""
        if not self._config.enabled or not self._config.image_path:
            return

        with self._state_lock:
            self._last_check_time = time.monotonic()
            self._status = "running"

        screen = self._grab_frame()
        try:
            rect = self._matcher.find(screen, self._config.image_path, self._config.threshold)
        except (FileNotFoundError, ValueError):
            return

        if rect is None:
            with self._state_lock:
                self._consecutive_count = 0
            self._push_state()
            return

        now = time.monotonic()

        # 冷却 + 连续触发 + 触发计数（合并为一次加锁，避免 _last_trigger_time 竞态）
        with self._state_lock:
            if now - self._last_trigger_time < self._config.cooldown:
                return
            self._consecutive_count += 1
            if self._consecutive_count > self._config.max_consecutive:
                log.warning(
                    f"{self._config.name} {t('monitor.log.consecutive_limit')}: "
                    f"{self._consecutive_count}/{self._config.max_consecutive}"
                )
                return
            self._trigger_count += 1
            self._last_trigger_time = now

        log.info(f"{self._config.name} {t('monitor.log.target_found')}: {rect}")

        # 发布类型化事件
        if self._event_bus is not None:
            self._event_bus.publish(MonitorTriggeredEvent(
                monitor_id=self._config.name,
                match_position=(rect[0], rect[1]),
                action_taken=self._config.handler_action.value,
                consecutive_count=self._consecutive_count,
            ))

        # 执行处理
        target_rect = rect
        if self._config.handler_image_path:
            try:
                handler_rect = self._matcher.find(
                    screen, self._config.handler_image_path, self._config.threshold
                )
                if handler_rect:
                    target_rect = handler_rect
            except (FileNotFoundError, ValueError):
                pass

        self._handle(target_rect)
        self._push_state()

    def _handle(self, rect: tuple[int, int, int, int]) -> None:
        """对检测到的区域执行处理动作"""
        if self._handler_enter:
            self._handler_enter()
        try:
            with self._state_lock:
                self._status = "handling"
            self._push_state()

            logical_rect = self._capture.to_logical_rect(rect)
            lx, ly, lw, lh = logical_rect
            cx, cy = lx + lw // 2, ly + lh // 2

            match self._config.handler_action:
                case FoundAction.LEFT_CLICK:
                    ax, ay = self._input.move_to(cx, cy)
                    self._input.left_click(ax, ay)
                case FoundAction.RIGHT_CLICK:
                    ax, ay = self._input.move_to(cx, cy)
                    self._input.right_click(ax, ay)
                case FoundAction.LEFT_DOUBLE_CLICK:
                    ax, ay = self._input.move_to(cx, cy)
                    self._input.left_double_click(ax, ay)
                case FoundAction.ONLY_MOVE:
                    self._input.move_to(cx, cy)
                case _:
                    ax, ay = self._input.move_to(cx, cy)
                    self._input.left_click(ax, ay)

            log.info(
                f"{self._config.name} {t('monitor.log.handled')}: "
                f"{self._config.handler_action.value} at ({cx}, {cy})"
            )
        finally:
            with self._state_lock:
                self._status = "running"
            if self._handler_exit:
                self._handler_exit()

    def _grab_frame(self) -> np.ndarray:
        """获取截图帧，优先使用 SharedFrameProvider。"""
        if self._frame_provider is not None:
            return self._frame_provider.get_frame()
        return self._capture.grab()

    def _push_state(self) -> None:
        """推送当前状态快照到 MonitorManager。"""
        if self._state_callback is None:
            return
        from src.core.monitor_manager import MonitorState
        with self._state_lock:
            state = MonitorState(
                monitor_id=self._config.name,
                config_name=self._config.name,
                status=self._status,
                trigger_count=self._trigger_count,
                last_trigger_time=self._last_trigger_time,
                consecutive_count=self._consecutive_count,
                error_count=self._error_count,
                last_error=self._last_error,
                last_check_time=self._last_check_time,
            )
        self._state_callback(state)
