"""step_param_view 纯函数测试：重排 order 构造 + 字段值格式化。

这些函数被 Qt/tk 共用，是详情面板与列表重排的基础工具。
"""

from __future__ import annotations

from src.panel.components.step_param_view import (
    build_batch_move_order,
    build_bottom_order,
    build_move_order,
    build_top_order,
    format_field_value,
    iter_all_fields,
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
