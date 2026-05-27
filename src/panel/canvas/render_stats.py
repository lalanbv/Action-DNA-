"""渲染统计 — 跟踪画布渲染性能指标。"""

from collections import deque
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RenderStats:
    """一次 render_graph 调用的渲染统计快照。"""

    node_count: int
    visible_node_count: int
    edge_count: int
    canvas_item_count: int
    render_time_ms: float
    diff_added: int = 0
    diff_removed: int = 0
    diff_updated: int = 0


@dataclass
class RenderStatsCollector:
    """累积渲染统计，供调试面板读取。"""

    _history: deque[RenderStats] = field(default_factory=lambda: deque(maxlen=100))

    def record(self, stats: RenderStats) -> None:
        self._history.append(stats)

    @property
    def last(self) -> RenderStats | None:
        return self._history[-1] if self._history else None

    @property
    def history(self) -> list[RenderStats]:
        return list(self._history)

    def clear(self) -> None:
        self._history.clear()
