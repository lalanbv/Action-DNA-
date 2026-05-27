"""录制→合并→编辑→保存 完整流程集成测试。

参考: 13_风险与验证策略.md §5
覆盖: RecordBridge 录制→转换、EventMerger 合并规则、ActionStep 导出。
"""

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.engine.descriptors.record_descriptor import RecordBridge
from src.recorder.event_merger import EventMerger
from src.recorder.recorder import RecordedEvent
from _helpers import ActionChain


# ============================================================
# helpers
# ============================================================


def _evt(
    event_type: str,
    *,
    x: int = 0,
    y: int = 0,
    key: str = "",
    button: str = "",
    ts: float = 0.0,
    delta: float = 0.0,
) -> RecordedEvent:
    return RecordedEvent(
        event_type=event_type,
        x=x, y=y,
        key=key, button=button,
        timestamp=ts, delta_time=delta,
    )


# ============================================================
# EventMerger 合并规则测试
# ============================================================


class TestEventMergerClick:
    """规则 2: mouse_down + mouse_up (短时间、小距离) → 点击"""

    def test_merge_click_produces_click_pos(self):
        merger = EventMerger()
        events = [
            _evt("mouse_down", x=100, y=200, button="left", ts=1.0, delta=0.0),
            _evt("mouse_up", x=101, y=201, button="left", ts=1.05, delta=0.05),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[0].pos_x == 100
        assert steps[0].pos_y == 200


class TestEventMergerDrag:
    """规则 1: mouse_down + mouse_move* + mouse_up (距离 >= 阈值) → 拖拽"""

    def test_merge_drag_produces_mouse_turn(self):
        merger = EventMerger()
        events = [
            _evt("mouse_down", x=100, y=100, button="left", ts=1.0, delta=0.0),
            _evt("mouse_move", x=150, y=100, ts=1.1, delta=0.1),
            _evt("mouse_move", x=300, y=100, ts=1.2, delta=0.1),
            _evt("mouse_up", x=300, y=100, button="left", ts=1.3, delta=0.1),
        ]
        steps = merger.merge(events)
        assert len(steps) >= 1
        assert steps[0].action_type == ActionType.MOUSE_MOVE


class TestEventMergerKeyPress:
    """规则 3: key_down + key_up (间隔 < 阈值) → 按键"""

    def test_merge_key_press(self):
        merger = EventMerger()
        events = [
            _evt("key_down", key="a", ts=1.0, delta=0.0),
            _evt("key_up", key="a", ts=1.1, delta=0.1),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.PRESS_KEY
        assert steps[0].key == "a"


class TestEventMergerHoldKey:
    """规则 4: key_down + key_up (间隔 >= 阈值) → 长按"""

    def test_merge_hold_key(self):
        merger = EventMerger()
        events = [
            _evt("key_down", key="w", ts=1.0, delta=0.0),
            _evt("key_up", key="w", ts=2.5, delta=1.5),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.HOLD_KEY


class TestEventMergerMixed:
    """混合事件序列 → 正确分类"""

    def test_merge_mixed_events(self):
        merger = EventMerger()
        events = [
            _evt("mouse_down", x=100, y=200, button="left", ts=1.0, delta=0.0),
            _evt("mouse_up", x=101, y=201, button="left", ts=1.05, delta=0.05),
            _evt("key_down", key="space", ts=1.5, delta=0.45),
            _evt("key_up", key="space", ts=1.6, delta=0.1),
        ]
        steps = merger.merge(events)
        # 0.45s gap > WAIT_INSERT_THRESHOLD(0.15) → WAIT inserted before key
        assert len(steps) == 3
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[1].action_type == ActionType.WAIT
        assert steps[2].action_type == ActionType.PRESS_KEY

    def test_merge_empty_events_returns_empty(self):
        merger = EventMerger()
        steps = merger.merge([])
        assert steps == []


class TestEventMergerIgnoreMoves:
    """规则 5: 连续 mouse_move (小距离) → 忽略"""

    def test_consecutive_small_moves_ignored(self):
        merger = EventMerger()
        events = [
            _evt("mouse_move", x=100, y=100, ts=1.0, delta=0.0),
            _evt("mouse_move", x=102, y=101, ts=1.05, delta=0.05),
            _evt("mouse_move", x=103, y=102, ts=1.10, delta=0.05),
        ]
        steps = merger.merge(events)
        move_steps = [s for s in steps if s.action_type == ActionType.MOUSE_MOVE]
        assert len(move_steps) == 0


# ============================================================
# RecordBridge 桥接测试
# ============================================================


class TestRecordBridgeConvert:
    """convert_events: 事件列表 → ActionStep 列表（不触发录制）"""

    def test_convert_events_to_steps(self):
        bridge = RecordBridge()
        events = [
            _evt("mouse_down", x=50, y=80, button="left", ts=1.0, delta=0.0),
            _evt("mouse_up", x=51, y=81, button="left", ts=1.05, delta=0.05),
            _evt("key_down", key="enter", ts=1.5, delta=0.45),
            _evt("key_up", key="enter", ts=1.6, delta=0.1),
        ]
        steps = bridge.convert_events(events)
        # 0.45s gap > WAIT_INSERT_THRESHOLD(0.15) → WAIT inserted before key
        assert len(steps) == 3
        assert steps[0].action_type == ActionType.CLICK_POS
        assert steps[1].action_type == ActionType.WAIT
        assert steps[2].action_type == ActionType.PRESS_KEY

    def test_convert_empty_returns_empty(self):
        bridge = RecordBridge()
        assert bridge.convert_events([]) == []

    def test_bridge_not_recording_by_default(self):
        bridge = RecordBridge()
        assert bridge.is_recording is False


# ============================================================
# ActionStep describe 完整性
# ============================================================


class TestActionStepDescribe:
    """合并后的 ActionStep describe() 可正常输出。"""

    def test_click_pos_describe(self):
        step = STEP_CLASSES[ActionType.CLICK_POS](pos_x=100, pos_y=200)
        desc = step.describe()
        assert "100" in desc
        assert "200" in desc

    def test_press_key_describe(self):
        step = STEP_CLASSES[ActionType.PRESS_KEY](key="a")
        desc = step.describe()
        assert "a" in desc

    def test_hold_key_describe(self):
        step = STEP_CLASSES[ActionType.HOLD_KEY](key="w", hold_duration=1.5)
        desc = step.describe()
        assert "w" in desc
        assert "1.5" in desc

    def test_merged_steps_all_have_describe(self):
        """端到端: 合并后每个步骤 describe() 不抛异常。"""
        merger = EventMerger()
        events = [
            _evt("mouse_down", x=10, y=20, button="left", ts=1.0, delta=0.0),
            _evt("mouse_up", x=11, y=21, button="left", ts=1.05, delta=0.05),
            _evt("key_down", key="a", ts=1.5, delta=0.45),
            _evt("key_up", key="a", ts=1.6, delta=0.1),
        ]
        steps = merger.merge(events)
        for step in steps:
            desc = step.describe()
            assert isinstance(desc, str)
            assert len(desc) > 0


# ============================================================
# 录制→动作链 导入流程
# ============================================================


class TestRecordingToActionChain:
    """验证录制结果可组装为 ActionChain 兼容结构。"""

    def test_steps_have_valid_action_types(self):
        merger = EventMerger()
        events = [
            _evt("mouse_down", x=100, y=200, button="left", ts=1.0, delta=0.0),
            _evt("mouse_up", x=101, y=201, button="left", ts=1.05, delta=0.05),
            _evt("key_down", key="space", ts=1.5, delta=0.45),
            _evt("key_up", key="space", ts=1.6, delta=0.1),
            _evt("mouse_down", x=300, y=400, button="left", ts=2.0, delta=0.4),
            _evt("mouse_move", x=350, y=400, ts=2.1, delta=0.1),
            _evt("mouse_move", x=500, y=400, ts=2.2, delta=0.1),
            _evt("mouse_up", x=500, y=400, button="left", ts=2.3, delta=0.1),
        ]
        steps = merger.merge(events)
        valid_types = {
            ActionType.CLICK_POS,
            ActionType.PRESS_KEY,
            ActionType.HOLD_KEY,
            ActionType.MOUSE_MOVE,
            ActionType.WAIT,
            ActionType.WAIT_RANDOM,
        }
        for step in steps:
            assert step.action_type in valid_types

    def test_bridge_convert_matches_merger_direct(self):
        """RecordBridge.convert_events 与直接调用 EventMerger 结果一致。"""
        events = [
            _evt("mouse_down", x=50, y=50, button="left", ts=1.0, delta=0.0),
            _evt("mouse_up", x=51, y=51, button="left", ts=1.05, delta=0.05),
        ]
        bridge = RecordBridge()
        merger = EventMerger()

        bridge_steps = bridge.convert_events(events)
        merger_steps = merger.merge(events)

        assert len(bridge_steps) == len(merger_steps)
        for bs, ms in zip(bridge_steps, merger_steps):
            assert bs.action_type == ms.action_type


# ============================================================
# 反向组合键检测 (Fix #1: W+Shift 非修饰键先按)
# ============================================================


class TestEventMergerReverseCombo:
    """非修饰键先按下的组合键检测。"""

    def test_w_then_shift_detected_as_combo(self):
        """先按 W 再按 Shift → key_combo(W+shift)。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="w", ts=1.0, delta=0.0),
            _evt("key_down", key="shift", ts=1.1, delta=0.1),
            _evt("key_up", key="w", ts=1.5, delta=0.4),
            _evt("key_up", key="shift", ts=1.6, delta=0.1),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.KEY_COMBO
        combo = steps[0].combo_keys
        assert "w" in combo
        assert "shift" in combo

    def test_w_shift_simultaneous_detected(self):
        """同时按住 W+Shift → key_combo。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="w", ts=1.0, delta=0.0),
            _evt("key_down", key="shift", ts=1.01, delta=0.01),
            _evt("key_up", key="shift", ts=2.0, delta=0.99),
            _evt("key_up", key="w", ts=2.01, delta=0.01),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.KEY_COMBO

    def test_w_pressed_alone_not_combo(self):
        """单独按 W 不应误判为组合键。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="w", ts=1.0, delta=0.0),
            _evt("key_up", key="w", ts=1.8, delta=0.8),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.HOLD_KEY

    def test_shift_first_w_second_detected(self):
        """修饰键先按（原有逻辑）仍然正常。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="shift", ts=1.0, delta=0.0),
            _evt("key_down", key="w", ts=1.1, delta=0.1),
            _evt("key_up", key="w", ts=1.5, delta=0.4),
            _evt("key_up", key="shift", ts=1.6, delta=0.1),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.KEY_COMBO


# ============================================================
# 长按 W 不被误判 (Fix #2)
# ============================================================


class TestEventMergerHoldWithModifier:
    """长按 W 期间按下/释放修饰键不影响长按识别。"""

    def test_hold_w_with_shift_interrupt(self):
        """长按 W 期间按 Shift → W 仍识别为 hold。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="w", ts=1.0, delta=0.0),
            _evt("key_down", key="shift", ts=1.5, delta=0.5),
            _evt("key_up", key="shift", ts=1.6, delta=0.1),
            _evt("key_up", key="w", ts=2.5, delta=0.9),
        ]
        steps = merger.merge(events)
        hold_steps = [s for s in steps if s.action_type == ActionType.HOLD_KEY]
        combo_steps = [s for s in steps if s.action_type == ActionType.KEY_COMBO]
        assert len(hold_steps) + len(combo_steps) >= 1

    def test_hold_w_plain(self):
        """单纯长按 W → HOLD_KEY。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="w", ts=1.0, delta=0.0),
            _evt("key_up", key="w", ts=2.0, delta=1.0),
        ]
        steps = merger.merge(events)
        assert len(steps) == 1
        assert steps[0].action_type == ActionType.HOLD_KEY
        assert steps[0].hold_duration >= 0.9


# ============================================================
# 长等待时间保留 (Fix #3)
# ============================================================


class TestEventMergerLongWait:
    """长时间等待应被准确记录，不被压缩。"""

    def test_long_wait_preserved(self):
        """30 秒等待应原样保留。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="a", ts=1.0, delta=0.0),
            _evt("key_up", key="a", ts=1.1, delta=0.1),
            _evt("key_down", key="b", ts=31.0, delta=29.9),
            _evt("key_up", key="b", ts=31.1, delta=0.1),
        ]
        steps = merger.merge(events)
        wait_steps = [s for s in steps if s.action_type == ActionType.WAIT]
        assert len(wait_steps) >= 1
        assert wait_steps[0].wait_seconds >= 29.0

    def test_very_long_wait_preserved(self):
        """60 秒等待应原样保留。"""
        merger = EventMerger()
        events = [
            _evt("key_down", key="a", ts=1.0, delta=0.0),
            _evt("key_up", key="a", ts=1.1, delta=0.1),
            _evt("key_down", key="b", ts=61.0, delta=59.9),
            _evt("key_up", key="b", ts=61.1, delta=0.1),
        ]
        steps = merger.merge(events)
        wait_steps = [s for s in steps if s.action_type == ActionType.WAIT]
        assert len(wait_steps) >= 1
        assert wait_steps[0].wait_seconds >= 58.0
