"""FailSafeLayer — 将 FailSafe 检查移入 Layer 管道。

在每个节点执行前检查鼠标是否在屏幕角落，如果是则抛出 FailSafeTriggered
以紧急停止执行。替代 ActionExecutor._check_fail_safe() 的手动调用。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.fail_safe import FailSafeMonitor, FailSafeTriggered
from src.core.layers.layer import GraphLayer
from src.utils.i18n import t

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

__all__ = ["FailSafeLayer"]


class FailSafeLayer(GraphLayer):
    """在每个节点入口检查鼠标角落位置，触发紧急停止。"""

    def __init__(self, fail_safe: FailSafeMonitor, input_ctrl, capture) -> None:
        self._fail_safe = fail_safe
        self._input = input_ctrl
        self._capture = capture

    @property
    def name(self) -> str:
        return "failsafe"

    @property
    def priority(self) -> int:
        return SystemPriority.SAFETY_CHECK

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        if not self._fail_safe.enabled:
            return ctx
        try:
            mx, my = self._input.get_mouse_position()
            screen_w, screen_h = self._capture.get_screen_size()
            self._fail_safe.check(mx, my, screen_w, screen_h)
        except FailSafeTriggered:
            raise
        except Exception:
            logger.warning(t("layers.log.failsafe_check_exception"), exc_info=True)
        return ctx
