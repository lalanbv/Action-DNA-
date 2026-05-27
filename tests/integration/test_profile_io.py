"""集成测试 — Profile 保存/加载往返。

参考: 13_风险与验证策略.md §5.3
验证: ProfileManager.save → ProfileManager.load 序列化往返正确性。
覆盖: v1 迁移、v2 迁移、v3 往返、节点/边/监控器完整性。
"""

import json
import os

import pytest

pytestmark = pytest.mark.integration

from src.core.action import ActionType, DetectMode, FoundAction
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.condition import Condition, ConditionType
from src.core.error.error_config import ErrorConfig, ErrorStrategy, RetryPolicy
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType, chain_to_flow
from src.core.monitor import MonitorConfig
from src.panel.profile_manager import ProfileManager
from _helpers import ActionChain


# ============================================================
# helpers
# ============================================================


def _make_simple_graph(
    name: str = "test_graph",
    *,
    loop: bool = False,
    loop_count: int = 0,
) -> FlowGraph:
    """创建简单线性图: START → WAIT → CLICK_POS → END"""
    chain = ActionChain(
        name=name,
        steps=[
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
        ],
        loop=loop,
        loop_count=loop_count,
    )
    return chain_to_flow(chain.name, chain.steps, chain.loop, chain.loop_count)


def _make_complex_graph() -> FlowGraph:
    """创建包含多种节点类型的复杂图"""
    graph = FlowGraph(name="complex_test", start_node_id="start")

    start = FlowNode(node_id="start", node_type=NodeType.START)
    wait = FlowNode(
        node_id="wait_1",
        node_type=NodeType.ACTION,
        action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.05),
    )
    click = FlowNode(
        node_id="click_1",
        node_type=NodeType.ACTION,
        action=STEP_CLASSES[ActionType.CLICK_POS](
            pos_x=300,
            pos_y=400,
        ),
    )
    end = FlowNode(node_id="end", node_type=NodeType.END)

    for node in [start, wait, click, end]:
        graph.add_node(node)

    graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="wait_1"))
    graph.add_edge(FlowEdge(edge_id="e2", from_node="wait_1", to_node="click_1"))
    graph.add_edge(FlowEdge(edge_id="e3", from_node="click_1", to_node="end"))

    return graph


# ============================================================
# fixtures
# ============================================================


@pytest.fixture
def pm(tmp_path, monkeypatch):
    """创建使用临时目录的 ProfileManager"""
    monkeypatch.setattr(
        "src.panel.profile_manager.get_profiles_dir",
        lambda: str(tmp_path),
    )
    return ProfileManager()


# ============================================================
# D8: Profile 保存/加载往返测试
# ============================================================


class TestProfileRoundtrip:
    """保存 → 加载 → 验证图等价性"""

    def test_simple_graph_roundtrip(self, pm):
        """简单线性图保存/加载后等价"""
        original = _make_simple_graph("roundtrip_simple")

        pm.save("roundtrip_simple", original)
        loaded = pm.load("roundtrip_simple")

        assert loaded.name == original.name
        assert len(loaded.nodes) == len(original.nodes)
        assert len(loaded.edges) == len(original.edges)
        assert loaded.loop == original.loop
        assert loaded.loop_count == original.loop_count

    def test_complex_graph_roundtrip(self, pm):
        """复杂图保存/加载后节点和边完整"""
        original = _make_complex_graph()

        pm.save("complex_roundtrip", original)
        loaded = pm.load("complex_roundtrip")

        assert loaded.name == original.name
        assert len(loaded.nodes) == len(original.nodes)
        assert len(loaded.edges) == len(original.edges)

        # 验证节点类型正确
        node_types = {n.node_type for n in loaded.nodes.values()}
        assert NodeType.START in node_types
        assert NodeType.END in node_types
        assert NodeType.ACTION in node_types

    def test_loop_config_preserved(self, pm):
        """循环配置在往返后保持不变"""
        graph = _make_simple_graph("loop_test", loop=True, loop_count=5)
        pm.save("loop_test", graph)
        loaded = pm.load("loop_test")

        assert loaded.loop is True
        assert loaded.loop_count == 5

    def test_disabled_node_roundtrip(self, pm):
        """禁用节点状态在往返后保持"""
        graph = FlowGraph(name="disabled_test", start_node_id="start")
        start = FlowNode(node_id="start", node_type=NodeType.START)
        wait = FlowNode(
            node_id="wait_disabled",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0),
            enabled=False,
        )
        end = FlowNode(node_id="end", node_type=NodeType.END)

        for node in [start, wait, end]:
            graph.add_node(node)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="wait_disabled"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="wait_disabled", to_node="end"))

        pm.save("disabled_test", graph)
        loaded = pm.load("disabled_test")

        disabled_node = loaded.get_node("wait_disabled")
        assert disabled_node is not None
        assert disabled_node.enabled is False

    def test_node_comments_preserved(self, pm):
        """节点注释在往返后保持"""
        graph = FlowGraph(name="comment_test", start_node_id="start")
        start = FlowNode(node_id="start", node_type=NodeType.START, comment="开始节点")
        end = FlowNode(node_id="end", node_type=NodeType.END, comment="结束")

        graph.add_node(start)
        graph.add_node(end)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))

        pm.save("comment_test", graph)
        loaded = pm.load("comment_test")

        assert loaded.get_node("start").comment == "开始节点"
        assert loaded.get_node("end").comment == "结束"


class TestProfileV1Migration:
    """v1 格式配置迁移测试"""

    def test_v1_loads_as_flowgraph(self, pm):
        """v1 ActionChain 格式可加载为 FlowGraph"""
        profile_dir = os.path.join(pm.root, "v1_profile")
        os.makedirs(profile_dir, exist_ok=True)

        v1_data = {
            "version": 1,
            "chain": {
                "name": "v1_chain",
                "steps": [
                    {"action_type": "WAIT", "wait_seconds": 1.0},
                    {"action_type": "CLICK_POS", "pos_x": 100, "pos_y": 200},
                ],
                "loop": True,
                "loop_count": 3,
            },
        }

        with open(os.path.join(profile_dir, "profile.json"), "w", encoding="utf-8") as f:
            json.dump(v1_data, f)

        graph = pm.load("v1_profile")

        assert isinstance(graph, FlowGraph)
        assert graph.loop is True
        assert graph.loop_count == 3
        # v1 → FlowGraph 会生成 START + ACTION nodes + END
        assert len(graph.nodes) >= 4  # START, WAIT, CLICK_POS, END at minimum
        node_types = {n.node_type for n in graph.nodes.values()}
        assert NodeType.START in node_types
        assert NodeType.END in node_types


class TestProfileV2Migration:
    """v2/v3 格式兼容性测试"""

    def test_v2_missing_new_fields_gets_defaults(self, pm):
        """v2 配置缺少 v3 新字段时自动使用默认值"""
        profile_dir = os.path.join(pm.root, "v2_profile")
        os.makedirs(profile_dir, exist_ok=True)

        v2_data = {
            "version": 2,
            "flow": {
                "name": "v2_graph",
                "start_node_id": "start",
                "nodes": [
                    {"node_id": "start", "node_type": "START"},
                    {
                        "node_id": "wait_1",
                        "node_type": "ACTION",
                        "action": {"action_type": "WAIT", "wait_seconds": 0.5},
                    },
                    {"node_id": "end", "node_type": "END"},
                ],
                "edges": [
                    {"edge_id": "e1", "from_node": "start", "to_node": "wait_1"},
                    {"edge_id": "e2", "from_node": "wait_1", "to_node": "end"},
                ],
            },
        }

        with open(os.path.join(profile_dir, "profile.json"), "w", encoding="utf-8") as f:
            json.dump(v2_data, f)

        graph = pm.load("v2_profile")

        assert graph.name == "v2_graph"
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2

        # v3 新字段缺失时应使用默认值
        for node in graph.nodes.values():
            assert node.error_config is None  # 未设置则为 None
            assert node.breakpoint is False
            assert node.fsm_transitions == []


class TestProfileEdgeCases:
    """边界情况测试"""

    def test_save_creates_profile_directory(self, pm):
        """保存时自动创建 profile 目录"""
        graph = _make_simple_graph("auto_create")
        profile_dir = pm.save("auto_create", graph)

        assert os.path.isdir(profile_dir)
        assert os.path.isfile(os.path.join(profile_dir, "profile.json"))

    def test_save_creates_images_directory(self, pm):
        """保存时自动创建 images 子目录"""
        graph = _make_simple_graph("images_dir_test")
        profile_dir = pm.save("images_dir_test", graph)

        assert os.path.isdir(os.path.join(profile_dir, "images"))

    def test_list_profiles(self, pm):
        """列出所有已保存的配置"""
        graph1 = _make_simple_graph("profile_a")
        graph2 = _make_simple_graph("profile_b")

        pm.save("profile_a", graph1)
        pm.save("profile_b", graph2)

        profiles = pm.list_profiles()
        assert "profile_a" in profiles
        assert "profile_b" in profiles

    def test_overwrite_existing_profile(self, pm):
        """重复保存同名配置会覆盖"""
        graph1 = _make_simple_graph("first")
        graph2 = _make_complex_graph()

        pm.save("overwrite_test", graph1)
        pm.save("overwrite_test", graph2)

        loaded = pm.load("overwrite_test")
        assert loaded.name == "complex_test"

    def test_load_nonexistent_raises(self, pm):
        """加载不存在的配置抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            pm.load("nonexistent_profile")

    def test_invalid_name_raises(self, pm):
        """非法配置名称抛出 ValueError"""
        with pytest.raises(ValueError):
            pm.save("../traversal", _make_simple_graph())

    def test_empty_name_raises(self, pm):
        """空配置名称抛出 ValueError"""
        with pytest.raises(ValueError):
            pm.save("", _make_simple_graph())

    def test_save_and_load_preserves_edge_labels(self, pm):
        """边的 label 在往返后保持"""
        graph = FlowGraph(name="edge_label_test", start_node_id="start")
        start = FlowNode(node_id="start", node_type=NodeType.START)
        end = FlowNode(node_id="end", node_type=NodeType.END)

        graph.add_node(start)
        graph.add_node(end)
        graph.add_edge(FlowEdge(
            edge_id="e1", from_node="start", to_node="end", label="custom_label",
        ))

        pm.save("edge_label_test", graph)
        loaded = pm.load("edge_label_test")

        edge = loaded.edges[0]
        assert edge.label == "custom_label"

    def test_save_and_load_preserves_edge_priority(self, pm):
        """边的 priority 在往返后保持"""
        graph = FlowGraph(name="priority_test", start_node_id="start")
        start = FlowNode(node_id="start", node_type=NodeType.START)
        end = FlowNode(node_id="end", node_type=NodeType.END)

        graph.add_node(start)
        graph.add_node(end)
        graph.add_edge(FlowEdge(
            edge_id="e1", from_node="start", to_node="end", priority=5,
        ))

        pm.save("priority_test", graph)
        loaded = pm.load("priority_test")

        edge = loaded.edges[0]
        assert edge.priority == 5

    def test_monitor_roundtrip(self, pm, tmp_path):
        """监控器配置在保存/加载后保持"""
        graph = FlowGraph(name="monitor_test", start_node_id="start")
        start = FlowNode(node_id="start", node_type=NodeType.START)
        end = FlowNode(node_id="end", node_type=NodeType.END)

        graph.add_node(start)
        graph.add_node(end)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))

        monitor = MonitorConfig(
            name="test_monitor",
            enabled=True,
            image_path="",
            threshold=0.9,
            check_interval=2.0,
        )
        graph.monitors.append(monitor)

        pm.save("monitor_test", graph)
        loaded = pm.load("monitor_test")

        assert len(loaded.monitors) == 1
        assert loaded.monitors[0].name == "test_monitor"
        assert loaded.monitors[0].threshold == 0.9
        assert loaded.monitors[0].check_interval == 2.0
