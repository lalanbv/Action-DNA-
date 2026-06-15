"""D5 共享工作流编排纯逻辑测试 — import_steps_before_end / copy_to_clipboard。

验证从两后端 workflow_actions_mixin 提取出的图变异/剪贴板纯逻辑
（规格 §4.3 D5）。纯逻辑、无视觉副作用，用 fake graph/controller 测试。
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.core.action import ActionType
from src.panel.shared.controllers.workflow_ops import (
    ImportStepsResult,
    copy_to_clipboard,
    import_steps_before_end,
)


# ---- 测试替身：最小化 fake graph / controller / step ----


@dataclass
class _FakeNode:
    node_id: str
    pos_x: int = 0
    pos_y: int = 0
    action: object | None = None
    comment: str = ""
    enabled: bool = True


@dataclass
class _FakeEdge:
    edge_id: str
    from_node: str
    to_node: str


@dataclass
class _FakeStep:
    """dataclass —— 让 dataclasses.replace 可用（模拟 BaseStep）。"""

    action_type: ActionType = ActionType.WAIT
    comment: str = ""
    enabled: bool = True


class _FakeGraph:
    """模拟 FlowGraph 的必要子集。"""

    def __init__(self) -> None:
        self.nodes: dict[str, _FakeNode] = {
            "start": _FakeNode("start", 0, 0),
            "end": _FakeNode("end", 100, 500),
        }
        self._edges: dict[str, _FakeEdge] = {
            "start_end": _FakeEdge("start_end", "start", "end"),
        }

    def get_node(self, node_id: str) -> _FakeNode | None:
        return self.nodes.get(node_id)

    def get_incoming_edges(self, node_id: str) -> list[_FakeEdge]:
        return [e for e in self._edges.values() if e.to_node == node_id]

    def get_outgoing_edges(self, node_id: str) -> list[_FakeEdge]:
        return [e for e in self._edges.values() if e.from_node == node_id]


class _FakeController:
    """模拟 WorkflowController 的必要子集（纯模型变异，无视觉）。"""

    def __init__(self, graph: _FakeGraph) -> None:
        self._graph = graph
        self._n = 0
        self._e = 0

    def add_node(self, node_type, pos_x, pos_y, action_type=None):
        self._n += 1
        nid = f"n{self._n}"
        node = _FakeNode(nid, pos_x, pos_y)
        self._graph.nodes[nid] = node
        return node

    def add_edge(self, from_id, to_id, label=None):
        self._e += 1
        eid = f"e{self._e}"
        edge = _FakeEdge(eid, from_id, to_id)
        self._graph._edges[eid] = edge
        return edge

    def remove_edge(self, edge_id):
        self._graph._edges.pop(edge_id, None)

    def update_node_action(self, node_id, action):
        node = self._graph.get_node(node_id)
        if node is not None:
            node.action = action

    def copy_nodes(self, node_ids):
        """模拟 WorkflowController.copy_nodes：返回节点副本列表。"""
        return [
            _FakeNode(nid) for nid in node_ids if nid in self._graph.nodes
        ]


@pytest.fixture
def graph_controller():
    graph = _FakeGraph()
    controller = _FakeController(graph)
    return graph, controller


# ---- 测试用例 ----


def test_empty_steps_noop(graph_controller):
    """空 steps → 空结果，图不变。"""
    graph, controller = graph_controller
    result = import_steps_before_end(
        graph, controller, [], default_x=300, default_y=40, spacing_y=100,
    )
    assert isinstance(result, ImportStepsResult)
    assert result.imported == ()
    assert result.removed_edge_ids == ()
    assert result.end_edge is None
    assert result.end_position is None
    # 原有 start→end 边仍在
    assert "start_end" in graph._edges


def test_inserts_steps_chained_before_end(graph_controller):
    """3 个 step 被插入：start → n1 → n2 → n3 → end。"""
    graph, controller = graph_controller
    steps = [_FakeStep(ActionType.WAIT), _FakeStep(ActionType.CLICK_POS), _FakeStep(ActionType.OCR_CHECK)]

    result = import_steps_before_end(
        graph, controller, steps, default_x=300, default_y=40, spacing_y=100,
    )

    # 3 个新节点
    assert len(result.imported) == 3
    ids = [imp.node.node_id for imp in result.imported]
    assert ids == ["n1", "n2", "n3"]

    # 每个节点有入边，且链接顺序正确：start→n1, n1→n2, n2→n3
    assert result.imported[0].in_edge.from_node == "start"
    assert result.imported[0].in_edge.to_node == "n1"
    assert result.imported[1].in_edge.from_node == "n1"
    assert result.imported[1].in_edge.to_node == "n2"
    assert result.imported[2].in_edge.from_node == "n2"
    assert result.imported[2].in_edge.to_node == "n3"

    # 末节点 → End
    assert result.end_edge is not None
    assert result.end_edge.from_node == "n3"
    assert result.end_edge.to_node == "end"


def test_removes_old_insertion_point_to_end_edge(graph_controller):
    """原 start→end 边被移除并记录。"""
    graph, controller = graph_controller
    result = import_steps_before_end(
        graph, controller, [_FakeStep()], default_x=300, default_y=40, spacing_y=100,
    )
    assert "start_end" in result.removed_edge_ids
    assert "start_end" not in graph._edges


def test_node_positions_use_spacing(graph_controller):
    """节点纵向按 spacing_y 排布。"""
    graph, controller = graph_controller
    # start 在 (0,0)：pos_x/pos_y 均为 0(falsy) → base 回退到 default_x=300 / default_y=40
    steps = [_FakeStep(), _FakeStep(), _FakeStep()]
    result = import_steps_before_end(
        graph, controller, steps, default_x=300, default_y=40, spacing_y=100,
    )
    ys = [imp.node.pos_y for imp in result.imported]
    # first_y = default_y(40) + spacing_y(100) = 140；依次 +100
    assert ys == [140, 240, 340]
    assert all(imp.node.pos_x == 300 for imp in result.imported)


def test_end_moved_below_last_node(graph_controller):
    """End 被下移到最后节点之下。"""
    graph, controller = graph_controller
    steps = [_FakeStep(), _FakeStep()]
    result = import_steps_before_end(
        graph, controller, steps, default_x=300, default_y=40, spacing_y=100,
    )
    assert result.end_position is not None
    end_x, end_y = result.end_position
    assert end_x == 300
    # first_y=140 + len(2)*spacing_y(100) = 340
    assert end_y == 340
    # graph 中的 end 节点确实被更新
    assert graph.nodes["end"].pos_x == 300
    assert graph.nodes["end"].pos_y == 340


def test_update_node_action_called_with_copy(graph_controller):
    """每个新节点的 action 被设为 step 的副本（dataclasses.replace）。"""
    graph, controller = graph_controller
    step = _FakeStep(ActionType.PRESS_KEY, comment="hi")
    result = import_steps_before_end(
        graph, controller, [step], default_x=300, default_y=40, spacing_y=100,
    )
    node = result.imported[0].node
    assert node.action is not None
    assert node.action is not step  # 是副本，非同一对象
    assert node.action.action_type == ActionType.PRESS_KEY


def test_anchor_from_existing_node_not_default(graph_controller):
    """插入点节点有坐标时，用其坐标做锚点（而非 default）。"""
    graph, controller = graph_controller
    # 让 start 有明确坐标
    graph.nodes["start"].pos_x = 50
    graph.nodes["start"].pos_y = 70
    result = import_steps_before_end(
        graph, controller, [_FakeStep()], default_x=999, default_y=999, spacing_y=100,
    )
    # base_x=50（truthy）, base_y=70 → first_y=170
    assert result.imported[0].node.pos_x == 50
    assert result.imported[0].node.pos_y == 170


# ---- copy_to_clipboard 测试（D5：_on_copy 下沉纯逻辑）----


def test_copy_to_clipboard_returns_controller_result(graph_controller):
    """非空 node_ids → 返回 controller.copy_nodes() 的结果，透传不变形。"""
    _graph, controller = graph_controller
    node_ids = ["start", "end"]
    result = copy_to_clipboard(controller, node_ids)
    # controller.copy_nodes 对每个存在的节点返回一个副本
    assert result is not None
    assert len(result) == 2
    assert [n.node_id for n in result] == ["start", "end"]


def test_copy_empty_ids_is_noop(graph_controller):
    """空 node_ids → 直接返回 None，不调用 controller.copy_nodes。"""
    _graph, controller = graph_controller
    assert copy_to_clipboard(controller, []) is None


def test_copy_does_not_touch_graph(graph_controller):
    """copy 是纯逻辑：不改变图（只读 controller.copy_nodes）。"""
    graph, controller = graph_controller
    edges_before = set(graph._edges)
    nodes_before = set(graph.nodes)
    copy_to_clipboard(controller, ["start"])
    assert set(graph._edges) == edges_before
    assert set(graph.nodes) == nodes_before


# ---- Qt 后端 _on_paste/_on_duplicate_selected 魔法数字回归（D5/U2）----
# 锁定不变量：Qt 后端粘贴/复制偏移必须取自 controller 命名常量
# (PASTE_OFFSET / DUPLICATE_OFFSET_X / DUPLICATE_OFFSET_Y)，与 tk 后端一致，
# 不再出现裸魔法数字（* 30 / offset_x=40 / offset_y=40）。


def _qt_mixin_source() -> str:
    with open(
        "src/panel/qt_backend/pages/workflow_actions_mixin.py", encoding="utf-8"
    ) as fh:
        return fh.read()


def test_qt_paste_uses_controller_constant_not_magic_number():
    """Qt _on_paste 偏移来自 self._controller.PASTE_OFFSET，非裸 ``* 30``。"""
    src = _qt_mixin_source()
    assert "* 30" not in src, "Qt _on_paste 仍有裸魔法数字 * 30"
    assert "self._controller.PASTE_OFFSET" in src


def test_qt_duplicate_uses_controller_constants_not_magic_40():
    """Qt _on_duplicate_selected 偏移来自 controller 命名常量，非裸 ``40``。"""
    src = _qt_mixin_source()
    assert "offset_x=40" not in src, "Qt _on_duplicate 仍有裸魔法数字 offset_x=40"
    assert "offset_y=40" not in src, "Qt _on_duplicate 仍有裸魔法数字 offset_y=40"
    assert "self._controller.DUPLICATE_OFFSET_X" in src
    assert "self._controller.DUPLICATE_OFFSET_Y" in src
