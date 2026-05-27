"""ExecutionSnapshot — DAG 执行状态快照，用于断点恢复和状态回溯。

快照在关键节点创建后不可变，支持状态对比和回溯查询。
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.engine.execution_context import ExecutionContext

logger = logging.getLogger(__name__)

__all__ = ["ExecutionSnapshot", "SnapshotManager"]


@dataclass(frozen=True)
class ExecutionSnapshot:
    """DAG 执行状态快照（不可变）。

    记录某一时刻的执行位置和变量状态，用于：
    - 断点恢复：从快照位置继续执行
    - 状态回溯：对比不同时刻的变量变化
    - 调试诊断：查看出错时的完整上下文
    """

    graph_id: str
    node_id: str
    step_index: int
    variables: dict[str, Any]
    iteration_counts: dict[str, int]
    timestamp: float
    gen: int = 0


class SnapshotManager:
    """管理执行快照的创建和查询。

    维护一个固定大小的快照环形缓冲区，自动淘汰最旧的快照。
    """

    def __init__(self, max_snapshots: int = 100) -> None:
        self._snapshots: deque[ExecutionSnapshot] = deque(maxlen=max_snapshots)

    def capture(self, ctx: ExecutionContext) -> ExecutionSnapshot:
        """从执行上下文创建快照。"""
        graph_id = getattr(ctx.graph, "graph_id", "unknown") or "unknown"

        snapshot = ExecutionSnapshot(
            graph_id=graph_id,
            node_id=ctx.current_node.node_id,
            step_index=ctx.step_index,
            variables=ctx.flatten_variables(),
            iteration_counts=dict(ctx.loop_counts),
            timestamp=time.monotonic(),
            gen=ctx.gen,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def get_latest(self) -> ExecutionSnapshot | None:
        """获取最新快照。"""
        return self._snapshots[-1] if self._snapshots else None

    def get_at_step(self, step_index: int) -> ExecutionSnapshot | None:
        """按步骤索引查找快照（最近的匹配）。"""
        for snap in reversed(self._snapshots):
            if snap.step_index == step_index:
                return snap
        return None

    def get_at_node(self, node_id: str) -> ExecutionSnapshot | None:
        """按节点 ID 查找最新快照。"""
        for snap in reversed(self._snapshots):
            if snap.node_id == node_id:
                return snap
        return None

    def get_all(self) -> list[ExecutionSnapshot]:
        """返回所有快照（按时间排序）。"""
        return list(self._snapshots)

    def clear(self) -> None:
        """清空所有快照。"""
        self._snapshots.clear()

    @property
    def count(self) -> int:
        """当前快照数量。"""
        return len(self._snapshots)
