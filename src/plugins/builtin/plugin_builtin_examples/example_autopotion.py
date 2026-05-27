"""示例插件：自动喝药

演示一个完整的插件实现，包含：
- 单个节点描述符（模板匹配 + 点击）
- PluginInterface 实现
- 单元测试模式

用法：将本文件和 plugin.json 复制到 src/plugins/builtin/autopotion/ 即可加载。
目录结构：
    src/plugins/builtin/autopotion/
    ├── plugin.json
    └── __init__.py          (本文件重命名为 __init__.py)
"""

from __future__ import annotations

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.node_descriptor import NodeDescriptor, PortDef
from src.core.engine.node_result import NodeResult
from src.core.plugins.plugin_context import PluginContext
from src.core.plugins.plugin_interface import PluginInterface, PluginMetadata
from src.core.plugins.plugin_node_registry import PluginNodeRegistry


# ── 节点描述符 ──────────────────────────────────────────────


class AutoPotionDescriptor(NodeDescriptor):
    """检测血瓶图标并点击使用。

    输出变量:
        potion_used: bool — 本次是否使用了药水
        hp_percent: float — 检测到的血量百分比（-1 表示未检测到）
    """

    @classmethod
    def action_type(cls) -> str:
        return "auto_potion"

    @classmethod
    def display_name(cls) -> str:
        return "自动喝药"

    @classmethod
    def category(cls) -> str:
        return "示例"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "template": PortDef(type="string", description="药水瓶模板图", required=True),
            "threshold": PortDef(
                type="number", description="匹配阈值",
                required=False, default=0.8,
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {
            "potion_used": PortDef(type="bool", description="是否使用了药水"),
            "hp_percent": PortDef(type="number", description="血量百分比"),
        }

    def execute(self, ctx: ExecutionContext) -> NodeResult:
        action = ctx.current_node.action
        template = getattr(action, "template", "potion.png")
        threshold = getattr(action, "threshold", 0.8)

        if ctx.capture is None or ctx.matcher is None:
            return NodeResult.fail("截图或匹配服务不可用")

        screenshot = ctx.capture.grab()
        rect = ctx.matcher.find(screenshot, template, threshold=threshold)

        if rect is None:
            return NodeResult.ok(potion_used=False, hp_percent=-1.0)

        x, y, w, h = rect
        lx, ly = ctx.capture.to_logical(x + w // 2, y + h // 2)
        ctx.input_ctrl.click(lx, ly)

        return NodeResult.ok(potion_used=True, hp_percent=-1.0)


# ── 插件入口类 ──────────────────────────────────────────────


class AutoPotionPlugin(PluginInterface):
    """自动喝药插件 — 检测低血量并自动使用药水。"""

    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            plugin_id="autopotion",
            plugin_name="自动喝药",
            version="1.0.0",
            description="检测血瓶图标并自动使用药水",
            author="示例",
            permissions=("screen_capture", "template_matcher", "input_control"),
        )

    def on_load(self, context: PluginContext) -> None:
        pass  # 无额外初始化

    def on_unload(self) -> None:
        pass  # 无资源释放

    def register_nodes(self, registry: PluginNodeRegistry) -> None:
        registry.register(AutoPotionDescriptor)


# ── 对应的 plugin.json 内容（另存为 plugin.json）────────────
#
# {
#     "plugin_id": "autopotion",
#     "plugin_name": "自动喝药",
#     "version": "1.0.0",
#     "description": "检测血瓶图标并自动使用药水",
#     "author": "示例",
#     "entry_class": "AutoPotionPlugin",
#     "dependencies": [],
#     "permissions": ["screen_capture", "template_matcher", "input_control"],
#     "min_app_version": "2.0.0"
# }


# ── 单元测试模式（参考）─────────────────────────────────────
#
# import pytest
# from unittest.mock import MagicMock
# import numpy as np
# from src.core.engine.node_registry import NodeRegistry
# from src.core.events.bus import TypedEventBus
# from src.core.plugins.plugin_loader import PluginLoader
# from src.core.flow import FlowGraph, FlowNode, FlowEdge, NodeType
# from src.core.engine.execution_context import ExecutionContext
# from src.core.variables.pool import VariablePool
# import threading
#
#
# def _mock_io():
#     cap = MagicMock()
#     cap.grab.return_value = np.zeros((1080, 1920, 3), dtype=np.uint8)
#     cap.to_logical.side_effect = lambda x, y: (x, y)
#     matcher = MagicMock()
#     input_ctrl = MagicMock()
#     return cap, matcher, input_ctrl
#
#
# def test_auto_potion_found():
#     cap, matcher, input_ctrl = _mock_io()
#     matcher.find.return_value = (100, 200, 40, 40)
#
#     action = MagicMock()
#     action.template = "potion.png"
#     action.threshold = 0.8
#
#     desc = AutoPotionDescriptor()
#     graph = FlowGraph(name="test", start_node_id="s")
#     graph.add_node(FlowNode(node_id="s", node_type=NodeType.START))
#     node = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
#     graph.add_node(node)
#
#     ctx = ExecutionContext(
#         graph=graph, current_node=node, variables=VariablePool(),
#         capture=cap, matcher=matcher, input_ctrl=input_ctrl,
#         gen=0, stop_event=threading.Event(),
#         pause_event=threading.Event(), event_bus=None,
#     )
#
#     result = desc.execute(ctx)
#     assert result.success
#     assert result.output_vars["potion_used"] is True
#     input_ctrl.click.assert_called_once_with(120, 220)
#
#
# def test_auto_potion_not_found():
#     cap, matcher, input_ctrl = _mock_io()
#     matcher.find.return_value = None
#
#     action = MagicMock()
#     action.template = "potion.png"
#
#     desc = AutoPotionDescriptor()
#     graph = FlowGraph(name="test", start_node_id="s")
#     graph.add_node(FlowNode(node_id="s", node_type=NodeType.START))
#     node = FlowNode(node_id="n1", node_type=NodeType.ACTION, action=action)
#     graph.add_node(node)
#
#     ctx = ExecutionContext(
#         graph=graph, current_node=node, variables=VariablePool(),
#         capture=cap, matcher=matcher, input_ctrl=input_ctrl,
#         gen=0, stop_event=threading.Event(),
#         pause_event=threading.Event(), event_bus=None,
#     )
#
#     result = desc.execute(ctx)
#     assert result.success
#     assert result.output_vars["potion_used"] is False
#     input_ctrl.click.assert_not_called()
