"""EventMerger — 智能事件合并器

将原始录制事件流合并为语义级 ActionStep 列表。
合并规则（优先级排序）：
0. 事件间隔 > 阈值 → 等待
1. mouse_down + mouse_drag* + mouse_up (距离 >= 阈值) → 拖拽 (MOUSE_MOVE)
2. mouse_down + mouse_up (短时间、小距离) → 点击 / 鼠标长按
3. modifier_down + tap_keys + modifier_up → 组合键
4. key_down + key_up (间隔 < 阈值) → 按键
5. key_down + key_up (间隔 >= 阈值) → 长按
6. 连续滚轮（同方向） → 滚轮合并
7. 连续 mouse_move (大距离) → 视角移动 (MOUSE_MOVE)
8. 连续 mouse_drag (大距离，无配对 mouse_up) → 拖拽 (MOUSE_MOVE)
后处理: 拖拽/移动序列合并 → 等待序列合并
"""

from __future__ import annotations

import logging
import math
from src.core.step_types import (
    BaseStep, ClickPosStep, HoldKeyStep, KeyComboStep,
    MouseMoveStep, MouseScrollStep, PressKeyStep, WaitStep,
)
from src.recorder.post_merge import merge_path_sequences, merge_wait_sequences
from src.recorder.recorder import RecordedEvent
from src.utils.i18n import t

logger = logging.getLogger(__name__)


class EventMerger:
    """智能事件合并器。

    算法：滑动窗口 + 按优先级尝试模式匹配。
    从当前位置依次尝试拖拽、点击、按键、忽略移动，
    匹配成功则生成 ActionStep 并跳过已消费事件。
    """

    # 时间阈值（秒）
    CLICK_MAX_GAP: float = 0.2
    DRAG_MAX_DURATION: float = 10.0
    HOLD_THRESHOLD: float = 0.5
    WAIT_INSERT_THRESHOLD: float = 0.15

    # 空间阈值（像素）
    DRAG_MIN_DISTANCE: int = 10
    MOVE_IGNORE_THRESHOLD: int = 50

    # 修饰键集合（用于组合键检测）
    MODIFIER_KEYS: frozenset[str] = frozenset({
        "ctrl", "shift", "alt", "cmd", "capslock",
    })

    def __init__(self) -> None:
        self._cached_steps: list[BaseStep] = []
        self._cached_event_count: int = 0

    def merge(self, events: list[RecordedEvent]) -> list[BaseStep]:
        """将原始事件流合并为 BaseStep 列表。"""
        if not events:
            return []

        steps: list[BaseStep] = []
        i = 0
        last_step_time = events[0].timestamp

        while i < len(events):
            event = events[i]

            # 0. 检测与上一个已确认步骤之间的等待间隔
            gap = event.timestamp - last_step_time
            if gap > self.WAIT_INSERT_THRESHOLD and steps:
                steps.append(WaitStep(
                    wait_seconds=round(gap, 2),
                    recorded_duration=round(gap, 4),
                ))
                last_step_time = event.timestamp

            # 1. 尝试拖拽（最高优先级，是点击的超集）
            merged, consumed = self._try_merge_drag(events, i)
            if merged is not None:
                steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 2. 尝试点击 / 鼠标长按
            merged, consumed = self._try_merge_click(events, i)
            if merged is not None:
                steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 3. 尝试组合键（修饰键+按键）
            merged, consumed = self._try_merge_key_combo(events, i)
            if merged is not None:
                steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 反向组合键（非修饰键先按下，如 W+Shift）
            merged, consumed = self._try_merge_key_combo_reverse(events, i)
            if merged is not None:
                steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 文本输入合并
            merged, consumed = self._try_merge_text_input(events, i)
            if merged is not None:
                steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 4. 尝试按键/长按
            merged, consumed = self._try_merge_key(events, i)
            if merged is not None:
                steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 5. 尝试滚轮合并
            if event.event_type == "mouse_scroll":
                merged, consumed = self._try_merge_scroll(events, i)
                if merged is not None:
                    steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 6. 尝试忽略小范围鼠标移动或保留大范围路径
            if event.event_type in ("mouse_move", "mouse_drag"):
                merged, consumed = self._try_merge_move_path(events, i)
                if merged is not None:
                    steps.append(merged)
                last_step_time = events[i + consumed - 1].timestamp
                i += consumed
                continue

            # 7. 无法识别的事件，跳过
            i += 1

        # 后处理: 合并连续路径序列（拖拽/视角移动）
        steps = merge_path_sequences(steps)
        # 后处理: 合并连续等待步骤
        steps = merge_wait_sequences(steps)

        logger.info(
            t("recorder.log.merge_complete", events=len(events), steps=len(steps)),
        )
        return steps

    def merge_incremental(
        self, events: list[RecordedEvent],
    ) -> list[BaseStep]:
        """增量合并：始终全量合并以保证模式完整性。

        事件数量通常在千级以内，全量合并耗时毫秒级，
        远快于在边界处切割导致模式丢失的错误合并。
        """
        result = self.merge(events)
        self._cached_steps = result
        self._cached_event_count = len(events)
        return result

    def reset_cache(self) -> None:
        """重置增量合并缓存。"""
        self._cached_steps = []
        self._cached_event_count = 0

    # ---- 合并规则实现 ----

    # 双击检测阈值
    DOUBLE_CLICK_MAX_GAP: float = 0.5
    DOUBLE_CLICK_MAX_DISTANCE: int = 5
    # 多击检测中允许跳过的 mouse_move 最大距离（像素）
    MULTI_CLICK_MOVE_TOLERANCE: int = 10
    # 路径采样间距（像素）
    PATH_SAMPLE_DISTANCE: int = 8

    def _try_merge_click(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """模式: mouse_down -> [mouse_move/mouse_drag*] -> mouse_up

        跳过中间的小距离 mouse_move/mouse_drag 事件。
        条件: 总距离 < DRAG_MIN_DISTANCE → 点击
        条件: 时间间隔 > CLICK_MAX_GAP 且距离小 → 鼠标长按
        支持多击检测（双击/三击）。
        """
        if start >= len(events):
            return None, 1

        down = events[start]
        if down.event_type != "mouse_down":
            return None, 1

        # 向前搜索匹配的 mouse_up，跳过中间的 move/drag
        up_idx = self._find_matching_mouse_up(events, start, down.button)
        if up_idx is None:
            return None, 1

        up = events[up_idx]
        intermediate_consumed = up_idx - start + 1

        distance = math.hypot(up.x - down.x, up.y - down.y)

        if distance >= self.DRAG_MIN_DISTANCE:
            return None, 1

        gap = up.timestamp - down.timestamp

        # 鼠标长按：按下时间长但未移动
        if gap > self.CLICK_MAX_GAP:
            return ClickPosStep(
                pos_x=down.x,
                pos_y=down.y,
                clicks=1,
                button=down.button,
                hold_duration=round(gap, 2),
                recorded_duration=round(gap, 4),
            ), intermediate_consumed

        # 多击检测：检查后续是否有连续 down+up 对
        click_count = 1
        consumed = intermediate_consumed
        pos = start + intermediate_consumed
        last_up = up

        while click_count < 3:
            # 跳过小距离 mouse_move（仍在点击区域内）
            skipped_moves = 0
            while pos < len(events) and events[pos].event_type in ("mouse_move", "mouse_drag"):
                move_evt = events[pos]
                if (math.hypot(move_evt.x - down.x, move_evt.y - down.y)
                        > self.MULTI_CLICK_MOVE_TOLERANCE):
                    break
                skipped_moves += 1
                pos += 1

            if pos >= len(events):
                break
            next_down = events[pos]
            if next_down.event_type != "mouse_down":
                break
            if next_down.button != down.button:
                break
            if next_down.timestamp - last_up.timestamp > self.DOUBLE_CLICK_MAX_GAP:
                break
            if math.hypot(next_down.x - down.x, next_down.y - down.y) > self.DOUBLE_CLICK_MAX_DISTANCE:
                break

            next_up_idx = self._find_matching_mouse_up(events, pos, next_down.button)
            if next_up_idx is None:
                break
            next_up = events[next_up_idx]

            if math.hypot(next_up.x - next_down.x, next_up.y - next_down.y) >= self.DRAG_MIN_DISTANCE:
                break

            click_count += 1
            consumed += skipped_moves + (next_up_idx - pos + 1)
            pos = next_up_idx + 1
            last_up = next_up

        return ClickPosStep(
            pos_x=down.x,
            pos_y=down.y,
            clicks=click_count,
            button=down.button,
            hold_duration=0.0,
        ), consumed

    def _find_matching_mouse_up(
        self,
        events: list[RecordedEvent],
        start: int,
        button: str,
    ) -> int | None:
        """从 start+1 向前搜索匹配的 mouse_up。

        跳过中间的 mouse_move/mouse_drag。
        跳过中间的非鼠标事件（键盘/滚轮等），避免鼠标长按期间因键盘事件丢失匹配。
        遇到相同 button 的 mouse_down（重复按下）时中断。
        超时阈值: CLICK_MAX_GAP 的 10 倍（长按容差）。
        """
        max_gap = max(self.DRAG_MAX_DURATION, self.HOLD_THRESHOLD * 10)
        for j in range(start + 1, min(start + 500, len(events))):
            evt = events[j]
            if evt.event_type == "mouse_up" and evt.button == button:
                if evt.timestamp - events[start].timestamp <= max_gap:
                    return j
                return None
            if evt.event_type == "mouse_down" and evt.button == button:
                return None
            # 跳过 move/drag/键盘/滚轮等所有中间事件
            continue
        return None

    def _try_merge_drag(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """模式: mouse_down -> mouse_move/mouse_drag* -> mouse_up

        条件: 总距离 >= DRAG_MIN_DISTANCE, 总时长 < DRAG_MAX_DURATION
        保留采样后的鼠标路径点用于真人轨迹回放。
        """
        if start >= len(events):
            return None, 1

        down = events[start]
        if down.event_type != "mouse_down":
            return None, 1

        last_x, last_y = down.x, down.y
        total_distance = 0.0
        raw_points: list[tuple[int, int, float]] = [(down.x, down.y, 0.0)]
        last_sample_x, last_sample_y = down.x, down.y
        start_time = down.timestamp

        for j in range(start + 1, min(start + 500, len(events))):
            evt = events[j]

            if evt.timestamp - down.timestamp > self.DRAG_MAX_DURATION:
                break

            # 找到匹配的 mouse_up
            if evt.event_type == "mouse_up" and evt.button == down.button:
                consumed = j - start + 1
                duration = evt.timestamp - start_time
                # 添加终点（如果离上一个采样点足够远）
                sample_dist = math.hypot(
                    evt.x - last_sample_x, evt.y - last_sample_y,
                )
                if sample_dist >= self.PATH_SAMPLE_DISTANCE:
                    raw_points.append((
                        evt.x, evt.y,
                        round(evt.timestamp - start_time, 4),
                    ))
                if total_distance >= self.DRAG_MIN_DISTANCE:
                    return MouseMoveStep(
                        offset_x=evt.x - down.x,
                        offset_y=evt.y - down.y,
                        path_points=raw_points,
                        recorded_duration=round(duration, 4),
                        button=down.button,
                    ), consumed
                # 距离不够 — 不是拖拽，让点击合并器处理
                return None, 1

            # mouse_move / mouse_drag 累积路径
            if evt.event_type in ("mouse_move", "mouse_drag"):
                seg_dist = math.hypot(evt.x - last_x, evt.y - last_y)
                total_distance += seg_dist
                sample_dist = math.hypot(
                    evt.x - last_sample_x, evt.y - last_sample_y,
                )
                if sample_dist >= self.PATH_SAMPLE_DISTANCE:
                    raw_points.append((
                        evt.x, evt.y,
                        round(evt.timestamp - start_time, 4),
                    ))
                    last_sample_x, last_sample_y = evt.x, evt.y
                last_x, last_y = evt.x, evt.y
                continue

            # 另一个 mouse_down（不同按钮或重复按下）→ 中断
            if evt.event_type == "mouse_down":
                break

            # 非鼠标事件（键盘/滚轮等）→ 跳过，继续搜索 mouse_up
            continue

        return None, 1

    # 文本输入合并参数
    TEXT_INPUT_MAX_GAP: float = 0.1
    TEXT_INPUT_MIN_LENGTH: int = 3
    _PRINTABLE_KEYS: frozenset[str] = frozenset(
        "abcdefghijklmnopqrstuvwxyz"
        "0123456789"
    ) | frozenset({"space"})

    def _try_merge_text_input(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """连续可打印字符 key_down（间隔 < TEXT_INPUT_MAX_GAP）合并为文本。"""
        if start >= len(events):
            return None, 1

        first = events[start]
        if first.event_type != "key_down":
            return None, 1
        if first.key not in self._PRINTABLE_KEYS:
            return None, 1
        if first.is_repeat:
            return None, 1

        chars: list[str] = []
        consumed = 0
        last_time = first.timestamp

        for j in range(start, min(start + 500, len(events))):
            evt = events[j]
            if evt.event_type != "key_down":
                break
            if evt.timestamp - last_time > self.TEXT_INPUT_MAX_GAP:
                break
            if evt.key not in self._PRINTABLE_KEYS:
                break
            if evt.is_repeat:
                continue

            ch = " " if evt.key == "space" else evt.key
            chars.append(ch)
            last_time = evt.timestamp
            consumed = j - start + 1

        if len(chars) < self.TEXT_INPUT_MIN_LENGTH:
            return None, 1

        # 所有字符相同 → 长按，不是文本输入
        if len(set(chars)) == 1:
            return None, 1

        text = "".join(chars)
        duration = events[start + consumed - 1].timestamp - first.timestamp
        return PressKeyStep(
            text=text,
            recorded_duration=round(duration, 4),
        ), consumed

    # 长按搜索最大向前扫描事件数
    _KEY_PAIR_SCAN_LIMIT: int = 500

    def _try_merge_key(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """模式: key_down -> key_up

        间隔 < HOLD_THRESHOLD → PRESS_KEY
        间隔 >= HOLD_THRESHOLD → HOLD_KEY
        跳过中间同 key 的 key_down（长按产生的 repeat 事件）。
        跳过中间的非键盘事件（鼠标/滚轮等），避免长按期间因鼠标移动丢失匹配。
        遇到同 key 的 key_down+key_up 对（完整按键周期）时中断，说明长按已结束。
        """
        if start >= len(events):
            return None, 1

        down = events[start]
        if down.event_type != "key_down":
            return None, 1

        scan_end = min(start + self._KEY_PAIR_SCAN_LIMIT, len(events))

        for j in range(start + 1, scan_end):
            evt = events[j]
            # 跳过同 key 的 key_down（repeat 事件）
            if evt.event_type == "key_down" and evt.key == down.key:
                continue
            if evt.event_type == "key_up" and evt.key == down.key:
                gap = evt.timestamp - down.timestamp
                if gap >= self.HOLD_THRESHOLD:
                    return HoldKeyStep(
                        keys_hold=down.key,
                        hold_duration=round(gap, 2),
                    ), j - start + 1
                return PressKeyStep(
                    key=down.key,
                    recorded_duration=round(gap, 4),
                ), j - start + 1
            # 跳过非键盘事件（鼠标/滚轮等），长按期间可能有鼠标移动
            if not evt.is_key_event:
                continue
            # 修饰键事件 → 跳过（组合键按住时修饰键可能被按下/释放）
            if evt.key in self.MODIFIER_KEYS:
                continue
            # 其他按键的完整周期 → 中断
            if evt.event_type == "key_down" and evt.key != down.key:
                break
            if evt.event_type == "key_up" and evt.key != down.key:
                break

        # 未找到配对 key_up → 跳过
        return None, 1

    def _try_merge_key_combo(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """模式: modifier_down → [modifier_down]* → tap_key_down → tap_key_up
               → [more taps]* → modifier_up*

        检测修饰键组合，如 Ctrl+C, Cmd+Shift+3。
        所有修饰键释放后，如果有非修饰键被点击则合并为 KEY_COMBO。
        """
        if start >= len(events):
            return None, 1

        first = events[start]
        if first.event_type != "key_down" or first.key not in self.MODIFIER_KEYS:
            return None, 1

        combo_modifiers: set[str] = {first.key}
        currently_held: set[str] = {first.key}
        tapped_keys: list[str] = []
        end_idx = start

        for j in range(start + 1, min(start + 80, len(events))):
            evt = events[j]

            if evt.timestamp - first.timestamp > 3.0:
                break

            # 跳过非键盘事件（鼠标/滚轮等），组合键期间可能有鼠标移动
            if evt.event_type not in ("key_down", "key_up"):
                end_idx = j
                continue

            if evt.event_type == "key_down":
                currently_held.add(evt.key)
                if evt.key in self.MODIFIER_KEYS:
                    combo_modifiers.add(evt.key)
                end_idx = j
                continue

            # key_up
            if evt.key in currently_held:
                currently_held.discard(evt.key)
                if evt.key not in self.MODIFIER_KEYS:
                    tapped_keys.append(evt.key)
                end_idx = j
                if not currently_held:
                    break

        if not tapped_keys or currently_held:
            return None, 1

        combo_str = ",".join(sorted(combo_modifiers) + tapped_keys)

        return KeyComboStep(
            combo_keys=combo_str,
            combo_mode="hold_tap",
            recorded_duration=round(
                events[end_idx].timestamp - first.timestamp, 4,
            ),
        ), end_idx - start + 1

    def _try_merge_key_combo_reverse(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """模式: non_modifier_down → modifier_down → ... → all_up

        检测先按下非修饰键再按下修饰键的组合键，如 W+Shift。
        仅当修饰键在非修饰键释放前被按下时才触发。
        """
        if start >= len(events):
            return None, 1

        first = events[start]
        if first.event_type != "key_down":
            return None, 1
        if first.key in self.MODIFIER_KEYS:
            return None, 1
        if first.is_repeat:
            return None, 1

        currently_held: set[str] = {first.key}
        combo_modifiers: set[str] = set()
        tapped_keys: list[str] = []
        end_idx = start

        for j in range(start + 1, min(start + 80, len(events))):
            evt = events[j]

            if evt.timestamp - first.timestamp > 3.0:
                break

            if evt.event_type not in ("key_down", "key_up"):
                end_idx = j
                continue

            if evt.event_type == "key_down":
                currently_held.add(evt.key)
                if evt.key in self.MODIFIER_KEYS:
                    combo_modifiers.add(evt.key)
                end_idx = j
                continue

            # key_up
            if evt.key in currently_held:
                currently_held.discard(evt.key)
                if evt.key not in self.MODIFIER_KEYS:
                    tapped_keys.append(evt.key)
                end_idx = j
                if not currently_held:
                    break

        if not combo_modifiers or currently_held:
            return None, 1

        all_tapped = [first.key] + [k for k in tapped_keys if k != first.key]
        combo_str = ",".join(sorted(combo_modifiers) + all_tapped)

        return KeyComboStep(
            combo_keys=combo_str,
            combo_mode="hold_tap",
            recorded_duration=round(
                events[end_idx].timestamp - first.timestamp, 4,
            ),
        ), end_idx - start + 1

    # 滚轮合并时间阈值（秒）
    SCROLL_MERGE_MAX_GAP: float = 0.3

    def _try_merge_scroll(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """模式: mouse_scroll+

        合并连续滚轮事件（同方向、间隔 < SCROLL_MERGE_MAX_GAP），
        方向反转时中断合并。
        """
        first = events[start]
        if first.event_type != "mouse_scroll":
            return None, 1

        total_delta = first.scroll_delta
        total_delta_x = first.scroll_delta_x
        last_x, last_y = first.x, first.y
        last_time = first.timestamp
        consumed = 1

        for j in range(start + 1, min(start + 500, len(events))):
            evt = events[j]
            if evt.event_type != "mouse_scroll":
                break
            if evt.timestamp - last_time > self.SCROLL_MERGE_MAX_GAP:
                break
            # 方向反转：垂直或水平任一方向反转时中断
            if total_delta != 0 and evt.scroll_delta != 0:
                if (total_delta > 0) != (evt.scroll_delta > 0):
                    break
            if total_delta_x != 0 and evt.scroll_delta_x != 0:
                if (total_delta_x > 0) != (evt.scroll_delta_x > 0):
                    break
            total_delta += evt.scroll_delta
            total_delta_x += evt.scroll_delta_x
            last_x, last_y = evt.x, evt.y
            last_time = evt.timestamp
            consumed += 1

        return MouseScrollStep(
            scroll_clicks=total_delta,
            scroll_delta_x=total_delta_x,
            pos_x=last_x,
            pos_y=last_y,
        ), consumed

    # 大范围移动路径阈值（像素）
    MOVE_PATH_MIN_DISTANCE: int = 30

    def _try_merge_move_path(
        self,
        events: list[RecordedEvent],
        start: int,
    ) -> tuple[BaseStep | None, int]:
        """处理连续 mouse_move 或 mouse_drag（不混合）。

        mouse_move（无按键移动）→ MouseMoveStep（游戏视角移动）
        mouse_drag（按住按键移动）→ MouseMoveStep（拖拽操作，带按钮信息）
        小范围 → 忽略。
        """
        first = events[start]
        target_type = first.event_type  # "mouse_move" or "mouse_drag"
        button = first.button if target_type == "mouse_drag" else ""

        total_distance = 0.0
        consumed = 0
        prev_x, prev_y = first.x, first.y
        start_time = first.timestamp
        last_sample_x, last_sample_y = prev_x, prev_y
        path_points: list[tuple[int, int, float]] = [(prev_x, prev_y, 0.0)]

        for j in range(start, min(start + 500, len(events))):
            evt = events[j]
            # 只收集同类型事件，不混合 mouse_move 和 mouse_drag
            if evt.event_type != target_type:
                break
            total_distance += math.hypot(evt.x - prev_x, evt.y - prev_y)
            sample_dist = math.hypot(
                evt.x - last_sample_x, evt.y - last_sample_y,
            )
            if sample_dist >= self.PATH_SAMPLE_DISTANCE:
                path_points.append((
                    evt.x, evt.y,
                    round(evt.timestamp - start_time, 4),
                ))
                last_sample_x, last_sample_y = evt.x, evt.y
            prev_x, prev_y = evt.x, evt.y
            consumed += 1

        consumed = max(consumed, 1)

        if total_distance >= self.MOVE_PATH_MIN_DISTANCE:
            start_x, start_y, _ = path_points[0]
            duration = round(
                events[start + consumed - 1].timestamp - start_time, 4,
            )
            if target_type == "mouse_drag":
                return MouseMoveStep(
                    offset_x=prev_x - start_x,
                    offset_y=prev_y - start_y,
                    path_points=path_points,
                    recorded_duration=duration,
                    button=button,
                ), consumed
            return MouseMoveStep(
                offset_x=prev_x - start_x,
                offset_y=prev_y - start_y,
                path_points=path_points,
                recorded_duration=duration,
            ), consumed

        # 小范围移动 — 忽略
        return None, consumed
