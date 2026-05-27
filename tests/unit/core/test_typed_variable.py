"""TypedVariable 测试 — 引用解析、嵌套引用、循环检测。"""

import pytest

from src.core.variables.types import VariableType
from src.core.variables.scope import VariableScope
from src.core.variables.pool import VariablePool, _VarEntry
from src.core.variables.typed_variable import TypedVariable


# ============================================================
# 字面值模式
# ============================================================


class TestLiteralMode:
    """字面值模式：直接存储值。"""

    def test_literal_resolve_returns_value(self):
        var = TypedVariable(
            var_type=VariableType.INT,
            name="count",
            _literal_value=42,
        )
        pool = VariablePool()
        assert var.resolve(pool) == 42

    def test_literal_is_literal_true(self):
        var = TypedVariable(var_type=VariableType.STR, _literal_value="hello")
        assert var.is_literal is True

    def test_literal_is_reference_false(self):
        var = TypedVariable(var_type=VariableType.STR, _literal_value="hello")
        assert var.is_reference is False

    def test_literal_default_none(self):
        var = TypedVariable(var_type=VariableType.INT)
        pool = VariablePool()
        assert var.resolve(pool) is None

    def test_literal_coord_value(self):
        var = TypedVariable(
            var_type=VariableType.COORD,
            name="pos",
            _literal_value=(100, 200),
        )
        pool = VariablePool()
        assert var.resolve(pool) == (100, 200)

    def test_literal_bool_value(self):
        var = TypedVariable(
            var_type=VariableType.BOOL,
            name="flag",
            _literal_value=True,
        )
        pool = VariablePool()
        assert var.resolve(pool) is True

    def test_literal_list_value(self):
        var = TypedVariable(
            var_type=VariableType.LIST,
            name="items",
            _literal_value=[1, 2, 3],
        )
        pool = VariablePool()
        assert var.resolve(pool) == [1, 2, 3]


# ============================================================
# 引用模式
# ============================================================


class TestReferenceMode:
    """引用模式：从 VariablePool 获取值。"""

    def test_reference_resolve_from_pool(self):
        pool = VariablePool()
        pool.declare("max_retries", VariableType.INT, initial_value=5)

        var = TypedVariable(
            var_type=VariableType.INT,
            name="retry_count",
            _reference_name="max_retries",
        )
        assert var.resolve(pool) == 5

    def test_reference_is_reference_true(self):
        var = TypedVariable(var_type=VariableType.INT, _reference_name="some_var")
        assert var.is_reference is True

    def test_reference_is_literal_false(self):
        var = TypedVariable(var_type=VariableType.INT, _reference_name="some_var")
        assert var.is_literal is False

    def test_reference_nonexistent_raises_key_error(self):
        pool = VariablePool()
        var = TypedVariable(
            var_type=VariableType.INT,
            _reference_name="nonexistent",
        )
        with pytest.raises(KeyError, match="nonexistent"):
            var.resolve(pool)

    def test_reference_returns_latest_value(self):
        pool = VariablePool()
        pool.declare("threshold", VariableType.FLOAT, initial_value=0.8)

        var = TypedVariable(
            var_type=VariableType.FLOAT,
            name="conf",
            _reference_name="threshold",
        )
        assert var.resolve(pool) == 0.8

        pool.set("threshold", 0.95)
        assert var.resolve(pool) == 0.95

    def test_reference_coord_value(self):
        pool = VariablePool()
        pool.declare("match_pos", VariableType.COORD, initial_value=(320, 480))

        var = TypedVariable(
            var_type=VariableType.COORD,
            name="click_target",
            _reference_name="match_pos",
        )
        assert var.resolve(pool) == (320, 480)

    def test_reference_respects_scope_priority(self):
        """引用模式下 pool.get 按作用域优先级查找。"""
        pool = VariablePool()
        pool.declare("x", VariableType.INT, VariableScope.GLOBAL, initial_value=1)
        pool.declare("x", VariableType.INT, VariableScope.NODE, initial_value=2)

        var = TypedVariable(var_type=VariableType.INT, _reference_name="x")
        assert var.resolve(pool) == 2


# ============================================================
# 模式切换 (不可变)
# ============================================================


class TestModeSwitching:
    """set_literal / set_reference 返回新对象，不修改原对象。"""

    def test_set_literal_returns_new_object(self):
        original = TypedVariable(
            var_type=VariableType.INT,
            name="val",
            _reference_name="some_ref",
        )
        updated = original.set_literal(42)

        assert original is not updated
        assert original.is_reference is True
        assert updated.is_literal is True
        assert updated.resolve(VariablePool()) == 42

    def test_set_reference_returns_new_object(self):
        original = TypedVariable(
            var_type=VariableType.FLOAT,
            name="conf",
            _literal_value=0.8,
        )
        updated = original.set_reference("dynamic_threshold")

        assert original is not updated
        assert original.is_literal is True
        assert updated.is_reference is True
        assert updated._reference_name == "dynamic_threshold"

    def test_set_literal_preserves_metadata(self):
        original = TypedVariable(
            var_type=VariableType.COORD,
            scope=VariableScope.NODE,
            name="pos",
            _literal_value=(0, 0),
        )
        updated = original.set_literal((100, 200))

        assert updated.var_type == VariableType.COORD
        assert updated.scope == VariableScope.NODE
        assert updated.name == "pos"

    def test_set_reference_preserves_metadata(self):
        original = TypedVariable(
            var_type=VariableType.STR,
            scope=VariableScope.STEP,
            name="label",
            _literal_value="old",
        )
        updated = original.set_reference("dynamic_label")

        assert updated.var_type == VariableType.STR
        assert updated.scope == VariableScope.STEP
        assert updated.name == "label"

    def test_set_literal_clears_reference(self):
        var = TypedVariable(var_type=VariableType.INT, _reference_name="ref")
        updated = var.set_literal(10)
        assert updated._reference_name is None
        assert updated._literal_value == 10

    def test_set_reference_clears_literal(self):
        var = TypedVariable(var_type=VariableType.INT, _literal_value=10)
        updated = var.set_reference("new_ref")
        assert updated._literal_value is None
        assert updated._reference_name == "new_ref"

    def test_chain_mode_switching(self):
        """连续切换模式，每次都是新对象。"""
        var = TypedVariable(var_type=VariableType.INT, _literal_value=1)
        var = var.set_reference("x")
        var = var.set_literal(2)
        var = var.set_reference("y")

        pool = VariablePool()
        pool.declare("y", VariableType.INT, initial_value=99)
        assert var.is_reference is True
        assert var.resolve(pool) == 99


# ============================================================
# 循环引用检测
# ============================================================


class TestCircularDetection:
    """检测引用链中的循环。"""

    def test_self_reference_detected(self):
        """TypedVariable 引用自身名称应触发循环检测。"""
        pool = VariablePool()

        inner = TypedVariable(
            var_type=VariableType.INT,
            name="loop_var",
            _reference_name="loop_var",
        )
        pool.declare("loop_var", VariableType.INT, initial_value=0)
        pool._scopes[VariableScope.GLOBAL]["loop_var"] = _VarEntry(
            var_type=VariableType.INT,
            scope=VariableScope.GLOBAL,
            value=inner,
        )

        outer = TypedVariable(var_type=VariableType.INT, _reference_name="loop_var")
        with pytest.raises(ValueError, match="循环引用"):
            outer.resolve(pool)

    def test_indirect_cycle_detected(self):
        """A → B → A 间接循环检测。"""
        pool = VariablePool()

        a_ref = TypedVariable(
            var_type=VariableType.INT, name="a", _reference_name="b",
        )
        b_ref = TypedVariable(
            var_type=VariableType.INT, name="b", _reference_name="a",
        )

        pool.declare("a", VariableType.INT, initial_value=0)
        pool.declare("b", VariableType.INT, initial_value=0)

        pool._scopes[VariableScope.GLOBAL]["a"] = _VarEntry(
            var_type=VariableType.INT, scope=VariableScope.GLOBAL, value=a_ref,
        )
        pool._scopes[VariableScope.GLOBAL]["b"] = _VarEntry(
            var_type=VariableType.INT, scope=VariableScope.GLOBAL, value=b_ref,
        )

        outer = TypedVariable(var_type=VariableType.INT, _reference_name="a")
        with pytest.raises(ValueError, match="循环引用"):
            outer.resolve(pool)

    def test_no_false_positive_on_valid_chain(self):
        """不同变量引用同一目标不应触发循环检测。"""
        pool = VariablePool()
        pool.declare("shared", VariableType.INT, initial_value=42)

        var_a = TypedVariable(var_type=VariableType.INT, _reference_name="shared")
        var_b = TypedVariable(var_type=VariableType.INT, _reference_name="shared")

        assert var_a.resolve(pool) == 42
        assert var_b.resolve(pool) == 42


# ============================================================
# 嵌套引用
# ============================================================


class TestNestedReference:
    """嵌套引用：引用链的深度解析。"""

    def test_reference_chain_depth_2(self):
        """A 引用 B，B 引用 C，C 为字面值 → 解析到 C 的值。"""
        pool = VariablePool()
        pool.declare("c", VariableType.INT, initial_value=99)

        b_ref = TypedVariable(
            var_type=VariableType.INT, name="b", _reference_name="c",
        )
        pool.declare("b", VariableType.INT, initial_value=0)
        pool._scopes[VariableScope.GLOBAL]["b"] = _VarEntry(
            var_type=VariableType.INT, scope=VariableScope.GLOBAL, value=b_ref,
        )

        a = TypedVariable(var_type=VariableType.INT, _reference_name="b")
        assert a.resolve(pool) == 99

    def test_reference_chain_depth_3(self):
        """A → B → C → D(字面值)。"""
        pool = VariablePool()
        pool.declare("d", VariableType.FLOAT, initial_value=1.5)

        c_ref = TypedVariable(
            var_type=VariableType.FLOAT, name="c", _reference_name="d",
        )
        pool.declare("c", VariableType.FLOAT, initial_value=0.0)
        pool._scopes[VariableScope.GLOBAL]["c"] = _VarEntry(
            var_type=VariableType.FLOAT, scope=VariableScope.GLOBAL, value=c_ref,
        )

        b_ref = TypedVariable(
            var_type=VariableType.FLOAT, name="b", _reference_name="c",
        )
        pool.declare("b", VariableType.FLOAT, initial_value=0.0)
        pool._scopes[VariableScope.GLOBAL]["b"] = _VarEntry(
            var_type=VariableType.FLOAT, scope=VariableScope.GLOBAL, value=b_ref,
        )

        a = TypedVariable(var_type=VariableType.FLOAT, _reference_name="b")
        assert a.resolve(pool) == 1.5


# ============================================================
# 类型验证
# ============================================================


class TestValidation:
    """validate_value 委托给 VariableType.validate。"""

    def test_validate_correct_type(self):
        var = TypedVariable(var_type=VariableType.INT)
        assert var.validate_value(42) is True

    def test_validate_wrong_type(self):
        var = TypedVariable(var_type=VariableType.INT)
        assert var.validate_value("not an int") is False

    def test_validate_none_always_valid(self):
        var = TypedVariable(var_type=VariableType.INT)
        assert var.validate_value(None) is True

    def test_validate_coord(self):
        var = TypedVariable(var_type=VariableType.COORD)
        assert var.validate_value((100, 200)) is True
        assert var.validate_value((100, 200, 300)) is False

    def test_validate_bool_not_int(self):
        var = TypedVariable(var_type=VariableType.INT)
        assert var.validate_value(True) is False


# ============================================================
# repr
# ============================================================


class TestRepr:
    def test_literal_repr(self):
        var = TypedVariable(
            var_type=VariableType.INT, name="count", _literal_value=42,
        )
        r = repr(var)
        assert "int" in r
        assert "42" in r
        assert "count" in r

    def test_literal_repr_no_name(self):
        var = TypedVariable(var_type=VariableType.INT, _literal_value=42)
        r = repr(var)
        assert "name=" not in r

    def test_reference_repr(self):
        var = TypedVariable(
            var_type=VariableType.INT, name="val", _reference_name="my_var",
        )
        r = repr(var)
        assert "int" in r
        assert "ref=" in r
        assert "my_var" in r
        assert "val" in r

    def test_reference_repr_no_literal_leak(self):
        """引用模式的 repr 不应暴露 literal 值。"""
        var = TypedVariable(
            var_type=VariableType.INT,
            _literal_value=999,
            _reference_name="ref",
        )
        r = repr(var)
        assert "999" not in r
        assert "ref=" in r
