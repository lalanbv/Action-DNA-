"""MonitorCoordinationLayer — 确保主执行流程在 monitor handler 期间等待。

当 BackgroundMonitor 检测到目标并执行处理动作（如关闭弹窗）时，
该 Layer 阻塞主执行流程，避免鼠标/键盘操作冲突。
handler 通常极快（一次点击），等待时间极短。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.core.engine.priority import SystemPriority
from src.core.layers.layer import GraphLayer
from src.core.logger import log

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

__all__ = ["MonitorCoordinationLayer"]

_HANDLER_WAIT_TIMEOUT = 5.0


class MonitorCoordinationLayer(GraphLayer):
    """在 monitor handler 活跃期间阻塞主流程。"""

    def __init__(self, monitor_manager) -> None:
        self._monitor_manager = monitor_manager

    def set_manager(self, manager) -> None:
        """设置或清除 MonitorManager 引用。"""
        self._monitor_manager = manager

    @property
    def name(self) -> str:
        return "monitor_coordination"

    @property
    def priority(self) -> int:
        return SystemPriority.PRE_PROCESS

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        if self._monitor_manager is None or not self._monitor_manager.is_handler_active:
            return ctx

        done = self._monitor_manager.wait_for_handlers(_HANDLER_WAIT_TIMEOUT)
        if not done:
            log.warning("monitor handler 等待超时 (%.1fs)", _HANDLER_WAIT_TIMEOUT)
        return ctx
