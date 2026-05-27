"""ExecutionBlocker 单元测试 — 验证哨兵对象的构造、布尔语义、比较和哈希。"""

from __future__ import annotations

import pytest

from src.core.engine.execution_blocker import ExecutionBlocker


# ---- 构造测试 ----


class TestConstruction:
    """验证构造。"""

    def test_default_reason(self) -> None:
        b = ExecutionBlocker()
        assert b.reason == ""

    def test_custom_reason(self) -> None:
        b = ExecutionBlocker(reason="未找到模板")
        assert b.reason == "未找到模板"

    def test_empty_string_reason(self) -> None:
        b = ExecutionBlocker(reason="")
        assert b.reason == ""


# ---- repr 测试 ----


class TestRepr:
    """验证 __repr__。"""

    def test_repr_with_reason(self) -> None:
        b = ExecutionBlocker(reason="timeout")
        assert repr(b) == "ExecutionBlocker(reason='timeout')"

    def test_repr_empty_reason(self) -> None:
        b = ExecutionBlocker()
        assert repr(b) == "ExecutionBlocker(reason='')"

    def test_repr_with_single_quote(self) -> None:
        b = ExecutionBlocker(reason="it's broken")
        assert repr(b) == 'ExecutionBlocker(reason="it\'s broken")'


# ---- 布尔语义测试 ----


class TestBool:
    """验证 __bool__ 始终为 False。"""

    def test_bool_is_false(self) -> None:
        b = ExecutionBlocker()
        assert bool(b) is False

    def test_not_is_true(self) -> None:
        b = ExecutionBlocker()
        assert not b

    def test_if_not_pattern(self) -> None:
        b = ExecutionBlocker(reason="skip")
        blocked = True
        if not b:
            blocked = False
        assert blocked is False

    def test_with_reason_still_false(self) -> None:
        b = ExecutionBlocker(reason="有原因也是False")
        assert bool(b) is False


# ---- 相等比较测试 ----


class TestEquality:
    """验证 __eq__。"""

    def test_same_reason_equal(self) -> None:
        a = ExecutionBlocker(reason="x")
        b = ExecutionBlocker(reason="x")
        assert a == b

    def test_different_reason_not_equal(self) -> None:
        a = ExecutionBlocker(reason="x")
        b = ExecutionBlocker(reason="y")
        assert a != b

    def test_both_empty_equal(self) -> None:
        a = ExecutionBlocker()
        b = ExecutionBlocker()
        assert a == b

    def test_not_equal_to_other_types(self) -> None:
        b = ExecutionBlocker(reason="x")
        assert b != "x"
        assert b != 42

    def test_not_equal_to_none(self) -> None:
        b = ExecutionBlocker()
        assert b is not None
        assert b != None  # noqa: E711


# ---- 哈希测试 ----


class TestHash:
    """验证 __hash__ 支持集合和字典。"""

    def test_same_reason_same_hash(self) -> None:
        a = ExecutionBlocker(reason="skip")
        b = ExecutionBlocker(reason="skip")
        assert hash(a) == hash(b)

    def test_different_reason_different_hash(self) -> None:
        a = ExecutionBlocker(reason="a")
        b = ExecutionBlocker(reason="b")
        assert hash(a) != hash(b)

    def test_usable_in_set(self) -> None:
        s = {ExecutionBlocker(reason="a"), ExecutionBlocker(reason="a")}
        assert len(s) == 1

    def test_usable_in_dict_key(self) -> None:
        d = {ExecutionBlocker(reason="x"): 1}
        assert d[ExecutionBlocker(reason="x")] == 1


# ---- 不可变性测试 ----


class TestImmutability:
    """验证 reason 只读。"""

    def test_cannot_set_arbitrary_attribute(self) -> None:
        b = ExecutionBlocker()
        with pytest.raises(AttributeError):
            b.nonexistent = 42  # type: ignore[attr-defined]

    def test_reason_is_readonly(self) -> None:
        b = ExecutionBlocker(reason="old")
        with pytest.raises(AttributeError):
            b.reason = "new"  # type: ignore[misc]


# ---- 类型区分测试 ----


class TestTypeIdentity:
    """验证 ExecutionBlocker 与其他类型的区分。"""

    def test_isinstance_check(self) -> None:
        b = ExecutionBlocker()
        assert isinstance(b, ExecutionBlocker)

    def test_not_other_type(self) -> None:
        class Dummy:
            pass

        assert not isinstance(Dummy(), ExecutionBlocker)

    def test_not_none(self) -> None:
        b = ExecutionBlocker()
        assert b is not None

    def test_engine_pattern_isinstance(self) -> None:
        """模拟引擎中的 isinstance 检测模式。"""
        results: list[object] = [
            ExecutionBlocker(reason="skip"),
            "not a blocker",
            None,
        ]
        blocked = [r for r in results if isinstance(r, ExecutionBlocker)]
        assert len(blocked) == 1
        assert blocked[0].reason == "skip"
