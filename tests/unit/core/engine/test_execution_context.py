"""ExecutionContext 单元测试 — 验证不可变性、便利方法和 replace 语义。"""

from __future__ import annotations

import threading
from dataclasses import replace
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.core.engine.execution_context import ExecutionContext
from src.core.flow import FlowGraph, FlowNode, NodeType


# ---- 固定桩 ----


def _make_node(node_id: str = "n1") -> FlowNode:
    return FlowNode(node_id=node_id, node_type=NodeType.ACTION)


def _make_context(**overrides: Any) -> ExecutionContext:
    defaults = {
        "graph": MagicMock(spec=FlowGraph),
        "current_node": _make_node(),
        "variables": MagicMock(),
        "capture": MagicMock(),
        "matcher": MagicMock(),
        "input_ctrl": MagicMock(),
        "event_bus": MagicMock(),
        "gen": 1,
        "stop_event": threading.Event(),
        "pause_event": threading.Event(),
    }
    defaults.update(overrides)
    return ExecutionContext(**defaults)


# ---- 不可变性测试 ----


class TestImmutability:
    """验证 frozen=True 生效。"""

    def test_cannot_reassign_graph(self) -> None:
        ctx = _make_context()
        with pytest.raises(AttributeError):
            ctx.graph = MagicMock()  # type: ignore[misc]

    def test_cannot_reassign_step_index(self) -> None:
        ctx = _make_context()
        with pytest.raises(AttributeError):
            ctx.step_index = 99  # type: ignore[misc]

    def test_cannot_reassign_gen(self) -> None:
        ctx = _make_context()
        with pytest.raises(AttributeError):
            ctx.gen = 42  # type: ignore[misc]

    def test_cannot_add_new_attribute(self) -> None:
        ctx = _make_context()
        with pytest.raises(AttributeError):
            ctx.new_field = "oops"  # type: ignore[attr-defined]


# ---- 字段默认值测试 ----


class TestDefaults:
    """验证字段的默认值。"""

    def test_step_index_default(self) -> None:
        ctx = _make_context()
        assert ctx.step_index == 0

    def test_loop_counts_default_empty(self) -> None:
        ctx = _make_context()
        assert ctx.loop_counts == {}

    def test_extra_default_empty(self) -> None:
        ctx = _make_context()
        assert ctx.extra == {}


# ---- 便利属性测试 ----


class TestConvenienceProperties:
    """is_stopping / is_paused 代理到 threading.Event。"""

    def test_is_stopping_false_by_default(self) -> None:
        ctx = _make_context()
        assert ctx.is_stopping is False

    def test_is_stopping_true_when_set(self) -> None:
        stop = threading.Event()
        stop.set()
        ctx = _make_context(stop_event=stop)
        assert ctx.is_stopping is True

    def test_is_paused_false_by_default(self) -> None:
        ctx = _make_context()
        assert ctx.is_paused is False

    def test_is_paused_true_when_set(self) -> None:
        pause = threading.Event()
        pause.set()
        ctx = _make_context(pause_event=pause)
        assert ctx.is_paused is True


# ---- with_node 测试 ----


class TestWithNode:
    """with_node 创建新上下文，原始不变。"""

    def test_returns_new_instance(self) -> None:
        ctx = _make_context()
        new_node = _make_node("n2")
        updated = ctx.with_node(new_node)
        assert updated is not ctx

    def test_updates_current_node(self) -> None:
        ctx = _make_context()
        new_node = _make_node("n2")
        updated = ctx.with_node(new_node)
        assert updated.current_node is new_node

    def test_increments_step_index(self) -> None:
        ctx = _make_context(step_index=5)
        updated = ctx.with_node(_make_node("n2"))
        assert updated.step_index == 6

    def test_original_unchanged(self) -> None:
        original_node = _make_node("n1")
        ctx = _make_context(current_node=original_node, step_index=0)
        ctx.with_node(_make_node("n2"))
        assert ctx.current_node is original_node
        assert ctx.step_index == 0

    def test_preserves_other_fields(self) -> None:
        ctx = _make_context(gen=7)
        updated = ctx.with_node(_make_node("n2"))
        assert updated.gen == 7


# ---- with_loop_count 测试 ----


class TestWithLoopCount:
    """with_loop_count 不可变更新循环计数。"""

    def test_adds_new_count(self) -> None:
        ctx = _make_context()
        updated = ctx.with_loop_count("loop1", 3)
        assert updated.loop_counts == {"loop1": 3}

    def test_updates_existing_count(self) -> None:
        ctx = _make_context(loop_counts={"loop1": 2})
        updated = ctx.with_loop_count("loop1", 5)
        assert updated.loop_counts == {"loop1": 5}

    def test_preserves_other_counts(self) -> None:
        ctx = _make_context(loop_counts={"loop1": 2, "loop2": 4})
        updated = ctx.with_loop_count("loop1", 3)
        assert updated.loop_counts == {"loop1": 3, "loop2": 4}

    def test_original_unchanged(self) -> None:
        ctx = _make_context(loop_counts={"loop1": 1})
        ctx.with_loop_count("loop1", 99)
        assert ctx.loop_counts == {"loop1": 1}

    def test_returns_new_instance(self) -> None:
        ctx = _make_context()
        updated = ctx.with_loop_count("x", 1)
        assert updated is not ctx


# ---- get_loop_count 测试 ----


class TestGetLoopCount:
    """get_loop_count 返回计数或 0。"""

    def test_existing_count(self) -> None:
        ctx = _make_context(loop_counts={"loop1": 7})
        assert ctx.get_loop_count("loop1") == 7

    def test_missing_returns_zero(self) -> None:
        ctx = _make_context(loop_counts={})
        assert ctx.get_loop_count("nonexistent") == 0


# ---- dataclasses.replace 兼容性 ----


class TestReplace:
    """验证标准 dataclasses.replace 可用于创建新上下文。"""

    def test_replace_step_index(self) -> None:
        ctx = _make_context(step_index=0)
        updated = replace(ctx, step_index=10)
        assert updated.step_index == 10
        assert ctx.step_index == 0

    def test_replace_multiple_fields(self) -> None:
        ctx = _make_context(gen=1, step_index=0)
        updated = replace(ctx, gen=2, step_index=5)
        assert updated.gen == 2
        assert updated.step_index == 5

    def test_replace_preserves_unmodified(self) -> None:
        variables = MagicMock()
        ctx = _make_context(variables=variables, gen=1)
        updated = replace(ctx, step_index=1)
        assert updated.variables is variables
        assert updated.gen == 1


# ---- extra 字段测试 ----


class TestExtraField:
    """extra 字段存储扩展数据。"""

    def test_extra_with_values(self) -> None:
        ctx = _make_context(extra={"retry_count": 3, "region": (0, 0, 100, 100)})
        assert ctx.extra["retry_count"] == 3
        assert ctx.extra["region"] == (0, 0, 100, 100)

    def test_extra_preserved_on_replace(self) -> None:
        ctx = _make_context(extra={"k": "v"})
        updated = replace(ctx, step_index=1)
        assert updated.extra == {"k": "v"}


# ---- 所有字段存在性测试 ----


class TestAllFields:
    """验证所有必需字段在构造时提供。"""

    def test_missing_required_field_raises(self) -> None:
        with pytest.raises(TypeError):
            ExecutionContext()  # type: ignore[call-arg]

    def test_all_fields_accessible(self) -> None:
        stop = threading.Event()
        pause = threading.Event()
        variables = MagicMock()
        ctx = _make_context(
            graph=MagicMock(),
            current_node=_make_node(),
            variables=variables,
            capture=MagicMock(),
            matcher=MagicMock(),
            input_ctrl=MagicMock(),
            event_bus=MagicMock(),
            gen=42,
            stop_event=stop,
            pause_event=pause,
            step_index=5,
            loop_counts={"a": 1},
            extra={"k": "v"},
        )
        assert ctx.gen == 42
        assert ctx.step_index == 5
        assert ctx.stop_event is stop
        assert ctx.pause_event is pause
        assert ctx.variables is variables
