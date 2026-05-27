"""NavigationPlugin — 地图导航插件。

调用者:
  - PluginLoader.load() 通过 importlib.import_module("navigation") 导入
  - 获取 entry_class="NavigationPlugin" 实例化并加载

包含 5 个节点描述符:
  - MoveToDescriptor: 移动到指定坐标
  - PathNavigateDescriptor: 路径点序列导航（支持条件中断）
  - ZoneSwitchDescriptor: 区域切换（通过模板匹配传送入口）
  - TeleportDescriptor: 地图传送（点击传送点+确认）
  - PathFollowDescriptor: 路径跟随（逐点移动）
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

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# D8: MoveToDescriptor — 移动到
# ---------------------------------------------------------------------------


class MoveToDescriptor(NodeDescriptor):
    """移动到指定坐标节点描述符。"""

    @classmethod
    def action_type(cls) -> str:
        return "move_to"

    @classmethod
    def display_name(cls) -> str:
        return "移动到"

    @classmethod
    def category(cls) -> str:
        return "地图导航"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "target_pos": PortDef(
                type="coord", description="目标坐标", required=True,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "arrived": PortDef(type="bool", description="是否到达"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        target = action.target_pos
        ctx.input_ctrl.click(target[0], target[1], button="left", clicks=1)
        return NodeResult.ok(arrived=True)


# ---------------------------------------------------------------------------
# D8: PathNavigateDescriptor — 路径导航
# ---------------------------------------------------------------------------


class PathNavigateDescriptor(NodeDescriptor):
    """路径导航节点描述符 — 沿路径点序列逐步移动，支持条件中断。"""

    @classmethod
    def action_type(cls) -> str:
        return "path_navigate"

    @classmethod
    def display_name(cls) -> str:
        return "路径导航"

    @classmethod
    def category(cls) -> str:
        return "地图导航"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "waypoints": PortDef(
                type="list",
                description="路径点列表 [(x1,y1), (x2,y2), ...]",
                required=True,
            ),
            "step_delay": PortDef(
                type="number", description="每步间隔(秒)",
                required=False, default=1.0,
            ),
            "interrupt_template": PortDef(
                type="image", description="中断条件模板（到达目的地则停止）",
                required=False,
            ),
            "interrupt_confidence": PortDef(
                type="number", description="中断检测置信度",
                required=False, default=0.8,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "completed": PortDef(type="bool", description="是否走完全程"),
            "interrupted": PortDef(type="bool", description="是否被中断条件截停"),
            "reached_index": PortDef(type="number", description="到达的路径点索引"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        waypoints = action.waypoints
        step_delay = getattr(action, "step_delay", 1.0)
        interrupt_tpl = getattr(action, "interrupt_template", None)
        interrupt_conf = getattr(action, "interrupt_confidence", 0.8)

        if not waypoints:
            return NodeResult.ok(
                completed=True, interrupted=False, reached_index=-1,
            )

        for i, wp in enumerate(waypoints):
            ctx.input_ctrl.click(wp[0], wp[1], button="left", clicks=1)
            time.sleep(max(0, step_delay + random.uniform(-0.2, 0.3)))

            if interrupt_tpl:
                screenshot = ctx.capture.grab()
                match_rect = ctx.matcher.find(
                    screenshot, interrupt_tpl, threshold=interrupt_conf,
                )
                if match_rect is not None:
                    return NodeResult.ok(
                        completed=False,
                        interrupted=True,
                        reached_index=i,
                    )

        return NodeResult.ok(
            completed=True, interrupted=False,
            reached_index=len(waypoints) - 1,
        )


# ---------------------------------------------------------------------------
# D9: ZoneSwitchDescriptor — 区域切换
# ---------------------------------------------------------------------------


class ZoneSwitchDescriptor(NodeDescriptor):
    """区域切换节点描述符 — 通过模板匹配找到传送入口并点击切换区域。"""

    @classmethod
    def action_type(cls) -> str:
        return "zone_switch"

    @classmethod
    def display_name(cls) -> str:
        return "区域切换"

    @classmethod
    def category(cls) -> str:
        return "地图导航"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "zone_template": PortDef(
                type="image", description="传送入口模板图片", required=True,
            ),
            "confirm_template": PortDef(
                type="image", description="确认按钮模板", required=False,
            ),
            "confidence": PortDef(
                type="number", description="匹配置信度",
                required=False, default=0.8,
            ),
            "wait_after_switch": PortDef(
                type="number", description="切换后等待秒数",
                required=False, default=3.0,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "switched": PortDef(type="bool", description="是否成功切换"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        confidence = getattr(action, "confidence", 0.8)
        wait_after = getattr(action, "wait_after_switch", 3.0)

        screenshot = ctx.capture.grab()
        match_rect = ctx.matcher.find(
            screenshot, action.zone_template, threshold=confidence,
        )
        if match_rect is None:
            return NodeResult.ok(switched=False)

        x, y, w, h = match_rect
        lx, ly = ctx.capture.to_logical(x + w // 2, y + h // 2)
        ctx.input_ctrl.click(lx, ly, button="left", clicks=1)
        time.sleep(random.uniform(0.5, 1.0))

        confirm_tpl = getattr(action, "confirm_template", None)
        if confirm_tpl:
            screenshot = ctx.capture.grab()
            confirm_rect = ctx.matcher.find(
                screenshot, confirm_tpl, threshold=confidence,
            )
            if confirm_rect is not None:
                cx, cy, cw, ch = confirm_rect
                clx, cly = ctx.capture.to_logical(cx + cw // 2, cy + ch // 2)
                ctx.input_ctrl.click(clx, cly, button="left", clicks=1)

        time.sleep(max(0, wait_after + random.uniform(-0.3, 0.5)))
        return NodeResult.ok(switched=True)


# ---------------------------------------------------------------------------
# TeleportDescriptor — 传送
# ---------------------------------------------------------------------------


class TeleportDescriptor(NodeDescriptor):
    """传送节点描述符 — 点击地图传送点并确认。"""

    @classmethod
    def action_type(cls) -> str:
        return "teleport"

    @classmethod
    def display_name(cls) -> str:
        return "传送"

    @classmethod
    def category(cls) -> str:
        return "地图导航"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "map_template": PortDef(
                type="image", description="地图传送点模板", required=True,
            ),
            "confirm_button": PortDef(
                type="image", description="确认按钮模板", required=False,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "teleported": PortDef(type="bool", description="传送是否成功"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action

        screenshot = ctx.capture.grab()
        match_rect = ctx.matcher.find(
            screenshot, action.map_template, threshold=0.8,
        )
        if match_rect is None:
            return NodeResult.fail(f"未找到传送点: {action.map_template}")

        x, y, w, h = match_rect
        lx, ly = ctx.capture.to_logical(x + w // 2, y + h // 2)
        ctx.input_ctrl.click(lx, ly, button="left", clicks=1)
        time.sleep(random.uniform(0.5, 1.0))

        confirm = getattr(action, "confirm_button", None)
        if confirm:
            screenshot = ctx.capture.grab()
            confirm_rect = ctx.matcher.find(
                screenshot, confirm, threshold=0.8,
            )
            if confirm_rect is not None:
                cx, cy, cw, ch = confirm_rect
                clx, cly = ctx.capture.to_logical(cx + cw // 2, cy + ch // 2)
                ctx.input_ctrl.click(clx, cly, button="left", clicks=1)
            else:
                return NodeResult.ok(teleported=False)

        return NodeResult.ok(teleported=True)


# ---------------------------------------------------------------------------
# PathFollowDescriptor — 路径跟随
# ---------------------------------------------------------------------------


class PathFollowDescriptor(NodeDescriptor):
    """路径跟随节点描述符 — 逐点移动到路径上的每个坐标。"""

    @classmethod
    def action_type(cls) -> str:
        return "path_follow"

    @classmethod
    def display_name(cls) -> str:
        return "路径跟随"

    @classmethod
    def category(cls) -> str:
        return "地图导航"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "waypoints": PortDef(
                type="list",
                description="路径点列表 [(x1,y1), (x2,y2), ...]",
                required=True,
            ),
            "step_delay": PortDef(
                type="number", description="每步间隔(秒)",
                required=False, default=1.0,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "completed": PortDef(type="bool", description="是否走完全程"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action: Any = ctx.current_node.action
        waypoints = action.waypoints
        step_delay = getattr(action, "step_delay", 1.0)

        for wp in waypoints:
            ctx.input_ctrl.click(wp[0], wp[1], button="left", clicks=1)
            time.sleep(max(0, step_delay + random.uniform(-0.2, 0.3)))

        return NodeResult.ok(completed=True)


# ---------------------------------------------------------------------------
# NavigationPlugin 入口类
# ---------------------------------------------------------------------------


class NavigationPlugin(PluginInterface):
    """地图导航插件。"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="navigation",
            plugin_name="地图导航",
            version="1.0.0",
            description="地图导航节点：移动、传送、路径跟随、区域切换",
            dependencies=("combat",),
            permissions=(
                "screen_capture",
                "template_matcher",
                "input_control",
                "events",
            ),
        )

    def on_load(self, context: PluginContext) -> None:
        logger.info("NavigationPlugin 加载中...")

    def on_unload(self) -> None:
        logger.info("NavigationPlugin 卸载中...")

    def register_nodes(self, registry: PluginNodeRegistry) -> None:
        """注册导航节点描述符。"""
        registry.register(MoveToDescriptor)
        registry.register(PathNavigateDescriptor)
        registry.register(ZoneSwitchDescriptor)
        registry.register(TeleportDescriptor)
        registry.register(PathFollowDescriptor)
