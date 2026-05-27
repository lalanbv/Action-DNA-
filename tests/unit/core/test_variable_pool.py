"""VariablePool 类测试。"""

import threading
import time

import pytest

from src.core.variables.pool import VariablePool
from src.core.variables.types import VariableType
from src.core.variables.scope import VariableScope


# ---- declare / get / set 基础 CRUD ----


class TestDeclareAndGet:

    def test_declare_and_get(self, pool):
        pool.declare("pos", VariableType.COORD, initial_value=(100, 200))
        assert pool.get("pos") == (100, 200)

    def test_declare_default_value(self, pool):
        pool.declare("count", VariableType.INT)
        assert pool.get("count") == 0

    def test_declare_wrong_type_raises(self, pool):
        with pytest.raises(TypeError, match="不匹配类型"):
            pool.declare("bad", VariableType.INT, initial_value="not_int")

    def test_declare_overwrite_warns(self, pool):
        pool.declare("x", VariableType.INT, initial_value=1)
        pool.declare("x", VariableType.INT, initial_value=2)
        assert pool.get("x") == 2

    def test_declare_overwrite_type_change(self, pool):
        """覆盖声明时可改变类型（设计上允许，需谨慎使用）。"""
        pool.declare("x", VariableType.INT, initial_value=1)
        pool.declare("x", VariableType.STR, initial_value="hello")
        assert pool.get("x") == "hello"
        assert pool.get_type("x") == VariableType.STR


class TestSet:

    def test_set_updates_value(self, pool):
        pool.declare("pos", VariableType.COORD, initial_value=(0, 0))
        pool.set("pos", (320, 480))
        assert pool.get("pos") == (320, 480)

    def test_set_wrong_type_raises(self, pool):
        pool.declare("count", VariableType.INT, initial_value=0)
        with pytest.raises(TypeError, match="不匹配声明类型"):
            pool.set("count", "not_int")

    def test_set_auto_declare_infers_type(self, pool):
        pool.set("auto_var", 42)
        assert pool.get("auto_var") == 42
        assert pool.get_type("auto_var") == VariableType.INT

    def test_set_auto_declare_coord(self, pool):
        pool.set("pos", (100, 200))
        assert pool.get("pos") == (100, 200)
        assert pool.get_type("pos") == VariableType.COORD

    def test_set_auto_declare_bool(self, pool):
        pool.set("flag", True)
        assert pool.get("flag") is True
        assert pool.get_type("flag") == VariableType.BOOL


class TestTypeValidation:

    def test_float_accepts_int(self, pool):
        pool.declare("f", VariableType.FLOAT, initial_value=3.14)
        pool.set("f", 42)
        assert pool.get("f") == 42

    def test_int_rejects_bool(self, pool):
        with pytest.raises(TypeError):
            pool.declare("n", VariableType.INT, initial_value=True)

    def test_float_rejects_bool(self, pool):
        with pytest.raises(TypeError):
            pool.declare("f", VariableType.FLOAT, initial_value=False)

    def test_coord_rejects_bool_elements(self, pool):
        with pytest.raises(TypeError):
            pool.declare("c", VariableType.COORD, initial_value=(True, 200))

    def test_coord_rect_rejects_wrong_length(self, pool):
        with pytest.raises(TypeError):
            pool.declare("r", VariableType.COORD_RECT, initial_value=(1, 2, 3))

    def test_timer_accepts_int_and_float(self, pool):
        pool.declare("t1", VariableType.TIMER, initial_value=5)
        pool.declare("t2", VariableType.TIMER, initial_value=2.5)
        assert pool.get("t1") == 5
        assert pool.get("t2") == 2.5

    def test_image_accepts_any(self, pool):
        pool.declare("img", VariableType.IMAGE, initial_value="any_data")
        assert pool.get("img") == "any_data"

    def test_list_default_is_fresh_instance(self, pool):
        pool.declare("l1", VariableType.LIST)
        pool.declare("l2", VariableType.LIST)
        pool.get("l1").append(1)
        assert pool.get("l2") == []

    def test_declare_none_uses_default(self, pool):
        pool.declare("s", VariableType.STR)
        assert pool.get("s") == ""
        pool.declare("b", VariableType.BOOL)
        assert pool.get("b") is False


class TestGet:

    def test_get_nonexistent_raises(self, pool):
        with pytest.raises(KeyError, match="不存在"):
            pool.get("no_such_var")

    def test_get_scope_specific(self, pool):
        pool.declare("x", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.declare("x", VariableType.INT, scope=VariableScope.STEP, initial_value=2)
        assert pool.get("x", VariableScope.GLOBAL) == 1
        assert pool.get("x", VariableScope.STEP) == 2

    def test_get_scope_none_searches_order(self, pool):
        pool.declare("x", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.declare("x", VariableType.INT, scope=VariableScope.NODE, initial_value=2)
        assert pool.get("x") == 2


class TestHas:

    def test_has_returns_true(self, pool):
        pool.declare("x", VariableType.INT)
        assert pool.has("x") is True

    def test_has_returns_false(self, pool):
        assert pool.has("nonexistent") is False

    def test_has_scope_specific(self, pool):
        pool.declare("x", VariableType.INT, scope=VariableScope.NODE)
        assert pool.has("x", VariableScope.NODE) is True
        assert pool.has("x", VariableScope.GLOBAL) is False


class TestGetType:

    def test_get_type_returns_correct(self, pool):
        pool.declare("pos", VariableType.COORD, initial_value=(0, 0))
        assert pool.get_type("pos") == VariableType.COORD

    def test_get_type_nonexistent_returns_none(self, pool):
        assert pool.get_type("nope") is None


# ---- 作用域管理 ----


class TestScopeManagement:

    def test_scope_isolation(self, pool):
        pool.declare("a", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.declare("a", VariableType.INT, scope=VariableScope.NODE, initial_value=2)
        assert pool.get("a", VariableScope.GLOBAL) == 1
        assert pool.get("a", VariableScope.NODE) == 2

    def test_push_pop_scope(self, pool):
        pool.push_scope(VariableScope.NODE)
        pool.declare("temp", VariableType.STR, scope=VariableScope.NODE, initial_value="hello")
        assert pool.has("temp", VariableScope.NODE) is True
        pool.pop_scope(VariableScope.NODE)
        assert pool.has("temp", VariableScope.NODE) is False

    def test_pop_scope_clears_variables(self, pool):
        pool.declare("g", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=10)
        pool.push_scope(VariableScope.STEP)
        pool.declare("s", VariableType.INT, scope=VariableScope.STEP, initial_value=20)
        pool.pop_scope(VariableScope.STEP)
        assert pool.has("s", VariableScope.STEP) is False
        assert pool.has("g", VariableScope.GLOBAL) is True

    def test_lookup_order_step_first(self, pool):
        pool.declare("x", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.declare("x", VariableType.INT, scope=VariableScope.STEP, initial_value=3)
        assert pool.get("x") == 3

    def test_lookup_order_node_before_global(self, pool):
        pool.declare("x", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.declare("x", VariableType.INT, scope=VariableScope.NODE, initial_value=2)
        assert pool.get("x") == 2

    def test_lookup_order_full_three_levels(self, pool):
        """STEP > NODE > GLOBAL 三级查找优先级。"""
        pool.declare("x", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.declare("x", VariableType.INT, scope=VariableScope.NODE, initial_value=2)
        pool.declare("x", VariableType.INT, scope=VariableScope.STEP, initial_value=3)
        assert pool.get("x") == 3
        pool.pop_scope(VariableScope.STEP)
        assert pool.get("x") == 2
        pool.pop_scope(VariableScope.NODE)
        assert pool.get("x") == 1

    def test_get_explicit_scope_not_found_raises(self, pool):
        pool.declare("x", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        with pytest.raises(KeyError, match="不存在"):
            pool.get("x", VariableScope.STEP)

    def test_set_to_different_scope_creates_separate(self, pool):
        pool.declare("x", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.set("x", 99, scope=VariableScope.NODE)
        assert pool.get("x", VariableScope.GLOBAL) == 1
        assert pool.get("x", VariableScope.NODE) == 99


# ---- 模板解析 ----


class TestResolveTemplate:

    def test_resolve_simple(self, pool):
        pool.declare("pos", VariableType.COORD, initial_value=(100, 200))
        result = pool.resolve_template("坐标: {{pos}}")
        assert result == "坐标: (100, 200)"

    def test_resolve_multiple(self, pool):
        pool.declare("x", VariableType.INT, initial_value=10)
        pool.declare("y", VariableType.INT, initial_value=20)
        result = pool.resolve_template("{{x}} + {{y}}")
        assert result == "10 + 20"

    def test_resolve_unknown_preserved(self, pool):
        result = pool.resolve_template("hello {{unknown}}")
        assert result == "hello {{unknown}}"

    def test_resolve_builtin_timestamp(self, pool):
        result = pool.resolve_template("{{sys.timestamp}}")
        assert float(result) > 0

    def test_resolve_builtin_time(self, pool):
        result = pool.resolve_template("{{sys.time}}")
        assert len(result) == 8  # HH:MM:SS

    def test_resolve_empty_string(self, pool):
        assert pool.resolve_template("") == ""

    def test_resolve_no_placeholders(self, pool):
        assert pool.resolve_template("plain text") == "plain text"

    def test_resolve_same_var_twice(self, pool):
        pool.declare("x", VariableType.INT, initial_value=7)
        result = pool.resolve_template("{{x}} and {{x}}")
        assert result == "7 and 7"


# ---- 快照与恢复 ----


class TestSnapshot:

    def test_snapshot_captures_all(self, pool):
        pool.declare("a", VariableType.INT, scope=VariableScope.GLOBAL, initial_value=1)
        pool.declare("b", VariableType.STR, scope=VariableScope.NODE, initial_value="hi")
        snap = pool.snapshot()
        assert snap["global"]["a"] == 1
        assert snap["node"]["b"] == "hi"
        assert snap["step"] == {}

    def test_from_snapshot_restores(self, pool):
        pool.declare("x", VariableType.INT, initial_value=5)
        snap = pool.snapshot()

        pool2 = VariablePool()
        pool2.from_snapshot(snap)
        assert pool2.get("x") == 5

    def test_snapshot_isolation(self, pool):
        pool.declare("x", VariableType.INT, initial_value=1)
        snap = pool.snapshot()
        snap["global"]["x"] = 999
        assert pool.get("x") == 1

    def test_snapshot_isolation_mutable(self, pool):
        """修改快照中的可变值不应影响池内部状态。"""
        pool.declare("lst", VariableType.LIST, initial_value=[1, 2])
        snap = pool.snapshot()
        snap["global"]["lst"].append(3)
        assert pool.get("lst") == [1, 2]

    def test_from_snapshot_merge(self, pool):
        pool.declare("existing", VariableType.INT, initial_value=10)
        snap = {"global": {"new_var": 42}, "node": {}, "step": {}}
        pool.from_snapshot(snap)
        assert pool.get("existing") == 10
        assert pool.get("new_var") == 42

    def test_empty_pool_snapshot(self, pool):
        snap = pool.snapshot()
        assert snap == {"global": {}, "node": {}, "step": {}}

    def test_from_snapshot_type_mismatch_raises(self, pool):
        """从损坏快照恢复时，已有变量的类型不匹配应抛 TypeError。"""
        pool.declare("x", VariableType.INT, initial_value=1)
        bad_snap = {"global": {"x": "not_an_int"}, "node": {}, "step": {}}
        with pytest.raises(TypeError, match="不匹配声明类型"):
            pool.from_snapshot(bad_snap)


# ---- 变更回调 ----


class TestOnChange:

    def test_on_change_fired_on_set(self, pool):
        pool.declare("x", VariableType.INT, initial_value=0)
        changes = []
        pool.on_change(lambda name, old, new, scope: changes.append((name, old, new, scope)))
        pool.set("x", 42)
        assert len(changes) == 1
        assert changes[0] == ("x", 0, 42, VariableScope.GLOBAL)

    def test_remove_on_change(self, pool):
        pool.declare("x", VariableType.INT, initial_value=0)
        calls = []
        cb = lambda name, old, new, scope: calls.append(1)  # noqa: E731
        pool.on_change(cb)
        pool.remove_on_change(cb)
        pool.set("x", 1)
        assert len(calls) == 0

    def test_callback_exception_does_not_break(self, pool):
        pool.declare("x", VariableType.INT, initial_value=0)
        pool.on_change(lambda n, o, v, s: 1 / 0)
        pool.set("x", 1)
        assert pool.get("x") == 1

    def test_multiple_callbacks_fire(self, pool):
        pool.declare("x", VariableType.INT, initial_value=0)
        calls_a, calls_b = [], []
        pool.on_change(lambda n, o, v, s: calls_a.append((n, o, v)))
        pool.on_change(lambda n, o, v, s: calls_b.append((n, o, v)))
        pool.set("x", 5)
        assert len(calls_a) == 1
        assert len(calls_b) == 1
        assert calls_a[0] == ("x", 0, 5)
        assert calls_b[0] == ("x", 0, 5)

    def test_auto_declare_does_not_fire_callback(self, pool):
        """set() 自动声明时不触发 on_change 回调（语义：创建而非更新）。"""
        calls = []
        pool.on_change(lambda n, o, v, s: calls.append((n, o, v)))
        pool.set("new_var", 42)
        assert len(calls) == 0


# ---- 内置变量 ----


class TestBuiltins:

    def test_sys_time(self, pool):
        result = pool.get("sys.time")
        assert isinstance(result, str)
        assert ":" in result

    def test_sys_date(self, pool):
        result = pool.get("sys.date")
        assert isinstance(result, str)
        assert "-" in result

    def test_sys_timestamp(self, pool):
        result = pool.get("sys.timestamp")
        assert isinstance(result, float)
        assert result > 0

    def test_exec_defaults(self, pool):
        assert pool.get("exec.loop_count") == 0
        assert pool.get("exec.step_count") == 0
        assert pool.get("exec.step_index") == 0

    def test_runtime_resolvers(self, pool):
        pool.set_runtime_resolvers(
            mouse_x_fn=lambda: 960,
            mouse_y_fn=lambda: 540,
            screen_w_fn=lambda: 1920,
            screen_h_fn=lambda: 1080,
            region_fn=lambda: (100, 200, 800, 600),
        )
        assert pool.get("sys.mouse_x") == 960
        assert pool.get("sys.mouse_y") == 540
        assert pool.get("sys.screen_w") == 1920
        assert pool.get("sys.screen_h") == 1080
        assert pool.get("region.x") == 100
        assert pool.get("region.y") == 200
        assert pool.get("region.w") == 800
        assert pool.get("region.h") == 600

    def test_unknown_builtin_raises(self, pool):
        with pytest.raises(KeyError, match="未知的内置变量"):
            pool.get("sys.nonexistent")


# ---- 线程安全 ----


class TestThreadSafety:

    def test_concurrent_access(self, pool):
        pool.declare("counter", VariableType.INT, initial_value=0)
        errors = []

        def increment(n):
            try:
                for _ in range(100):
                    current = pool.get("counter")
                    pool.set("counter", current + 1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=increment, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert isinstance(pool.get("counter"), int)

    def test_concurrent_declare_and_get(self, pool):
        errors = []

        def writer(n):
            try:
                for i in range(50):
                    pool.declare(f"var_{n}_{i}", VariableType.INT, initial_value=i)
            except Exception as e:
                errors.append(e)

        def reader():
            try:
                for _ in range(50):
                    pool.snapshot()
            except Exception as e:
                errors.append(e)

        threads = [
            *[threading.Thread(target=writer, args=(i,)) for i in range(3)],
            threading.Thread(target=reader),
            threading.Thread(target=reader),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_set_different_vars(self, pool):
        pool.declare("a", VariableType.INT, initial_value=0)
        pool.declare("b", VariableType.INT, initial_value=0)
        errors = []

        def set_a():
            try:
                for _ in range(100):
                    pool.set("a", pool.get("a") + 1)
            except Exception as e:
                errors.append(e)

        def set_b():
            try:
                for _ in range(100):
                    pool.set("b", pool.get("b") + 1)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=set_a)
        t2 = threading.Thread(target=set_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert len(errors) == 0


# ---- _infer_type ----


class TestInferType:

    def test_infer_bool_before_int(self, pool):
        pool.set("b", True)
        assert pool.get_type("b") == VariableType.BOOL

    def test_infer_int(self, pool):
        pool.set("n", 42)
        assert pool.get_type("n") == VariableType.INT

    def test_infer_float(self, pool):
        pool.set("f", 3.14)
        assert pool.get_type("f") == VariableType.FLOAT

    def test_infer_str(self, pool):
        pool.set("s", "hello")
        assert pool.get_type("s") == VariableType.STR

    def test_infer_coord(self, pool):
        pool.set("c", (100, 200))
        assert pool.get_type("c") == VariableType.COORD

    def test_infer_coord_rect(self, pool):
        pool.set("r", (0, 0, 800, 600))
        assert pool.get_type("r") == VariableType.COORD_RECT

    def test_infer_list(self, pool):
        pool.set("l", [1, 2, 3])
        assert pool.get_type("l") == VariableType.LIST

    def test_infer_tuple_with_floats_raises(self, pool):
        """含 float 元素的 tuple 无法推断类型，应抛 TypeError。"""
        with pytest.raises(TypeError, match="无法推断 tuple"):
            pool.set("t", (1.5, 2.5))

    def test_infer_3_element_tuple_raises(self, pool):
        """长度非 2 或 4 的 tuple 无法推断类型，应抛 TypeError。"""
        with pytest.raises(TypeError, match="无法推断 tuple"):
            pool.set("t", (1, 2, 3))

    def test_infer_dict_raises(self, pool):
        """dict 类型无法推断，应抛 TypeError。"""
        with pytest.raises(TypeError, match="无法推断值"):
            pool.set("d", {"key": 1})

    def test_infer_set_raises(self, pool):
        """set 类型无法推断，应抛 TypeError。"""
        with pytest.raises(TypeError, match="无法推断值"):
            pool.set("s", {1, 2})

    def test_infer_none_raises(self, pool):
        """None 无法推断类型，应抛 TypeError。"""
        with pytest.raises(TypeError, match="无法推断值"):
            pool.set("n", None)

    def test_infer_bool_in_coord_tuple_raises(self, pool):
        """含 bool 元素的 tuple 无法推断为 COORD。"""
        with pytest.raises(TypeError, match="无法推断 tuple"):
            pool.set("t", (True, True))

    def test_infer_bool_in_coord_rect_tuple_raises(self, pool):
        """含 bool 元素的 4-tuple 无法推断为 COORD_RECT。"""
        with pytest.raises(TypeError, match="无法推断 tuple"):
            pool.set("t", (True, True, True, True))


class TestPopScopeMismatch:

    def test_pop_scope_stack_mismatch_warns(self, pool, caplog):
        """pop_scope 栈顶不匹配时应发出警告但不抛异常。"""
        import logging
        pool.push_scope(VariableScope.NODE)
        pool.declare("temp", VariableType.INT, scope=VariableScope.NODE, initial_value=1)
        with caplog.at_level(logging.WARNING, logger="src.core.variables.pool"):
            pool.pop_scope(VariableScope.STEP)
        assert "栈顶不匹配" in caplog.text
        assert pool.has("temp", VariableScope.NODE)


class TestIncrement:

    def test_increment_existing(self, pool):
        pool.declare("count", VariableType.INT, initial_value=5)
        result = pool.increment("count")
        assert result == 6
        assert pool.get("count") == 6

    def test_increment_with_step(self, pool):
        pool.declare("count", VariableType.INT, initial_value=0)
        result = pool.increment("count", step=5)
        assert result == 5

    def test_increment_nonexistent_creates(self, pool):
        result = pool.increment("new_counter")
        assert result == 1
        assert pool.get("new_counter") == 1

    def test_increment_fires_callback(self, pool):
        pool.declare("count", VariableType.INT, initial_value=0)
        changes = []
        pool.on_change(lambda n, o, v, s: changes.append((n, o, v)))
        pool.increment("count", step=3)
        assert len(changes) == 1
        assert changes[0] == ("count", 0, 3)


class TestRuntimeResolversNoRegion:

    def test_runtime_resolvers_without_region(self, pool):
        """不提供 region_fn 时 region.* 变量应抛 KeyError。"""
        pool.set_runtime_resolvers(
            mouse_x_fn=lambda: 100,
            mouse_y_fn=lambda: 200,
            screen_w_fn=lambda: 1920,
            screen_h_fn=lambda: 1080,
        )
        assert pool.get("sys.mouse_x") == 100
        assert pool.get("sys.mouse_y") == 200
        with pytest.raises(KeyError, match="未知的内置变量"):
            pool.get("region.x")


class TestTemplateResolveBuiltinMissing:

    def test_resolve_builtin_missing_preserved(self, pool):
        """模板中引用不存在的内置变量时保留原样。"""
        result = pool.resolve_template("{{sys.nonexistent_var}}")
        assert result == "{{sys.nonexistent_var}}"


class TestFromSnapshotNewVariable:

    def test_from_snapshot_creates_new_variable(self, pool):
        """快照中的新变量应自动推断类型并创建。"""
        snap = {"global": {"new_float": 3.14}, "node": {"new_str": "hi"}, "step": {}}
        pool.from_snapshot(snap)
        assert pool.get("new_float") == 3.14
        assert pool.get_type("new_float") == VariableType.FLOAT
        assert pool.get("new_str") == "hi"
        assert pool.get_type("new_str") == VariableType.STR
