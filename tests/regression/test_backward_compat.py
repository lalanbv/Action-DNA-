"""回归测试 — v1/v2 配置执行结果不变。

参考: 13_风险与验证策略.md §3 迁移风险（向后兼容）
验证:
- v1 ActionChain 通过 chain_to_flow 转换后执行结果与直接构造 FlowGraph 一致
- v2 FlowGraph 序列化/反序列化后执行结果不变
- 旧配置的所有步骤类型在新引擎中行为正确
"""

import json
import threading
from unittest.mock import MagicMock

import pytest

from src.core.action import ActionType, DetectMode, FoundAction
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.execution_context import ExecutionContext
from src.core.engine.graph_engine import GraphEngine, GraphEngineConfig
from src.core.engine.node_registry import NodeRegistry
from src.core.engine.node_result import NodeResult
from src.core.error.error_config import ErrorStrategy
from src.core.exporter import FlowExporter
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType, chain_to_flow
from src.core.importer import FlowImporter
from src.core.variables.pool import VariablePool

# 确保所有内置描述符注册
from src.core.engine.descriptors.flow_descriptors import (  # noqa: F401
    StartDescriptor,
    EndDescriptor,
    LoopDescriptor,
)
from src.core.engine.descriptors.wait_descriptor import (  # noqa: F401
    WaitDescriptor,
    WaitRandomDescriptor,
)
from src.core.engine.descriptors.click_pos_descriptor import (  # noqa: F401
    ClickPosDescriptor,
)
from src.core.engine.descriptors.press_key_descriptor import (  # noqa: F401
    PressKeyDescriptor,
)
from src.core.engine.descriptors.click_image_descriptor import (  # noqa: F401
    ClickImageDescriptor,
)
from src.core.engine.descriptors.extended_descriptors import (  # noqa: F401
    HoldKeyDescriptor,
    MouseScrollDescriptor,
    MouseDragDescriptor,
    KeyComboDescriptor,
    MultiKeySequenceDescriptor,
    IdleBehaviorDescriptor,
    StartTimerDescriptor,
)
from _helpers import ActionChain


# ============================================================
# helpers
# ============================================================


def _make_ctx(
    graph: FlowGraph,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
    variables: VariablePool | None = None,
) -> ExecutionContext:
    start = graph.find_by_type("START")
    assert start is not None
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
        event_bus=None,
    )


def _run_v1_chain(
    chain: ActionChain,
    capture: MagicMock,
    matcher: MagicMock,
    input_ctrl: MagicMock,
) -> FlowGraph:
    """v1 路径: ActionChain → chain_to_flow → GraphEngine.run()"""
    graph = chain_to_flow(chain.name, chain.steps, loop=chain.loop, loop_count=chain.loop_count)
    ctx = _make_ctx(graph, capture, matcher, input_ctrl)
    engine = GraphEngine()
    engine.run(graph, ctx)
    return graph


def _mock_io():
    capture = MagicMock()
    matcher = MagicMock()
    matcher.find.return_value = []
    input_ctrl = MagicMock()
    return capture, matcher, input_ctrl


# ============================================================
# 1. v1 基础步骤 — 每种 ActionType 执行无异常
# ============================================================


class TestV1BasicSteps:
    """v1 ActionChain 中每种步骤类型在新引擎中执行成功。"""

    def test_wait_step(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_wait",
            steps=[STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01)],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)

    def test_wait_random_step(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_wait_random",
            steps=[STEP_CLASSES[ActionType.WAIT_RANDOM](wait_min=0.01, wait_max=0.02)],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)

    def test_press_key_step(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_press_key",
            steps=[STEP_CLASSES[ActionType.PRESS_KEY](key="enter")],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        input_ctrl.press_key.assert_called_once_with("enter")

    def test_click_pos_step(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_click_pos",
            steps=[STEP_CLASSES[ActionType.CLICK_POS](pos_x=150, pos_y=250)],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        input_ctrl.click.assert_called_once_with(150, 250, button="left", clicks=1)

    def test_mouse_scroll_step(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_scroll",
            steps=[STEP_CLASSES[ActionType.MOUSE_SCROLL](scroll_clicks=3)],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        input_ctrl.scroll.assert_called_once_with(3)


# ============================================================
# 2. v1 组合链 — 多步骤顺序执行验证
# ============================================================


class TestV1ChainExecution:
    """v1 多步骤动作链在新引擎中保持正确的执行顺序。"""

    def test_wait_then_click_order(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_chain_1",
            steps=[
                STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200),
            ],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        input_ctrl.click.assert_called_once_with(100, 200, button="left", clicks=1)

    def test_click_then_key_order(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_chain_2",
            steps=[
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=50, pos_y=60),
                STEP_CLASSES[ActionType.PRESS_KEY](key="space"),
            ],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        input_ctrl.click.assert_called_once_with(50, 60, button="left", clicks=1)
        input_ctrl.press_key.assert_called_once_with("space")

    def test_three_step_chain(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_chain_3",
            steps=[
                STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
                STEP_CLASSES[ActionType.CLICK_POS](pos_x=10, pos_y=20),
                STEP_CLASSES[ActionType.PRESS_KEY](key="a"),
            ],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        input_ctrl.click.assert_called_once_with(10, 20, button="left", clicks=1)
        input_ctrl.press_key.assert_called_once_with("a")

    def test_empty_chain(self):
        """空步骤列表不应崩溃。"""
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(name="v1_empty", steps=[], loop=False)
        graph = _run_v1_chain(chain, capture, matcher, input_ctrl)
        action_nodes = [n for n in graph.nodes.values() if n.node_type == NodeType.ACTION]
        assert len(action_nodes) == 0


# ============================================================
# 3. v1 loop 配置 — 循环参数正确传递
# ============================================================


class TestV1LoopConfig:
    """v1 ActionChain 的 loop/loop_count 参数在 chain_to_flow 后正确保留。"""

    def test_loop_false(self):
        chain = ActionChain(
            name="no_loop",
            steps=[STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01)],
            loop=False,
        )
        graph = chain_to_flow(chain.name, chain.steps, loop=False)
        assert graph.loop is False
        end_edges = [e for e in graph.edges if e.from_node == "end" and e.to_node == "start"]
        assert len(end_edges) == 0

    def test_loop_true(self):
        chain = ActionChain(
            name="with_loop",
            steps=[STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01)],
            loop=True,
        )
        graph = chain_to_flow(chain.name, chain.steps, loop=True)
        assert graph.loop is True
        end_edges = [e for e in graph.edges if e.from_node == "end" and e.to_node == "start"]
        assert len(end_edges) == 1

    def test_loop_count_preserved(self):
        chain = ActionChain(
            name="counted",
            steps=[STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01)],
            loop=True,
            loop_count=5,
        )
        graph = chain_to_flow(chain.name, chain.steps, loop=True, loop_count=5)
        assert graph.loop_count == 5


# ============================================================
# 4. chain_to_flow 图结构 — 验证转换后的节点/边完整性
# ============================================================


class TestChainToFlowStructure:
    """chain_to_flow 生成的 FlowGraph 结构满足 GraphEngine 执行条件。"""

    def test_has_start_and_end(self):
        chain = ActionChain(
            name="struct",
            steps=[STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0)],
            loop=False,
        )
        graph = chain_to_flow(chain.name, chain.steps, loop=False)
        assert graph.find_by_type("START") is not None
        assert graph.find_by_type("END") is not None

    def test_start_node_id_set(self):
        chain = ActionChain(
            name="sid",
            steps=[STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0)],
            loop=False,
        )
        graph = chain_to_flow(chain.name, chain.steps, loop=False)
        assert graph.start_node_id == "start"

    def test_action_nodes_count(self):
        steps = [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=1, pos_y=2),
            STEP_CLASSES[ActionType.PRESS_KEY](key="a"),
        ]
        graph = chain_to_flow("test", steps, loop=False)
        action_nodes = [n for n in graph.nodes.values() if n.node_type == NodeType.ACTION]
        assert len(action_nodes) == 3

    def test_linear_chain_connected(self):
        steps = [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=1, pos_y=2),
        ]
        graph = chain_to_flow("test", steps, loop=False)
        start_edges = graph.get_outgoing_edges("start")
        assert len(start_edges) == 1
        first_target = start_edges[0].to_node
        assert graph.nodes[first_target].action.action_type == ActionType.WAIT

        end_node = graph.find_by_type("END")
        assert end_node is not None
        incoming_to_end = [e for e in graph.edges if e.to_node == "end"]
        assert len(incoming_to_end) == 1

    def test_all_nodes_reachable(self):
        steps = [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.1),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=1, pos_y=2),
        ]
        graph = chain_to_flow("test", steps, loop=False)
        reachable = graph.get_reachable_nodes("start")
        assert reachable == graph.get_all_node_ids()


# ============================================================
# 5. v1 → v2 执行等价性 — 同一配置走两条路结果一致
# ============================================================


class TestV1V2ExecutionEquivalence:
    """v1 ActionChain 和手动构造的等价 FlowGraph 产生相同的 I/O 调用。"""

    def test_click_pos_equivalence(self):
        capture, matcher, input_ctrl = _mock_io()

        # v1 路径
        chain = ActionChain(
            name="equiv",
            steps=[STEP_CLASSES[ActionType.CLICK_POS](pos_x=777, pos_y=888)],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        v1_calls = list(input_ctrl.click.call_args_list)

        # v2 路径 — 手动构造等价图
        input_ctrl.reset_mock()
        graph = FlowGraph(name="equiv", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.start_node_id = "start"
        graph.add_node(FlowNode(
            node_id="a1", node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.CLICK_POS](pos_x=777, pos_y=888),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))

        ctx = _make_ctx(graph, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(graph, ctx)
        v2_calls = list(input_ctrl.click.call_args_list)

        assert v1_calls == v2_calls

    def test_press_key_equivalence(self):
        capture, matcher, input_ctrl = _mock_io()

        chain = ActionChain(
            name="equiv_key",
            steps=[STEP_CLASSES[ActionType.PRESS_KEY](key="f1")],
            loop=False,
        )
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        v1_calls = list(input_ctrl.press_key.call_args_list)

        input_ctrl.reset_mock()
        graph = FlowGraph(name="equiv_key", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.start_node_id = "start"
        graph.add_node(FlowNode(
            node_id="a1", node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.PRESS_KEY](key="f1"),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))

        ctx = _make_ctx(graph, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(graph, ctx)
        v2_calls = list(input_ctrl.press_key.call_args_list)

        assert v1_calls == v2_calls

    def test_multi_step_equivalence(self):
        capture, matcher, input_ctrl = _mock_io()

        steps = [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=300, pos_y=400),
            STEP_CLASSES[ActionType.PRESS_KEY](key="space"),
        ]
        chain = ActionChain(name="equiv_multi", steps=steps, loop=False)
        _run_v1_chain(chain, capture, matcher, input_ctrl)
        v1_clicks = list(input_ctrl.click.call_args_list)
        v1_keys = list(input_ctrl.press_key.call_args_list)

        input_ctrl.reset_mock()
        graph = chain_to_flow("equiv_multi", steps, loop=False)
        ctx = _make_ctx(graph, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(graph, ctx)
        v2_clicks = list(input_ctrl.click.call_args_list)
        v2_keys = list(input_ctrl.press_key.call_args_list)

        assert v1_clicks == v2_clicks
        assert v1_keys == v2_keys


# ============================================================
# 6. 序列化往返 — 导出再导入后执行不变
# ============================================================


class TestSerializationRoundtrip:
    """FlowGraph → 导出 JSON → 重新导入 → 执行结果不变。"""

    def test_roundtrip_preserves_click_pos(self, tmp_path):
        capture, matcher, input_ctrl = _mock_io()

        graph = FlowGraph(name="roundtrip_click", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.start_node_id = "start"
        graph.add_node(FlowNode(
            node_id="a1", node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.CLICK_POS](pos_x=123, pos_y=456),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))

        exported = FlowExporter.export(graph, str(tmp_path))
        export_path = tmp_path / "exported.json"
        FlowExporter.save_file(exported, str(export_path))

        loaded = FlowImporter.import_from_file(str(export_path), str(tmp_path / "profile"))

        ctx = _make_ctx(loaded, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(loaded, ctx)

        input_ctrl.click.assert_called_once_with(123, 456, button="left", clicks=1)

    def test_roundtrip_preserves_press_key(self, tmp_path):
        capture, matcher, input_ctrl = _mock_io()

        graph = FlowGraph(name="roundtrip_key", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.start_node_id = "start"
        graph.add_node(FlowNode(
            node_id="a1", node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.PRESS_KEY](key="enter"),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))

        exported = FlowExporter.export(graph, str(tmp_path))
        export_path = tmp_path / "exported.json"
        FlowExporter.save_file(exported, str(export_path))

        loaded = FlowImporter.import_from_file(str(export_path), str(tmp_path / "profile"))

        ctx = _make_ctx(loaded, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(loaded, ctx)

        input_ctrl.press_key.assert_called_once_with("enter")

    def test_roundtrip_preserves_graph_structure(self, tmp_path):
        graph = FlowGraph(name="roundtrip_struct", loop=True, loop_count=3)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.start_node_id = "start"
        graph.add_node(FlowNode(
            node_id="a1", node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.WAIT](wait_seconds=0.5),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))

        exported = FlowExporter.export(graph, str(tmp_path))
        export_path = tmp_path / "exported.json"
        FlowExporter.save_file(exported, str(export_path))

        loaded = FlowImporter.import_from_file(str(export_path), str(tmp_path / "profile"))

        assert loaded.name == graph.name
        assert loaded.loop == graph.loop
        assert loaded.loop_count == graph.loop_count
        assert len(loaded.nodes) == len(graph.nodes)
        assert len(loaded.edges) == len(graph.edges)


# ============================================================
# 7. v1 特殊参数 — DetectMode / 坐标变量
# ============================================================


class TestV1SpecialParams:
    """v1 配置中的特殊参数在新引擎中正确传递。"""

    def test_click_image_skip_if_not_found(self):
        capture, matcher, input_ctrl = _mock_io()
        chain = ActionChain(
            name="v1_cimg_skip",
            steps=[STEP_CLASSES[ActionType.CLICK_IMAGE](
                image_path="test.png",
                detect_mode=DetectMode.SKIP_IF_NOT_FOUND,
            )],
            loop=False,
        )
        graph = chain_to_flow(chain.name, chain.steps, loop=False)
        ctx = _make_ctx(graph, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(graph, ctx)
        input_ctrl.click.assert_not_called()

    def test_click_pos_coord_var(self):
        capture, matcher, input_ctrl = _mock_io()
        pool = VariablePool()
        pool.set("my_target", [333, 444])

        chain = ActionChain(
            name="v1_coord_var",
            steps=[STEP_CLASSES[ActionType.CLICK_POS](
                use_coord_var=True,
                coord_var_name="my_target",
            )],
            loop=False,
        )
        graph = chain_to_flow(chain.name, chain.steps, loop=False)
        ctx = _make_ctx(graph, capture, matcher, input_ctrl, variables=pool)
        engine = GraphEngine()
        engine.run(graph, ctx)

        input_ctrl.click.assert_called_once_with(333, 444, button="left", clicks=1)


# ============================================================
# 8. ActionExecutor Facade — v1 兼容入口验证
# ============================================================


class TestFacadeV1Compat:
    """chain_to_flow + ActionExecutor.start(FlowGraph) 委托验证。"""

    def test_start_accepts_converted_chain(self):
        from src.core.action_executor import ActionExecutor

        capture, matcher, input_ctrl = MagicMock(), MagicMock(), MagicMock()
        ex = ActionExecutor(capture, matcher, input_ctrl)

        steps = [
            STEP_CLASSES[ActionType.WAIT](wait_seconds=0.01),
            STEP_CLASSES[ActionType.CLICK_POS](pos_x=99, pos_y=88),
        ]
        graph = chain_to_flow("facade_v1", steps, loop=False)

        import threading
        with pytest.MonkeyPatch.context() as m:
            original_thread = threading.Thread

            def mock_thread(*args, **kwargs):
                t = original_thread(*args, **kwargs)
                t.start = MagicMock()
                return t

            m.setattr(threading, "Thread", mock_thread)
            ex.start(graph)

        assert ex.is_running

    def test_start_accepts_flow_graph(self):
        from src.core.action_executor import ActionExecutor

        capture, matcher, input_ctrl = MagicMock(), MagicMock(), MagicMock()
        ex = ActionExecutor(capture, matcher, input_ctrl)

        graph = FlowGraph(name="facade_v2", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.start_node_id = "start"
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="end"))

        import threading
        with pytest.MonkeyPatch.context() as m:
            original_thread = threading.Thread

            def mock_thread(*args, **kwargs):
                t = original_thread(*args, **kwargs)
                t.start = MagicMock()
                return t

            m.setattr(threading, "Thread", mock_thread)
            ex.start(graph)

        assert ex.is_running


# ============================================================
# 9. v3 向后兼容 — v2 配置保存后执行结果不变
# ============================================================


class TestV3BackwardCompat:
    """v2 配置在 v3 引擎中执行结果不变（新增字段不影响旧配置行为）。"""

    def test_v2_graph_executes_same_after_v3_save(self, tmp_path):
        """v2 配置 → v3 save → load → 执行结果与原始 v2 一致。"""
        capture, matcher, input_ctrl = _mock_io()

        # 构造 v2 等价 FlowGraph
        graph = FlowGraph(name="v2_compat", start_node_id="start", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="a1", node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.CLICK_POS](pos_x=555, pos_y=666),
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))

        # 原始执行
        ctx = _make_ctx(graph, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(graph, ctx)
        v1_clicks = list(input_ctrl.click.call_args_list)

        # v3 save → load
        from src.panel.profile_manager import ProfileManager
        pm = ProfileManager()
        pm.root = str(tmp_path)
        pm.save("compat_test", graph)
        loaded = pm.load("compat_test")

        # 加载后执行
        input_ctrl.reset_mock()
        ctx2 = _make_ctx(loaded, capture, matcher, input_ctrl)
        engine2 = GraphEngine()
        engine2.run(loaded, ctx2)
        v2_clicks = list(input_ctrl.click.call_args_list)

        assert v1_clicks == v2_clicks

    def test_v2_config_new_fields_default_no_side_effects(self, tmp_path):
        """v2 加载后新字段为默认值，不影响执行行为。"""
        from src.panel.profile_manager import ProfileManager

        v2_data = {
            "version": 2,
            "name": "v2_node",
            "flow": {
                "name": "test",
                "start_node_id": "start",
                "loop": False,
                "loop_count": 0,
                "nodes": [
                    {"node_id": "start", "node_type": "START", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 0, "pos_y": 0},
                    {"node_id": "a1", "node_type": "ACTION", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 0, "pos_y": 0,
                     "action": {"action_type": "WAIT", "wait_seconds": 0.01, "detect_mode": "WAIT_UNTIL_FOUND", "found_action": "LEFT_CLICK"}},
                    {"node_id": "end", "node_type": "END", "comment": "", "enabled": True, "loop_count": 0, "pos_x": 0, "pos_y": 0},
                ],
                "edges": [
                    {"edge_id": "e1", "from_node": "start", "to_node": "a1", "label": "default", "priority": 0},
                    {"edge_id": "e2", "from_node": "a1", "to_node": "end", "label": "default", "priority": 0},
                ],
                "monitors": [],
            },
        }

        import json, os
        profile_dir = os.path.join(str(tmp_path), "v2_node")
        os.makedirs(profile_dir, exist_ok=True)
        with open(os.path.join(profile_dir, "profile.json"), "w") as f:
            json.dump(v2_data, f)

        pm = ProfileManager()
        pm.root = str(tmp_path)
        graph = pm.load("v2_node")

        for node in graph.nodes.values():
            assert node.error_config is None
            assert node.breakpoint is False
            assert node.fsm_transitions == []
            assert node.fsm_global_transitions == []

        # 执行无异常
        capture, matcher, input_ctrl = _mock_io()
        ctx = _make_ctx(graph, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(graph, ctx)

    def test_export_import_with_v3_fields(self, tmp_path):
        """含 v3 字段的 FlowGraph 导出再导入后执行不变。"""
        from src.core.engine.fsm_engine import Transition as T, GlobalTransition as GT
        from src.core.error.error_config import ErrorConfig, ErrorStrategy

        capture, matcher, input_ctrl = _mock_io()

        graph = FlowGraph(name="v3_export", start_node_id="start", loop=False)
        graph.add_node(FlowNode(node_id="start", node_type=NodeType.START))
        graph.add_node(FlowNode(
            node_id="a1",
            node_type=NodeType.ACTION,
            action=STEP_CLASSES[ActionType.PRESS_KEY](key="f2"),
            error_config=ErrorConfig.skip(),
            breakpoint=True,
            fsm_transitions=[T("X", "Y", "go")],
            fsm_global_transitions=[GT("panic", "SAFE")],
        ))
        graph.add_node(FlowNode(node_id="end", node_type=NodeType.END))
        graph.add_edge(FlowEdge(edge_id="e1", from_node="start", to_node="a1"))
        graph.add_edge(FlowEdge(edge_id="e2", from_node="a1", to_node="end"))

        exported = FlowExporter.export(graph, str(tmp_path))
        export_path = tmp_path / "v3_export.json"
        FlowExporter.save_file(exported, str(export_path))

        loaded = FlowImporter.import_from_file(str(export_path), str(tmp_path / "loaded"))

        # v3 字段保留
        a1 = loaded.nodes["a1"]
        assert a1.error_config is not None
        assert a1.error_config.strategy == ErrorStrategy.SKIP
        assert a1.breakpoint is True
        assert len(a1.fsm_transitions) == 1
        assert len(a1.fsm_global_transitions) == 1

        # 执行不变
        ctx = _make_ctx(loaded, capture, matcher, input_ctrl)
        engine = GraphEngine()
        engine.run(loaded, ctx)
        input_ctrl.press_key.assert_called_once_with("f2")
