"""NodeDescriptor ABC 单元测试 — 验证接口契约和默认行为。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.node_descriptor import NodeDescriptor, PortDef


# ---- 测试用具体子类 ----


class _MinimalDescriptor(NodeDescriptor):
    """满足 ABC 最小要求的测试子类。"""

    @classmethod
    def action_type(cls) -> str:
        return "TEST_NODE"

    @classmethod
    def display_name(cls) -> str:
        return "测试节点"

    @classmethod
    def category(cls) -> str:
        return "测试分类"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "image_path": PortDef(type="image", description="模板图片路径"),
            "confidence": PortDef(
                type="number", description="置信度", required=False, default=0.8
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {"match_pos": PortDef(type="coord", description="匹配坐标")}

    def execute(self, ctx: Any) -> Any:
        return None


class _FullDescriptor(NodeDescriptor):
    """覆盖所有可选方法的测试子类。"""

    @classmethod
    def action_type(cls) -> str:
        return "FULL_TEST"

    @classmethod
    def display_name(cls) -> str:
        return "完整测试节点"

    @classmethod
    def category(cls) -> str:
        return "完整分类"

    @classmethod
    def input_types(cls) -> dict[str, PortDef]:
        return {
            "key": PortDef(type="key", description="按键"),
            "optional_param": PortDef(
                type="number", description="可选参数", required=False, default=42
            ),
        }

    @classmethod
    def output_types(cls) -> dict[str, PortDef]:
        return {}

    @classmethod
    def validate_inputs(cls, action: BaseStep) -> list[str]:
        errors = super().validate_inputs(action)
        if not errors:
            key_val = getattr(action, "key", "")
            if isinstance(key_val, str) and len(key_val) < 1:
                errors.append("key 不能为空字符串")
        return errors

    def execute(self, ctx: Any) -> Any:
        return None

    def on_enter(self, ctx: Any) -> None:
        self.enter_called = True

    def on_exit(self, ctx: Any) -> None:
        self.exit_called = True

    def __init__(self) -> None:
        self.enter_called: bool = False
        self.exit_called: bool = False


# ---- PortDef 测试 ----


class TestPortDef:
    """PortDef 数据类测试。"""

    def test_defaults(self) -> None:
        port = PortDef(type="image", description="测试")
        assert port.type == "image"
        assert port.description == "测试"
        assert port.required is True
        assert port.default is None

    def test_all_fields(self) -> None:
        port = PortDef(type="number", description="数值", required=False, default=0.8)
        assert port.required is False
        assert port.default == 0.8

    def test_frozen(self) -> None:
        port = PortDef(type="string", description="冻结测试")
        with pytest.raises(AttributeError):
            port.type = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = PortDef(type="image", description="x")
        b = PortDef(type="image", description="x")
        assert a == b

    def test_inequality(self) -> None:
        a = PortDef(type="image", description="x")
        b = PortDef(type="number", description="x")
        assert a != b


# ---- ABC 契约测试 ----


class TestABCContract:
    """验证 ABC 无法直接实例化，且缺少方法会报错。"""

    def test_cannot_instantiate_abc(self) -> None:
        with pytest.raises(TypeError):
            NodeDescriptor()  # type: ignore[abstract]

    def test_missing_abstract_methods_raises(self) -> None:
        class Incomplete(NodeDescriptor):
            @classmethod
            def action_type(cls) -> str:
                return "INCOMPLETE"

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    def test_minimal_subclass_instantiates(self) -> None:
        desc = _MinimalDescriptor()
        assert isinstance(desc, NodeDescriptor)


# ---- 元数据类方法测试 ----


class TestMetadata:
    """验证元数据类方法。"""

    def test_action_type(self) -> None:
        assert _MinimalDescriptor.action_type() == "TEST_NODE"

    def test_display_name(self) -> None:
        assert _MinimalDescriptor.display_name() == "测试节点"

    def test_category(self) -> None:
        assert _MinimalDescriptor.category() == "测试分类"

    def test_input_types_structure(self) -> None:
        inputs = _MinimalDescriptor.input_types()
        assert "image_path" in inputs
        assert inputs["image_path"].type == "image"
        assert inputs["image_path"].required is True

    def test_output_types_structure(self) -> None:
        outputs = _MinimalDescriptor.output_types()
        assert "match_pos" in outputs
        assert outputs["match_pos"].type == "coord"

    def test_optional_input_has_default(self) -> None:
        inputs = _MinimalDescriptor.input_types()
        assert inputs["confidence"].required is False
        assert inputs["confidence"].default == 0.8

    def test_metadata_on_instance(self) -> None:
        desc = _MinimalDescriptor()
        assert desc.action_type() == "TEST_NODE"
        assert desc.display_name() == "测试节点"


# ---- validate_inputs 默认实现测试 ----


class TestValidateInputs:
    """validate_inputs 默认行为验证。"""

    def test_all_required_present(self) -> None:
        """image_path 有值，验证通过。"""
        action = STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="img.png")
        errors = _MinimalDescriptor.validate_inputs(action)
        assert errors == []

    def test_explicit_none_rejected(self) -> None:
        """显式设为 None 的必需字段被拒绝。"""
        action = STEP_CLASSES[ActionType.CLICK_IMAGE](image_path=None)
        errors = _MinimalDescriptor.validate_inputs(action)
        assert len(errors) == 1
        assert "image_path" in errors[0]

    def test_empty_string_passes_default_validation(self) -> None:
        """空字符串通过默认 required 检查（子类可覆盖 validate_inputs 添加额外规则）。"""
        action = STEP_CLASSES[ActionType.CLICK_IMAGE](image_path="")
        errors = _MinimalDescriptor.validate_inputs(action)
        assert errors == []

    def test_optional_field_not_checked(self) -> None:
        """optional 字段即使缺失也不会报错。"""
        action = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        errors = _MinimalDescriptor.validate_inputs(action)
        assert errors == []

    def test_custom_validate_with_valid_input(self) -> None:
        """自定义 validate 通过有效输入。"""
        action = STEP_CLASSES[ActionType.PRESS_KEY](key="enter")
        errors = _FullDescriptor.validate_inputs(action)
        assert errors == []

    def test_custom_validate_catches_invalid_value(self) -> None:
        """自定义 validate 捕获有效属性但语义无效的值。"""
        action = STEP_CLASSES[ActionType.PRESS_KEY](key="")
        errors = _FullDescriptor.validate_inputs(action)
        assert len(errors) >= 1
        assert any("key" in e for e in errors)


# ---- 生命周期钩子测试 ----


class TestLifecycleHooks:
    """on_enter / on_exit 默认和覆盖行为。"""

    def test_default_hooks_do_nothing(self) -> None:
        desc = _MinimalDescriptor()
        desc.on_enter(None)  # type: ignore[arg-type]
        desc.on_exit(None)  # type: ignore[arg-type]

    def test_overridden_hooks_called(self) -> None:
        desc = _FullDescriptor()
        assert desc.enter_called is False
        assert desc.exit_called is False
        desc.on_enter(None)  # type: ignore[arg-type]
        desc.on_exit(None)  # type: ignore[arg-type]
        assert desc.enter_called is True
        assert desc.exit_called is True

    def test_hooks_per_instance(self) -> None:
        """每个实例的钩子状态独立。"""
        a = _FullDescriptor()
        b = _FullDescriptor()
        a.on_enter(None)  # type: ignore[arg-type]
        assert a.enter_called is True
        assert b.enter_called is False


# ---- build_dialog 测试 ----


class TestBuildDialog:
    """build_dialog 默认行为 — UI 模块不存在时静默跳过。"""

    def test_build_dialog_no_ui_module(self) -> None:
        action = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        _MinimalDescriptor.build_dialog(None, action, lambda a: None)


# ---- 多态测试 ----


class TestPolymorphism:
    """验证多态行为 — 不同子类返回不同元数据。"""

    def test_different_subclasses_different_types(self) -> None:
        assert _MinimalDescriptor.action_type() != _FullDescriptor.action_type()

    def test_descriptor_isolation(self) -> None:
        assert _MinimalDescriptor.category() == "测试分类"
        assert _FullDescriptor.category() == "完整分类"

    def test_multiple_instances_independent(self) -> None:
        a = _MinimalDescriptor()
        b = _MinimalDescriptor()
        assert a is not b
        assert a.action_type() == b.action_type()
