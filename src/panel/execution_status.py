"""执行进度分段构建器 — 把执行器原始值格式化为 3 段状态文本。

供 tkinter / Qt 双框架的动作链与工作流页面共用,保证 4 个界面格式一致。
纯函数,可脱离 GUI 单元测试。
"""

from __future__ import annotations

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
