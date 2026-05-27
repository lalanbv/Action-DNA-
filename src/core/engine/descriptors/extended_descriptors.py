"""占位描述符 — 委托回 ActionExecutor 私有方法的过渡实现。

这些描述符将在后续迭代中逐步提取为独立实现。
当前通过 ctx.extra["executor"] 回调到 ActionExecutor 的私有方法，
确保 GraphEngine 管道统一，不出现未注册类型的异常。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_registry import auto_register
from src.core.engine.node_result import NodeResult

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

from src.core.step_types import (
    HoldKeyStep,
    IdleBehaviorStep,
    KeyComboStep,
    MouseDragStep,
    MouseScrollStep,
    MultiKeySequenceStep,
    MouseMoveStep,
    StartTimerStep,
)

logger = logging.getLogger(__name__)


def _get_executor(ctx: ExecutionContext):
    """从上下文获取 ActionExecutor 引用。"""
    return ctx.extra.get("_executor")


@auto_register
class HoldKeyDescriptor(NodeDescriptor):
    """HOLD_KEY: 长按一个或多个按键。"""

    @classmethod
    def action_type(cls) -> str:
        return "HOLD_KEY"

    @classmethod
    def display_name(cls) -> str:
        return "长按按键"

    @classmethod
    def category(cls) -> str:
        return "高级动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "keys_hold": PortDef("str", "按键列表(逗号分隔)", required=False),
            "key": PortDef("str", "按键", required=False),
            "hold_duration": PortDef("float", "按住时长(秒)", required=True, default=1.0),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        executor = _get_executor(ctx)
        if executor is None:
            return NodeResult.fail("executor not available")
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("HOLD_KEY 节点缺少步骤配置")
        executor._do_hold_key(cast(HoldKeyStep, node.action), ctx.gen)
        return NodeResult.ok()


@auto_register
class MouseScrollDescriptor(NodeDescriptor):
    """MOUSE_SCROLL: 鼠标滚轮。"""

    @classmethod
    def action_type(cls) -> str:
        return "MOUSE_SCROLL"

    @classmethod
    def display_name(cls) -> str:
        return "鼠标滚轮"

    @classmethod
    def category(cls) -> str:
        return "基础动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {"scroll_clicks": PortDef("int", "滚动次数", required=True, default=3)}

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("MOUSE_SCROLL 节点缺少步骤配置")
        ctx.input_ctrl.scroll(cast(MouseScrollStep, node.action).scroll_clicks)
        return NodeResult.ok()


@auto_register
class MouseMoveDescriptor(NodeDescriptor):
    """MOUSE_MOVE: 鼠标移动（支持无按键移动和按住按键拖拽）。"""

    @classmethod
    def action_type(cls) -> str:
        return "MOUSE_MOVE"

    @classmethod
    def display_name(cls) -> str:
        return "鼠标移动"

    @classmethod
    def category(cls) -> str:
        return "高级动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "offset_x": PortDef("int", "X偏移", required=True, default=0),
            "offset_y": PortDef("int", "Y偏移", required=True, default=0),
            "move_speed": PortDef("float", "移动速度(秒)", required=True, default=0.3),
            "curve_amount": PortDef("float", "曲线强度", required=True, default=0.0),
            "button": PortDef("str", "按住按键(空=无)", required=False, default=""),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        executor = _get_executor(ctx)
        if executor is None:
            return NodeResult.fail("executor not available")
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("MOUSE_MOVE 节点缺少步骤配置")
        action = cast(MouseMoveStep, node.action)
        if action.path_points:
            ctx.input_ctrl.replay_path(
                action.path_points,
                time_scale=action.move_speed / max(action.recorded_duration, 0.01),
            )
        else:
            executor._do_mouse_move(action, ctx.gen)
        return NodeResult.ok()


@auto_register
class MouseDragDescriptor(NodeDescriptor):
    """MOUSE_DRAG: 鼠标拖拽（从起点拖到终点）。"""

    @classmethod
    def action_type(cls) -> str:
        return "MOUSE_DRAG"

    @classmethod
    def display_name(cls) -> str:
        return "鼠标拖拽"

    @classmethod
    def category(cls) -> str:
        return "基础动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "start_x": PortDef("int", "起点X", required=True, default=0),
            "start_y": PortDef("int", "起点Y", required=True, default=0),
            "end_x": PortDef("int", "终点X", required=True, default=0),
            "end_y": PortDef("int", "终点Y", required=True, default=0),
            "button": PortDef("str", "按键(left/middle/right)", required=True, default="left"),
            "duration": PortDef("float", "拖拽时长(秒)", required=True, default=0.5),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("MOUSE_DRAG 节点缺少步骤配置")
        action = cast(MouseDragStep, node.action)
        ctx.input_ctrl.drag_to(
            action.start_x, action.start_y,
            action.end_x, action.end_y,
            duration=action.duration,
        )
        return NodeResult.ok()


@auto_register
class KeyComboDescriptor(NodeDescriptor):
    """KEY_COMBO: 组合按键。"""

    @classmethod
    def action_type(cls) -> str:
        return "KEY_COMBO"

    @classmethod
    def display_name(cls) -> str:
        return "组合按键"

    @classmethod
    def category(cls) -> str:
        return "高级动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "combo_keys": PortDef("str", "按键列表(逗号分隔)", required=True),
            "combo_mode": PortDef("str", "模式(hold_tap/sequence/all_hold)", required=True, default="hold_tap"),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        executor = _get_executor(ctx)
        if executor is None:
            return NodeResult.fail("executor not available")
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("KEY_COMBO 节点缺少步骤配置")
        executor._do_key_combo(cast(KeyComboStep, node.action), ctx.gen)
        return NodeResult.ok()


@auto_register
class MultiKeySequenceDescriptor(NodeDescriptor):
    """MULTI_KEY_SEQUENCE: 按顺序执行多个按键。"""

    @classmethod
    def action_type(cls) -> str:
        return "MULTI_KEY_SEQUENCE"

    @classmethod
    def display_name(cls) -> str:
        return "多键序列"

    @classmethod
    def category(cls) -> str:
        return "高级动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "key_sequence": PortDef("str", "按键序列(逗号分隔)", required=True),
            "key_interval_min": PortDef("float", "最小间隔(秒)", required=False, default=0.05),
            "key_interval_max": PortDef("float", "最大间隔(秒)", required=False, default=0.15),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        executor = _get_executor(ctx)
        if executor is None:
            return NodeResult.fail("executor not available")
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("MULTI_KEY_SEQUENCE 节点缺少步骤配置")
        executor._do_multi_key_sequence(cast(MultiKeySequenceStep, node.action), ctx.gen)
        return NodeResult.ok()


@auto_register
class IdleBehaviorDescriptor(NodeDescriptor):
    """IDLE_BEHAVIOR: 随机 idle 微行为。"""

    @classmethod
    def action_type(cls) -> str:
        return "IDLE_BEHAVIOR"

    @classmethod
    def display_name(cls) -> str:
        return "随机空闲行为"

    @classmethod
    def category(cls) -> str:
        return "高级动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "idle_duration": PortDef("float", "持续时间(秒)", required=True, default=5.0),
            "jitter_intensity": PortDef("int", "抖动强度(px)", required=False, default=10),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        executor = _get_executor(ctx)
        if executor is None:
            return NodeResult.fail("executor not available")
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("IDLE_BEHAVIOR 节点缺少步骤配置")
        executor._do_idle_behavior(cast(IdleBehaviorStep, node.action), ctx.gen)
        return NodeResult.ok()


@auto_register
class StartTimerDescriptor(NodeDescriptor):
    """START_TIMER: 启动命名计时器。"""

    @classmethod
    def action_type(cls) -> str:
        return "START_TIMER"

    @classmethod
    def display_name(cls) -> str:
        return "启动计时器"

    @classmethod
    def category(cls) -> str:
        return "高级动作"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "timer_name": PortDef("str", "计时器名称", required=True),
            "timer_timeout": PortDef("float", "超时(秒)", required=False, default=0.0),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        executor = _get_executor(ctx)
        if executor is None:
            return NodeResult.fail("executor not available")
        node = ctx.current_node
        if node is None or node.action is None:
            return NodeResult.fail("START_TIMER 节点缺少步骤配置")
        executor._do_start_timer(cast(StartTimerStep, node.action))
        return NodeResult.ok()
