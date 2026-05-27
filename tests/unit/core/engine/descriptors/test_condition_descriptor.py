"""ConditionDescriptor 单元测试。

验证条件分支节点的元数据、无条件降级、有评估器和评估结果。
覆盖所有 ConditionType 的分支逻辑。
"""

from __future__ import annotations

from unittest.mock import MagicMock

from src.core.condition import Condition, ConditionEvaluator, ConditionType
from src.core.engine.descriptors.condition_descriptor import ConditionDescriptor
from src.core.engine.node_result import NodeResult

from .conftest import _make_ctx as _base_make_ctx


# ---- Fixtures ----


def _make_ctx(
    *,
    node_id: str = "cond_1",
    condition: Condition | None = None,
    evaluator: ConditionEvaluator | None = None,
) -> MagicMock:
    """构建模拟 ExecutionContext。"""
    return _base_make_ctx(node_id=node_id, condition=condition, evaluator=evaluator)


def _make_evaluator(return_value: bool) -> MagicMock:
    """构建模拟 ConditionEvaluator，evaluate() 返回指定值。"""
    ev = MagicMock(spec=ConditionEvaluator)
    ev.evaluate.return_value = return_value
    return ev


# ---- 元数据测试 ----


class TestConditionDescriptorMetadata:
    def test_action_type(self) -> None:
        assert ConditionDescriptor.action_type() == "CONDITION"

    def test_display_name(self) -> None:
        assert ConditionDescriptor.display_name() == "条件"

    def test_category(self) -> None:
        assert ConditionDescriptor.category() == "流程控制"

    def test_input_types(self) -> None:
        inputs = ConditionDescriptor.input_types()
        assert "condition" in inputs
        assert inputs["condition"].required is False

    def test_output_types(self) -> None:
        outputs = ConditionDescriptor.output_types()
        assert "result" in outputs
        assert outputs["result"].type == "bool"

    def test_metadata_consistency(self) -> None:
        desc = ConditionDescriptor()
        assert desc.action_type() == "CONDITION"
        assert desc.display_name() == "条件"
        assert desc.category() == "流程控制"


# ---- 无条件降级 ----


class TestConditionDescriptorNoCondition:
    def test_no_condition_defaults_true(self) -> None:
        ctx = _make_ctx(condition=None, evaluator=_make_evaluator(True))

        result = ConditionDescriptor().execute(ctx)

        assert isinstance(result, NodeResult)
        assert result.success is True
        assert result.next_label == "true"
        assert result.output_vars["result"] is True

    def test_no_condition_no_evaluator_still_true(self) -> None:
        ctx = _make_ctx(condition=None, evaluator=None)

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "true"

    def test_no_condition_does_not_call_evaluator(self) -> None:
        ev = _make_evaluator(True)
        ctx = _make_ctx(condition=None, evaluator=ev)

        ConditionDescriptor().execute(ctx)

        ev.evaluate.assert_not_called()


# ---- 无评估器降级 ----


class TestConditionDescriptorNoEvaluator:
    def test_has_condition_but_no_evaluator(self) -> None:
        cond = Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="x")
        ctx = _make_ctx(condition=cond, evaluator=None)

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "true"
        assert result.output_vars["result"] is True


# ---- 条件评估 — True ----


class TestConditionDescriptorTrueBranch:
    def test_condition_true(self) -> None:
        cond = Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="x")
        ctx = _make_ctx(condition=cond, evaluator=_make_evaluator(True))

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "true"
        assert result.output_vars["result"] is True

    def test_image_found_true(self) -> None:
        cond = Condition(condition_type=ConditionType.IMAGE_FOUND, image_path="test.png")
        ctx = _make_ctx(condition=cond, evaluator=_make_evaluator(True))

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "true"

    def test_compound_and_true(self) -> None:
        cond = Condition(
            condition_type=ConditionType.COMPOUND_AND,
            children=[
                Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="a"),
            ],
        )
        ctx = _make_ctx(condition=cond, evaluator=_make_evaluator(True))

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "true"


# ---- 条件评估 — False ----


class TestConditionDescriptorFalseBranch:
    def test_condition_false_branches_to_false(self) -> None:
        cond = Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="y")
        ctx = _make_ctx(condition=cond, evaluator=_make_evaluator(False))

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "false"
        assert result.output_vars["result"] is False

    def test_evaluator_returns_false_routes_false(self) -> None:
        cond = Condition(
            condition_type=ConditionType.IMAGE_NOT_FOUND, image_path="missing.png",
        )
        ctx = _make_ctx(condition=cond, evaluator=_make_evaluator(False))

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "false"

    def test_compound_or_false_branch(self) -> None:
        cond = Condition(
            condition_type=ConditionType.COMPOUND_OR,
            children=[
                Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="a"),
                Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="b"),
            ],
        )
        ctx = _make_ctx(condition=cond, evaluator=_make_evaluator(False))

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "false"


# ---- 评估器调用 ----


class TestConditionDescriptorEvaluatorCall:
    def test_evaluator_called_with_condition(self) -> None:
        cond = Condition(condition_type=ConditionType.ELAPSED_TIME, timer_name="t1")
        ev = _make_evaluator(True)
        ctx = _make_ctx(condition=cond, evaluator=ev)

        ConditionDescriptor().execute(ctx)

        ev.evaluate.assert_called_once_with(cond)

    def test_compound_not_evaluated(self) -> None:
        cond = Condition(
            condition_type=ConditionType.COMPOUND_NOT,
            children=[Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="x")],
        )
        ev = _make_evaluator(False)
        ctx = _make_ctx(condition=cond, evaluator=ev)

        result = ConditionDescriptor().execute(ctx)

        ev.evaluate.assert_called_once_with(cond)
        assert result.next_label == "false"


# ---- 异常处理 ----


class TestConditionDescriptorException:
    def test_evaluate_exception_defaults_true(self) -> None:
        cond = Condition(condition_type=ConditionType.IMAGE_FOUND, image_path="bad.png")
        ev = MagicMock(spec=ConditionEvaluator)
        ev.evaluate.side_effect = RuntimeError("图片读取失败")
        ctx = _make_ctx(condition=cond, evaluator=ev)

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "true"
        assert result.output_vars["result"] is True

    def test_evaluate_file_not_found_defaults_true(self) -> None:
        cond = Condition(condition_type=ConditionType.IMAGE_FOUND, image_path="missing.png")
        ev = MagicMock(spec=ConditionEvaluator)
        ev.evaluate.side_effect = FileNotFoundError("no such file")
        ctx = _make_ctx(condition=cond, evaluator=ev)

        result = ConditionDescriptor().execute(ctx)

        assert result.success is True
        assert result.next_label == "true"


# ---- output_vars ----


class TestConditionDescriptorOutputVars:
    def test_true_result_has_output(self) -> None:
        ctx = _make_ctx(
            condition=Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="v"),
            evaluator=_make_evaluator(True),
        )

        result = ConditionDescriptor().execute(ctx)

        assert "result" in result.output_vars
        assert result.output_vars["result"] is True

    def test_false_result_has_output(self) -> None:
        ctx = _make_ctx(
            condition=Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="v"),
            evaluator=_make_evaluator(False),
        )

        result = ConditionDescriptor().execute(ctx)

        assert "result" in result.output_vars
        assert result.output_vars["result"] is False


# ---- 多条件节点隔离 ----


class TestConditionDescriptorIsolation:
    def test_different_nodes_independent(self) -> None:
        cond_a = Condition(condition_type=ConditionType.VARIABLE_EXISTS, variable_name="a")
        cond_b = Condition(condition_type=ConditionType.IMAGE_FOUND, image_path="b.png")
        ev = _make_evaluator(True)

        ctx_a = _make_ctx(node_id="cond_A", condition=cond_a, evaluator=ev)
        result_a = ConditionDescriptor().execute(ctx_a)

        ctx_b = _make_ctx(node_id="cond_B", condition=cond_b, evaluator=ev)
        result_b = ConditionDescriptor().execute(ctx_b)

        assert result_a.success is True
        assert result_a.next_label == "true"
        assert result_b.success is True
        assert result_b.next_label == "true"
        assert ev.evaluate.call_count == 2
