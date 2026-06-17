"""执行进度分段构建器 — 把执行器原始值格式化为 3 段状态文本。

供 tkinter / Qt 双框架的动作链与工作流页面共用,保证 4 个界面格式一致。
纯函数,可脱离 GUI 单元测试。

另提供 :class:`ExecutionStatusTicker` —— 统一 4 个页面的每秒轮询逻辑
(tk 用 ``frame.after`` / ``after_cancel``,Qt 用 ``schedule`` / ``timer.cancel``),
避免每个页面各自维护一份 start/tick/stop 三件套。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.core.flow import FlowGraph, NodeType
from src.utils.i18n import t
from src.utils.timing import format_duration_human

if TYPE_CHECKING:
    from src.core.action_executor import ActionExecutor


@dataclass(frozen=True)
class ExecutionSegments:
    """3 段执行状态文本。"""

    loop_text: str
    step_text: str
    time_text: str


def count_reachable_action_nodes(graph: FlowGraph) -> int:
    """从 START 可达、启用、且有 action 的 ACTION 节点数。

    动作链(线性)= 精确值;工作流(DAG)= 最优静态上界
    (分支场景下当前步数可能不达总数,属不可消除限制)。
    """
    return sum(
        1
        for node in graph.ordered_nodes()
        if node.node_type == NodeType.ACTION and node.enabled and node.action is not None
    )


def build_execution_segments(
    *,
    completed_rounds: int,
    loop_count: int,
    is_loop: bool,
    step_index: int,
    total_steps: int,
    elapsed_seconds: float | None,
) -> ExecutionSegments:
    """把原始执行值格式化为 3 段文本。

    Args:
        completed_rounds: 已完整跑完的回合数。
        loop_count: 总循环数(0 = 无限)。
        is_loop: graph.loop,为 False 表示单次模式。
        step_index: 引擎发布的当前步骤(首个 ACTION = 1,已是 1 基);< 0 表示未运行。
        total_steps: 可达启用 ACTION 节点数。
        elapsed_seconds: 活跃秒数(排除暂停);None 表示未启动。
    """
    if is_loop and loop_count == 0:
        loop_total_label = t("exec.status.infinite")
    else:
        loop_total_label = str(loop_count if is_loop else 1)
    loop_text = t("exec.status.loop", current=completed_rounds, total=loop_total_label)

    step_current_label = t("exec.status.dash") if step_index < 0 else str(step_index)
    step_text = t("exec.status.step", current=step_current_label, total=total_steps)

    time_label = (
        t("exec.status.dash") if elapsed_seconds is None else format_duration_human(elapsed_seconds)
    )
    time_text = t("exec.status.time", duration=time_label)

    return ExecutionSegments(loop_text=loop_text, step_text=step_text, time_text=time_text)


def compose_execution_status(executor: "ActionExecutor", graph: FlowGraph) -> ExecutionSegments:
    """从执行器 + 图组装执行状态分段(UI 刷新入口)。"""
    return build_execution_segments(
        completed_rounds=executor.completed_rounds,
        loop_count=graph.loop_count,
        is_loop=graph.loop,
        step_index=executor.current_step_index,
        total_steps=count_reachable_action_nodes(graph),
        elapsed_seconds=executor.elapsed_active,
    )


class ExecutionStatusTicker:
    """每秒刷新执行进度段的轮询器 —— 统一 tk/Qt 4 个页面的轮询逻辑。

    各页面只负责提供两个回调:
    - ``refresh``: 从执行器读值并写回状态栏/标签(页面特有,因属性名不同)。
    - ``is_running``: 当前是否处于 RUNNING(决定是否继续 re-arm)。

    调度/取消对由页面注入(tk: ``frame.after`` / ``frame.after_cancel``;
    Qt: ``self.schedule`` / ``self._timer.cancel``)。``cancel`` 失败被吞掉
    (token 失效 / 解释器拆除期无害)。

    生命周期: ``start()``(先取消旧回调再排定) → 每秒 ``_tick`` → ``stop()``。
    """

    def __init__(
        self,
        schedule: Callable,
        cancel: Callable,
        refresh: Callable[[], None],
        is_running: Callable[[], bool],
        interval_ms: int = 1000,
    ) -> None:
        self._schedule = schedule
        self._cancel = cancel
        self._refresh = refresh
        self._is_running = is_running
        self._interval_ms = interval_ms
        self._token: object | None = None

    def start(self) -> None:
        """开始轮询(若已在运行先取消,避免重复回调)。"""
        self.stop()
        self._token = self._schedule(self._interval_ms, self._tick)

    def _tick(self) -> None:
        self._token = None
        self._refresh()
        if self._is_running():
            self._token = self._schedule(self._interval_ms, self._tick)

    def stop(self) -> None:
        """取消待执行的回调(token 失效无害)。"""
        token = self._token
        if token is not None:
            try:
                self._cancel(token)
            except Exception:  # noqa: BLE001 — token 失效/解释器拆除期无害
                pass
            self._token = None
