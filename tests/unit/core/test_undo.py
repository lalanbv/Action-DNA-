"""UndoManager + EditCommand 单元测试。

覆盖：7 个 EditCommand 的 do/undo 对称性、UndoManager 双栈操作、
命令合并、深度裁剪、回调通知、边界条件。
"""

from __future__ import annotations

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.editor import UndoManager, UndoManagerConfig
from src.core.editor.commands import (
    AddEdgeCommand,
    AddNodeCommand,
    CompositeCommand,
    EditPropertyCommand,
    MoveNodeCommand,
    RemoveEdgeCommand,
    RemoveNodeCommand,
)
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def graph() -> FlowGraph:
    return FlowGraph(name="test")


@pytest.fixture
def graph_with_node(graph: FlowGraph) -> FlowGraph:
    node = FlowNode(node_id="n1", node_type=NodeType.ACTION, pos_x=10, pos_y=20)
    graph.add_node(node)
    return graph


@pytest.fixture
def graph_with_two_nodes(graph: FlowGraph) -> FlowGraph:
    a = FlowNode(node_id="a", node_type=NodeType.START, pos_x=0, pos_y=0)
    b = FlowNode(node_id="b", node_type=NodeType.ACTION, pos_x=100, pos_y=100)
    graph.add_node(a)
    graph.add_node(b)
    return graph


@pytest.fixture
def graph_with_edge(graph_with_two_nodes: FlowGraph) -> FlowGraph:
    edge = FlowEdge(edge_id="e1", from_node="a", to_node="b")
    graph_with_two_nodes.add_edge(edge)
    return graph_with_two_nodes


# ── AddNodeCommand ────────────────────────────────────────────


class TestAddNodeCommand:
    def test_execute_adds_node(self, graph: FlowGraph) -> None:
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=50, y=60)
        cmd.execute()
        assert len(graph.nodes) == 1
        node = list(graph.nodes.values())[0]
        assert node.pos_x == 50
        assert node.pos_y == 60
        assert node.node_type == NodeType.ACTION

    def test_undo_removes_node(self, graph: FlowGraph) -> None:
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        cmd.execute()
        node_id = cmd._node_id
        assert node_id is not None
        cmd.undo()
        assert graph.get_node(node_id) is None
        assert len(graph.nodes) == 0

    def test_redo_restores_node(self, graph: FlowGraph) -> None:
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        cmd.execute()
        node_id = cmd._node_id
        cmd.undo()
        cmd.execute()
        assert graph.get_node(node_id) is not None

    def test_execute_with_action(self, graph: FlowGraph) -> None:
        action = STEP_CLASSES[ActionType.WAIT](wait_seconds=2.0)
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0, action=action)
        cmd.execute()
        node = list(graph.nodes.values())[0]
        assert node.action is not None
        assert node.action.action_type == ActionType.WAIT

    def test_description(self, graph: FlowGraph) -> None:
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        assert "添加节点" in cmd.description


# ── RemoveNodeCommand ─────────────────────────────────────────


class TestRemoveNodeCommand:
    def test_execute_removes_node(self, graph_with_node: FlowGraph) -> None:
        cmd = RemoveNodeCommand(graph=graph_with_node, node_id="n1")
        cmd.execute()
        assert graph_with_node.get_node("n1") is None

    def test_undo_restores_node(self, graph_with_node: FlowGraph) -> None:
        cmd = RemoveNodeCommand(graph=graph_with_node, node_id="n1")
        cmd.execute()
        cmd.undo()
        node = graph_with_node.get_node("n1")
        assert node is not None
        assert node.pos_x == 10
        assert node.pos_y == 20

    def test_removes_connected_edges(self, graph_with_edge: FlowGraph) -> None:
        cmd = RemoveNodeCommand(graph=graph_with_edge, node_id="b")
        cmd.execute()
        assert graph_with_edge.get_node("b") is None
        assert all(e.to_node != "b" and e.from_node != "b" for e in graph_with_edge.edges)

    def test_undo_restores_edges(self, graph_with_edge: FlowGraph) -> None:
        cmd = RemoveNodeCommand(graph=graph_with_edge, node_id="b")
        cmd.execute()
        assert len(graph_with_edge.edges) == 0
        cmd.undo()
        assert any(e.edge_id == "e1" for e in graph_with_edge.edges)

    def test_execute_nonexistent_is_noop(self, graph: FlowGraph) -> None:
        cmd = RemoveNodeCommand(graph=graph, node_id="missing")
        cmd.execute()
        assert len(graph.nodes) == 0

    def test_description(self, graph_with_node: FlowGraph) -> None:
        cmd = RemoveNodeCommand(graph=graph_with_node, node_id="n1")
        assert "删除节点" in cmd.description


# ── MoveNodeCommand ───────────────────────────────────────────


class TestMoveNodeCommand:
    def test_execute_moves_node(self, graph_with_node: FlowGraph) -> None:
        cmd = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=200, new_y=300)
        cmd.execute()
        node = graph_with_node.get_node("n1")
        assert node is not None
        assert node.pos_x == 200
        assert node.pos_y == 300

    def test_undo_restores_position(self, graph_with_node: FlowGraph) -> None:
        cmd = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=200, new_y=300)
        cmd.execute()
        cmd.undo()
        node = graph_with_node.get_node("n1")
        assert node is not None
        assert node.pos_x == 10
        assert node.pos_y == 20

    def test_can_merge(self, graph_with_node: FlowGraph) -> None:
        cmd = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=0, new_y=0)
        assert cmd.can_merge is True

    def test_merge_same_node(self, graph_with_node: FlowGraph) -> None:
        cmd1 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=100)
        cmd2 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=200, new_y=200)
        cmd1.execute()
        assert cmd1.merge(cmd2) is True
        assert cmd1.new_x == 200
        assert cmd1.new_y == 200
        assert cmd1._old_x == 10
        assert cmd1._old_y == 20

    def test_merge_different_node_fails(self, graph_with_node: FlowGraph) -> None:
        cmd1 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=100)
        cmd2 = MoveNodeCommand(graph=graph_with_node, node_id="other", new_x=200, new_y=200)
        assert cmd1.merge(cmd2) is False

    def test_merge_wrong_type_fails(self, graph_with_node: FlowGraph) -> None:
        cmd1 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=100)
        cmd2 = AddNodeCommand(graph=graph_with_node, node_type=NodeType.ACTION, x=0, y=0)
        assert cmd1.merge(cmd2) is False

    def test_execute_nonexistent_is_noop(self, graph: FlowGraph) -> None:
        cmd = MoveNodeCommand(graph=graph, node_id="missing", new_x=1, new_y=2)
        cmd.execute()

    def test_description(self, graph_with_node: FlowGraph) -> None:
        cmd = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=0, new_y=0)
        assert "移动节点" in cmd.description


# ── AddEdgeCommand ────────────────────────────────────────────


class TestAddEdgeCommand:
    def test_execute_adds_edge(self, graph_with_two_nodes: FlowGraph) -> None:
        cmd = AddEdgeCommand(graph=graph_with_two_nodes, source_id="a", target_id="b")
        cmd.execute()
        assert len(graph_with_two_nodes.edges) == 1
        edge = graph_with_two_nodes.edges[0]
        assert edge.from_node == "a"
        assert edge.to_node == "b"

    def test_undo_removes_edge(self, graph_with_two_nodes: FlowGraph) -> None:
        cmd = AddEdgeCommand(graph=graph_with_two_nodes, source_id="a", target_id="b")
        cmd.execute()
        cmd.undo()
        assert len(graph_with_two_nodes.edges) == 0

    def test_redo_restores_edge(self, graph_with_two_nodes: FlowGraph) -> None:
        cmd = AddEdgeCommand(graph=graph_with_two_nodes, source_id="a", target_id="b")
        cmd.execute()
        edge_id = cmd._edge_id
        cmd.undo()
        cmd.execute()
        assert any(e.edge_id == edge_id for e in graph_with_two_nodes.edges)

    def test_custom_label(self, graph_with_two_nodes: FlowGraph) -> None:
        cmd = AddEdgeCommand(graph=graph_with_two_nodes, source_id="a", target_id="b", label="true")
        cmd.execute()
        assert graph_with_two_nodes.edges[0].label == "true"

    def test_description(self, graph_with_two_nodes: FlowGraph) -> None:
        cmd = AddEdgeCommand(graph=graph_with_two_nodes, source_id="a", target_id="b")
        assert "添加连线" in cmd.description


# ── RemoveEdgeCommand ─────────────────────────────────────────


class TestRemoveEdgeCommand:
    def test_execute_removes_edge(self, graph_with_edge: FlowGraph) -> None:
        cmd = RemoveEdgeCommand(graph=graph_with_edge, edge_id="e1")
        cmd.execute()
        assert len(graph_with_edge.edges) == 0

    def test_undo_restores_edge(self, graph_with_edge: FlowGraph) -> None:
        cmd = RemoveEdgeCommand(graph=graph_with_edge, edge_id="e1")
        cmd.execute()
        cmd.undo()
        assert len(graph_with_edge.edges) == 1
        assert graph_with_edge.edges[0].edge_id == "e1"

    def test_execute_nonexistent_is_noop(self, graph: FlowGraph) -> None:
        cmd = RemoveEdgeCommand(graph=graph, edge_id="missing")
        cmd.execute()
        assert len(graph.edges) == 0

    def test_undo_nonexistent_is_noop(self, graph: FlowGraph) -> None:
        cmd = RemoveEdgeCommand(graph=graph, edge_id="missing")
        cmd.execute()
        cmd.undo()
        assert len(graph.edges) == 0

    def test_description(self, graph_with_edge: FlowGraph) -> None:
        cmd = RemoveEdgeCommand(graph=graph_with_edge, edge_id="e1")
        assert "删除连线" in cmd.description


# ── EditPropertyCommand ───────────────────────────────────────


class TestEditPropertyCommand:
    def test_execute_sets_property(self, graph_with_node: FlowGraph) -> None:
        cmd = EditPropertyCommand(
            graph=graph_with_node, node_id="n1",
            property_path="comment", old_value="", new_value="hello",
        )
        cmd.execute()
        assert graph_with_node.get_node("n1").comment == "hello"

    def test_undo_restores_property(self, graph_with_node: FlowGraph) -> None:
        cmd = EditPropertyCommand(
            graph=graph_with_node, node_id="n1",
            property_path="comment", old_value="", new_value="hello",
        )
        cmd.execute()
        cmd.undo()
        assert graph_with_node.get_node("n1").comment == ""

    def test_nested_property(self, graph_with_node: FlowGraph) -> None:
        graph_with_node.get_node("n1").action = STEP_CLASSES[ActionType.WAIT](wait_seconds=1.0)
        cmd = EditPropertyCommand(
            graph=graph_with_node, node_id="n1",
            property_path="action.wait_seconds", old_value=1.0, new_value=5.0,
        )
        cmd.execute()
        assert graph_with_node.get_node("n1").action.wait_seconds == 5.0
        cmd.undo()
        assert graph_with_node.get_node("n1").action.wait_seconds == 1.0

    def test_missing_node_is_noop(self, graph: FlowGraph) -> None:
        cmd = EditPropertyCommand(
            graph=graph, node_id="missing",
            property_path="comment", old_value="", new_value="x",
        )
        cmd.execute()
        cmd.undo()

    def test_missing_intermediate_path_is_noop(self, graph_with_node: FlowGraph) -> None:
        cmd = EditPropertyCommand(
            graph=graph_with_node, node_id="n1",
            property_path="nonexistent.field", old_value=None, new_value="x",
        )
        cmd.execute()

    def test_description(self, graph_with_node: FlowGraph) -> None:
        cmd = EditPropertyCommand(
            graph=graph_with_node, node_id="n1",
            property_path="comment", old_value="", new_value="x",
        )
        assert "编辑属性" in cmd.description


# ── CompositeCommand ──────────────────────────────────────────


class TestCompositeCommand:
    def test_execute_runs_all(self, graph_with_two_nodes: FlowGraph) -> None:
        c1 = AddEdgeCommand(graph=graph_with_two_nodes, source_id="a", target_id="b")
        c2 = EditPropertyCommand(
            graph=graph_with_two_nodes, node_id="a",
            property_path="comment", old_value="", new_value="start node",
        )
        composite = CompositeCommand()
        composite.add(c1)
        composite.add(c2)
        composite.execute()
        assert len(graph_with_two_nodes.edges) == 1
        assert graph_with_two_nodes.get_node("a").comment == "start node"

    def test_undo_reverses_all(self, graph_with_two_nodes: FlowGraph) -> None:
        c1 = AddEdgeCommand(graph=graph_with_two_nodes, source_id="a", target_id="b")
        c2 = EditPropertyCommand(
            graph=graph_with_two_nodes, node_id="a",
            property_path="comment", old_value="", new_value="start node",
        )
        composite = CompositeCommand()
        composite.add(c1)
        composite.add(c2)
        composite.execute()
        composite.undo()
        assert len(graph_with_two_nodes.edges) == 0
        assert graph_with_two_nodes.get_node("a").comment == ""

    def test_empty_composite(self) -> None:
        composite = CompositeCommand()
        composite.execute()
        composite.undo()

    def test_description_with_label(self) -> None:
        composite = CompositeCommand(_label="批量粘贴")
        assert composite.description == "批量粘贴"

    def test_description_empty(self) -> None:
        assert CompositeCommand().description == "空复合命令"

    def test_description_single_child(self, graph: FlowGraph) -> None:
        c = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        composite = CompositeCommand()
        composite.add(c)
        assert "添加节点" in composite.description

    def test_description_multi_child(self, graph: FlowGraph) -> None:
        c1 = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        c2 = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=10, y=10)
        composite = CompositeCommand()
        composite.add(c1)
        composite.add(c2)
        assert "复合操作" in composite.description

    def test_commands_returns_copy(self, graph: FlowGraph) -> None:
        c = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        composite = CompositeCommand()
        composite.add(c)
        cmds = composite.commands
        assert len(cmds) == 1
        cmds.clear()
        assert len(composite.commands) == 1


# ── UndoManager ───────────────────────────────────────────────


class TestUndoManager:
    def test_execute_and_undo(self, graph_with_node: FlowGraph) -> None:
        mgr = UndoManager()
        cmd = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=200)
        mgr.execute(cmd)
        assert graph_with_node.get_node("n1").pos_x == 100
        assert mgr.undo() is cmd
        assert graph_with_node.get_node("n1").pos_x == 10

    def test_redo(self, graph_with_node: FlowGraph) -> None:
        mgr = UndoManager()
        cmd = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=200)
        mgr.execute(cmd)
        mgr.undo()
        assert mgr.redo() is cmd
        assert graph_with_node.get_node("n1").pos_x == 100

    def test_undo_empty_stack(self) -> None:
        mgr = UndoManager()
        assert mgr.undo() is None

    def test_redo_empty_stack(self) -> None:
        mgr = UndoManager()
        assert mgr.redo() is None

    def test_can_undo_can_redo(self, graph: FlowGraph) -> None:
        mgr = UndoManager()
        assert mgr.can_undo is False
        assert mgr.can_redo is False
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        mgr.execute(cmd)
        assert mgr.can_undo is True
        mgr.undo()
        assert mgr.can_redo is True
        assert mgr.can_undo is False

    def test_new_command_clears_redo(self, graph: FlowGraph) -> None:
        mgr = UndoManager()
        c1 = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        mgr.execute(c1)
        mgr.undo()
        assert mgr.redo_count == 1
        c2 = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=10, y=10)
        mgr.execute(c2)
        assert mgr.redo_count == 0

    def test_undo_redo_descriptions(self, graph: FlowGraph) -> None:
        mgr = UndoManager()
        assert mgr.undo_description is None
        assert mgr.redo_description is None
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        mgr.execute(cmd)
        assert mgr.undo_description is not None
        assert "添加节点" in mgr.undo_description
        mgr.undo()
        assert mgr.redo_description is not None

    def test_max_depth_trimming(self, graph: FlowGraph) -> None:
        graph.add_node(FlowNode(node_id="n1", node_type=NodeType.ACTION))
        mgr = UndoManager(UndoManagerConfig(max_depth=3))
        for i in range(5):
            mgr.execute(MoveNodeCommand(graph=graph, node_id="n1", new_x=i, new_y=i))
        assert mgr.undo_count <= 3

    def test_callback_on_change(self, graph: FlowGraph) -> None:
        changes: list[int] = []
        mgr = UndoManager()
        mgr.on_change(lambda: changes.append(1))
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        mgr.execute(cmd)
        assert len(changes) == 1
        mgr.undo()
        assert len(changes) == 2
        mgr.redo()
        assert len(changes) == 3

    def test_callback_exception_does_not_stop_others(self, graph: FlowGraph) -> None:
        changes: list[int] = []
        mgr = UndoManager()

        def bad() -> None:
            raise RuntimeError("boom")

        mgr.on_change(bad)
        mgr.on_change(lambda: changes.append(1))
        cmd = AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0)
        mgr.execute(cmd)
        assert len(changes) == 1

    def test_clear(self, graph: FlowGraph) -> None:
        mgr = UndoManager()
        mgr.execute(AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0))
        mgr.undo()
        assert mgr.redo_count == 1
        mgr.clear()
        assert mgr.undo_count == 0
        assert mgr.redo_count == 0

    def test_undo_redo_counts(self, graph: FlowGraph) -> None:
        mgr = UndoManager()
        mgr.execute(AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=0, y=0))
        mgr.execute(AddNodeCommand(graph=graph, node_type=NodeType.ACTION, x=10, y=10))
        assert mgr.undo_count == 2
        assert mgr.redo_count == 0
        mgr.undo()
        assert mgr.undo_count == 1
        assert mgr.redo_count == 1

    def test_merge_move_commands(self, graph_with_node: FlowGraph) -> None:
        mgr = UndoManager(UndoManagerConfig(merge_interval_ms=10000))
        c1 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=100)
        c2 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=200, new_y=200)
        mgr.execute(c1)
        mgr.execute(c2)
        assert mgr.undo_count == 1
        assert graph_with_node.get_node("n1").pos_x == 200
        assert graph_with_node.get_node("n1").pos_y == 200
        mgr.undo()
        assert graph_with_node.get_node("n1").pos_x == 10
        assert graph_with_node.get_node("n1").pos_y == 20

    def test_no_merge_across_time_window(self, graph_with_node: FlowGraph) -> None:
        mgr = UndoManager(UndoManagerConfig(merge_interval_ms=0))
        c1 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=100)
        c2 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=200, new_y=200)
        mgr.execute(c1)
        mgr.execute(c2)
        assert mgr.undo_count == 2

    def test_no_merge_different_command_types(self, graph_with_node: FlowGraph) -> None:
        mgr = UndoManager(UndoManagerConfig(merge_interval_ms=10000))
        c1 = MoveNodeCommand(graph=graph_with_node, node_id="n1", new_x=100, new_y=100)
        c2 = EditPropertyCommand(
            graph=graph_with_node, node_id="n1",
            property_path="comment", old_value="", new_value="x",
        )
        mgr.execute(c1)
        mgr.execute(c2)
        assert mgr.undo_count == 2

    def test_full_do_undo_symmetry_cycle(self, graph_with_edge: FlowGraph) -> None:
        mgr = UndoManager()
        original_b_x = graph_with_edge.get_node("b").pos_x

        cmd = MoveNodeCommand(graph=graph_with_edge, node_id="b", new_x=999, new_y=888)
        mgr.execute(cmd)
        assert graph_with_edge.get_node("b").pos_x == 999

        mgr.undo()
        assert graph_with_edge.get_node("b").pos_x == original_b_x

        mgr.redo()
        assert graph_with_edge.get_node("b").pos_x == 999

        mgr.undo()
        assert graph_with_edge.get_node("b").pos_x == original_b_x

        mgr.redo()
        assert graph_with_edge.get_node("b").pos_x == 999
