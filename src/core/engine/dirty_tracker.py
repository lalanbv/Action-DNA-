"""脏标记追踪器 — 受 Blender depsgraph flush/tag 启发。

当工作流节点被编辑时，仅重新评估该节点及其下游依赖，
而非全量拓扑遍历。适用于 GraphEngine 增量执行模式。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class DirtyTracker:
    """追踪哪些节点需要重新评估。

    使用方式：
    1. 用户编辑节点 → mark_dirty(node_id) + propagate_downstream(...)
    2. 引擎执行 → needs_eval(node_id, generation) 判断是否跳过
    3. 节点执行完毕 → mark_clean(node_id, generation)
    """

    _dirty: set[str] = field(default_factory=set)
    _generation: dict[str, int] = field(default_factory=dict)

    def mark_dirty(self, node_id: str) -> None:
        """标记节点为脏（需要重新评估）。"""
        self._dirty.add(node_id)

    def mark_clean(self, node_id: str, generation: int) -> None:
        """标记节点已评估到指定代。"""
        self._dirty.discard(node_id)
        self._generation[node_id] = generation

    def mark_all_dirty(self, node_ids: list[str]) -> None:
        """标记所有节点为脏（全量重跑）。"""
        self._dirty.update(node_ids)

    def needs_eval(self, node_id: str, current_gen: int) -> bool:
        """判断节点是否需要评估。"""
        return (
            node_id in self._dirty
            or self._generation.get(node_id, 0) < current_gen
        )

    def propagate_downstream(
        self,
        get_successors: Callable[[str], list[str]],
        node_id: str,
    ) -> None:
        """将脏标记传播到所有下游节点（Blender flush 模式）。"""
        visited: set[str] = set()
        queue = deque(get_successors(node_id))
        while queue:
            nid = queue.popleft()
            if nid in visited:
                continue
            visited.add(nid)
            self._dirty.add(nid)
            queue.extend(get_successors(nid))

    def reset(self) -> None:
        """重置所有追踪状态。"""
        self._dirty.clear()
        self._generation.clear()

    @property
    def dirty_nodes(self) -> frozenset[str]:
        """返回当前脏节点集合的只读视图。"""
        return frozenset(self._dirty)
