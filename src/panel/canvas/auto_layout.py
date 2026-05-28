"""auto_layout — 共享自动布局计算。

提供 BFS 分层算法，供 Qt / tkinter 后端复用。
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from src.core.flow import NodeType

if TYPE_CHECKING:
    from src.core.flow import FlowGraph, FlowNode

_AUTO_LAYOUT_THRESHOLD = 10


def all_nodes_at_origin(
    nodes: list[FlowNode],
    *,
    threshold: float = _AUTO_LAYOUT_THRESHOLD,
    exclude_types: tuple[NodeType, ...] | None = None,
) -> bool:
    """检查节点是否都在原点附近。

    exclude_types: 需要排除的节点类型（如 START/END），None 表示不排除。
    """
    if exclude_types:
        nodes = [n for n in nodes if n.node_type not in exclude_types]
    return all(
        abs(n.pos_x) < threshold and abs(n.pos_y) < threshold
        for n in nodes
    )


def bfs_layers(
    graph: FlowGraph,
    root: FlowNode,
) -> dict[str, int]:
    """BFS 遍历，返回 {node_id: depth}。

    未被 BFS 访问到的孤立节点会被放到 max_depth + 1 层。
    """
    visited: set[str] = set()
    layers: dict[str, int] = {}
    queue: deque[tuple[FlowNode, int]] = deque([(root, 0)])

    while queue:
        current, depth = queue.popleft()
        if current.node_id in visited:
            continue
        visited.add(current.node_id)
        layers[current.node_id] = depth
        for edge in graph.get_outgoing_edges(current.node_id):
            child = graph.get_node(edge.to_node)
            if child and child.node_id not in visited:
                queue.append((child, depth + 1))

    max_depth = max(layers.values(), default=0)
    for node in graph.nodes.values():
        if node.node_id not in visited:
            layers[node.node_id] = max_depth + 1

    return layers


def apply_bfs_positions(
    graph: FlowGraph,
    *,
    spacing_x: float = 250,
    spacing_y: float = 120,
    origin_x: float = 50,
    origin_y: float = 50,
) -> None:
    """BFS 自动布局，直接设置 node.pos_x / pos_y。"""
    if not graph.nodes:
        return

    nodes = list(graph.nodes.values())
    if not all_nodes_at_origin(nodes):
        return

    root = graph.find_by_type("START") or nodes[0]

    layers = bfs_layers(graph, root)

    layer_nodes: dict[int, list[FlowNode]] = {}
    for nid, depth in layers.items():
        node = graph.get_node(nid)
        if node:
            layer_nodes.setdefault(depth, []).append(node)

    for depth, layer_list in layer_nodes.items():
        count = len(layer_list)
        for i, node in enumerate(layer_list):
            node.pos_x = int(depth * spacing_x + origin_x)
            node.pos_y = int(i * spacing_y - (count - 1) * spacing_y / 2 + origin_y)
