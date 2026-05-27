"""DNAError / GraphExecutionError / NodeExecutionError 单元测试。"""

from __future__ import annotations

import pytest

from src.core.error.exceptions import (
    DNAError,
    GraphExecutionError,
    NodeExecutionError,
)


# ---- DNAError ----


class TestDNAError:
    """基础异常类。"""

    def test_message_stored(self) -> None:
        e = DNAError("test error")
        assert e.message == "test error"

    def test_str_returns_message(self) -> None:
        e = DNAError("hello")
        assert str(e) == "hello"

    def test_is_exception(self) -> None:
        assert isinstance(DNAError("x"), Exception)

    def test_raise_and_catch(self) -> None:
        with pytest.raises(DNAError, match="boom"):
            raise DNAError("boom")

    def test_catch_as_base_exception(self) -> None:
        with pytest.raises(Exception):
            raise DNAError("base catch")


# ---- GraphExecutionError ----


class TestGraphExecutionError:
    """图执行级错误。"""

    def test_inherits_dna_error(self) -> None:
        e = GraphExecutionError("fail")
        assert isinstance(e, DNAError)

    def test_default_fields(self) -> None:
        e = GraphExecutionError("err")
        assert e.graph_id == ""
        assert e.node_id is None

    def test_with_graph_id(self) -> None:
        e = GraphExecutionError("err", graph_id="g1")
        assert e.graph_id == "g1"

    def test_with_node_id(self) -> None:
        e = GraphExecutionError("err", graph_id="g1", node_id="n1")
        assert e.node_id == "n1"

    def test_str_returns_message(self) -> None:
        e = GraphExecutionError("graph failed")
        assert str(e) == "graph failed"

    def test_catch_by_dna_error(self) -> None:
        with pytest.raises(DNAError):
            raise GraphExecutionError("caught")


# ---- NodeExecutionError ----


class TestNodeExecutionError:
    """节点执行级错误。"""

    def test_inherits_dna_error(self) -> None:
        e = NodeExecutionError("fail", node_id="n1", node_type="CLICK")
        assert isinstance(e, DNAError)

    def test_required_fields(self) -> None:
        e = NodeExecutionError("fail", node_id="n1", node_type="CLICK")
        assert e.node_id == "n1"
        assert e.node_type == "CLICK"

    def test_default_optional_fields(self) -> None:
        e = NodeExecutionError("fail", node_id="n1", node_type="CLICK")
        assert e.step_index == -1
        assert e.retry_count == 0
        assert e.original_error is None

    def test_all_fields(self) -> None:
        original = ValueError("root cause")
        e = NodeExecutionError(
            "node fail",
            node_id="n2",
            node_type="WAIT",
            step_index=5,
            retry_count=3,
            original_error=original,
        )
        assert e.node_id == "n2"
        assert e.node_type == "WAIT"
        assert e.step_index == 5
        assert e.retry_count == 3
        assert e.original_error is original

    def test_str_returns_message(self) -> None:
        e = NodeExecutionError("node err", node_id="n1", node_type="LOOP")
        assert str(e) == "node err"

    def test_catch_by_dna_error(self) -> None:
        with pytest.raises(DNAError):
            raise NodeExecutionError("caught", node_id="n1", node_type="X")

    def test_catch_hierarchy(self) -> None:
        """GraphExecutionError 和 NodeExecutionError 都可被 DNAError 捕获。"""
        with pytest.raises(DNAError):
            raise NodeExecutionError("h", node_id="n1", node_type="X")
        with pytest.raises(DNAError):
            raise GraphExecutionError("h")
