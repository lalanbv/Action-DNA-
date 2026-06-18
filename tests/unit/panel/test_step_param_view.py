"""step_param_view 纯函数测试：重排 order 构造 + 字段值格式化。

这些函数被 Qt/tk 共用，是详情面板与列表重排的基础工具。
"""

from __future__ import annotations

from src.panel.components.step_param_view import (
    build_batch_move_order,
    build_block_insert_order,
    build_bottom_order,
    build_edge_order,
    build_move_order,
    build_top_order,
    drop_insert_target,
    format_field_value,
    iter_all_fields,
    key_field_rows,
    wait_text,
)
from src.core.action import ActionType
from src.core.step_types import STEP_CLASSES


class TestBuildMoveOrder:
    def test_insert_forward(self) -> None:
        # [A,B,C,D] 把 A(0)移到 2 → [B,C,A,D]
        assert build_move_order(4, 0, 2) == [1, 2, 0, 3]

    def test_insert_to_front(self) -> None:
        # [A,B,C,D] 把 D(3)移到 0 → [D,A,B,C]
        assert build_move_order(4, 3, 0) == [3, 0, 1, 2]

    def test_noop_when_same(self) -> None:
        assert build_move_order(3, 1, 1) == [0, 1, 2]

    def test_noop_when_out_of_range(self) -> None:
        assert build_move_order(3, 0, 5) == [0, 1, 2]
        assert build_move_order(3, 5, 0) == [0, 1, 2]


class TestBuildBatchMoveOrder:
    def test_block_up(self) -> None:
        # 选中 [1,2] 整体上移：[0,1,2,3] → [1,2,0,3]
        assert build_batch_move_order(4, [1, 2], -1) == [1, 2, 0, 3]

    def test_block_down(self) -> None:
        # 选中 [1,2] 整体下移：[0,1,2,3] → [0,3,1,2]
        assert build_batch_move_order(4, [1, 2], 1) == [0, 3, 1, 2]

    def test_already_at_top_no_change(self) -> None:
        # 选中 [0,1] 上移（已在顶部）→ 不变
        assert build_batch_move_order(4, [0, 1], -1) == [0, 1, 2, 3]

    def test_non_contiguous_up(self) -> None:
        # 选中 [0,2] 上移：idx0 已在顶不动，idx2 上移 → [0,2,1,3]
        assert build_batch_move_order(4, [0, 2], -1) == [0, 2, 1, 3]


class TestFormatFieldValue:
    def test_path_to_basename(self) -> None:
        s = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        s.image_path = "/x/y/btn.png"
        assert format_field_value(s, "image_path") == "btn.png"

    def test_float(self) -> None:
        s = STEP_CLASSES[ActionType.WAIT]()
        s.wait_seconds = 1.5
        assert format_field_value(s, "wait_seconds") == "1.5"

    def test_none_is_dash(self) -> None:
        s = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        # alt 阈值列表默认非 None；用一个明确 None 的可选属性测
        s.alt_thresholds = None  # type: ignore[assignment]
        assert format_field_value(s, "alt_thresholds") == "--"


class TestIterAllFields:
    def test_includes_dataclass_fields(self) -> None:
        s = STEP_CLASSES[ActionType.WAIT]()
        names = [name for name, _ in iter_all_fields(s)]
        assert "wait_seconds" in names

    def test_yields_formatted_values(self) -> None:
        s = STEP_CLASSES[ActionType.WAIT]()
        s.wait_seconds = 2.0
        pairs = dict(iter_all_fields(s))
        assert pairs["wait_seconds"] == "2.0"


class TestBuildTopBottomOrder:
    def test_top_keeps_relative_order(self) -> None:
        # 选中 [1,3] 置顶 → [1,3,0,2,4]
        assert build_top_order(5, [1, 3]) == [1, 3, 0, 2, 4]

    def test_top_already_at_top_no_change(self) -> None:
        assert build_top_order(4, [0, 1]) == [0, 1, 2, 3]

    def test_bottom_keeps_relative_order(self) -> None:
        # 选中 [0,2] 置底 → [1,3,4,0,2]
        assert build_bottom_order(5, [0, 2]) == [1, 3, 4, 0, 2]

    def test_bottom_already_at_bottom_no_change(self) -> None:
        assert build_bottom_order(3, [2]) == [0, 1, 2]

    def test_top_single(self) -> None:
        # 单项置顶 = build_move_order(n, src, 0)
        assert build_top_order(4, [2]) == build_move_order(4, 2, 0)


def test_key_fields_match_dataclass_fields() -> None:
    """守卫：KEY_FIELDS 字段名必须存在于对应 dataclass，防改名后静默降级为 --。"""
    import dataclasses
    from src.panel.components.step_key_fields import KEY_FIELDS

    for action_type, fields in KEY_FIELDS.items():
        valid = {f.name for f in dataclasses.fields(STEP_CLASSES[action_type])}
        for fname, _ in fields:
            assert fname in valid, f"{action_type.name}.{fname} 不在 dataclass 字段中"


def test_key_field_rows_and_wait_text() -> None:
    """共用 helper 冒烟：key_field_rows / wait_text。"""
    assert wait_text(STEP_CLASSES[ActionType.WAIT](wait_seconds=2.5)) == "2.5s"
    rows = key_field_rows(STEP_CLASSES[ActionType.CLICK_IMAGE]())
    assert rows, "CLICK_IMAGE 应有关键字段"
    assert all(isinstance(label, str) and isinstance(val, str) for label, val in rows)


class TestBuildBlockInsertOrder:
    def test_single_insert_before_target(self) -> None:
        # 单选 [0] insert 到 target=2 前 → [1,0,2,3]
        assert build_block_insert_order(4, [0], 2) == [1, 0, 2, 3]

    def test_multi_block_to_top(self) -> None:
        # 选中 [1,3] 拖到 0 → 块在顶部，其余顺延
        assert build_block_insert_order(5, [1, 3], 0) == [1, 3, 0, 2, 4]

    def test_no_selection_no_change(self) -> None:
        assert build_block_insert_order(4, [], 2) == [0, 1, 2, 3]

    def test_block_insert_append_at_end(self) -> None:
        # 选中 [0,1] 拖到列表下方(target=n)→ 追加末尾 [2,3,4,0,1]
        assert build_block_insert_order(5, [0, 1], 5) == [2, 3, 4, 0, 1]

    def test_block_insert_drop_on_self_is_noop(self) -> None:
        # 选中 [2,3],target 落在块内 → 原序
        assert build_block_insert_order(5, [2, 3], 2) == [0, 1, 2, 3, 4]


class TestDropInsertTarget:
    def test_below_all_appends(self) -> None:
        assert drop_insert_target(None, False, 5) == 5

    def test_upper_half_before(self) -> None:
        assert drop_insert_target(3, False, 5) == 3

    def test_lower_half_after(self) -> None:
        assert drop_insert_target(3, True, 5) == 4


class TestBuildEdgeOrder:
    def test_top_and_bottom(self) -> None:
        assert build_edge_order(5, [1, 3], to_top=True) == [1, 3, 0, 2, 4]
        assert build_edge_order(5, [0, 2], to_top=False) == [1, 3, 4, 0, 2]


class TestFormatFieldFixes:
    def test_path_field_basename(self) -> None:
        s = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        s.image_path = "/x/y/btn.png"
        assert format_field_value(s, "image_path") == "btn.png"

    def test_non_path_string_with_slash_not_truncated(self) -> None:
        """combo_keys 含 / 不应被 basename 截断（非 _path 字段）。"""
        s = STEP_CLASSES[ActionType.KEY_COMBO]()
        s.combo_keys = "Shift+a/Shift+b"
        assert format_field_value(s, "combo_keys") == "Shift+a/Shift+b"

    def test_found_action_uses_i18n_not_raw_name(self) -> None:
        """found_action 应显示 i18n 标签，而非裸 LEFT_CLICK。"""
        s = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        val = format_field_value(s, "found_action")
        assert val != "LEFT_CLICK"


class TestSemanticFieldI18nCoverage:
    """全部注册字段应走 i18n(与 describe() 同源 step_types._FIELD_VALUE_I18N),不残留裸值。"""

    def test_detect_mode_translated(self) -> None:
        s = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        assert format_field_value(s, "detect_mode") != "SKIP_IF_NOT_FOUND"

    def test_match_strategy_translated(self) -> None:
        s = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        assert format_field_value(s, "match_strategy") != "ADAPTIVE"

    def test_threshold_mode_translated(self) -> None:
        s = STEP_CLASSES[ActionType.CLICK_IMAGE]()
        assert format_field_value(s, "threshold_mode") != "GLOBAL"

    def test_combo_mode_translated(self) -> None:
        s = STEP_CLASSES[ActionType.KEY_COMBO]()
        assert format_field_value(s, "combo_mode") != "hold_tap"

    def test_button_translated(self) -> None:
        s = STEP_CLASSES[ActionType.CLICK_POS]()
        assert format_field_value(s, "button") != "left"

    def test_color_mode_translated(self) -> None:
        s = STEP_CLASSES[ActionType.PIXEL_SEARCH]()
        assert format_field_value(s, "color_mode") != "hsv"

    def test_unregistered_key_passthrough(self) -> None:
        """未注册的按键名字段保持原值(不翻译)。"""
        s = STEP_CLASSES[ActionType.PRESS_KEY](key="space")
        assert format_field_value(s, "key") == "space"
