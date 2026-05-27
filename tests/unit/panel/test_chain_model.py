"""ChainModel 单元测试 — 可观察的流程图数据模型。

验证线性步骤操作、图操作、监控器、执行状态、区域管理。
EventBus 通过 mock 隔离。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.core.monitor import MonitorConfig
from src.core.action import FoundAction
from src.core.step_types import BaseStep, STEP_CLASSES
from src.panel.models.chain_model import ChainModel


@pytest.fixture
def bus() -> MagicMock:
    return MagicMock()


@pytest.fixture
def model(bus: MagicMock) -> ChainModel:
    return ChainModel(event_bus=bus)


def _step(action_type: ActionType = ActionType.WAIT, **kw) -> ActionStep:
    return STEP_CLASSES[action_type](**kw)


# ---- 初始化 ----


class TestInit:
    def test_default_graph(self, model: ChainModel) -> None:
        assert model.graph.start_node_id == "start"
        assert "start" in model.graph.nodes
        assert "end" in model.graph.nodes

    def test_default_state(self, model: ChainModel) -> None:
        assert model.current_profile_name is None
        assert model.region_mode == "fullscreen"
        assert model.executor_state == "idle"

    def test_initial_edges(self, model: ChainModel) -> None:
        labels = {(e.from_node, e.to_node, e.label) for e in model.graph.edges}
        assert ("start", "end", "default") in labels
        assert ("end", "start", "loop") in labels

    def test_chain_name_default(self, model: ChainModel) -> None:
        assert model.chain_name == model.graph.name


# ---- 线性步骤操作 ----


class TestAddStep:
    def test_add_wait(self, model: ChainModel, bus: MagicMock) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))

        steps = model.get_steps()
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.WAIT
        bus.emit.assert_called_with("chain.steps_changed")

    def test_add_click_image(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.CLICK_IMAGE, image_path="/tmp/img.png"))

        steps = model.get_steps()
        assert len(steps) == 1
        assert steps[0].image_path == "/tmp/img.png"

    def test_add_multiple(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        model.add_step(_step(ActionType.PRESS_KEY, key="enter"))

        assert len(model.get_steps()) == 2

    def test_edges_after_add(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))

        labels = {(e.from_node, e.to_node) for e in model.graph.edges
                   if e.label == "default"}
        action_nodes = model.graph.action_nodes()
        action_id = action_nodes[0].node_id
        assert ("start", action_id) in labels
        assert (action_id, "end") in labels


class TestRemoveStep:
    def test_remove_by_index(self, model: ChainModel, bus: MagicMock) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        model.add_step(_step(ActionType.PRESS_KEY, key="a"))

        model.remove_step(0)

        assert len(model.get_steps()) == 1
        assert model.get_steps()[0].action_type == ActionType.PRESS_KEY
        bus.emit.assert_called_with("chain.steps_changed")

    def test_remove_out_of_range_noop(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        model._bus.reset_mock()

        model.remove_step(99)

        assert len(model.get_steps()) == 1
        model._bus.emit.assert_not_called()


class TestUpdateStep:
    def test_update_action(self, model: ChainModel, bus: MagicMock) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))

        new_step = _step(ActionType.PRESS_KEY, key="space")
        model.update_step(0, new_step)

        assert model.get_steps()[0].action_type == ActionType.PRESS_KEY
        bus.emit.assert_called_with("chain.steps_changed")

    def test_update_out_of_range_noop(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        model._bus.reset_mock()

        model.update_step(99, _step(ActionType.WAIT))

        model._bus.emit.assert_not_called()


class TestMoveStep:
    def test_swap(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0, comment="A"))
        model.add_step(_step(ActionType.PRESS_KEY, key="x", comment="B"))

        model.move_step(0, 1)

        steps = model.get_steps()
        assert steps[0].comment == "B"
        assert steps[1].comment == "A"

    def test_move_out_of_range_noop(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        bus = model._bus
        bus.reset_mock()

        model.move_step(0, 99)

        bus.emit.assert_not_called()


class TestClearSteps:
    def test_clear(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        model.add_step(_step(ActionType.PRESS_KEY, key="x"))

        model.clear_steps()

        assert len(model.get_steps()) == 0
        assert "start" in model.graph.nodes
        assert "end" in model.graph.nodes


class TestGetSteps:
    def test_empty(self, model: ChainModel) -> None:
        assert model.get_steps() == []

    def test_filters_none_actions(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        steps = model.get_steps()
        assert len(steps) == 1


class TestChainName:
    def test_getter(self, model: ChainModel) -> None:
        assert model.chain_name == model.graph.name

    def test_setter(self, model: ChainModel) -> None:
        model.chain_name = "new_name"
        assert model.graph.name == "new_name"


# ---- 图操作 ----


class TestAddNodeAt:
    def test_add_action_node(self, model: ChainModel) -> None:
        node = model.add_node_at(NodeType.ACTION, 100, 200, ActionType.WAIT)

        assert node.node_type == NodeType.ACTION
        assert node.action is not None
        assert node.pos_x == 100
        assert node.pos_y == 200

    def test_add_non_action_no_action(self, model: ChainModel) -> None:
        node = model.add_node_at(NodeType.CONDITION, 50, 50)

        assert node.action is None
        assert node.node_type == NodeType.CONDITION


class TestRemoveNodeById:
    def test_remove_action_node(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        action_id = model.graph.action_nodes()[0].node_id

        model.remove_node_by_id(action_id)

        assert action_id not in model.graph.nodes

    def test_protect_start(self, model: ChainModel) -> None:
        model.remove_node_by_id("start")

        assert "start" in model.graph.nodes

    def test_protect_end(self, model: ChainModel) -> None:
        model.remove_node_by_id("end")

        assert "end" in model.graph.nodes

    def test_nonexistent_noop(self, model: ChainModel) -> None:
        model.remove_node_by_id("ghost")


class TestAddEdgeBetween:
    def test_add_edge(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        action_id = model.graph.action_nodes()[0].node_id

        edge = model.add_edge_between("start", action_id, "custom")

        assert edge is not None
        assert edge.label == "custom"

    def test_self_loop_rejected(self, model: ChainModel) -> None:
        edge = model.add_edge_between("start", "start")

        assert edge is None

    def test_nonexistent_node_rejected(self, model: ChainModel) -> None:
        edge = model.add_edge_between("start", "ghost")

        assert edge is None

    def test_duplicate_rejected(self, model: ChainModel) -> None:
        model.add_edge_between("start", "end", "dup_test")
        edge2 = model.add_edge_between("start", "end", "dup_test")

        assert edge2 is None


class TestRemoveEdgeById:
    def test_remove(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        action_id = model.graph.action_nodes()[0].node_id
        edge = model.add_edge_between("start", action_id, "extra")

        model.remove_edge_by_id(edge.edge_id)

        edge_ids = {e.edge_id for e in model.graph.edges}
        assert edge.edge_id not in edge_ids


class TestUpdateNodePosition:
    def test_update(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        action_id = model.graph.action_nodes()[0].node_id

        model.update_node_position(action_id, 42, 84)

        node = model.graph.get_node(action_id)
        assert node.pos_x == 42
        assert node.pos_y == 84

    def test_nonexistent_noop(self, model: ChainModel) -> None:
        model.update_node_position("ghost", 1, 2)


# ---- 加载图 ----


class TestLoadGraph:
    def test_load(self, model: ChainModel, bus: MagicMock) -> None:
        graph = FlowGraph(name="loaded", start_node_id="s")
        graph.add_node(FlowNode(node_id="s", node_type=NodeType.START))

        model.load_graph(graph, "my_profile")

        assert model.graph is graph
        assert model.current_profile_name == "my_profile"
        bus.emit.assert_called_with("chain.loaded")


# ---- 条件节点 ----


class TestAddConditionNode:
    def test_add_with_branches(self, model: ChainModel, bus: MagicMock) -> None:
        cond_node = FlowNode(node_id="cond1", node_type=NodeType.CONDITION)
        true_id = "true_branch"
        false_id = "false_branch"

        true_node = FlowNode(node_id=true_id, node_type=NodeType.ACTION)
        false_node = FlowNode(node_id=false_id, node_type=NodeType.ACTION)
        model.graph.add_node(true_node)
        model.graph.add_node(false_node)

        model.add_condition_node(cond_node, true_id, false_id)

        assert "cond1" in model.graph.nodes
        edge_labels = {(e.from_node, e.to_node, e.label) for e in model.graph.edges}
        assert ("cond1", true_id, "true") in edge_labels
        assert ("cond1", false_id, "false") in edge_labels


# ---- 监控器 ----


class TestMonitorOps:
    def test_add_monitor(self, model: ChainModel, bus: MagicMock) -> None:
        mon = MonitorConfig(name="test_mon")
        model.add_monitor(mon)

        assert len(model.get_monitors()) == 1
        bus.emit.assert_called_with("chain.monitors_changed")

    def test_remove_monitor(self, model: ChainModel) -> None:
        mon = MonitorConfig(name="m1")
        model.add_monitor(mon)
        model.remove_monitor(0)

        assert len(model.get_monitors()) == 0

    def test_remove_out_of_range_noop(self, model: ChainModel) -> None:
        model.remove_monitor(99)

    def test_update_monitor(self, model: ChainModel) -> None:
        model.add_monitor(MonitorConfig(name="old"))
        new_mon = MonitorConfig(name="new")
        model.update_monitor(0, new_mon)

        assert model.get_monitors()[0].name == "new"

    def test_update_out_of_range_noop(self, model: ChainModel) -> None:
        model.update_monitor(99, MonitorConfig(name="x"))


# ---- 执行状态 ----


class TestExecutorState:
    def test_set_state(self, model: ChainModel, bus: MagicMock) -> None:
        model.set_executor_state("running")

        assert model.executor_state == "running"
        bus.emit.assert_called_with("executor.state_changed", state="running")


# ---- 区域 ----


class TestRegion:
    def test_set_region(self, model: ChainModel, bus: MagicMock) -> None:
        model.set_region("window", rect=(0, 0, 800, 600))

        assert model.region_mode == "window"
        bus.emit.assert_called_with("region.changed", mode="window", rect=(0, 0, 800, 600))


# ---- 内部辅助 ----


class TestHelpers:
    def test_find_node_before_end(self, model: ChainModel) -> None:
        assert model._find_node_before_end() == "start"

    def test_find_node_after_add(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        action_id = model.graph.action_nodes()[0].node_id

        assert model._find_node_before_end() == action_id

    def test_reroute_to_end(self, model: ChainModel) -> None:
        model.add_step(_step(ActionType.WAIT, wait_seconds=1.0))
        first_id = model.graph.action_nodes()[0].node_id

        new_id = "new_node"
        new_node = FlowNode(node_id=new_id, node_type=NodeType.ACTION)
        model.graph.add_node(new_node)
        model._reroute_to_end(first_id, new_id)

        labels = {(e.from_node, e.to_node) for e in model.graph.edges
                   if e.label == "default"}
        assert (first_id, new_id) in labels
        assert (new_id, "end") in labels
