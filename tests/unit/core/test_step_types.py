"""类型化 Step 类单元测试 — Phase 9h。

覆盖：
- BaseStep 抽象约束
- 14 个类型化 Step 的字段默认值和 action_type
- describe() 方法
- STEP_CLASSES 注册表完整性
- typed_step_to_dict / dict_to_typed_step 序列化往返
- 鸭子类型兼容性（字段名与 ActionStep 一致）
"""

from __future__ import annotations

import pytest

from src.core.action import ActionType, DetectMode, FoundAction
from src.core.step_types import BaseStep
from src.core.serialization import dict_to_typed_step, typed_step_to_dict
from src.core.step_types import (
    STEP_CLASSES,
    BaseStep,
    ClickImageStep,
    ClickPosStep,
    HoldKeyStep,
    IdleBehaviorStep,
    KeyComboStep,
    MouseScrollStep,
    MouseDragStep,
    MultiKeySequenceStep,
    OcrCheckStep,
    PixelSearchStep,
    PressKeyStep,
    StartTimerStep,
    WaitRandomStep,
    WaitStep,
)


# ── BaseStep 抽象约束 ──────────────────────────────────────────


class TestBaseStepAbstract:
    def test_cannot_instantiate_base(self):
        with pytest.raises(TypeError):
            BaseStep()

    def test_abstract_methods(self):
        assert "action_type" in BaseStep.__abstractmethods__
        assert "describe" in BaseStep.__abstractmethods__


# ── 注册表完整性 ───────────────────────────────────────────────


class TestStepRegistry:
    def test_all_action_types_registered(self):
        for atype in ActionType:
            assert atype in STEP_CLASSES, f"{atype.name} 未注册"

    def test_registry_size(self):
        assert len(STEP_CLASSES) == len(ActionType)

    @pytest.mark.parametrize("atype,cls", list(STEP_CLASSES.items()))
    def test_registry_maps_correct_class(self, atype, cls):
        assert cls.action_type == atype

    @pytest.mark.parametrize("atype,cls", list(STEP_CLASSES.items()))
    def test_class_is_base_step_subclass(self, atype, cls):
        assert issubclass(cls, BaseStep)


# ── 类型化 Step 默认值和 action_type ────────────────────────────


class TestClickImageStep:
    def test_defaults(self):
        s = ClickImageStep()
        assert s.action_type == ActionType.CLICK_IMAGE
        assert s.image_path == ""
        assert s.threshold == 0.8
        assert s.detect_mode == DetectMode.SKIP_IF_NOT_FOUND
        assert s.retry_count == 0
        assert s.found_action == FoundAction.LEFT_CLICK
        assert s.enabled is True

    def test_describe(self):
        s = ClickImageStep(image_path="/tmp/test.png")
        desc = s.describe()
        assert "test.png" in desc

    def test_describe_no_image(self):
        s = ClickImageStep()
        desc = s.describe()
        assert isinstance(desc, str)
        assert len(desc) > 0


class TestClickPosStep:
    def test_defaults(self):
        s = ClickPosStep()
        assert s.action_type == ActionType.CLICK_POS
        assert s.pos_x == 0
        assert s.pos_y == 0
        assert s.clicks == 1
        assert s.button == "left"

    def test_describe(self):
        s = ClickPosStep(pos_x=100, pos_y=200)
        desc = s.describe()
        assert "100" in desc
        assert "200" in desc

    def test_describe_coord_var(self):
        s = ClickPosStep(use_coord_var=True, coord_var_name="my_var")
        desc = s.describe()
        assert "my_var" in desc

    def test_describe_right_click(self):
        s = ClickPosStep(button="right", pos_x=10, pos_y=20)
        desc = s.describe()
        assert isinstance(desc, str)


class TestPressKeyStep:
    def test_defaults(self):
        s = PressKeyStep()
        assert s.action_type == ActionType.PRESS_KEY
        assert s.key == ""
        assert s.text == ""

    def test_describe_key(self):
        s = PressKeyStep(key="enter")
        desc = s.describe()
        assert "enter" in desc

    def test_describe_text(self):
        s = PressKeyStep(text="hello world")
        desc = s.describe()
        assert "hello world" in desc

    def test_describe_mouse_key(self):
        s = PressKeyStep(key="mouse_left")
        desc = s.describe()
        assert isinstance(desc, str)
        assert len(desc) > 0


class TestHoldKeyStep:
    def test_defaults(self):
        s = HoldKeyStep()
        assert s.action_type == ActionType.HOLD_KEY
        assert s.keys_hold == ""
        assert s.hold_duration == 0.0

    def test_describe(self):
        s = HoldKeyStep(keys_hold="shift", hold_duration=2.0)
        desc = s.describe()
        assert "shift" in desc
        assert "2.0" in desc

    def test_describe_fallback_to_key(self):
        s = HoldKeyStep(key="ctrl", hold_duration=1.5)
        desc = s.describe()
        assert "ctrl" in desc


class TestMouseScrollStep:
    def test_defaults(self):
        s = MouseScrollStep()
        assert s.action_type == ActionType.MOUSE_SCROLL
        assert s.scroll_clicks == 3
        assert s.scroll_delta_x == 0

    def test_describe_vertical(self):
        s = MouseScrollStep(scroll_clicks=5)
        desc = s.describe()
        assert isinstance(desc, str)
        assert len(desc) > 0

    def test_describe_both_directions(self):
        s = MouseScrollStep(scroll_clicks=3, scroll_delta_x=-2)
        desc = s.describe()
        assert isinstance(desc, str)
        assert len(desc) > 0


class TestMouseDragStep:
    def test_defaults(self):
        s = MouseDragStep()
        assert s.action_type == ActionType.MOUSE_DRAG
        assert s.start_x == 0
        assert s.start_y == 0
        assert s.end_x == 0
        assert s.end_y == 0
        assert s.duration == 0.5

    def test_describe(self):
        s = MouseDragStep(start_x=10, start_y=20, end_x=100, end_y=200)
        desc = s.describe()
        assert "10" in desc
        assert "200" in desc


class TestWaitStep:
    def test_defaults(self):
        s = WaitStep()
        assert s.action_type == ActionType.WAIT
        assert s.wait_seconds == 1.0

    def test_describe(self):
        s = WaitStep(wait_seconds=2.5)
        desc = s.describe()
        assert "2.5" in desc


class TestWaitRandomStep:
    def test_defaults(self):
        s = WaitRandomStep()
        assert s.action_type == ActionType.WAIT_RANDOM
        assert s.wait_min == 0.5
        assert s.wait_max == 2.0

    def test_describe(self):
        s = WaitRandomStep(wait_min=1.0, wait_max=3.0)
        desc = s.describe()
        assert isinstance(desc, str)


class TestKeyComboStep:
    def test_defaults(self):
        s = KeyComboStep()
        assert s.action_type == ActionType.KEY_COMBO
        assert s.combo_keys == ""
        assert s.combo_mode == "hold_tap"

    def test_describe(self):
        s = KeyComboStep(combo_keys="cmd+c", combo_mode="hold_tap")
        desc = s.describe()
        assert "cmd+c" in desc


class TestMultiKeySequenceStep:
    def test_defaults(self):
        s = MultiKeySequenceStep()
        assert s.action_type == ActionType.MULTI_KEY_SEQUENCE
        assert s.key_sequence == ""

    def test_describe(self):
        s = MultiKeySequenceStep(key_sequence="abc")
        desc = s.describe()
        assert "abc" in desc


class TestIdleBehaviorStep:
    def test_defaults(self):
        s = IdleBehaviorStep()
        assert s.action_type == ActionType.IDLE_BEHAVIOR
        assert s.idle_duration == 3.0
        assert s.jitter_intensity == 3

    def test_describe(self):
        s = IdleBehaviorStep(idle_duration=5.0)
        desc = s.describe()
        assert "5.0" in desc


class TestStartTimerStep:
    def test_defaults(self):
        s = StartTimerStep()
        assert s.action_type == ActionType.START_TIMER
        assert s.timer_name == ""
        assert s.timer_timeout == 0.0

    def test_describe_no_timeout(self):
        s = StartTimerStep(timer_name="test_timer")
        desc = s.describe()
        assert "test_timer" in desc

    def test_describe_with_timeout(self):
        s = StartTimerStep(timer_name="test_timer", timer_timeout=30.0)
        desc = s.describe()
        assert "test_timer" in desc
        assert "30.0" in desc


class TestPixelSearchStep:
    def test_defaults(self):
        s = PixelSearchStep()
        assert s.action_type == ActionType.PIXEL_SEARCH
        assert s.target_color is None
        assert s.color_tolerance == 10

    def test_describe(self):
        s = PixelSearchStep(target_color=(255, 0, 0))
        desc = s.describe()
        assert isinstance(desc, str)


class TestOcrCheckStep:
    def test_defaults(self):
        s = OcrCheckStep()
        assert s.action_type == ActionType.OCR_CHECK
        assert s.target_text == ""
        assert s.ocr_fuzzy is True

    def test_describe(self):
        s = OcrCheckStep(target_text="Hello")
        desc = s.describe()
        assert "Hello" in desc


# ── 序列化往返测试 ─────────────────────────────────────────────


def _get_dataclass_fields(obj: object) -> list[str]:
    import dataclasses
    return [f.name for f in dataclasses.fields(obj) if f.name != "_deprecated_warned"]


class TestSerializationRoundtrip:
    @pytest.mark.parametrize("step", [
        ClickImageStep(image_path="/test/img.png", threshold=0.9),
        ClickPosStep(pos_x=100, pos_y=200, clicks=2, button="right"),
        PressKeyStep(key="enter"),
        PressKeyStep(text="hello"),
        HoldKeyStep(keys_hold="shift", hold_duration=2.0),
        MouseScrollStep(scroll_clicks=5, scroll_delta_x=-3),
        MouseDragStep(start_x=10, start_y=20, end_x=100, end_y=200),
        WaitStep(wait_seconds=3.0),
        WaitRandomStep(wait_min=1.0, wait_max=5.0),
        KeyComboStep(combo_keys="cmd+c"),
        MultiKeySequenceStep(key_sequence="abc", key_interval_min=0.2),
        IdleBehaviorStep(idle_duration=5.0),
        StartTimerStep(timer_name="timer1", timer_timeout=60.0),
        PixelSearchStep(target_color=(255, 0, 0), color_tolerance=15),
        OcrCheckStep(target_text="test", ocr_fuzzy=False),
    ])
    def test_roundtrip(self, step):
        d = typed_step_to_dict(step)
        assert d["action_type"] == step.action_type.name
        restored = dict_to_typed_step(d)
        assert type(restored) == type(step)
        assert restored.action_type == step.action_type
        for field_name in _get_dataclass_fields(step):
            assert getattr(restored, field_name) == getattr(step, field_name), (
                f"{type(step).__name__}.{field_name}: "
                f"{getattr(restored, field_name)} != {getattr(step, field_name)}"
            )

    def test_click_image_enum_roundtrip(self):
        s = ClickImageStep(
            detect_mode=DetectMode.FAIL_IF_NOT_FOUND,
            found_action=FoundAction.RIGHT_CLICK,
        )
        d = typed_step_to_dict(s)
        assert d["detect_mode"] == "FAIL_IF_NOT_FOUND"
        assert d["found_action"] == "RIGHT_CLICK"
        restored = dict_to_typed_step(d)
        assert restored.detect_mode == DetectMode.FAIL_IF_NOT_FOUND
        assert restored.found_action == FoundAction.RIGHT_CLICK

    def test_unknown_fields_ignored(self):
        d = {"action_type": "CLICK_POS", "pos_x": 100, "unknown_field": "ignored"}
        step = dict_to_typed_step(d)
        assert isinstance(step, ClickPosStep)
        assert step.pos_x == 100
        assert not hasattr(step, "unknown_field")

    def test_missing_action_type_raises(self):
        with pytest.raises(ValueError, match="action_type"):
            dict_to_typed_step({"pos_x": 100})
