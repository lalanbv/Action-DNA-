"""示例插件：快速旅行 — 点击固定坐标传送

演示最简插件模式：
- 无模板匹配，仅点击固定坐标
- 多个描述符注册
- 使用变量池读写

用法：复制到 src/plugins/builtin/quick_travel/ (重命名 __init__.py)
"""

from __future__ import annotations

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_result import NodeResult
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata
from src.core.plugins.plugin_node_registry import PluginNodeRegistry


class TeleportToTownDescriptor(NodeDescriptor):
    """传送到主城 — 点击传送按钮坐标。"""

    @classmethod
    def action_type(cls) -> str:
        return "teleport_town"

    @classmethod
    def display_name(cls) -> str:
        return "传送到主城"

    @classmethod
    def category(cls) -> str:
        return "快速旅行"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {}

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "teleported": PortDef(type="bool", description="是否传送成功"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        pos = getattr(action, "target_pos", (500, 300))
        ctx.input_ctrl.click(pos[0], pos[1])
        return NodeResult.ok(teleported=True)


class TeleportToDungeonDescriptor(NodeDescriptor):
    """传送到副本入口。"""

    @classmethod
    def action_type(cls) -> str:
        return "teleport_dungeon"

    @classmethod
    def display_name(cls) -> str:
        return "传送到副本"

    @classmethod
    def category(cls) -> str:
        return "快速旅行"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "dungeon_id": PortDef(type="string", description="副本编号", required=False, default="1"),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "teleported": PortDef(type="bool", description="是否传送成功"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        pos = getattr(action, "target_pos", (500, 400))
        ctx.input_ctrl.click(pos[0], pos[1])
        return NodeResult.ok(teleported=True)


class QuickTravelPlugin(PluginInterface):
    """快速旅行插件 — 点击固定坐标进行传送。"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="quick_travel",
            plugin_name="快速旅行",
            version="1.0.0",
            description="提供传送点快捷操作",
            permissions=("input_control",),
        )

    def on_load(self, context: PluginContext) -> None:
        pass

    def on_unload(self) -> None:
        pass

    def register_nodes(self, registry: PluginNodeRegistry) -> None:
        registry.register(TeleportToTownDescriptor)
        registry.register(TeleportToDungeonDescriptor)


# ── plugin.json ─────────────────────────────────────────────
#
# {
#     "plugin_id": "quick_travel",
#     "plugin_name": "快速旅行",
#     "version": "1.0.0",
#     "description": "提供传送点快捷操作",
#     "entry_class": "QuickTravelPlugin",
#     "dependencies": [],
#     "permissions": ["input_control"],
#     "min_app_version": "2.0.0"
# }
