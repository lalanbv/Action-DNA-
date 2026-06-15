"""CombatPlugin — 战斗辅助插件。

调用者:
  - PluginLoader.load() 通过 importlib.import_module("combat") 导入
  - 获取 entry_class="CombatPlugin" 实例化并加载

包含 5 个节点描述符:
  - FindEnemyDescriptor: 查找敌人（模板匹配）
  - AttackDescriptor: 攻击（点击+按键连击）
  - UseSkillDescriptor: 使用技能（按键+等待）
  - DodgeDescriptor: 闪避（方向+按键）
  - TargetSelectionDescriptor: 目标选择（多匹配结果选优）
"""

from __future__ import annotations

import logging
import random
import time

from typing import Any

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_result import NodeResult
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata
from src.core.plugins.plugin_node_registry import PluginNodeRegistry
from src.utils.i18n import t

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D5: FindEnemyDescriptor — 查找敌人
# ---------------------------------------------------------------------------


class FindEnemyDescriptor(NodeDescriptor):
    """查找敌人节点描述符 — 通过模板匹配定位敌人位置。"""

    @classmethod
    def action_type(cls) -> str:
        return "find_enemy"

    @classmethod
    def display_name(cls) -> str:
        return "查找敌人"

    @classmethod
    def category(cls) -> str:
        return "战斗辅助"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "template_path": PortDef(
                type="image", description="敌人模板图片", required=True,
            ),
            "region": PortDef(
                type="coord_rect", description="搜索区域", required=False,
            ),
            "confidence": PortDef(
                type="number", description="匹配置信度", required=False, default=0.7,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "enemy_pos": PortDef(type="coord", description="敌人位置"),
            "enemy_found": PortDef(type="bool", description="是否找到敌人"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        assert action is not None
        template_path = action.template_path
        confidence = getattr(action, "confidence", 0.7)
        screenshot = ctx.capture.grab()
        match_rect = ctx.matcher.find(
            screenshot,
            template_path,
            threshold=confidence,
        )

        if match_rect is not None:
            x, y, w, h = match_rect
            center_x = x + w // 2
            center_y = y + h // 2
            return NodeResult.ok(
                enemy_pos=(center_x, center_y),
                enemy_found=True,
            )
        return NodeResult.ok(enemy_found=False)


# ---------------------------------------------------------------------------
# D5: AttackDescriptor — 攻击
# ---------------------------------------------------------------------------


class AttackDescriptor(NodeDescriptor):
    """攻击节点描述符 — 点击目标位置并执行攻击连击。"""

    @classmethod
    def action_type(cls) -> str:
        return "attack"

    @classmethod
    def display_name(cls) -> str:
        return "攻击"

    @classmethod
    def category(cls) -> str:
        return "战斗辅助"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "target_pos": PortDef(
                type="coord", description="目标位置 (x, y)", required=False,
            ),
            "attack_count": PortDef(
                type="number", description="攻击次数", required=False, default=3,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        target_pos = getattr(action, "target_pos", None)
        attack_count = getattr(action, "attack_count", 3)

        if target_pos:
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-5, 5)
            ctx.input_ctrl.click(
                target_pos[0] + offset_x,
                target_pos[1] + offset_y,
            )

        for _ in range(attack_count):
            ctx.input_ctrl.press_key("j")
            time.sleep(random.uniform(0.3, 0.6))

        return NodeResult.ok()


# ---------------------------------------------------------------------------
# D6: UseSkillDescriptor — 技能链
# ---------------------------------------------------------------------------


class UseSkillDescriptor(NodeDescriptor):
    """使用技能节点描述符 — 释放技能按键并等待。"""

    @classmethod
    def action_type(cls) -> str:
        return "use_skill"

    @classmethod
    def display_name(cls) -> str:
        return "使用技能"

    @classmethod
    def category(cls) -> str:
        return "战斗辅助"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "skill_key": PortDef(
                type="key", description="技能按键", required=True,
            ),
            "wait_after": PortDef(
                type="number", description="释放后等待秒数", required=False, default=1.0,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        skill_key = action.skill_key
        wait_after = getattr(action, "wait_after", 1.0)

        ctx.input_ctrl.press_key(skill_key)
        time.sleep(wait_after + random.uniform(0, 0.3))

        return NodeResult.ok()


# ---------------------------------------------------------------------------
# D7: DodgeDescriptor — 闪避
# ---------------------------------------------------------------------------


class DodgeDescriptor(NodeDescriptor):
    """闪避节点描述符 — 向指定方向闪避。"""

    @classmethod
    def action_type(cls) -> str:
        return "dodge"

    @classmethod
    def display_name(cls) -> str:
        return "闪避"

    @classmethod
    def category(cls) -> str:
        return "战斗辅助"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "direction": PortDef(
                type="string",
                description="闪避方向: left | right | random",
                required=False,
                default="random",
            ),
            "dodge_key": PortDef(
                type="key", description="闪避按键", required=False, default="space",
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        direction = getattr(action, "direction", "random")
        dodge_key = getattr(action, "dodge_key", "space")

        if direction == "random":
            direction = random.choice(["left", "right"])

        move_key = "a" if direction == "left" else "d"
        ctx.input_ctrl.press_key(move_key)
        time.sleep(random.uniform(0.05, 0.1))
        ctx.input_ctrl.press_key(dodge_key)
        time.sleep(random.uniform(0.2, 0.4))

        return NodeResult.ok()


# ---------------------------------------------------------------------------
# D7: TargetSelectionDescriptor — 目标选择
# ---------------------------------------------------------------------------


class TargetSelectionDescriptor(NodeDescriptor):
    """目标选择节点描述符 — 从多个匹配结果中选择最优目标。"""

    @classmethod
    def action_type(cls) -> str:
        return "target_select"

    @classmethod
    def display_name(cls) -> str:
        return "选择目标"

    @classmethod
    def category(cls) -> str:
        return "战斗辅助"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "template_path": PortDef(
                type="image", description="敌人模板图片", required=True,
            ),
            "region": PortDef(
                type="coord_rect", description="搜索区域", required=False,
            ),
            "confidence": PortDef(
                type="number", description="匹配置信度", required=False, default=0.7,
            ),
            "strategy": PortDef(
                type="string",
                description="选择策略: nearest | farthest | random",
                required=False,
                default="nearest",
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "target_pos": PortDef(type="coord", description="选中目标位置"),
            "target_found": PortDef(type="bool", description="是否找到目标"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        template_path = action.template_path
        confidence = getattr(action, "confidence", 0.7)
        strategy = getattr(action, "strategy", "nearest")

        screenshot = ctx.capture.grab()
        matches = ctx.matcher.find_all(
            screenshot,
            template_path,
            threshold=confidence,
        )

        if not matches:
            return NodeResult.ok(target_found=False)

        if strategy == "nearest":
            chosen = min(matches, key=lambda m: m[0] ** 2 + m[1] ** 2)
        elif strategy == "farthest":
            chosen = max(matches, key=lambda m: m[0] ** 2 + m[1] ** 2)
        else:
            chosen = random.choice(matches)

        x, y, w, h = chosen
        center_x = x + w // 2
        center_y = y + h // 2
        return NodeResult.ok(
            target_pos=(center_x, center_y),
            target_found=True,
        )


# ---------------------------------------------------------------------------
# CombatPlugin 入口类
# ---------------------------------------------------------------------------


class CombatPlugin(PluginInterface):
    """战斗辅助插件。"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="combat",
            plugin_name="战斗辅助",
            version="1.0.0",
            description="自动战斗节点：找怪、攻击、技能、闪避",
            permissions=(
                "screen_capture",
                "template_matcher",
                "input_control",
                "events",
            ),
        )

    def on_load(self, context: PluginContext) -> None:
        logger.info(t("plugins.builtin.log.combat_loading"))

    def on_unload(self) -> None:
        logger.info(t("plugins.builtin.log.combat_unloading"))

    def register_nodes(self, registry: PluginNodeRegistry) -> None:
        """注册战斗节点描述符。"""
        registry.register(FindEnemyDescriptor)
        registry.register(AttackDescriptor)
        registry.register(UseSkillDescriptor)
        registry.register(DodgeDescriptor)
        registry.register(TargetSelectionDescriptor)
