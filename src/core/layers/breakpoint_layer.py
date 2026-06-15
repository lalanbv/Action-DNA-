"""BreakpointLayer — 断点调试支持层。

管理断点集合，在命中断点时暂停执行等待用户操作。
支持无条件断点、条件断点、一次性断点。

所有断点存储统一委托给 Debugger.breakpoints (BreakpointManager)。
"""

from __future__ import annotations

import logging
import os
import threading
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from src.core.debug.breakpoint_manager import BreakpointType
from src.core.debug.debugger import Debugger
from src.core.engine.priority import SystemPriority
from src.core.layers.layer import ErrorContext, GraphLayer
from src.core.safe_eval import build_eval_context, safe_eval
from src.utils.i18n import t
from src.utils.paths import get_logs_dir

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext
    from src.core.engine.node_result import NodeResult

__all__ = ["BreakpointLayer", "StopExecution", "DebugMode"]

logger = logging.getLogger(__name__)


class DebugMode(StrEnum):
    """调试模式枚举。"""

    CONTINUE = "continue"
    STEP_OVER = "step_over"
    STEP_INTO = "step_into"
    STOP = "stop"


class StopExecution(Exception):
    """用户请求停止执行（非错误，正常退出）。"""


class BreakpointLayer(GraphLayer):
    """断点调试支持层。

    所有断点通过 Debugger.breakpoints (BreakpointManager) 管理，
    单步执行（step_over/step_into）由本层负责。
    """

    def __init__(self, debugger: Debugger | None = None) -> None:
        self._debugger: Debugger = debugger or Debugger()
        self._lock = threading.Lock()
        self._debug_mode: DebugMode = DebugMode.CONTINUE
        self._step_next: bool = False
        self._step_target_node: str | None = None
        self._resume_event: threading.Event = threading.Event()
        self._hit_count: dict[str, int] = {}
        self._screenshot_on_hit: bool = True

    @property
    def name(self) -> str:
        return "breakpoint"

    @property
    def priority(self) -> int:
        return SystemPriority.DEBUG

    @property
    def debugger(self) -> Debugger:
        return self._debugger

    @property
    def debug_mode(self) -> DebugMode:
        return self._debug_mode

    @debug_mode.setter
    def debug_mode(self, mode: DebugMode | str) -> None:
        if isinstance(mode, str):
            try:
                mode = DebugMode(mode)
            except ValueError:
                valid = ", ".join(m.value for m in DebugMode)
                raise ValueError(t("layers.exc.invalid_debug_mode", mode=mode, valid=valid)) from None
        with self._lock:
            self._debug_mode = mode

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        with self._lock:
            self._hit_count.clear()
            self._step_next = False

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        node_id = ctx.current_node.node_id

        with self._lock:
            step_next = self._step_next
            target = self._step_target_node
            if step_next:
                self._step_next = False
                self._step_target_node = None

        if step_next and (target is None or target == node_id):
            hit_count = self._increment_hit_count(node_id)
            self._hit_and_wait(ctx, node_id, hit_count)
            return ctx

        bp = self._debugger.breakpoints.get_breakpoint(node_id)

        if bp is None:
            if getattr(ctx.current_node, "breakpoint", False) is not True:
                return ctx
            self._debugger.breakpoints.add_breakpoint(node_id)
            bp = self._debugger.breakpoints.get_breakpoint(node_id)

        hit_count = self._increment_hit_count(node_id)

        if bp.condition and not self._evaluate_condition(bp.condition, ctx, hit_count):
            return ctx

        self._hit_and_wait(ctx, node_id, hit_count)

        if bp.one_shot:
            self._debugger.breakpoints.remove_breakpoint(node_id)

        return ctx

    def on_node_exit(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult:
        # Lock-free read: enum reference assignment is atomic under GIL.
        # Only acquire lock when we actually need to write _step_next.
        if self._debug_mode == DebugMode.STEP_OVER:
            with self._lock:
                self._step_next = True
                self._step_target_node = None
        return result

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        logger.debug(
            "[BREAKPOINT] 节点 %s 异常: %s",
            ctx.current_node.node_id,
            err_ctx.error,
        )
        return err_ctx

    # ---- 断点管理（委托给 BreakpointManager）----

    def add_breakpoint(
        self,
        node_id: str,
        condition: str | None = None,
        one_shot: bool = False,
    ) -> None:
        bp_type = BreakpointType.CONDITIONAL if condition else BreakpointType.LINE
        self._debugger.breakpoints.add_breakpoint(
            node_id,
            bp_type=bp_type,
            condition=condition or "",
        )
        if one_shot:
            bp = self._debugger.breakpoints.get_breakpoint(node_id)
            if bp is not None:
                bp.one_shot = True
        logger.info(
            "添加断点: %s (条件=%s, 一次性=%s)", node_id, condition, one_shot
        )

    def remove_breakpoint(self, node_id: str) -> None:
        self._debugger.breakpoints.remove_breakpoint(node_id)
        logger.info(t("layers.log.breakpoint_removed", node_id=node_id))

    def clear_breakpoints(self) -> None:
        self._debugger.breakpoints.clear_all()
        with self._lock:
            self._hit_count.clear()

    def resume(self, mode: DebugMode | str = DebugMode.CONTINUE) -> None:
        if isinstance(mode, str):
            mode = DebugMode(mode)
        with self._lock:
            self._debug_mode = mode
        self._resume_event.set()

    def get_breakpoints(self) -> list[str]:
        return [bp.node_id for bp in self._debugger.breakpoints.get_all()]

    def get_hit_count(self, node_id: str) -> int:
        with self._lock:
            return self._hit_count.get(node_id, 0)

    # ---- 内部方法 ----

    def _increment_hit_count(self, node_id: str) -> int:
        with self._lock:
            self._hit_count[node_id] = self._hit_count.get(node_id, 0) + 1
            return self._hit_count[node_id]

    def _hit_and_wait(self, ctx: ExecutionContext, node_id: str, hit_count: int) -> None:

        logger.info(
            "[BREAKPOINT] 命中断点: %s (第 %d 次)", node_id, hit_count
        )

        if self._screenshot_on_hit:
            self._save_debug_screenshot(ctx)

        if ctx.event_bus is not None:
            from src.core.events.events import BreakpointHitEvent

            ctx.event_bus.publish(
                BreakpointHitEvent(node_id=node_id)
            )

        self._resume_event.clear()
        while not self._resume_event.wait(timeout=0.2):
            if ctx.is_stopping:
                raise StopExecution(t("layers.exc.execution_stop_requested"))

        with self._lock:
            mode = self._debug_mode
        if mode == DebugMode.STOP:
            raise StopExecution(t("layers.exc.debug_mode_user_stop"))

    def _evaluate_condition(
        self,
        condition: str,
        ctx: ExecutionContext,
        hit_count: int,
    ) -> bool:
        local_vars = build_eval_context(
            ctx, {"hit_count": hit_count, "step_index": ctx.step_index, "gen": ctx.gen}
        )
        return safe_eval(condition, local_vars)

    def _save_debug_screenshot(self, ctx: ExecutionContext) -> None:
        try:
            import cv2

            debug_dir = os.path.join(get_logs_dir(), "debug")
            os.makedirs(debug_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            node_id = ctx.current_node.node_id
            filename = f"{timestamp}_{node_id}_breakpoint.png"
            filepath = os.path.join(debug_dir, filename)

            screenshot = ctx.capture.grab()
            cv2.imwrite(filepath, screenshot)

            logger.debug(t("layers.log.breakpoint_shot_saved", path=filepath))
        except Exception as e:
            logger.debug(t("layers.log.breakpoint_shot_save_failed", error=e))
