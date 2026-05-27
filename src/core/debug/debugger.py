"""Debugger — 节点级调试器 + 桌面上下文服务。

提供断点管理、单步执行（step-over/step-into/step-out）、
变量检视和执行状态可视化。

与 BreakpointLayer 集成：BreakpointLayer 在 on_node_enter 中
调用 Debugger.check_breakpoint()，命中断点时阻塞工作线程等待用户操作。

DesktopContextService 收集运行时桌面状态（光标、屏幕、截图年龄、引擎状态），
注入到执行日志和调试信息中。
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Protocol

from src.core.debug.breakpoint_manager import (
    BreakpointManager,
    BreakpointType,
)
from src.core.safe_eval import build_eval_context, safe_eval

logger = logging.getLogger(__name__)

__all__ = [
    "DebugAction",
    "DebuggerState",
    "Debugger",
    "DesktopContextService",
    "VariableSnapshot",
]


class DebugAction(Enum):
    """调试动作。"""

    CONTINUE = "continue"
    STEP_OVER = "step_over"
    STEP_INTO = "step_into"
    STEP_OUT = "step_out"
    STOP = "stop"


class DebuggerState(Enum):
    """调试器状态。"""

    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STEPPING = "stepping"


@dataclass
class VariableSnapshot:
    """变量快照。"""

    name: str
    value: Any
    var_type: str


class Debugger:
    """节点级调试器。

    通过 threading.Event 实现线程同步：
    命中断点时暂停工作线程，等待用户操作（继续/单步/停止）。
    """

    def __init__(self) -> None:
        self._state = DebuggerState.IDLE
        self._breakpoint_manager = BreakpointManager()
        self._action_event = threading.Event()
        self._pending_action: DebugAction = DebugAction.CONTINUE
        self._lock = threading.Lock()

        self._on_state_change: list[Callable] = []
        self._on_breakpoint_hit: list[Callable] = []

        self._current_variables: list[VariableSnapshot] = []
        self._current_node_id: str | None = None
        self._call_stack: list[str] = []

    # ---- 状态 ----

    @property
    def state(self) -> DebuggerState:
        return self._state

    def _set_state(self, new_state: DebuggerState) -> None:
        old_state = self._state
        self._state = new_state
        if old_state != new_state:
            logger.info("调试器状态: %s → %s", old_state.value, new_state.value)
            for cb in self._on_state_change:
                try:
                    cb(old_state, new_state)
                except Exception as e:
                    logger.error("调试器回调异常: %s", e)

    # ---- 断点 ----

    @property
    def breakpoints(self) -> BreakpointManager:
        return self._breakpoint_manager

    # ---- 调试控制 ----

    def start(self) -> None:
        """开始调试会话。"""
        self._action_event.clear()
        self._set_state(DebuggerState.RUNNING)

    def pause(self) -> None:
        """暂停执行。"""
        self._set_state(DebuggerState.PAUSED)

    def resume(self) -> None:
        """继续执行。"""
        self._pending_action = DebugAction.CONTINUE
        self._set_state(DebuggerState.RUNNING)
        self._action_event.set()

    def step_over(self) -> None:
        """单步跳过。"""
        self._pending_action = DebugAction.STEP_OVER
        self._set_state(DebuggerState.STEPPING)
        self._action_event.set()

    def step_into(self) -> None:
        """单步进入。"""
        self._pending_action = DebugAction.STEP_INTO
        self._set_state(DebuggerState.STEPPING)
        self._action_event.set()

    def step_out(self) -> None:
        """单步跳出。"""
        self._pending_action = DebugAction.STEP_OUT
        self._set_state(DebuggerState.RUNNING)
        self._action_event.set()

    def stop(self) -> None:
        """停止调试。"""
        self._pending_action = DebugAction.STOP
        self._set_state(DebuggerState.IDLE)
        self._action_event.set()

    # ---- 断点检查（由 BreakpointLayer 调用）----

    def check_breakpoint(self, node_id: str, ctx: Any = None) -> DebugAction | None:
        """检查是否命中断点。

        由 BreakpointLayer.on_node_enter() 调用。
        命中断点时阻塞工作线程直到用户操作。

        返回 DebugAction（用户选择的动作）或 None（未命中）。
        """
        bp = self._breakpoint_manager.get_breakpoint(node_id)

        if bp is None or not bp.enabled:
            if self._state == DebuggerState.STEPPING:
                eval_ctx = build_eval_context(ctx)
                self._pause_at_node(node_id, eval_ctx)
                return self._pending_action
            return None

        with self._lock:
            bp.hit_count += 1

        if bp.bp_type == BreakpointType.LOG:
            logger.info("[日志断点] %s: %s", node_id, bp.log_message)
            return None

        eval_ctx = build_eval_context(ctx)

        if bp.bp_type == BreakpointType.CONDITIONAL and not safe_eval(bp.condition, eval_ctx):
            return None

        self._pause_at_node(node_id, eval_ctx)
        return self._pending_action

    def _pause_at_node(self, node_id: str, eval_ctx: dict[str, Any]) -> None:
        """在节点处暂停，阻塞工作线程。"""
        self._current_node_id = node_id
        self._update_variable_snapshot(eval_ctx)
        self._set_state(DebuggerState.PAUSED)

        for cb in self._on_breakpoint_hit:
            try:
                cb(node_id)
            except Exception as e:
                logger.error("断点回调异常: %s", e)

        self._action_event.wait()
        self._action_event.clear()

    def _update_variable_snapshot(self, eval_ctx: dict[str, Any]) -> None:
        """更新变量快照。"""
        self._current_variables = [
            VariableSnapshot(
                name=name,
                value=value,
                var_type=type(value).__name__,
            )
            for name, value in eval_ctx.items()
        ]

    # ---- 变量检视 ----

    @property
    def current_variables(self) -> list[VariableSnapshot]:
        return list(self._current_variables)

    @property
    def current_node_id(self) -> str | None:
        return self._current_node_id

    @property
    def call_stack(self) -> list[str]:
        return list(self._call_stack)

    # ---- 回调 ----

    def on_state_change(self, callback: Callable) -> None:
        """注册状态变化回调。"""
        self._on_state_change.append(callback)

    def remove_on_state_change(self, callback: Callable) -> None:
        """移除状态变化回调。"""
        self._on_state_change = [cb for cb in self._on_state_change if cb != callback]

    def on_breakpoint_hit(self, callback: Callable) -> None:
        """注册断点命中回调。"""
        self._on_breakpoint_hit.append(callback)

    def remove_on_breakpoint_hit(self, callback: Callable) -> None:
        """移除断点命中回调。"""
        self._on_breakpoint_hit = [cb for cb in self._on_breakpoint_hit if cb != callback]


# ---------------------------------------------------------------------------
# DesktopContextService — 运行时桌面上下文收集
# ---------------------------------------------------------------------------


class _HasPosition(Protocol):
    def position(self) -> tuple[int, int]: ...


class _HasSize(Protocol):
    def size(self) -> tuple[int, int]: ...


class _HasRegion(Protocol):
    def get_active_region(self) -> tuple[int, int, int, int] | None: ...


class _HasFrameAge(Protocol):
    @property
    def cache_age(self) -> float: ...


class _HasState(Protocol):
    @property
    def state(self) -> str: ...


@dataclass(frozen=True)
class DesktopContext:
    """某一时刻的桌面上下文快照（不可变）。"""

    cursor_position: tuple[int, int]
    screen_size: tuple[int, int]
    active_region: tuple[int, int, int, int] | None
    buffer_pool_age_ms: float
    engine_state: str
    timestamp: float


class DesktopContextService:
    """收集运行时桌面上下文，注入到执行日志和调试信息。

    可选依赖通过 setter 注入，缺失时返回默认值（优雅降级）。
    """

    def __init__(
        self,
        *,
        pyautogui_module: _HasPosition & _HasSize | None = None,
    ) -> None:
        self._pyautogui = pyautogui_module
        self._region_picker: _HasRegion | None = None
        self._frame_provider: _HasFrameAge | None = None
        self._executor: _HasState | None = None

    def set_region_picker(self, picker: _HasRegion | None) -> None:
        self._region_picker = picker

    def set_frame_provider(self, provider: _HasFrameAge | None) -> None:
        self._frame_provider = provider

    def set_executor(self, executor: _HasState | None) -> None:
        self._executor = executor

    def get_context(self) -> DesktopContext:
        """收集当前桌面上下文。"""
        cursor = (0, 0)
        screen = (0, 0)
        if self._pyautogui is not None:
            try:
                cursor = self._pyautogui.position()
            except Exception:
                logger.debug("获取光标位置失败", exc_info=True)
            try:
                screen = self._pyautogui.size()
            except Exception:
                logger.debug("获取屏幕尺寸失败", exc_info=True)

        active_region: tuple[int, int, int, int] | None = None
        if self._region_picker is not None:
            try:
                active_region = self._region_picker.get_active_region()
            except Exception:
                logger.debug("获取活动区域失败", exc_info=True)

        cache_age = 0.0
        if self._frame_provider is not None:
            try:
                cache_age = self._frame_provider.cache_age * 1000
            except Exception:
                logger.debug("获取缓存年龄失败", exc_info=True)

        engine_state = "idle"
        if self._executor is not None:
            try:
                engine_state = self._executor.state
            except Exception:
                logger.debug("获取引擎状态失败", exc_info=True)

        return DesktopContext(
            cursor_position=cursor,
            screen_size=screen,
            active_region=active_region,
            buffer_pool_age_ms=cache_age,
            engine_state=engine_state,
            timestamp=time.time(),
        )

    def format_for_log(self) -> str:
        """格式化为日志友好的一行。"""
        ctx = self.get_context()
        parts = [
            f"cursor={ctx.cursor_position}",
            f"screen={ctx.screen_size}",
            f"region={ctx.active_region}",
            f"buffer_age={ctx.buffer_pool_age_ms:.0f}ms",
            f"engine={ctx.engine_state}",
        ]
        return "DESKTOP_CONTEXT | " + " ".join(parts)

    def format_for_debug(self) -> dict[str, Any]:
        """格式化为调试面板字典。"""
        ctx = self.get_context()
        return {
            "cursor_position": ctx.cursor_position,
            "screen_size": ctx.screen_size,
            "active_region": ctx.active_region,
            "buffer_pool_age_ms": round(ctx.buffer_pool_age_ms, 1),
            "engine_state": ctx.engine_state,
            "timestamp": ctx.timestamp,
        }
