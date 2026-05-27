"""E2E 测试 — 完整用户流程。

参考: 13_风险与验证策略.md §5.4
覆盖: 创建图 → 添加节点 → 连接 → 保存 → 加载 → 执行 → 验证结果。
模拟用户从创建动作链到保存配置、重新加载、执行并验证的完整流程。
"""

import os
import threading

import pytest

pytestmark = pytest.mark.e2e

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.execution_context import ExecutionContext
from src.core.engine.graph_engine import GraphEngine
from src.core.events.bus import TypedEventBus
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType, chain_to_flow
from src.core.layers.event_bridge_layer import EventBridgeLayer
from src.core.variables.pool import VariablePool
from src.panel.profile_manager import ProfileManager

# 确保内置描述符注册
import src.core.engine.descriptors as _builtin_descriptors  # noqa: F401
from _helpers import ActionChain


# ============================================================
# helpers
# ============================================================


def _make_context(
    graph: FlowGraph,
    *,
    capture,
    matcher,
    input_ctrl,
    variables: VariablePool | None = None,
    event_bus: TypedEventBus | None = None,
) -> ExecutionContext:
    start = graph.find_by_type("START")
    assert start is not None, "图缺少 START 节点"
    return ExecutionContext(
        graph=graph,
        current_node=start,
        variables=variables or VariablePool(),
        capture=capture,
        matcher=matcher,
        input_ctrl=input_ctrl,
        gen=0,
        stop_event=threading.Event(),
        pause_event=threading.Event(),
        event_bus=event_bus,
    )


# ============================================================
# E2E: 创建 → 保存 → 加载 → 执行 完整用户流程
# ============================================================


class TestFullWorkflow:
    """完整用户流程端到端测试。"""

    def test_create_save_load_execute_wait_click(
        self, mock_capture, mock_matcher, mock_input, tmp_path, monkeypatch,
    ):
        """
        模拟用户完整流程:
        1. 用户创建动作链 (WAIT + CLICK_POS)
        2. chain_to_flow 转换为 FlowGraph
        3. 保存配置
        4. 重新加载配置
        5. 执行并验证结果
        """
        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        # Step 1: 用户创建动作链
        chain = ActionChain(
            name="e2e_workflow",
            steps=[
                STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=500, pos_y=300),
            ],
            loop=False,
        )

        # Step 2: 转换为 FlowGraph
        graph = chain_to_flow(chain.name, chain.steps, chain.loop, chain.loop_count)
        assert graph is not None
        assert len(graph.nodes) >= 4  # START + 2 ACTION + END

        # Step 3: 保存配置
        pm.save("e2e_workflow", graph)

        profile_dir = os.path.join(str(tmp_path), "e2e_workflow")
        assert os.path.isfile(os.path.join(profile_dir, "profile.json"))

        # Step 4: 重新加载配置
        loaded = pm.load("e2e_workflow")
        assert loaded.name == "e2e_workflow"
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)

        # Step 5: 执行
        pool = VariablePool()
        ctx = _make_context(
            loaded,
            capture=mock_capture,
            matcher=mock_matcher,
            input_ctrl=mock_input,
            variables=pool,
        )

        engine = GraphEngine()
        engine.run(loaded, ctx)

        mock_input.click.assert_called_once_with(500, 300, button="left", clicks=1)

    def test_create_save_load_execute_with_events(
        self, mock_capture, mock_matcher, mock_input, tmp_path, monkeypatch,
    ):
        """
        完整流程 + 事件系统验证:
        创建 → 保存 → 加载 → 执行 → 验证事件发布
        """
        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        chain = ActionChain(
            name="e2e_events",
            steps=[
                STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
                STEP_CLASSES[ActionType.PRESS_KEY](key="space"),
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
            ],
        )
        graph = chain_to_flow(chain.name, chain.steps)
        pm.save("e2e_events", graph)

        loaded = pm.load("e2e_events")

        collected: list[dict] = []

        def publish_fn(topic: str, **kwargs):
            collected.append({"topic": topic, **kwargs})

        ctx = _make_context(
            loaded,
            capture=mock_capture,
            matcher=mock_matcher,
            input_ctrl=mock_input,
        )

        engine = GraphEngine()
        engine.add_layer(EventBridgeLayer(publish_fn))
        engine.run(loaded, ctx)

        step_events = [e for e in collected if e["topic"] == "executor.step_changed"]
        assert len(step_events) == 3

        indices = [e["step_index"] for e in step_events]
        assert indices == sorted(indices)

        mock_input.press_key.assert_called_once_with("space")
        mock_input.click.assert_called_once_with(100, 200, button="left", clicks=1)

    def test_overwrite_save_and_reload(
        self, mock_capture, mock_matcher, mock_input, tmp_path, monkeypatch,
    ):
        """
        用户修改配置 → 保存覆盖 → 重新加载 → 执行新配置。
        """
        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        chain1 = ActionChain(
            name="e2e_overwrite",
            steps=[
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=10, pos_y=20),
            ],
        )
        graph1 = chain_to_flow(chain1.name, chain1.steps)
        pm.save("e2e_overwrite", graph1)

        chain2 = ActionChain(
            name="e2e_overwrite",
            steps=[
                STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=999, pos_y=888),
            ],
        )
        graph2 = chain_to_flow(chain2.name, chain2.steps)
        pm.save("e2e_overwrite", graph2)

        loaded = pm.load("e2e_overwrite")
        ctx = _make_context(
            loaded,
            capture=mock_capture,
            matcher=mock_matcher,
            input_ctrl=mock_input,
        )

        engine = GraphEngine()
        engine.run(loaded, ctx)

        mock_input.click.assert_called_once_with(999, 888, button="left", clicks=1)

    def test_multiple_profiles_independent(
        self, mock_capture, mock_matcher, mock_input, tmp_path, monkeypatch,
    ):
        """多个配置文件独立保存/加载/执行。"""
        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        chain_a = ActionChain(
            name="profile_a",
            steps=[STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=100)],
        )
        chain_b = ActionChain(
            name="profile_b",
            steps=[STEP_CLASSES[ActionType.CLICK_POS](pos_x=200, pos_y=200)],
        )

        graph_a = chain_to_flow("profile_a", chain_a.steps)
        graph_b = chain_to_flow("profile_b", chain_b.steps)

        pm.save("profile_a", graph_a)
        pm.save("profile_b", graph_b)

        loaded_a = pm.load("profile_a")
        loaded_b = pm.load("profile_b")

        ctx_a = _make_context(
            loaded_a, capture=mock_capture, matcher=mock_matcher, input_ctrl=mock_input,
        )
        GraphEngine().run(loaded_a, ctx_a)
        mock_input.click.assert_called_once_with(100, 100, button="left", clicks=1)
        mock_input.reset_mock()

        ctx_b = _make_context(
            loaded_b, capture=mock_capture, matcher=mock_matcher, input_ctrl=mock_input,
        )
        GraphEngine().run(loaded_b, ctx_b)
        mock_input.click.assert_called_once_with(200, 200, button="left", clicks=1)

    def test_loop_graph_save_load_execute(
        self, mock_capture, mock_matcher, mock_input, tmp_path, monkeypatch,
    ):
        """带循环配置的图保存/加载后 loop 属性正确。"""
        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        graph = FlowGraph(name="e2e_loop", start_node_id="start", loop=True, loop_count=3)

        start = FlowNode(node_id="start", node_type=NodeType.START)
        wait = FlowNode(
            node_id="wait_1",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
        )
        end = FlowNode(node_id="end", node_type=NodeType.END)

        for node in [start, wait, end]:
            graph.add_node(node)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="wait_1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="wait_1", to_node="end"))

        pm.save("e2e_loop", graph)
        loaded = pm.load("e2e_loop")

        assert loaded.loop is True
        assert loaded.loop_count == 3

        ctx = _make_context(
            loaded, capture=mock_capture, matcher=mock_matcher, input_ctrl=mock_input,
        )
        GraphEngine().run(loaded, ctx)

        assert loaded.loop is True
        assert loaded.loop_count == 3

    def test_disabled_node_skipped_in_e2e(
        self, mock_capture, mock_matcher, mock_input, tmp_path, monkeypatch,
    ):
        """禁用节点在 E2E 流程中被跳过。"""
        monkeypatch.setattr(
            "src.panel.profile_manager.get_profiles_dir",
            lambda: str(tmp_path),
        )
        pm = ProfileManager()

        graph = FlowGraph(name="e2e_disabled", start_node_id="start")
        start = FlowNode(node_id="start", node_type=NodeType.START)
        wait = FlowNode(
            node_id="wait_1",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
        )
        disabled_click = FlowNode(
            node_id="click_disabled",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
            enabled=False,
        )
        end = FlowNode(node_id="end", node_type=NodeType.END)

        for node in [start, wait, disabled_click, end]:
            graph.add_node(node)
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="wait_1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="wait_1", to_node="click_disabled"))
        graph.add_edge(FlowEdge(edge_id="e3", from_node="click_disabled", to_node="end"))

        pm.save("e2e_disabled", graph)
        loaded = pm.load("e2e_disabled")

        ctx = _make_context(
            loaded, capture=mock_capture, matcher=mock_matcher, input_ctrl=mock_input,
        )
        GraphEngine().run(loaded, ctx)

        mock_input.click.assert_not_called()
