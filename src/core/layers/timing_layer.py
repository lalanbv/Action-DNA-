"""TimingLayer — 节点计时统计层。

记录每个节点的执行耗时，按节点类型汇总统计。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.engine.execution_context import ExecutionContext
from src.core.engine.priority import SystemPriority
from src.core.layers.layer import ErrorContext, GraphLayer
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.core.engine.node_result import NodeResult

__all__ = ["TimingLayer", "TimingStats", "TimingEntry"]

logger = logging.getLogger(__name__)


@dataclass
class TimingStats:
    """单个节点类型的计时统计。"""

    call_count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    success_count: int = 0
    error_count: int = 0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.call_count if self.call_count > 0 else 0.0

    @property
    def success_rate(self) -> float:
        return (
            self.success_count / self.call_count * 100
            if self.call_count > 0
            else 0.0
        )


@dataclass
class TimingEntry:
    """单次节点执行的时间记录。"""

    node_id: str
    node_type: str
    start_time: float
    end_time: float = 0.0
    success: bool = True

    @property
    def elapsed_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000


class TimingLayer(GraphLayer):
    """节点计时统计层。"""

    _TIMING_KEY = "_timing_entry"
    _GraphEngine: type | None = None  # lazy import cache

    def __init__(self, report_on_exit: bool = True) -> None:
        self._report_on_exit = report_on_exit
        self._timeline: deque[TimingEntry] = deque(maxlen=1000)
        self._stats: dict[str, TimingStats] = defaultdict(TimingStats)
        self._lock = threading.Lock()

    @classmethod
    def _get_graph_engine(cls) -> type:
        if cls._GraphEngine is None:
            from src.core.engine.graph_engine import GraphEngine
            cls._GraphEngine = GraphEngine
        return cls._GraphEngine

    @property
    def name(self) -> str:
        return "timing"

    @property
    def priority(self) -> int:
        return SystemPriority.MEASURE

    @property
    def timeline(self) -> list[TimingEntry]:
        with self._lock:
            return list(self._timeline)

    @property
    def stats(self) -> dict[str, TimingStats]:
        with self._lock:
            return dict(self._stats)

    def on_graph_start(self, ctx: ExecutionContext) -> None:
        with self._lock:
            self._timeline.clear()
            self._stats.clear()

    def on_graph_end(self, ctx: ExecutionContext) -> None:
        if not self._report_on_exit:
            return

        logger.info(t("layers.log.perf_report_header"))
        for node_type, stats in sorted(self._stats.items()):
            if stats.call_count == 0:
                continue
            logger.info(
                "%-20s 调用=%3d  平均=%8.1fms  最大=%8.1fms  "
                "最小=%8.1fms  成功率=%5.1f%%",
                node_type,
                stats.call_count,
                stats.avg_ms,
                stats.max_ms,
                stats.min_ms,
                stats.success_rate,
            )
        logger.info("==================================")

    def on_node_enter(self, ctx: ExecutionContext) -> ExecutionContext:
        node = ctx.current_node
        node_label = self._get_graph_engine().get_action_type(node)

        entry = TimingEntry(
            node_id=node.node_id,
            node_type=node_label,
            start_time=time.monotonic(),
        )
        return ctx.with_extra(self._TIMING_KEY, entry)

    def _get_entry(self, ctx: ExecutionContext) -> TimingEntry | None:
        return ctx.extra.get(self._TIMING_KEY)

    def _record_completion(self, entry: TimingEntry, success: bool) -> None:
        """记录节点完成，更新时间线和统计。"""
        completed = TimingEntry(
            node_id=entry.node_id,
            node_type=entry.node_type,
            start_time=entry.start_time,
            end_time=time.monotonic(),
            success=success,
        )
        elapsed = completed.elapsed_ms
        with self._lock:
            self._timeline.append(completed)
            stats = self._stats[completed.node_type]
            stats.call_count += 1
            stats.total_ms += elapsed
            stats.min_ms = min(stats.min_ms, elapsed)
            stats.max_ms = max(stats.max_ms, elapsed)
            if success:
                stats.success_count += 1
            else:
                stats.error_count += 1

    def on_node_exit(
        self,
        ctx: ExecutionContext,
        result: NodeResult,
    ) -> NodeResult:
        entry = self._get_entry(ctx)
        if entry is not None:
            self._record_completion(entry, success=result.success)
        return result

    def on_node_error(
        self,
        ctx: ExecutionContext,
        err_ctx: ErrorContext,
    ) -> ErrorContext:
        entry = self._get_entry(ctx)
        if entry is not None:
            self._record_completion(entry, success=False)
        return err_ctx
