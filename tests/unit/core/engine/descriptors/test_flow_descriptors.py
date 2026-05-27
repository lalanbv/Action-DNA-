"""StartDescriptor + EndDescriptor + MergeDescriptor + LoopDescriptor 单元测试。

验证流程控制节点的元数据、执行逻辑和循环计数管理。
LoopDescriptor 测试覆盖：有限循环退出、无限循环继续、首次迭代。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.engine.descriptors.flow_descriptors import (
    EndDescriptor,
    LoopDescriptor,
    MergeDescriptor,
    StartDescriptor,
)
from src.core.engine.node_result import NodeResult

from .conftest import _FakeFlowNode, _make_ctx as _base_make_ctx


# ---- Fixtures ----


def _make_ctx(
    *,
    node_id: str = "test_node",
    loop_count: int = 0,
    existing_counts: dict[str, int] | None = None,
) -> MagicMock:
    """构建模拟 ExecutionContext。"""
    ctx = _base_make_ctx(node_id=node_id, loop_count=loop_count)
    ctx.loop_counts = dict(existing_counts) if existing_counts else {}

    def _get_loop_count(nid: str) -> int:
        return ctx.loop_counts.get(nid, 0)

    def _with_loop_count(nid: str, count: int) -> MagicMock:
        ctx.loop_counts[nid] = count
        return ctx

    ctx.get_loop_count = _get_loop_count
    ctx.with_loop_count = _with_loop_count

    return ctx


# ---- StartDescriptor 测试 ----


class TestStartDescriptor:
    def test_action_type(self) -> None:
        assert StartDescriptor.action_type() == "START"

    def test_display_name(self) -> None:
        assert StartDescriptor.display_name() == "开始"

    def test_category(self) -> None:
        assert StartDescriptor.category() == "流程控制"

    def test_input_types_empty(self) -> None:
        assert StartDescriptor.input_types() == {}

    def test_output_types_empty(self) -> None:
        assert StartDescriptor.output_types() == {}

    def test_execute_returns_success(self) -> None:
        ctx = _make_ctx()
        result = StartDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success
        assert result.next_label is None
        assert result.error is None

    def test_metadata_consistency(self) -> None:
        desc = StartDescriptor()
        assert desc.action_type() == "START"
        assert desc.display_name() == "开始"
        assert desc.category() == "流程控制"


# ---- EndDescriptor 测试 ----


class TestEndDescriptor:
    def test_action_type(self) -> None:
        assert EndDescriptor.action_type() == "END"

    def test_display_name(self) -> None:
        assert EndDescriptor.display_name() == "结束"

    def test_category(self) -> None:
        assert EndDescriptor.category() == "流程控制"

    def test_input_types_empty(self) -> None:
        assert EndDescriptor.input_types() == {}

    def test_output_types_empty(self) -> None:
        assert EndDescriptor.output_types() == {}

    def test_execute_returns_success(self) -> None:
        ctx = _make_ctx()
        result = EndDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success
        assert result.next_label is None
        assert result.error is None

    def test_metadata_consistency(self) -> None:
        desc = EndDescriptor()
        assert desc.action_type() == "END"
        assert desc.display_name() == "结束"
        assert desc.category() == "流程控制"


# ---- MergeDescriptor 测试 ----


class TestMergeDescriptor:
    def test_action_type(self) -> None:
        assert MergeDescriptor.action_type() == "MERGE"

    def test_display_name(self) -> None:
        assert MergeDescriptor.display_name() == "汇合"

    def test_category(self) -> None:
        assert MergeDescriptor.category() == "流程控制"

    def test_input_types_empty(self) -> None:
        assert MergeDescriptor.input_types() == {}

    def test_output_types_empty(self) -> None:
        assert MergeDescriptor.output_types() == {}

    def test_execute_returns_success(self) -> None:
        ctx = _make_ctx()
        result = MergeDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success
        assert result.next_label is None
        assert result.error is None

    def test_metadata_consistency(self) -> None:
        desc = MergeDescriptor()
        assert desc.action_type() == "MERGE"
        assert desc.display_name() == "汇合"
        assert desc.category() == "流程控制"


# ---- LoopDescriptor 测试 ----


class TestLoopDescriptor:
    def test_action_type(self) -> None:
        assert LoopDescriptor.action_type() == "LOOP"

    def test_display_name(self) -> None:
        assert LoopDescriptor.display_name() == "循环"

    def test_category(self) -> None:
        assert LoopDescriptor.category() == "流程控制"

    def test_input_types(self) -> None:
        inputs = LoopDescriptor.input_types()
        assert "loop_count" in inputs
        assert inputs["loop_count"].required is False
        assert inputs["loop_count"].default == 0

    def test_output_types(self) -> None:
        outputs = LoopDescriptor.output_types()
        assert "current_iteration" in outputs

    def test_metadata_consistency(self) -> None:
        desc = LoopDescriptor()
        assert desc.action_type() == "LOOP"
        assert desc.display_name() == "循环"
        assert desc.category() == "流程控制"

    # -- 无限循环（loop_count=0）--

    def test_infinite_loop_continues(self) -> None:
        ctx = _make_ctx(loop_count=0)

        result = LoopDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success
        assert result.next_label == "loop"

    def test_infinite_loop_iter_5(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=0, existing_counts={"loop_1": 4})

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.next_label == "loop"
        assert result.output_vars["current_iteration"] == 5

    # -- 有限循环 --

    def test_limited_loop_first_iteration(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=3)

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.next_label == "loop"
        assert result.output_vars["current_iteration"] == 1

    def test_limited_loop_mid_iteration(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=3, existing_counts={"loop_1": 1})

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.next_label == "loop"
        assert result.output_vars["current_iteration"] == 2

    def test_limited_loop_third_iteration_still_loops(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=3, existing_counts={"loop_1": 2})

        result = LoopDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success
        assert result.next_label == "loop"
        assert result.output_vars["current_iteration"] == 3

    def test_limited_loop_exits_after_count(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=3, existing_counts={"loop_1": 3})

        result = LoopDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert not result.success
        assert result.next_label == "exit"
        assert result.output_vars["current_iteration"] == 4

    def test_limited_loop_count_1_loops_once(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=1)

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.next_label == "loop"
        assert result.output_vars["current_iteration"] == 1

    def test_limited_loop_count_1_exits_after_one(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=1, existing_counts={"loop_1": 1})

        result = LoopDescriptor().execute(ctx)

        assert not result.success
        assert result.next_label == "exit"

    def test_limited_loop_already_exceeded(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=3, existing_counts={"loop_1": 5})

        result = LoopDescriptor().execute(ctx)

        assert not result.success
        assert result.next_label == "exit"

    # -- 循环计数更新 --

    def test_loop_count_updates_context(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=5)

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.output_vars["_loop_node_id"] == "loop_1"
        assert result.output_vars["_loop_count"] == 1

    def test_loop_count_increments(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=5, existing_counts={"loop_1": 2})

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.output_vars["_loop_node_id"] == "loop_1"
        assert result.output_vars["_loop_count"] == 3

    # -- 多循环节点隔离 --

    def test_multiple_loop_nodes_isolated(self) -> None:
        ctx = _make_ctx(node_id="loop_B", loop_count=0, existing_counts={"loop_A": 10})

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.output_vars["current_iteration"] == 1
        assert result.output_vars["_loop_node_id"] == "loop_B"
        assert result.output_vars["_loop_count"] == 1

    # -- 边界值 --

    def test_negative_loop_count_treated_as_infinite(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=-1)

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.next_label == "loop"

    def test_exit_still_writes_loop_count(self) -> None:
        ctx = _make_ctx(node_id="loop_1", loop_count=1, existing_counts={"loop_1": 1})

        result = LoopDescriptor().execute(ctx)

        assert not result.success
        assert result.output_vars["_loop_node_id"] == "loop_1"
        assert result.output_vars["_loop_count"] == 2


# ---- D18 边界条件补充 ----


class TestLoopDescriptorBoundary:
    """LoopDescriptor 额外边界条件。"""

    def test_very_large_loop_count(self) -> None:
        """极大循环次数应在首次迭代继续。"""
        ctx = _make_ctx(node_id="loop_1", loop_count=999999)

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.next_label == "loop"
        assert result.output_vars["current_iteration"] == 1

    def test_zero_loop_count_is_infinite(self) -> None:
        """loop_count=0 明确视为无限循环。"""
        ctx = _make_ctx(node_id="loop_1", loop_count=0)

        result = LoopDescriptor().execute(ctx)

        assert result.success
        assert result.next_label == "loop"
