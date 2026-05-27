"""NodeResult 单元测试 — 验证字段、工厂方法和默认值。"""

from __future__ import annotations

import dataclasses
from dataclasses import replace

import pytest

from src.core.engine.node_result import NodeResult


# ---- 直接构造测试 ----


class TestConstruction:
    """验证直接构造。"""

    def test_success_required(self) -> None:
        with pytest.raises(TypeError):
            NodeResult()  # type: ignore[call-arg]

    def test_success_true(self) -> None:
        r = NodeResult(success=True)
        assert r.success is True

    def test_success_false(self) -> None:
        r = NodeResult(success=False)
        assert r.success is False


# ---- 默认值测试 ----


class TestDefaults:
    """验证字段的默认值。"""

    def test_output_vars_default_empty(self) -> None:
        r = NodeResult(success=True)
        assert r.output_vars == {}

    def test_next_label_default_none(self) -> None:
        r = NodeResult(success=True)
        assert r.next_label is None

    def test_error_default_none(self) -> None:
        r = NodeResult(success=True)
        assert r.error is None

    def test_cooldown_default_zero(self) -> None:
        r = NodeResult(success=True)
        assert r.cooldown == 0.0


# ---- 字段赋值测试 ----


class TestFieldAssignment:
    """验证所有字段可正确赋值。"""

    def test_output_vars(self) -> None:
        r = NodeResult(success=True, output_vars={"x": 1, "y": "hello"})
        assert r.output_vars == {"x": 1, "y": "hello"}

    def test_next_label(self) -> None:
        r = NodeResult(success=True, next_label="true_branch")
        assert r.next_label == "true_branch"

    def test_error_with_exception(self) -> None:
        err = ValueError("boom")
        r = NodeResult(success=False, error=err)
        assert r.error is err

    def test_cooldown(self) -> None:
        r = NodeResult(success=True, cooldown=2.5)
        assert r.cooldown == 2.5

    def test_all_fields_together(self) -> None:
        err = RuntimeError("test")
        r = NodeResult(
            success=False,
            output_vars={"k": "v"},
            next_label="retry",
            error=err,
            cooldown=1.5,
        )
        assert r.success is False
        assert r.output_vars == {"k": "v"}
        assert r.next_label == "retry"
        assert r.error is err
        assert r.cooldown == 1.5


# ---- ok() 工厂方法 ----


class TestOkFactory:
    """验证 ok() 创建成功结果。"""

    def test_basic_ok(self) -> None:
        r = NodeResult.ok()
        assert r.success is True
        assert r.output_vars == {}
        assert r.error is None

    def test_ok_with_output_vars(self) -> None:
        r = NodeResult.ok(found=True, confidence=0.95)
        assert r.success is True
        assert r.output_vars == {"found": True, "confidence": 0.95}

    def test_ok_no_error(self) -> None:
        r = NodeResult.ok()
        assert r.error is None

    def test_ok_no_next_label(self) -> None:
        r = NodeResult.ok()
        assert r.next_label is None

    def test_ok_rejects_field_name_clash(self) -> None:
        with pytest.raises(ValueError, match="clash with fields"):
            NodeResult.ok(cooldown=5.0)

    def test_ok_rejects_success_as_kwarg(self) -> None:
        with pytest.raises(ValueError, match="clash with fields"):
            NodeResult.ok(success=False)


# ---- fail() 工厂方法 ----


class TestFailFactory:
    """验证 fail() 创建失败结果。"""

    def test_fail_with_exception(self) -> None:
        err = ValueError("bad input")
        r = NodeResult.fail(err)
        assert r.success is False
        assert r.error is err

    def test_fail_with_string(self) -> None:
        r = NodeResult.fail("something went wrong")
        assert r.success is False
        assert isinstance(r.error, RuntimeError)
        assert "something went wrong" in str(r.error)

    def test_fail_default_output_vars(self) -> None:
        r = NodeResult.fail("err")
        assert r.output_vars == {}

    def test_fail_no_next_label(self) -> None:
        r = NodeResult.fail("err")
        assert r.next_label is None

    def test_fail_cooldown_zero(self) -> None:
        r = NodeResult.fail("err")
        assert r.cooldown == 0.0

    def test_fail_with_empty_string(self) -> None:
        r = NodeResult.fail("")
        assert isinstance(r.error, RuntimeError)


# ---- branch() 工厂方法 ----


class TestBranchFactory:
    """验证 branch() 创建分支结果。"""

    def test_branch_default_success(self) -> None:
        r = NodeResult.branch("true")
        assert r.success is True
        assert r.next_label == "true"

    def test_branch_explicit_failure(self) -> None:
        r = NodeResult.branch("false", success=False)
        assert r.success is False
        assert r.next_label == "false"

    def test_branch_no_output_vars(self) -> None:
        r = NodeResult.branch("loop_end")
        assert r.output_vars == {}

    def test_branch_no_error(self) -> None:
        r = NodeResult.branch("label")
        assert r.error is None

    def test_branch_rejects_empty_label(self) -> None:
        with pytest.raises(ValueError, match="non-empty string"):
            NodeResult.branch("")


# ---- 不可变性测试（frozen） ----


class TestImmutability:
    """验证 NodeResult 不可变（frozen），Layer 通过替换而非修改。"""

    def test_negative_cooldown_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-negative"):
            NodeResult(success=True, cooldown=-1.0)

    def test_cannot_reassign_cooldown(self) -> None:
        r = NodeResult(success=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.cooldown = 3.0  # type: ignore[misc]

    def test_cannot_reassign_next_label(self) -> None:
        r = NodeResult(success=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.next_label = "retry"  # type: ignore[misc]

    def test_cannot_reassign_output_vars(self) -> None:
        r = NodeResult(success=True)
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.output_vars = {"x": 1}  # type: ignore[misc]


# ---- dataclasses.replace 兼容性 ----


class TestReplace:
    """验证标准 dataclasses.replace 可用于创建新实例。"""

    def test_replace_cooldown(self) -> None:
        r = NodeResult.ok()
        updated = replace(r, cooldown=5.0)
        assert updated.cooldown == 5.0
        assert r.cooldown == 0.0

    def test_replace_next_label(self) -> None:
        r = NodeResult.ok()
        updated = replace(r, next_label="retry")
        assert updated.next_label == "retry"
        assert r.next_label is None

    def test_replace_preserves_success(self) -> None:
        r = NodeResult.fail("err")
        updated = replace(r, cooldown=1.0)
        assert updated.success is False
        assert updated.error is r.error

    def test_replace_multiple_fields(self) -> None:
        r = NodeResult.ok()
        updated = replace(r, cooldown=2.0, next_label="branch_a")
        assert updated.cooldown == 2.0
        assert updated.next_label == "branch_a"
        assert updated.success is True


# ---- output_vars 独立性测试 ----


class TestOutputVarsIsolation:
    """验证不同实例的 output_vars 互不影响（default_factory 生效）。"""

    def test_independent_output_vars(self) -> None:
        r1 = NodeResult(success=True)
        r2 = NodeResult(success=True)
        r1.output_vars["key"] = "value"
        assert "key" not in r2.output_vars
