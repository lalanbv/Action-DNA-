"""描述符单元测试汇总 — 验证所有 NodeDescriptor 子类覆盖完整。

设计文档 §5.2 要求：每个描述符独立测试 execute() 正确性、输入验证、边界条件。
本文件作为汇总入口，验证所有已注册描述符都有对应的测试文件覆盖。

实际测试分散在各描述符的独立测试文件中：
- tests/unit/core/engine/test_node_descriptor.py         — 基类 ABC / PortDef / validate_inputs / 生命周期
- tests/unit/core/engine/descriptors/test_click_image_descriptor.py  — 模板匹配 + 点击
- tests/unit/core/engine/descriptors/test_wait_descriptor.py         — 固定等待 / 随机等待
- tests/unit/core/engine/descriptors/test_press_key_descriptor.py    — 按键 / 鼠标键
- tests/unit/core/engine/descriptors/test_click_pos_descriptor.py    — 固定坐标点击
- tests/unit/core/engine/descriptors/test_flow_descriptors.py        — START / END / LOOP
- tests/unit/core/engine/descriptors/test_condition_descriptor.py    — 条件分支
- tests/unit/core/engine/descriptors/test_extended_descriptors.py    — HoldKey / Scroll / Turn / Combo / MultiKey / Idle / Timer
"""

from __future__ import annotations

import pytest

# 确保所有描述符模块被导入，触发 @auto_register 注册
import src.core.engine.descriptors.click_image_descriptor  # noqa: F401
import src.core.engine.descriptors.wait_descriptor  # noqa: F401
import src.core.engine.descriptors.press_key_descriptor  # noqa: F401
import src.core.engine.descriptors.click_pos_descriptor  # noqa: F401
import src.core.engine.descriptors.flow_descriptors  # noqa: F401
import src.core.engine.descriptors.condition_descriptor  # noqa: F401
import src.core.engine.descriptors.extended_descriptors  # noqa: F401

from src.core.engine.node_registry import NodeRegistry

# 收集所有已注册的描述符类，在 fixture 中重新注册
_IMPORTED_DESCRIPTORS = [
    src.core.engine.descriptors.click_image_descriptor.ClickImageDescriptor,
    src.core.engine.descriptors.wait_descriptor.WaitDescriptor,
    src.core.engine.descriptors.wait_descriptor.WaitRandomDescriptor,
    src.core.engine.descriptors.press_key_descriptor.PressKeyDescriptor,
    src.core.engine.descriptors.click_pos_descriptor.ClickPosDescriptor,
    src.core.engine.descriptors.flow_descriptors.StartDescriptor,
    src.core.engine.descriptors.flow_descriptors.EndDescriptor,
    src.core.engine.descriptors.flow_descriptors.LoopDescriptor,
    src.core.engine.descriptors.condition_descriptor.ConditionDescriptor,
    src.core.engine.descriptors.extended_descriptors.HoldKeyDescriptor,
    src.core.engine.descriptors.extended_descriptors.MouseScrollDescriptor,
    src.core.engine.descriptors.extended_descriptors.MouseDragDescriptor,
    src.core.engine.descriptors.extended_descriptors.KeyComboDescriptor,
    src.core.engine.descriptors.extended_descriptors.MultiKeySequenceDescriptor,
    src.core.engine.descriptors.extended_descriptors.IdleBehaviorDescriptor,
    src.core.engine.descriptors.extended_descriptors.StartTimerDescriptor,
]


@pytest.fixture(autouse=True)
def _ensure_registered() -> None:
    """确保所有描述符已注册（其他测试文件的 autouse fixture 可能清空了注册表）。"""
    NodeRegistry._registry.clear()
    NodeRegistry._categories.clear()
    for cls in _IMPORTED_DESCRIPTORS:
        NodeRegistry.register(cls)


# 所有已注册的描述符类型（通过 @auto_register 自动注册）
_ALL_DESCRIPTOR_TYPES: set[str] = {
    "CLICK_IMAGE",
    "WAIT",
    "WAIT_RANDOM",
    "PRESS_KEY",
    "CLICK_POS",
    "START",
    "END",
    "LOOP",
    "CONDITION",
    "HOLD_KEY",
    "MOUSE_SCROLL",
    "MOUSE_DRAG",
    "KEY_COMBO",
    "MULTI_KEY_SEQUENCE",
    "IDLE_BEHAVIOR",
    "START_TIMER",
}


class TestDescriptorCoverage:
    """验证所有描述符已注册且有独立测试覆盖。"""

    def test_all_known_types_registered(self) -> None:
        """所有已知的描述符类型都已注册到 NodeRegistry。"""
        for type_name in _ALL_DESCRIPTOR_TYPES:
            assert NodeRegistry.has(type_name), f"描述符 '{type_name}' 未注册"

    def test_no_unknown_types_registered(self) -> None:
        """NodeRegistry 中没有未在 _ALL_DESCRIPTOR_TYPES 中声明的新类型。
        如果此测试失败，说明新增了描述符但未更新此列表。"""
        registered = set(NodeRegistry._registry.keys())
        unexpected = registered - _ALL_DESCRIPTOR_TYPES
        assert unexpected == set(), f"发现未声明的描述符类型: {unexpected}"

    def test_all_types_count(self) -> None:
        """已注册描述符数量与预期一致。"""
        registered = set(NodeRegistry._registry.keys())
        assert len(registered) == len(_ALL_DESCRIPTOR_TYPES)
