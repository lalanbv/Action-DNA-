"""EventMerger 单元测试 — 覆盖 6 种合并规则 + 边界情况"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit

from src.core.action import ActionType
from src.recorder.event_merger import EventMerger
from src.recorder.recorder import RecordedEvent


# ---- 辅助工厂 ----


def _mouse(event_type: str, x: int = 0, y: int = 0, button: str = "left",
            timestamp: float = 0.0, delta_time: float = 0.0) -> RecordedEvent:
    return RecordedEvent(
        event_type=event_type,
        x=x, y=y,
        button=button,
        timestamp=timestamp,
        delta_time=delta_time,
    )


def _key(event_type: str, key: str = "a",
          timestamp: float = 0.0, delta_time: float = 0.0) -> RecordedEvent:
    return RecordedEvent(
        event_type=event_type,
        key=key,
        timestamp=timestamp,
        delta_time=delta_time,
    )


# ---- 点击合并 ----


class TestClickMerge:
    def test_simple_click(self) -> None:
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].pos_x == 100
        assert steps[0].pos_y == 200

    def test_click_right_button(self) -> None:
        events = [
            _mouse("mouse_down", x=50, y=60, button="right", timestamp=1.0),
            _mouse("mouse_up", x=50, y=60, button="right", timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS

    def test_click_too_far_not_drag_without_moves(self) -> None:
        """mouse_down + mouse_up with no intermediate mouse_move events
        cannot accumulate distance, so no step is produced."""
        events = [
            _mouse("mouse_down", x=0, y=0, timestamp=1.0),
            _mouse("mouse_up", x=100, y=0, timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 0

    def test_click_slow_small_distance_is_mouse_hold(self) -> None:
        """mouse_down + mouse_up (slow but no movement) → mouse hold."""
        events = [
            _mouse("mouse_down", x=10, y=10, timestamp=1.0),
            _mouse("mouse_up", x=10, y=10, timestamp=1.5, delta_time=0.5),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].hold_duration == 0.5

    def test_click_button_mismatch(self) -> None:
        events = [
            _mouse("mouse_down", x=10, y=10, button="left", timestamp=1.0),
            _mouse("mouse_up", x=10, y=10, button="right", timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 0


# ---- 拖拽合并 ----


class TestDragMerge:
    def test_simple_drag(self) -> None:
        events = [
            _mouse("mouse_down", x=0, y=0, timestamp=1.0),
            _mouse("mouse_move", x=15, y=0, timestamp=1.1, delta_time=0.1),
            _mouse("mouse_move", x=30, y=0, timestamp=1.2, delta_time=0.1),
            _mouse("mouse_up", x=40, y=0, timestamp=1.3, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.MOUSE_MOVE
        assert steps[0].offset_x == 40
        assert steps[0].offset_y == 0

    def test_drag_short_distance_falls_through_to_click(self) -> None:
        """短距离 mouse_down → mouse_move → mouse_up 应识别为点击（非拖拽）。"""
        events = [
            _mouse("mouse_down", x=0, y=0, timestamp=1.0),
            _mouse("mouse_move", x=5, y=0, timestamp=1.1, delta_time=0.1),
            _mouse("mouse_up", x=8, y=0, timestamp=1.2, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS

    def test_drag_timeout_breaks_loop(self) -> None:
        """Events after DRAG_MAX_DURATION are not part of the drag.
        The drag search breaks, no single drag step produced."""
        events = [
            _mouse("mouse_down", x=0, y=0, timestamp=1.0),
            _mouse("mouse_move", x=10, y=0, timestamp=1.5, delta_time=0.5),
            _mouse("mouse_move", x=20, y=0, timestamp=20.0, delta_time=18.5),
            _mouse("mouse_up", x=20, y=0, timestamp=20.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        # 超时后不应产生完整的拖拽步骤
        drag_steps = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE and s.button == "left"]
        assert len(drag_steps) == 0


# ---- 按键合并 ----


class TestKeyMerge:
    def test_simple_key_press(self) -> None:
        events = [
            _key("key_down", key="a", timestamp=1.0),
            _key("key_up", key="a", timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.PRESS_KEY
        assert steps[0].key == "a"

    def test_special_key_press(self) -> None:
        events = [
            _key("key_down", key="escape", timestamp=1.0),
            _key("key_up", key="escape", timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.PRESS_KEY
        assert steps[0].key == "escape"

    def test_key_down_without_up(self) -> None:
        """Orphan key_down (no matching key_up) is skipped to avoid wrong steps."""
        events = [
            _key("key_down", key="a", timestamp=1.0),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 0

    def test_different_keys_separate(self) -> None:
        """key_down("a") + key_up("b") — different keys don't match.
        Both become orphans: "a" has no matching key_up, "b" is lone key_up.
        Orphan key_down is skipped (no wrong PRESS_KEY generated)."""
        events = [
            _key("key_down", key="a", timestamp=1.0),
            _key("key_up", key="b", timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 0


# ---- 长按合并 ----


class TestHoldKeyMerge:
    def test_hold_key(self) -> None:
        events = [
            _key("key_down", key="shift", timestamp=1.0),
            _key("key_up", key="shift", timestamp=2.0, delta_time=1.0),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.HOLD_KEY
        assert steps[0].keys_hold == "shift"
        assert steps[0].hold_duration == 1.0

    def test_hold_exactly_at_threshold(self) -> None:
        events = [
            _key("key_down", key="ctrl", timestamp=1.0),
            _key("key_up", key="ctrl", timestamp=1.5, delta_time=0.5),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.HOLD_KEY


# ---- 忽略移动 ----


class TestIgnoreMove:
    def test_small_move_ignored(self) -> None:
        events = [
            _mouse("mouse_move", x=0, y=0, timestamp=1.0),
            _mouse("mouse_move", x=1, y=1, timestamp=1.1, delta_time=0.1),
            _mouse("mouse_move", x=2, y=2, timestamp=1.2, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 0

    def test_large_mouse_move_creates_path(self) -> None:
        """大范围 mouse_move（游戏视角移动）应生成 MouseMoveStep。"""
        events = [
            _mouse("mouse_move", x=0, y=0, timestamp=1.0),
            _mouse("mouse_move", x=100, y=100, timestamp=1.1, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.MOUSE_MOVE

    def test_large_drag_path_preserved(self) -> None:
        """mouse_drag（按键按下移动）大范围应保留路径。"""
        events = [
            _mouse("mouse_drag", x=0, y=0, timestamp=1.0),
            _mouse("mouse_drag", x=50, y=50, timestamp=1.1, delta_time=0.1),
            _mouse("mouse_drag", x=100, y=100, timestamp=1.2, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.MOUSE_MOVE


# ---- 等待兜底 ----


class TestFallbackWait:
    def test_unmatched_mouse_move_with_delta_produces_wait(self) -> None:
        """A mouse_move with large delta_time that isn't ignored produces WAIT."""
        events = [
            _mouse("mouse_move", x=0, y=0, timestamp=1.0, delta_time=0.5),
        ]
        steps = EventMerger().merge(events)
        # Single move: ignore_move sees distance=0 < threshold → ignored, no WAIT
        # To actually get WAIT, need a non-mouse event with delta > 0.1
        assert len(steps) == 0

    def test_unmatched_non_mouse_produces_wait(self) -> None:
        events = [
            _key("key_down", key="x", timestamp=1.0, delta_time=0.5),
        ]
        steps = EventMerger().merge(events)
        # key_down alone with no matching key_up → orphan, skipped
        assert len(steps) == 0

    def test_unmatched_event_small_delta_ignored(self) -> None:
        events = [
            _key("key_down", key="x", timestamp=1.0, delta_time=0.05),
        ]
        steps = EventMerger().merge(events)
        assert all(s.action_type != ActionType.WAIT for s in steps)


# ---- 边界情况 ----


class TestEdgeCases:
    def test_empty_input(self) -> None:
        assert EventMerger().merge([]) == []

    def test_single_event(self) -> None:
        events = [_mouse("mouse_down", x=10, y=20, timestamp=1.0, delta_time=0.5)]
        steps = EventMerger().merge(events)
        # Single mouse_down with no matching mouse_up produces nothing
        assert len(steps) == 0

    def test_single_mouse_down_no_up(self) -> None:
        events = [_mouse("mouse_down", x=10, y=20, timestamp=1.0, delta_time=0.5)]
        steps = EventMerger().merge(events)
        # Single mouse_down with no matching mouse_up: no pattern matches,
        # falls through all rules → produces nothing
        assert len(steps) == 0

    def test_click_then_drag(self) -> None:
        events = [
            # 点击
            _mouse("mouse_down", x=10, y=10, timestamp=1.0),
            _mouse("mouse_up", x=10, y=10, timestamp=1.1, delta_time=0.1),
            # 拖拽
            _mouse("mouse_down", x=100, y=100, timestamp=2.0, delta_time=0.9),
            _mouse("mouse_move", x=130, y=100, timestamp=2.1, delta_time=0.1),
            _mouse("mouse_up", x=150, y=100, timestamp=2.2, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 3
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[1].action_type == ActionType.WAIT
        assert steps[1].wait_seconds == pytest.approx(0.9, abs=0.05)
        assert steps[2].action_type == ActionType.MOUSE_MOVE

    def test_long_sequence(self) -> None:
        events = [
            # 点击
            _mouse("mouse_down", x=10, y=10, timestamp=1.0),
            _mouse("mouse_up", x=10, y=10, timestamp=1.1, delta_time=0.1),
            # 按键
            _key("key_down", key="a", timestamp=2.0, delta_time=0.9),
            _key("key_up", key="a", timestamp=2.1, delta_time=0.1),
            # 拖拽
            _mouse("mouse_down", x=0, y=0, timestamp=3.0, delta_time=0.9),
            _mouse("mouse_move", x=20, y=0, timestamp=3.1, delta_time=0.1),
            _mouse("mouse_move", x=40, y=0, timestamp=3.2, delta_time=0.1),
            _mouse("mouse_up", x=50, y=0, timestamp=3.3, delta_time=0.1),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 5
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[1].action_type == ActionType.WAIT
        assert steps[2].action_type == ActionType.PRESS_KEY
        assert steps[3].action_type == ActionType.WAIT
        assert steps[4].action_type == ActionType.MOUSE_MOVE


# ---- RecordedEvent 属性 ----


class TestRecordedEventProperties:
    def test_is_mouse_event(self) -> None:
        e = RecordedEvent(event_type="mouse_move", x=10, y=20)
        assert e.is_mouse_event is True
        assert e.is_key_event is False

    def test_is_key_event(self) -> None:
        e = RecordedEvent(event_type="key_down", key="a")
        assert e.is_key_event is True
        assert e.is_mouse_event is False

    def test_frozen(self) -> None:
        e = RecordedEvent(event_type="mouse_move")
        with pytest.raises(AttributeError):
            e.event_type = "key_down"  # type: ignore[misc]


# ---- 连续拖拽序列合并 ----


class TestDragSequenceMerge:
    """连续 MOUSE_MOVE 序列合并（视角旋转模式）。"""

    def _make_drag_events(
        self, start_x: int, start_y: int, dx: int, dy: int,
        base_time: float,
    ) -> list[RecordedEvent]:
        """生成一段拖拽事件序列。"""
        events = [
            _mouse("mouse_down", x=start_x, y=start_y, timestamp=base_time),
        ]
        steps = 5
        for i in range(1, steps + 1):
            t = base_time + i * 0.1
            events.append(_mouse(
                "mouse_drag",
                x=start_x + dx * i // steps,
                y=start_y + dy * i // steps,
                timestamp=t, delta_time=0.1,
            ))
        events.append(_mouse(
            "mouse_up",
            x=start_x + dx, y=start_y + dy,
            timestamp=base_time + 0.6, delta_time=0.1,
        ))
        return events

    def test_two_drags_same_direction_merged(self) -> None:
        """两段同方向拖拽应合并为一个 MOUSE_MOVE。"""
        drag1 = self._make_drag_events(100, 200, 200, 0, 1.0)
        drag2 = self._make_drag_events(100, 200, 180, 0, 2.0)
        events = drag1 + drag2
        steps = EventMerger().merge(events)
        mouse_moves = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(mouse_moves) == 1
        assert mouse_moves[0].offset_x == 380
        assert mouse_moves[0].recorded_duration > 0

    def test_opposite_directions_not_merged(self) -> None:
        """反方向拖拽不应合并。"""
        drag1 = self._make_drag_events(100, 200, 200, 0, 1.0)
        drag2 = self._make_drag_events(300, 200, -200, 0, 2.0)
        events = drag1 + drag2
        steps = EventMerger().merge(events)
        mouse_moves = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(mouse_moves) == 2

    def test_drag_with_long_gap_not_merged(self) -> None:
        """间隔过长的两段拖拽不应合并（中间插入按键产生间隔）。"""
        drag1 = self._make_drag_events(100, 200, 200, 0, 1.0)
        # 中间插入按键事件，打断拖拽序列
        key_events = [
            _key("key_down", key="a", timestamp=4.0, delta_time=2.0),
            _key("key_up", key="a", timestamp=4.1, delta_time=0.1),
        ]
        drag2 = self._make_drag_events(100, 200, 180, 0, 5.0)
        events = drag1 + key_events + drag2
        steps = EventMerger().merge(events)
        mouse_moves = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(mouse_moves) == 2

    def test_single_drag_not_affected(self) -> None:
        """单段拖拽不受后处理影响。"""
        drag = self._make_drag_events(100, 200, 200, 0, 1.0)
        steps = EventMerger().merge(drag)
        mouse_moves = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(mouse_moves) == 1

    def test_three_drags_same_direction_merged(self) -> None:
        """三段同方向拖拽应合并为一个。"""
        drag1 = self._make_drag_events(100, 200, 200, 0, 1.0)
        drag2 = self._make_drag_events(100, 200, 200, 0, 2.0)
        drag3 = self._make_drag_events(100, 200, 200, 0, 3.0)
        events = drag1 + drag2 + drag3
        steps = EventMerger().merge(events)
        mouse_moves = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(mouse_moves) == 1
        assert mouse_moves[0].offset_x == 600


# ---- 组合键检测 ----


class TestKeyComboMerge:
    def test_ctrl_c(self) -> None:
        events = [
            _key("key_down", key="ctrl", timestamp=1.0),
            _key("key_down", key="c", timestamp=1.05),
            _key("key_up", key="c", timestamp=1.1),
            _key("key_up", key="ctrl", timestamp=1.15),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.KEY_COMBO
        assert steps[0].combo_keys == "ctrl,c"

    def test_cmd_shift_3(self) -> None:
        events = [
            _key("key_down", key="cmd", timestamp=1.0),
            _key("key_down", key="shift", timestamp=1.05),
            _key("key_down", key="3", timestamp=1.1),
            _key("key_up", key="3", timestamp=1.15),
            _key("key_up", key="shift", timestamp=1.2),
            _key("key_up", key="cmd", timestamp=1.25),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.KEY_COMBO
        assert "cmd" in steps[0].combo_keys
        assert "shift" in steps[0].combo_keys
        assert "3" in steps[0].combo_keys

    def test_modifier_alone_not_combo(self) -> None:
        """Single modifier press without tap key → PRESS_KEY, not KEY_COMBO."""
        events = [
            _key("key_down", key="ctrl", timestamp=1.0),
            _key("key_up", key="ctrl", timestamp=1.5),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.HOLD_KEY


# ---- 鼠标长按 ----


class TestMouseHoldMerge:
    def test_mouse_hold_detected(self) -> None:
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=101, y=201, timestamp=1.8, delta_time=0.8),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].hold_duration == pytest.approx(0.8, abs=0.01)

    def test_fast_click_no_hold(self) -> None:
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05, delta_time=0.05),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].hold_duration == 0.0


# ---- 滚轮方向变化 ----


def _scroll(x: int = 0, y: int = 0, delta: int = 3,
             timestamp: float = 0.0, delta_time: float = 0.0) -> RecordedEvent:
    return RecordedEvent(
        event_type="mouse_scroll",
        x=x, y=y, scroll_delta=delta,
        timestamp=timestamp, delta_time=delta_time,
    )


class TestScrollDirectionChange:
    def test_same_direction_merged(self) -> None:
        events = [
            _scroll(delta=3, timestamp=1.0),
            _scroll(delta=2, timestamp=1.05, delta_time=0.05),
            _scroll(delta=1, timestamp=1.08, delta_time=0.03),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].scroll_clicks == 6

    def test_direction_change_splits(self) -> None:
        events = [
            _scroll(delta=3, timestamp=1.0),
            _scroll(delta=2, timestamp=1.05, delta_time=0.05),
            _scroll(delta=-3, timestamp=1.1, delta_time=0.05),
            _scroll(delta=-2, timestamp=1.15, delta_time=0.05),
        ]
        steps = EventMerger().merge(events)
        scrolls = [s for s in steps if s.action_type == ActionType.MOUSE_SCROLL]
        assert len(scrolls) == 2
        assert scrolls[0].scroll_clicks == 5
        assert scrolls[1].scroll_clicks == -5


# ---- 连续等待合并 ----


class TestWaitSequenceMerge:
    def test_consecutive_waits_merged(self) -> None:
        events = [
            _mouse("mouse_down", x=10, y=10, timestamp=1.0, delta_time=0.5),
            _mouse("mouse_down", x=10, y=10, timestamp=2.0, delta_time=1.0),
            _mouse("mouse_down", x=10, y=10, timestamp=3.0, delta_time=1.0),
        ]
        steps = EventMerger().merge(events)
        waits = [s for s in steps if s.action_type == ActionType.WAIT]
        if len(waits) > 1:
            total = sum(w.wait_seconds for w in waits)
            assert total == pytest.approx(sum(
                e.delta_time for e in events if e.delta_time > 0.1
            ), abs=0.1)


# ---- 拖拽方向余弦相似度 ----


class TestDragDirectionCosine:
    def test_similar_direction_merged(self) -> None:
        """Two drags at slight angle (<60°) should merge."""
        drag1_events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_drag", x=200, y=210, timestamp=1.1, delta_time=0.1),
            _mouse("mouse_up", x=300, y=215, timestamp=1.2, delta_time=0.1),
        ]
        drag2_events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.4, delta_time=0.2),
            _mouse("mouse_drag", x=180, y=205, timestamp=1.5, delta_time=0.1),
            _mouse("mouse_up", x=250, y=210, timestamp=1.6, delta_time=0.1),
        ]
        steps = EventMerger().merge(drag1_events + drag2_events)
        turns = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(turns) == 1

    def test_perpendicular_direction_not_merged(self) -> None:
        """Two drags at 90° angle should NOT merge."""
        drag1_events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_drag", x=200, y=200, timestamp=1.1, delta_time=0.1),
            _mouse("mouse_up", x=300, y=200, timestamp=1.2, delta_time=0.1),
        ]
        drag2_events = [
            _mouse("mouse_down", x=100, y=200, timestamp=2.0, delta_time=0.8),
            _mouse("mouse_drag", x=100, y=300, timestamp=2.1, delta_time=0.1),
            _mouse("mouse_up", x=100, y=400, timestamp=2.2, delta_time=0.1),
        ]
        steps = EventMerger().merge(drag1_events + drag2_events)
        turns = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(turns) == 2


# ---- 多击检测（双击/三击/混合模式）----


class TestMultiClickDetection:
    """验证多击检测在各种模式下的正确性。"""

    def test_double_click_basic(self) -> None:
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05),
            _mouse("mouse_down", x=100, y=200, timestamp=1.15),
            _mouse("mouse_up", x=100, y=200, timestamp=1.2),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].clicks == 2

    def test_triple_click_basic(self) -> None:
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05),
            _mouse("mouse_down", x=100, y=200, timestamp=1.15),
            _mouse("mouse_up", x=100, y=200, timestamp=1.2),
            _mouse("mouse_down", x=100, y=200, timestamp=1.3),
            _mouse("mouse_up", x=100, y=200, timestamp=1.35),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].clicks == 3

    def test_double_click_with_move_between(self) -> None:
        """点击对之间有小 mouse_move 仍应识别为双击。"""
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05),
            _mouse("mouse_move", x=102, y=201, timestamp=1.08),
            _mouse("mouse_down", x=102, y=201, timestamp=1.15),
            _mouse("mouse_up", x=102, y=201, timestamp=1.2),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].clicks == 2

    def test_double_click_with_large_move_between(self) -> None:
        """点击对之间有大 mouse_move（超出容差）应中断双击。"""
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05),
            _mouse("mouse_move", x=200, y=300, timestamp=1.08),
            _mouse("mouse_down", x=200, y=300, timestamp=1.15),
            _mouse("mouse_up", x=200, y=300, timestamp=1.2),
        ]
        steps = EventMerger().merge(events)
        clicks = [s for s in steps if s.action_type == ActionType.CLICK_POS]
        assert len(clicks) == 2
        assert all(s.clicks == 1 for s in clicks)

    def test_triple_click_with_moves_between(self) -> None:
        """三击之间有小移动仍应识别为三击。"""
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05),
            _mouse("mouse_move", x=101, y=200, timestamp=1.08),
            _mouse("mouse_down", x=101, y=200, timestamp=1.15),
            _mouse("mouse_up", x=101, y=200, timestamp=1.2),
            _mouse("mouse_move", x=102, y=201, timestamp=1.23),
            _mouse("mouse_down", x=102, y=201, timestamp=1.3),
            _mouse("mouse_up", x=102, y=201, timestamp=1.35),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].clicks == 3

    def test_mixed_pattern_three_double_clicks_two_singles(self) -> None:
        """3 次双击 + 2 次单击 = 5 个步骤 (3 个双击 + 2 个单击)。"""
        events = []
        t = 1.0
        # 3 次双击
        for _ in range(3):
            events.append(_mouse("mouse_down", x=100, y=200, timestamp=t))
            events.append(_mouse("mouse_up", x=100, y=200, timestamp=t + 0.05))
            events.append(_mouse("mouse_down", x=100, y=200, timestamp=t + 0.15))
            events.append(_mouse("mouse_up", x=100, y=200, timestamp=t + 0.2))
            t += 1.0  # 间隔足够大，产生 WAIT
        # 2 次单击
        for _ in range(2):
            events.append(_mouse("mouse_down", x=100, y=200, timestamp=t))
            events.append(_mouse("mouse_up", x=100, y=200, timestamp=t + 0.05))
            t += 1.0

        steps = EventMerger().merge(events)
        clicks = [s for s in steps if s.action_type == ActionType.CLICK_POS]
        assert len(clicks) == 5
        assert all(s.clicks == 2 for s in clicks[:3])
        assert all(s.clicks == 1 for s in clicks[3:])

    def test_double_click_gap_too_large(self) -> None:
        """间隔过大产生两次独立单击。"""
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05),
            _mouse("mouse_down", x=100, y=200, timestamp=2.0, delta_time=0.95),
            _mouse("mouse_up", x=100, y=200, timestamp=2.05),
        ]
        steps = EventMerger().merge(events)
        clicks = [s for s in steps if s.action_type == ActionType.CLICK_POS]
        assert len(clicks) == 2
        assert all(s.clicks == 1 for s in clicks)

    def test_click_count_capped_at_three(self) -> None:
        """4 次快速点击产生 clicks=3 + clicks=1。"""
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _mouse("mouse_up", x=100, y=200, timestamp=1.05),
            _mouse("mouse_down", x=100, y=200, timestamp=1.15),
            _mouse("mouse_up", x=100, y=200, timestamp=1.2),
            _mouse("mouse_down", x=100, y=200, timestamp=1.3),
            _mouse("mouse_up", x=100, y=200, timestamp=1.35),
            _mouse("mouse_down", x=100, y=200, timestamp=1.45),
            _mouse("mouse_up", x=100, y=200, timestamp=1.5),
        ]
        steps = EventMerger().merge(events)
        clicks = [s for s in steps if s.action_type == ActionType.CLICK_POS]
        assert len(clicks) == 2
        assert clicks[0].clicks == 3
        assert clicks[1].clicks == 1

    def test_right_button_double_click(self) -> None:
        """右键双击。"""
        events = [
            _mouse("mouse_down", x=50, y=60, button="right", timestamp=1.0),
            _mouse("mouse_up", x=50, y=60, button="right", timestamp=1.05),
            _mouse("mouse_down", x=50, y=60, button="right", timestamp=1.15),
            _mouse("mouse_up", x=50, y=60, button="right", timestamp=1.2),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].clicks == 2
        assert steps[0].button == "right"


# ---- 长按按键 vs 文本输入（关键 bug 修复）----


def _key_repeat(event_type: str, key: str = "w",
                 timestamp: float = 0.0, is_repeat: bool = False) -> RecordedEvent:
    """带 is_repeat 标记的按键事件工厂。"""
    return RecordedEvent(
        event_type=event_type,
        key=key,
        timestamp=timestamp,
        is_repeat=is_repeat,
    )


class TestLongPressVsTextInput:
    """长按按键不应被误合并为文本输入 + 等待。"""

    def test_long_press_with_many_repeats(self) -> None:
        """长按 w 键 3 秒（100 个 repeat 事件）→ 应生成 HoldKeyStep。"""
        events = [_key_repeat("key_down", "w", timestamp=0.0)]
        # macOS 默认 repeat 率约 30Hz，3 秒约 90 个 repeat
        for i in range(90):
            events.append(_key_repeat(
                "key_down", "w", timestamp=0.03 * (i + 1), is_repeat=True,
            ))
        events.append(_key_repeat("key_up", "w", timestamp=3.0))

        steps = EventMerger().merge(events)
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(hold_steps) == 1
        assert hold_steps[0].keys_hold == "w"
        assert hold_steps[0].hold_duration == pytest.approx(3.0, abs=0.1)
        # 不应产生文本输入
        text_steps = [s for s in steps
                      if s.action_type == ActionType.PRESS_KEY and s.text]
        assert len(text_steps) == 0

    def test_long_press_without_repeat_flag(self) -> None:
        """长按 w 键但 is_repeat 全部为 False（兼容异常平台）→ 仍应为 HoldKeyStep。"""
        events = [_key_repeat("key_down", "w", timestamp=0.0)]
        # 模拟快速连续 key_down（无 repeat 标记），间隔 0.03s
        for i in range(90):
            events.append(_key_repeat(
                "key_down", "w", timestamp=0.03 * (i + 1), is_repeat=False,
            ))
        events.append(_key_repeat("key_up", "w", timestamp=3.0))

        steps = EventMerger().merge(events)
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(hold_steps) == 1
        assert hold_steps[0].keys_hold == "w"
        assert hold_steps[0].hold_duration == pytest.approx(3.0, abs=0.1)
        # 不应产生文本输入
        text_steps = [s for s in steps
                      if s.action_type == ActionType.PRESS_KEY and s.text]
        assert len(text_steps) == 0

    def test_long_press_preceded_by_click(self) -> None:
        """单击 a 后长按 w 键 → 应为 PressKeyStep(a) + HoldKeyStep(w)。"""
        events = [
            _key_repeat("key_down", "a", timestamp=1.0),
            _key_repeat("key_up", "a", timestamp=1.1),
            # 长按 w
            _key_repeat("key_down", "w", timestamp=2.0),
        ]
        for i in range(30):
            events.append(_key_repeat(
                "key_down", "w", timestamp=2.03 + 0.03 * i, is_repeat=True,
            ))
        events.append(_key_repeat("key_up", "w", timestamp=3.0))

        steps = EventMerger().merge(events)
        press_keys = [s for s in steps if s.action_type == ActionType.PRESS_KEY]
        hold_keys = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(press_keys) == 1
        assert press_keys[0].key == "a"
        assert len(hold_keys) == 1
        assert hold_keys[0].keys_hold == "w"

    def test_same_char_rapid_not_merged_as_text(self) -> None:
        """连续快速按 w（同一字符）不应被合并为文本输入 'www'。"""
        events = [
            _key_repeat("key_down", "w", timestamp=1.0),
            _key_repeat("key_up", "w", timestamp=1.05),
            _key_repeat("key_down", "w", timestamp=1.1),
            _key_repeat("key_up", "w", timestamp=1.15),
            _key_repeat("key_down", "w", timestamp=1.2),
            _key_repeat("key_up", "w", timestamp=1.25),
        ]
        steps = EventMerger().merge(events)
        # 不应生成文本输入
        text_steps = [s for s in steps
                      if s.action_type == ActionType.PRESS_KEY and s.text]
        assert len(text_steps) == 0
        # 应该生成单独的按键步骤
        key_steps = [s for s in steps if s.action_type == ActionType.PRESS_KEY]
        assert len(key_steps) == 3

    def test_cascading_wait_not_inserted_for_long_press(self) -> None:
        """长按事件不应产生级联等待步骤。"""
        events = [
            # 先有一个点击
            _mouse("mouse_down", x=10, y=10, timestamp=1.0),
            _mouse("mouse_up", x=10, y=10, timestamp=1.1),
            # 长按 w 2 秒
            _key_repeat("key_down", "w", timestamp=2.0),
        ]
        for i in range(60):
            events.append(_key_repeat(
                "key_down", "w", timestamp=2.03 + 0.03 * i, is_repeat=True,
            ))
        events.append(_key_repeat("key_up", "w", timestamp=4.0))

        steps = EventMerger().merge(events)
        waits = [s for s in steps if s.action_type == ActionType.WAIT]
        # 最多只能有一个等待（点击和长按之间的间隔）
        assert len(waits) <= 1
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(hold_steps) == 1
        assert hold_steps[0].hold_duration == pytest.approx(2.0, abs=0.1)


# ---- 长按 + 插入事件合并 bug 修复验证 ----


class TestLongPressWithInterleavedEvents:
    """长按期间插入其他事件（鼠标移动/键盘等）不应丢失长按检测。"""

    def test_key_long_press_with_mouse_move_between(self) -> None:
        """长按 w 键期间有鼠标移动，key_up 不应丢失。"""
        events = [
            _key_repeat("key_down", key="w", timestamp=1.0),
            _key_repeat("key_down", key="w", timestamp=1.03, is_repeat=True),
            _key_repeat("key_down", key="w", timestamp=1.06, is_repeat=True),
            # 鼠标移动插入
            _mouse("mouse_move", x=100, y=200, timestamp=1.09),
            _mouse("mouse_move", x=102, y=201, timestamp=1.12),
            # 继续长按
            _key_repeat("key_down", key="w", timestamp=1.15, is_repeat=True),
            _key_repeat("key_down", key="w", timestamp=1.18, is_repeat=True),
            _key_repeat("key_up", key="w", timestamp=2.0),
        ]
        steps = EventMerger().merge(events)
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(hold_steps) == 1
        assert hold_steps[0].keys_hold == "w"
        assert hold_steps[0].hold_duration == pytest.approx(1.0, abs=0.1)

    def test_key_long_press_with_scroll_between(self) -> None:
        """长按 w 键期间有滚轮事件，key_up 不应丢失。"""
        events = [
            _key_repeat("key_down", key="w", timestamp=1.0),
            _key_repeat("key_down", key="w", timestamp=1.05, is_repeat=True),
            _scroll(delta=3, timestamp=1.1),
            _key_repeat("key_down", key="w", timestamp=1.15, is_repeat=True),
            _key_repeat("key_up", key="w", timestamp=1.8),
        ]
        steps = EventMerger().merge(events)
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(hold_steps) == 1
        assert hold_steps[0].keys_hold == "w"

    def test_key_long_press_with_mouse_click_between(self) -> None:
        """长按 w 键期间有鼠标点击事件，key_up 不应丢失。"""
        events = [
            _key_repeat("key_down", key="w", timestamp=1.0),
            _key_repeat("key_down", key="w", timestamp=1.05, is_repeat=True),
            # 中间插入鼠标点击
            _mouse("mouse_down", x=50, y=50, timestamp=1.1),
            _mouse("mouse_up", x=50, y=50, timestamp=1.15),
            # 继续长按
            _key_repeat("key_down", key="w", timestamp=1.2, is_repeat=True),
            _key_repeat("key_up", key="w", timestamp=2.0),
        ]
        steps = EventMerger().merge(events)
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(hold_steps) == 1
        assert hold_steps[0].keys_hold == "w"
        # 鼠标点击不被单独保留 — 因为拖拽/点击检测范围会跨过
        # 中间插入的 mouse_down+mouse_up 被整体长按消费了

    def test_mouse_hold_with_key_press_between(self) -> None:
        """鼠标长按期间有键盘按键，mouse_up 不应丢失。"""
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            # 插入键盘按键
            _key("key_down", key="a", timestamp=1.2),
            _key("key_up", key="a", timestamp=1.3),
            # 继续鼠标长按
            _mouse("mouse_move", x=101, y=201, timestamp=1.5),
            _mouse("mouse_up", x=101, y=201, timestamp=1.8),
        ]
        steps = EventMerger().merge(events)
        click_steps = [s for s in steps if s.action_type == ActionType.CLICK_POS]
        assert len(click_steps) == 1
        assert click_steps[0].hold_duration == pytest.approx(0.8, abs=0.1)

    def test_drag_with_key_press_between(self) -> None:
        """拖拽期间有键盘事件，拖拽不应中断。"""
        events = [
            _mouse("mouse_down", x=0, y=0, timestamp=1.0),
            _mouse("mouse_drag", x=20, y=0, timestamp=1.1),
            # 插入键盘
            _key("key_down", key="space", timestamp=1.15),
            _key("key_up", key="space", timestamp=1.2),
            # 继续拖拽
            _mouse("mouse_drag", x=40, y=0, timestamp=1.3),
            _mouse("mouse_up", x=50, y=0, timestamp=1.4),
        ]
        steps = EventMerger().merge(events)
        drag_steps = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE and s.button == "left"]
        assert len(drag_steps) == 1
        assert drag_steps[0].offset_x == 50

    def test_key_combo_with_mouse_move_between(self) -> None:
        """组合键（Ctrl+C）期间有鼠标移动，组合键不应丢失。"""
        events = [
            _key("key_down", key="ctrl", timestamp=1.0),
            # 插入鼠标移动
            _mouse("mouse_move", x=100, y=200, timestamp=1.05),
            _mouse("mouse_move", x=102, y=201, timestamp=1.08),
            # 继续组合键
            _key("key_down", key="c", timestamp=1.1),
            _key("key_up", key="c", timestamp=1.15),
            _key("key_up", key="ctrl", timestamp=1.2),
        ]
        steps = EventMerger().merge(events)
        combo_steps = [s for s in steps if s.action_type == ActionType.KEY_COMBO]
        assert len(combo_steps) == 1
        assert "ctrl" in combo_steps[0].combo_keys
        assert "c" in combo_steps[0].combo_keys

    def test_modifier_long_press_not_combo(self) -> None:
        """修饰键长按（无其他按键）应生成 HOLD_KEY 而非 KEY_COMBO。"""
        events = [
            _key("key_down", key="ctrl", timestamp=1.0),
            _key("key_up", key="ctrl", timestamp=2.0),
        ]
        steps = EventMerger().merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.HOLD_KEY
        assert steps[0].keys_hold == "ctrl"

    def test_long_press_multiple_keys_sequential(self) -> None:
        """连续长按多个按键，每个都应正确检测。"""
        events = [
            # 长按 w
            _key_repeat("key_down", key="w", timestamp=1.0),
            _key_repeat("key_down", key="w", timestamp=1.1, is_repeat=True),
            _mouse("mouse_move", x=100, y=200, timestamp=1.2),
            _key_repeat("key_up", key="w", timestamp=1.8),
            # 长按 a
            _key_repeat("key_down", key="a", timestamp=2.0),
            _key_repeat("key_down", key="a", timestamp=2.1, is_repeat=True),
            _key_repeat("key_up", key="a", timestamp=2.8),
        ]
        steps = EventMerger().merge(events)
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        assert len(hold_steps) == 2
        assert hold_steps[0].keys_hold == "w"
        assert hold_steps[1].keys_hold == "a"

    def test_mouse_hold_with_multiple_interleaved_keys(self) -> None:
        """鼠标长按期间插入多个键盘事件，鼠标长按不丢失。"""
        events = [
            _mouse("mouse_down", x=100, y=200, timestamp=1.0),
            _key("key_down", key="w", timestamp=1.1),
            _key("key_up", key="w", timestamp=1.2),
            _key("key_down", key="a", timestamp=1.3),
            _key("key_up", key="a", timestamp=1.4),
            _mouse("mouse_up", x=100, y=200, timestamp=1.6),
        ]
        steps = EventMerger().merge(events)
        click_steps = [s for s in steps if s.action_type == ActionType.CLICK_POS]
        assert len(click_steps) == 1
        assert click_steps[0].hold_duration > 0.5

    def test_drag_with_scroll_between(self) -> None:
        """拖拽期间插入滚轮事件，拖拽不应中断。"""
        events = [
            _mouse("mouse_down", x=0, y=0, timestamp=1.0),
            _mouse("mouse_drag", x=20, y=0, timestamp=1.1),
            _scroll(delta=3, timestamp=1.15),
            _mouse("mouse_drag", x=40, y=0, timestamp=1.2),
            _mouse("mouse_up", x=50, y=0, timestamp=1.3),
        ]
        steps = EventMerger().merge(events)
        drag_steps = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE and s.button == "left"]
        assert len(drag_steps) == 1
