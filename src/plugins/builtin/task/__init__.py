"""TaskPlugin — 任务自动化插件。

调用者:
  - PluginLoader.load() 通过 importlib.import_module("task") 导入
  - 获取 entry_class="TaskPlugin" 实例化并加载

包含 4 个节点描述符:
  - QuestAcceptDescriptor: 接取任务（找NPC+点击接取按钮）
  - DialogInteractDescriptor: 对话交互（多轮对话推进+选项选择）
  - CompleteQuestDescriptor: 完成任务（找NPC+领奖）
  - DailyResetDescriptor: 日常重置（时间判断）
"""

from __future__ import annotations

import logging
import random
import time
from datetime import datetime

from typing import Any

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_result import NodeResult
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata
from src.core.plugins.plugin_node_registry import PluginNodeRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D10: QuestAcceptDescriptor — 接取任务
# ---------------------------------------------------------------------------


class QuestAcceptDescriptor(NodeDescriptor):
    """接取任务节点描述符 — 查找NPC并接取任务。"""

    @classmethod
    def action_type(cls) -> str:
        return "accept_quest"

    @classmethod
    def display_name(cls) -> str:
        return "接取任务"

    @classmethod
    def category(cls) -> str:
        return "任务自动化"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "quest_npc_template": PortDef(
                type="image", description="任务NPC模板图片", required=True,
            ),
            "dialog_button_template": PortDef(
                type="image", description="对话框接取按钮模板", required=False,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "accepted": PortDef(type="bool", description="是否成功接取"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action

        screenshot = ctx.capture.grab()
        npc_rect = ctx.matcher.find(
            screenshot, action.quest_npc_template, threshold=0.8,
        )
        if npc_rect is None:
            return NodeResult.ok(accepted=False)

        x, y, w, h = npc_rect
        lx, ly = ctx.capture.to_logical(x + w // 2, y + h // 2)
        ctx.input_ctrl.click(lx, ly)
        time.sleep(random.uniform(0.5, 1.0))

        dialog_btn = getattr(action, "dialog_button_template", None)
        if dialog_btn:
            screenshot = ctx.capture.grab()
            btn_rect = ctx.matcher.find(
                screenshot, dialog_btn, threshold=0.8,
            )
            if btn_rect is not None:
                bx, by, bw, bh = btn_rect
                blx, bly = ctx.capture.to_logical(bx + bw // 2, by + bh // 2)
                ctx.input_ctrl.click(blx, bly)

        return NodeResult.ok(accepted=True)


# ---------------------------------------------------------------------------
# D11: DialogInteractDescriptor — 对话交互
# ---------------------------------------------------------------------------


class DialogInteractDescriptor(NodeDescriptor):
    """对话交互节点描述符 — 推进多轮对话并选择选项。"""

    @classmethod
    def action_type(cls) -> str:
        return "dialog_interact"

    @classmethod
    def display_name(cls) -> str:
        return "对话交互"

    @classmethod
    def category(cls) -> str:
        return "任务自动化"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "click_region": PortDef(
                type="coord_rect", description="对话推进点击区域",
                required=False,
            ),
            "rounds": PortDef(
                type="number", description="对话推进轮数",
                required=False, default=1,
            ),
            "option_template": PortDef(
                type="image", description="需要选择的对话选项模板",
                required=False,
            ),
            "option_round": PortDef(
                type="number",
                description="在第几轮选择选项（1-based），0 表示最后一轮",
                required=False, default=0,
            ),
            "round_delay": PortDef(
                type="number", description="每轮间隔(秒)",
                required=False, default=1.0,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "completed": PortDef(type="bool", description="对话是否完成"),
            "option_selected": PortDef(type="bool", description="是否选择了选项"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        click_region = getattr(action, "click_region", None)
        rounds = getattr(action, "rounds", 1)
        option_tpl = getattr(action, "option_template", None)
        option_round = getattr(action, "option_round", 0)
        round_delay = getattr(action, "round_delay", 1.0)

        select_at = rounds if option_round == 0 else option_round
        option_selected = False

        for i in range(1, rounds + 1):
            if option_tpl and i == select_at:
                time.sleep(round_delay * 0.5)
                screenshot = ctx.capture.grab()
                opt_rect = ctx.matcher.find(
                    screenshot, option_tpl, threshold=0.8,
                )
                if opt_rect is not None:
                    ox, oy, ow, oh = opt_rect
                    olx, oly = ctx.capture.to_logical(ox + ow // 2, oy + oh // 2)
                    ctx.input_ctrl.click(olx, oly)
                    option_selected = True
                else:
                    self._advance_dialog(ctx, click_region)
            else:
                self._advance_dialog(ctx, click_region)

            time.sleep(max(0, round_delay + random.uniform(-0.1, 0.2)))

        return NodeResult.ok(completed=True, option_selected=option_selected)

    @staticmethod
    def _advance_dialog(
        ctx: ExecutionContext,
        click_region: tuple | None,
    ) -> None:
        """推进对话 — 点击指定区域或屏幕中央。"""
        if click_region:
            rx, ry, rw, rh = click_region
            cx = rx + rw // 2 + random.randint(-10, 10)
            cy = ry + rh // 2 + random.randint(-10, 10)
            ctx.input_ctrl.click(cx, cy)
        else:
            ctx.input_ctrl.click(
                400 + random.randint(-20, 20),
                500 + random.randint(-20, 20),
            )


# ---------------------------------------------------------------------------
# CompleteQuestDescriptor — 完成任务
# ---------------------------------------------------------------------------


class CompleteQuestDescriptor(NodeDescriptor):
    """完成任务节点描述符 — 查找NPC并提交任务领奖。"""

    @classmethod
    def action_type(cls) -> str:
        return "complete_quest"

    @classmethod
    def display_name(cls) -> str:
        return "完成任务"

    @classmethod
    def category(cls) -> str:
        return "任务自动化"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "npc_template": PortDef(
                type="image", description="提交NPC模板", required=True,
            ),
            "reward_button_template": PortDef(
                type="image", description="领奖按钮模板", required=False,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "completed": PortDef(type="bool", description="是否完成提交"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action

        screenshot = ctx.capture.grab()
        npc_rect = ctx.matcher.find(
            screenshot, action.npc_template, threshold=0.8,
        )
        if npc_rect is None:
            return NodeResult.ok(completed=False)

        x, y, w, h = npc_rect
        lx, ly = ctx.capture.to_logical(x + w // 2, y + h // 2)
        ctx.input_ctrl.click(lx, ly)
        time.sleep(random.uniform(0.5, 1.0))

        reward_tpl = getattr(action, "reward_button_template", None)
        if reward_tpl:
            screenshot = ctx.capture.grab()
            reward_rect = ctx.matcher.find(
                screenshot, reward_tpl, threshold=0.8,
            )
            if reward_rect is not None:
                rx, ry, rw, rh = reward_rect
                rlx, rly = ctx.capture.to_logical(rx + rw // 2, ry + rh // 2)
                ctx.input_ctrl.click(rlx, rly)

        return NodeResult.ok(completed=True)


# ---------------------------------------------------------------------------
# DailyResetDescriptor — 日常重置
# ---------------------------------------------------------------------------


class DailyResetDescriptor(NodeDescriptor):
    """日常重置节点描述符 — 判断当前是否为日常重置时间。"""

    @classmethod
    def action_type(cls) -> str:
        return "daily_reset"

    @classmethod
    def display_name(cls) -> str:
        return "日常重置"

    @classmethod
    def category(cls) -> str:
        return "任务自动化"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "reset_time": PortDef(
                type="string", description="重置时间 (HH:MM)",
                required=False, default="04:00",
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "should_reset": PortDef(type="bool", description="是否需要重置"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        reset_time_str = getattr(action, "reset_time", "04:00")

        try:
            parts = reset_time_str.split(":")
            if len(parts) != 2:
                raise ValueError(f"Invalid time format: {reset_time_str}")
            reset_h, reset_m = int(parts[0]), int(parts[1])
            if not (0 <= reset_h <= 23 and 0 <= reset_m <= 59):
                raise ValueError(f"Time out of range: {reset_time_str}")
        except (ValueError, AttributeError) as e:
            return NodeResult.fail(f"DailyReset 时间格式错误 {reset_time_str!r}: {e}")

        now = datetime.now()
        minutes_since_midnight = now.hour * 60 + now.minute
        reset_minutes = reset_h * 60 + reset_m
        should_reset = abs(minutes_since_midnight - reset_minutes) <= 1

        if should_reset:
            return NodeResult.branch("reset", should_reset=True)
        return NodeResult.branch("skip", should_reset=False)


# ---------------------------------------------------------------------------
# TaskPlugin 入口类
# ---------------------------------------------------------------------------


class TaskPlugin(PluginInterface):
    """任务自动化插件。"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="task",
            plugin_name="任务自动化",
            version="1.0.0",
            description="任务自动化节点：接取任务、对话交互、完成任务、日常重置",
            dependencies=("navigation",),
            permissions=(
                "screen_capture",
                "template_matcher",
                "input_control",
                "events",
            ),
        )

    def on_load(self, context: PluginContext) -> None:
        logger.info("TaskPlugin 加载中...")

    def on_unload(self) -> None:
        logger.info("TaskPlugin 卸载中...")

    def register_nodes(self, registry: PluginNodeRegistry) -> None:
        """注册任务节点描述符。"""
        registry.register(QuestAcceptDescriptor)
        registry.register(DialogInteractDescriptor)
        registry.register(CompleteQuestDescriptor)
        registry.register(DailyResetDescriptor)
