"""VariableType 枚举测试。"""

from src.core.variables.types import VariableType


class TestVariableTypeMembers:
    """枚举成员完整性测试。"""

    def test_all_nine_members_exist(self):
        members = list(VariableType)
        assert len(members) == 9
        names = {m.name for m in members}
        expected = {"INT", "FLOAT", "STR", "BOOL", "COORD", "COORD_RECT", "TIMER", "IMAGE", "LIST"}
        assert names == expected

    def test_string_values(self):
        assert VariableType.INT.value == "int"
        assert VariableType.FLOAT.value == "float"
        assert VariableType.STR.value == "str"
        assert VariableType.BOOL.value == "bool"
        assert VariableType.COORD.value == "coord"
        assert VariableType.COORD_RECT.value == "coord_rect"
        assert VariableType.TIMER.value == "timer"
        assert VariableType.IMAGE.value == "image"
        assert VariableType.LIST.value == "list"


class TestPythonType:
    """python_type 属性测试。"""

    def test_int_returns_int(self):
        assert VariableType.INT.python_type is int

    def test_float_returns_float(self):
        assert VariableType.FLOAT.python_type is float

    def test_str_returns_str(self):
        assert VariableType.STR.python_type is str

    def test_bool_returns_bool(self):
        assert VariableType.BOOL.python_type is bool

    def test_coord_returns_tuple(self):
        assert VariableType.COORD.python_type is tuple

    def test_timer_returns_float(self):
        assert VariableType.TIMER.python_type is float

    def test_image_returns_string(self):
        assert VariableType.IMAGE.python_type == "numpy.ndarray"

    def test_list_returns_list(self):
        assert VariableType.LIST.python_type is list


class TestDefaultValue:
    """default_value 属性测试。"""

    def test_int_default(self):
        assert VariableType.INT.default_value == 0

    def test_float_default(self):
        assert VariableType.FLOAT.default_value == 0.0

    def test_str_default(self):
        assert VariableType.STR.default_value == ""

    def test_bool_default(self):
        assert VariableType.BOOL.default_value is False

    def test_coord_default(self):
        assert VariableType.COORD.default_value == (0, 0)

    def test_coord_rect_default(self):
        assert VariableType.COORD_RECT.default_value == (0, 0, 0, 0)

    def test_timer_default(self):
        assert VariableType.TIMER.default_value == 0.0

    def test_image_default(self):
        assert VariableType.IMAGE.default_value is None

    def test_list_default(self):
        assert VariableType.LIST.default_value == []


class TestValidate:
    """validate() 方法测试。"""

    # -- None 始终合法 --
    def test_none_always_valid(self):
        for vt in VariableType:
            assert vt.validate(None) is True

    # -- INT --
    def test_int_accepts_int(self):
        assert VariableType.INT.validate(42) is True

    def test_int_rejects_bool(self):
        assert VariableType.INT.validate(True) is False
        assert VariableType.INT.validate(False) is False

    def test_int_rejects_float(self):
        assert VariableType.INT.validate(3.14) is False

    # -- FLOAT --
    def test_float_accepts_float(self):
        assert VariableType.FLOAT.validate(3.14) is True

    def test_float_accepts_int(self):
        assert VariableType.FLOAT.validate(3) is True

    def test_float_rejects_bool(self):
        assert VariableType.FLOAT.validate(True) is False

    def test_float_rejects_str(self):
        assert VariableType.FLOAT.validate("3.14") is False

    # -- STR --
    def test_str_accepts_str(self):
        assert VariableType.STR.validate("hello") is True

    def test_str_rejects_int(self):
        assert VariableType.STR.validate(42) is False

    # -- BOOL --
    def test_bool_accepts_true(self):
        assert VariableType.BOOL.validate(True) is True

    def test_bool_accepts_false(self):
        assert VariableType.BOOL.validate(False) is True

    def test_bool_rejects_int(self):
        assert VariableType.BOOL.validate(1) is False
        assert VariableType.BOOL.validate(0) is False

    # -- COORD --
    def test_coord_valid(self):
        assert VariableType.COORD.validate((100, 200)) is True

    def test_coord_rejects_wrong_length(self):
        assert VariableType.COORD.validate((1, 2, 3)) is False

    def test_coord_rejects_float_elements(self):
        assert VariableType.COORD.validate((1.0, 2.0)) is False

    def test_coord_rejects_empty(self):
        assert VariableType.COORD.validate(()) is False

    def test_coord_rejects_bool_elements(self):
        assert VariableType.COORD.validate((True, False)) is False

    # -- COORD_RECT --
    def test_coord_rect_valid(self):
        assert VariableType.COORD_RECT.validate((0, 0, 800, 600)) is True

    def test_coord_rect_rejects_wrong_length(self):
        assert VariableType.COORD_RECT.validate((1, 2, 3)) is False

    # -- TIMER --
    def test_timer_accepts_float(self):
        assert VariableType.TIMER.validate(1.5) is True

    def test_timer_accepts_int(self):
        assert VariableType.TIMER.validate(10) is True

    def test_timer_rejects_bool(self):
        assert VariableType.TIMER.validate(True) is False

    # -- IMAGE --
    def test_image_always_true(self):
        assert VariableType.IMAGE.validate("anything") is True
        assert VariableType.IMAGE.validate(42) is True

    # -- LIST --
    def test_list_accepts_list(self):
        assert VariableType.LIST.validate([1, 2, 3]) is True

    def test_list_rejects_tuple(self):
        assert VariableType.LIST.validate((1, 2, 3)) is False

    def test_list_accepts_empty(self):
        assert VariableType.LIST.validate([]) is True

    # -- COORD_RECT float elements --
    def test_coord_rect_rejects_float_elements(self):
        assert VariableType.COORD_RECT.validate((1.0, 2.0, 3.0, 4.0)) is False

    # -- COORD_RECT bool elements --
    def test_coord_rect_rejects_bool_elements(self):
        assert VariableType.COORD_RECT.validate((True, False, True, False)) is False

    # -- TIMER rejects string --
    def test_timer_rejects_str(self):
        assert VariableType.TIMER.validate("5") is False
