"""框架无关的工作流图编排纯逻辑（D5 下沉）。

提取自两后端 ``workflow_actions_mixin._import_steps`` 中**完全相同**的图变异
序列（规格 docs/superpowers/specs/2026-06-15-theme-dedup-unify-design.md §4.3 D5）。

设计要点：
- **纯逻辑、无视觉副作用**：只做图变异，返回结构变更记录。
- **行为保持**：调用顺序与原 mixin 完全一致（找插入点→删边→循环加节点加边→
  重连 End→下移 End），各后端拿到记录后按自身方式回放视觉
  （tk 逐个 ``add_*_visual`` / Qt 末尾 ``render_graph``），视觉最终态不变。
- **布局常量参数化**：两后端各自传入（tk ``LAYOUT_*`` / Qt ``_DEFAULT_NODE_*``），
  避免改变任一后端既有布局。
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from src.core.flow import FlowEdge, FlowNode, NodeType

if TYPE_CHECKING:
    from src.panel.controllers.workflow_controller import WorkflowController
    from src.panel.models.chain_model import FlowGraph


@dataclass(frozen=True)
class ImportedNode:
    """``import_steps_before_end`` 创建的一个节点记录（按创建顺序）。"""

    node: FlowNode
    in_edge: FlowEdge | None
    """prev → 本节点的连边（首个节点的 prev 为插入点节点）。"""


@dataclass(frozen=True)
class ImportStepsResult:
    """``import_steps_before_end`` 的结构变更记录。"""

    imported: tuple[ImportedNode, ...]
    """按创建顺序的节点 + 各自入边。"""
    removed_edge_ids: tuple[str, ...]
    """被移除的「插入点 → End」边 id。"""
    end_edge: FlowEdge | None
    """末节点 → End 的连边。"""
    end_position: tuple[int, int] | None
    """End 被下移到的新坐标；图中无 End 时为 None。"""


def import_steps_before_end(
    graph: "FlowGraph",
    controller: "WorkflowController",
    steps: list,
    *,
    default_x: int,
    default_y: int,
    spacing_y: int,
) -> ImportStepsResult:
    """将 ``steps`` 插入 End 节点之前，返回结构变更记录（纯逻辑，无视觉副作用）。

    Args:
        graph: FlowGraph（通常 ``model.graph``）。
        controller: WorkflowController，提供 ``add_node`` / ``add_edge`` /
            ``remove_edge`` / ``update_node_action``。
        steps: 待导入的 ``BaseStep`` 列表（需 ``.action_type`` 属性且可被
            :func:`dataclasses.replace` 复制）。
        default_x: 锚点缺省时的 X 坐标。
        default_y: 锚点缺省时的 Y 坐标。
        spacing_y: 节点纵向间距。

    Returns:
        结构变更记录；``steps`` 为空时返回空记录且不修改图。
    """
    if not steps:
        return ImportStepsResult(
            imported=(), removed_edge_ids=(), end_edge=None, end_position=None,
        )

    # 1. 插入点：End 前一个非 start 节点（线性链假设）
    end_incoming = graph.get_incoming_edges("end")
    last_node_id = "start"
    for edge in end_incoming:
        if edge.from_node != "start":
            last_node_id = edge.from_node

    # 2. 移除「插入点 → End」边，记录以便后端回放视觉移除
    removed_edge_ids: list[str] = []
    for edge in graph.get_outgoing_edges(last_node_id):
        if edge.to_node == "end":
            controller.remove_edge(edge.edge_id)
            removed_edge_ids.append(edge.edge_id)

    # 3. 布局锚点：插入点节点坐标，缺省（0/空）回退到默认值
    anchor = graph.get_node(last_node_id)
    base_x = anchor.pos_x if anchor and anchor.pos_x else default_x
    base_y = anchor.pos_y if anchor and anchor.pos_y else default_y
    first_y = base_y + spacing_y

    # 4. 循环加节点 + 连边（顺序与原 mixin 一致）
    imported: list[ImportedNode] = []
    prev_id: str = last_node_id
    for index, step in enumerate(steps):
        node_y = first_y + index * spacing_y
        node = controller.add_node(
            NodeType.ACTION, int(base_x), int(node_y), step.action_type,
        )
        controller.update_node_action(node.node_id, replace(step))
        in_edge = controller.add_edge(prev_id, node.node_id)
        imported.append(ImportedNode(node=node, in_edge=in_edge))
        prev_id = node.node_id

    # 5. 末节点 → End
    end_edge = controller.add_edge(prev_id, "end")

    # 6. End 下移到最后节点之下（不可变 replace，直写 graph —— 与原 mixin 一致）
    end_node = graph.get_node("end")
    end_position: tuple[int, int] | None = None
    if end_node is not None:
        new_x, new_y = int(base_x), int(first_y + len(steps) * spacing_y)
        graph.nodes["end"] = replace(end_node, pos_x=new_x, pos_y=new_y)
        end_position = (new_x, new_y)

    return ImportStepsResult(
        imported=tuple(imported),
        removed_edge_ids=tuple(removed_edge_ids),
        end_edge=end_edge,
        end_position=end_position,
    )
