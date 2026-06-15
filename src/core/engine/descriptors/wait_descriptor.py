"""WaitDescriptor + WaitRandomDescriptor — 固定等待与随机等待。

WaitDescriptor:  暂停指定秒数，使用 stop_event.wait() 以便即时响应停止信号。
WaitRandomDescriptor: 在 [wait_min, wait_max] 范围内随机等待，增加操作不可预测性。
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

from src.core.engine.execution_blocker import ExecutionBlocker
from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult
from src.core.engine.pause_aware_wait import pause_aware_wait
from src.core.step_types import WaitRandomStep, WaitStep
from src.utils.i18n import t
from src.utils.timing import human_like_duration

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["WaitDescriptor", "WaitRandomDescriptor"]


@auto_register
class WaitDescriptor(NodeDescriptor):
    """固定等待描述符 — 暂停指定秒数。"""

    @classmethod
    def action_type(cls) -> str:
        return "WAIT"

    @classmethod
    def display_name(cls) -> str:
        return "等待"

    @classmethod
    def category(cls) -> str:
        return "基础动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "wait_seconds": PortDef("number", "等待秒数", required=True, default=1.0),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult | ExecutionBlocker:
        action = ctx.current_node.action
        if action is None:
            return NodeResult.fail(t("engine.node_fail.missing_step_config", node_type="WAIT"))

        if not isinstance(action, WaitStep):
            return NodeResult.fail(t("engine.node_fail.step_type_mismatch", node_type="WAIT"))

        seconds = action.wait_seconds
        if not math.isfinite(seconds):
            return NodeResult.fail(t("engine.node_fail.wait_seconds_invalid", seconds=seconds))
        if seconds < 0:
            return NodeResult.fail(t("engine.node_fail.wait_seconds_negative", seconds=seconds))

        if action.recorded_duration > 0:
            seconds = human_like_duration(action.recorded_duration)

        logger.info(t("engine.log.wait_fixed", seconds=seconds))
        if _interruptible_wait(ctx, seconds):
            return NodeResult.fail(t("engine.node_fail.stop_signal_wait_interrupt"))

        return NodeResult.ok()


@auto_register
class WaitRandomDescriptor(NodeDescriptor):
    """随机等待描述符 — 在指定范围内随机等待。"""

    @classmethod
    def action_type(cls) -> str:
        return "WAIT_RANDOM"

    @classmethod
    def display_name(cls) -> str:
        return "随机等待"

    @classmethod
    def category(cls) -> str:
        return "基础动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "wait_min": PortDef("number", "最小等待秒数", required=True, default=0.5),
            "wait_max": PortDef("number", "最大等待秒数", required=True, default=2.0),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult | ExecutionBlocker:
        action = ctx.current_node.action
        if action is None:
            return NodeResult.fail(t("engine.node_fail.missing_step_config", node_type="WAIT_RANDOM"))

        if not isinstance(action, WaitRandomStep):
            return NodeResult.fail(t("engine.node_fail.step_type_mismatch", node_type="WAIT_RANDOM"))

        wait_min = action.wait_min
        wait_max = action.wait_max

        if not (math.isfinite(wait_min) and math.isfinite(wait_max)):
            return NodeResult.fail(
                t("engine.node_fail.wait_range_invalid", wait_min=wait_min, wait_max=wait_max),
            )

        if wait_min > wait_max:
            wait_min, wait_max = wait_max, wait_min

        if wait_max < 0:
            return NodeResult.fail(t("engine.node_fail.wait_range_negative", wait_min=wait_min, wait_max=wait_max))

        wait_min = max(0.0, wait_min)
        seconds = random.uniform(wait_min, wait_max)
        logger.info(t("engine.log.wait_random", seconds=seconds, wait_min=wait_min, wait_max=wait_max))
        if _interruptible_wait(ctx, seconds):
            return NodeResult.fail(t("engine.node_fail.stop_signal_random_wait_interrupt"))

        return NodeResult.ok()


def _interruptible_wait(ctx: ExecutionContext, target_seconds: float) -> bool:
    """暂停感知的可中断等待（委托给共享工具函数）。"""
    return pause_aware_wait(ctx, target_seconds)
