"""execution_status 测试 — 分段构建 + 可达 ACTION 节点计数。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.panel.execution_status import (
    build_execution_segments,
    compose_execution_status,
    count_reachable_action_nodes,
)
from src.utils import i18n


@pytest.fixture(autouse=True)
def _zh():
    """锁定中文。"""
    i18n.set_language("zh")


def _make_action_graph(n_actions: int, loop: bool = True, loop_count: int = 0) -> FlowGraph:
    """线性 START → a0 → ... → aN → END。"""
    g = FlowGraph(name="t", start_node_id="start", loop=loop, loop_count=loop_count)
    g.add_node(FlowNode("start", NodeType.START))
    g.add_node(FlowNode("end", NodeType.END))
    prev = "start"
    for i in range(n_actions):
        nid = f"a{i}"
        g.add_node(FlowNode(nid, NodeType.ACTION, action=SimpleNamespace()))
        g.add_edge(FlowEdge(edge_id=f"e{i}", from_node=prev, to_node=nid, label="default"))
        prev = nid
    g.add_edge(FlowEdge(edge_id="eend", from_node=prev, to_node="end", label="default"))
    return g


class TestCountReachableActionNodes:
    def test_counts_actions(self) -> None:
        assert count_reachable_action_nodes(_make_action_graph(3)) == 3

    def test_excludes_start_end(self) -> None:
        assert count_reachable_action_nodes(_make_action_graph(0)) == 0

    def test_excludes_disabled(self) -> None:
        g = _make_action_graph(3)
        g.nodes["a1"].enabled = False
        assert count_reachable_action_nodes(g) == 2

    def test_excludes_action_without_step(self) -> None:
        g = _make_action_graph(2)
        g.nodes["a0"].action = None
        assert count_reachable_action_nodes(g) == 1


class TestBuildExecutionSegments:
    def test_infinite_loop(self) -> None:
        segs = build_execution_segments(
            completed_rounds=2, loop_count=0, is_loop=True,
            step_index=2, total_steps=3, elapsed_seconds=134.0,
        )
        assert segs.loop_text == "循环次数: 2/∞"
        assert segs.step_text == "当前步骤: 2/3"
        assert segs.time_text == "执行时间: 2分14秒"

    def test_finite_loop(self) -> None:
        segs = build_execution_segments(
            completed_rounds=3, loop_count=5, is_loop=True,
            step_index=1, total_steps=4, elapsed_seconds=45.0,
        )
        assert segs.loop_text == "循环次数: 3/5"

    def test_single_mode_total_is_one(self) -> None:
        segs = build_execution_segments(
            completed_rounds=0, loop_count=1, is_loop=False,
            step_index=-1, total_steps=3, elapsed_seconds=None,
        )
        assert segs.loop_text == "循环次数: 0/1"

    def test_step_one_based_no_plus_one(self) -> None:
        """回归守卫: step_index=1 应显示 1/3,不是 2/3。"""
        segs = build_execution_segments(
            completed_rounds=0, loop_count=0, is_loop=True,
            step_index=1, total_steps=3, elapsed_seconds=0.0,
        )
        assert segs.step_text == "当前步骤: 1/3"

    def test_step_negative_shows_dash(self) -> None:
        segs = build_execution_segments(
            completed_rounds=0, loop_count=0, is_loop=True,
            step_index=-1, total_steps=3, elapsed_seconds=0.0,
        )
        assert segs.step_text == "当前步骤: —/3"

    def test_elapsed_none_shows_dash(self) -> None:
        segs = build_execution_segments(
            completed_rounds=0, loop_count=0, is_loop=True,
            step_index=1, total_steps=3, elapsed_seconds=None,
        )
        assert segs.time_text == "执行时间: —"


class TestComposeExecutionStatus:
    def test_reads_executor_and_graph(self) -> None:
        graph = _make_action_graph(3, loop=True, loop_count=0)
        executor = SimpleNamespace(
            completed_rounds=2, current_step_index=2, elapsed_active=134.0,
        )
        segs = compose_execution_status(executor, graph)
        assert segs.loop_text == "循环次数: 2/∞"
        assert segs.step_text == "当前步骤: 2/3"
        assert segs.time_text == "执行时间: 2分14秒"

    def test_elapsed_none_propagates(self) -> None:
        graph = _make_action_graph(2)
        executor = SimpleNamespace(
            completed_rounds=0, current_step_index=-1, elapsed_active=None,
        )
        segs = compose_execution_status(executor, graph)
        assert segs.time_text == "执行时间: —"
        assert segs.step_text == "当前步骤: —/2"
