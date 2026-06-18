"""step_types 字段值翻译注册表 + describe() 行为保持回归。"""
from __future__ import annotations

from src.core.action import FoundAction
from src.core.step_types import (
    ClickImageStep,
    KeyComboStep,
    field_value_i18n_key,
)


def test_found_action_lookup() -> None:
    assert field_value_i18n_key("found_action", "LEFT_CLICK") == "dialog.found_action.left_click"
    assert field_value_i18n_key("found_action", "OUTPUT_COORD") == "dialog.found_action.output_coord"


def test_combo_mode_lookup() -> None:
    assert field_value_i18n_key("combo_mode", "hold_tap") == "common.mode.hold_tap"
    assert field_value_i18n_key("combo_mode", "sequence") == "common.mode.sequence"


def test_detect_match_threshold_lookup() -> None:
    assert field_value_i18n_key("detect_mode", "SKIP_IF_NOT_FOUND") == "dialog.detect_mode.skip_if_not_found"
    assert field_value_i18n_key("match_strategy", "ADAPTIVE") == "dialog.match_strategy.adaptive"
    assert field_value_i18n_key("threshold_mode", "GLOBAL") == "dialog.threshold_mode.global"


def test_button_color_mode_lookup() -> None:
    # button 复用既有 dialog.btn.left/right/middle(鼠标按键标签),DRY
    assert field_value_i18n_key("button", "left") == "dialog.btn.left"
    assert field_value_i18n_key("button", "right") == "dialog.btn.right"
    assert field_value_i18n_key("button", "middle") == "dialog.btn.middle"
    assert field_value_i18n_key("color_mode", "hsv") == "dialog.color_mode.hsv"
    assert field_value_i18n_key("color_mode", "rgb") == "dialog.color_mode.rgb"


def test_unknown_returns_none() -> None:
    assert field_value_i18n_key("found_action", "NOPE") is None
    assert field_value_i18n_key("not_a_field", "x") is None


def test_click_image_describe_translates_found_action() -> None:
    s = ClickImageStep(image_path="/x/btn.png", found_action=FoundAction.RIGHT_CLICK)
    desc = s.describe()
    assert "RIGHT_CLICK" not in desc
    assert "右键点击" in desc or "Right" in desc  # 视当前 locale


def test_key_combo_describe_translates_mode() -> None:
    s = KeyComboStep(combo_keys="ctrl+c", combo_mode="sequence")
    desc = s.describe()
    # 模式名应被翻译,不应残留裸 "sequence" 作为模式标签
    assert "顺序连按" in desc or "Sequential" in desc
