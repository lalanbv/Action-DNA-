"""safe_eval 模块测试 — 安全表达式求值器。

覆盖：合法表达式、语法错误、注入攻击、变量访问、边界情况。
"""

import pytest

from src.core.safe_eval import safe_eval


class TestBasicExpressions:
    """基本布尔/比较/算术表达式。"""

    def test_true_literal(self) -> None:
        assert safe_eval("True") is True

    def test_false_literal(self) -> None:
        assert safe_eval("False") is False

    def test_integer_comparison(self) -> None:
        assert safe_eval("1 < 2") is True

    def test_equality(self) -> None:
        assert safe_eval("1 == 1") is True

    def test_inequality(self) -> None:
        assert safe_eval("1 != 2") is True

    def test_greater_than(self) -> None:
        assert safe_eval("5 > 3") is True

    def test_greater_equal(self) -> None:
        assert safe_eval("3 >= 3") is True

    def test_less_equal(self) -> None:
        assert safe_eval("2 <= 3") is True

    def test_chained_comparison(self) -> None:
        assert safe_eval("1 < 2 < 3") is True

    def test_boolean_and(self) -> None:
        assert safe_eval("True and False") is False

    def test_boolean_or(self) -> None:
        assert safe_eval("True or False") is True

    def test_boolean_not(self) -> None:
        assert safe_eval("not False") is True

    def test_arithmetic_add(self) -> None:
        assert safe_eval("1 + 1 == 2") is True

    def test_arithmetic_sub(self) -> None:
        assert safe_eval("5 - 3 == 2") is True

    def test_arithmetic_mult(self) -> None:
        assert safe_eval("2 * 3 == 6") is True

    def test_arithmetic_div(self) -> None:
        assert safe_eval("6 / 2 == 3") is True

    def test_arithmetic_mod(self) -> None:
        assert safe_eval("7 % 3 == 1") is True

    def test_unary_negative(self) -> None:
        assert safe_eval("-1 < 0") is True

    def test_complex_expression(self) -> None:
        assert safe_eval("(1 + 2) * 3 == 9") is True

    def test_string_comparison(self) -> None:
        assert safe_eval("'hello' == 'hello'") is True

    def test_float_comparison(self) -> None:
        assert safe_eval("1.5 > 1.0") is True


class TestVariableAccess:
    """变量访问测试。"""

    def test_variable_access(self) -> None:
        assert safe_eval("x > 0", {"x": 5}) is True

    def test_variable_equality(self) -> None:
        assert safe_eval("name == 'test'", {"name": "test"}) is True

    def test_multiple_variables(self) -> None:
        assert safe_eval("a + b == 10", {"a": 3, "b": 7}) is True

    def test_nested_variable_expression(self) -> None:
        assert safe_eval("x > 0 and y < 10", {"x": 5, "y": 3}) is True

    def test_missing_variable_returns_false(self) -> None:
        # NameError 被捕获，返回 False
        assert safe_eval("undefined_var > 0") is False

    def test_none_local_vars(self) -> None:
        # local_vars=None 时使用空字典
        assert safe_eval("True") is True

    def test_empty_local_vars(self) -> None:
        assert safe_eval("1 == 1") is True


class TestSyntaxErrors:
    """语法错误应返回 False。"""

    def test_empty_string(self) -> None:
        assert safe_eval("") is False

    def test_invalid_syntax(self) -> None:
        assert safe_eval("1 + + 2") is False

    def test_incomplete_expression(self) -> None:
        assert safe_eval("(1 + 2") is False

    def test_assignment_in_expression(self) -> None:
        # 赋值不是合法的 eval 表达式
        assert safe_eval("x = 1") is False

    def test_random_gibberish(self) -> None:
        assert safe_eval("@#$%^&*()") is False


class TestSecurityInjections:
    """注入攻击应被拦截，返回 False。"""

    def test_function_call_blocked(self) -> None:
        assert safe_eval("print('hello')") is False

    def test_import_blocked(self) -> None:
        assert safe_eval("__import__('os')") is False

    def test_attribute_access_blocked(self) -> None:
        assert safe_eval("''.__class__") is False

    def test_subscript_blocked(self) -> None:
        assert safe_eval("[1, 2, 3][0]") is False

    def test_list_literal_blocked(self) -> None:
        assert safe_eval("[1, 2, 3]") is False

    def test_dict_literal_blocked(self) -> None:
        assert safe_eval("{'a': 1}") is False

    def test_lambda_blocked(self) -> None:
        assert safe_eval("lambda x: x") is False

    def test_if_expr_blocked(self) -> None:
        assert safe_eval("True if 1 else False") is False

    def test_f_string_blocked(self) -> None:
        assert safe_eval("f'{1+1}'") is False

    def test_builtin_access_blocked(self) -> None:
        assert safe_eval("open") is False

    def test_exec_blocked(self) -> None:
        assert safe_eval("exec('pass')") is False

    def test_eval_blocked(self) -> None:
        assert safe_eval("eval('1')") is False

    def test_dunder_builtins_blocked(self) -> None:
        # __builtins__ 在 eval 沙箱中被设为空
        assert safe_eval("len([1,2,3])") is False

    def test_class_definition_blocked(self) -> None:
        assert safe_eval("type('X', (), {})") is False

    def test_assignment_expr_blocked(self) -> None:
        assert safe_eval("(x := 5)") is False


class TestEdgeCases:
    """边界情况。"""

    def test_result_coerced_to_bool(self) -> None:
        # 非零整数应为 True
        assert safe_eval("1 + 1") is True

    def test_zero_is_false(self) -> None:
        assert safe_eval("1 - 1") is False

    def test_division_by_zero_returns_false(self) -> None:
        assert safe_eval("1 / 0 == 0") is False

    def test_none_in_local_vars(self) -> None:
        # None 比较
        assert safe_eval("x == None", {"x": None}) is True

    def test_boolean_in_local_vars(self) -> None:
        assert safe_eval("flag == True", {"flag": True}) is True

    def test_negative_result(self) -> None:
        # 非零负数也是 True
        assert safe_eval("0 - 1") is True
