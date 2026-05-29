"""路径序列合并 + 等待序列合并。"""

from __future__ import annotations

import math

from src.core.action import ActionType
from src.core.step_types import BaseStep, MouseMoveStep, WaitStep
from src.recorder.path_utils import simplify_path as _simplify_path


def merge_path_sequences(
    steps: list[BaseStep],
    *,
    drag_sequence_max_gap: float = 0.5,
    direction_cosine_threshold: float = 0.7,
) -> list[BaseStep]:
    """后处理: 合并同类型的连续路径序列。

    MOUSE_MOVE 序列（带 button）：连续拖拽（同方向）合并。
    MOUSE_MOVE 序列：连续视角移动（同方向）合并。
    两者不会交叉合并。
    """
    if len(steps) < 2:
        return steps

    result: list[BaseStep] = []
    i = 0

    while i < len(steps):
        step = steps[i]
        step_type = step.action_type

        if step_type not in (ActionType.MOUSE_MOVE,) or not isinstance(step, MouseMoveStep):
            result.append(step)
            i += 1
            continue

        if not step.path_points:
            result.append(step)
            i += 1
            continue

        sequence: list[MouseMoveStep] = [step]
        inter_waits: list[float] = []
        trailing_waits: list[WaitStep] = []
        pending_wait = 0.0
        j = i + 1
        accumulated_gap = 0.0

        while j < len(steps):
            next_step = steps[j]

            if next_step.action_type == ActionType.WAIT and isinstance(next_step, WaitStep):
                accumulated_gap += next_step.wait_seconds
                if accumulated_gap > drag_sequence_max_gap:
                    break
                trailing_waits.append(next_step)
                pending_wait += next_step.recorded_duration
                j += 1
                continue

            if next_step.action_type != step_type:
                break
            if not isinstance(next_step, MouseMoveStep) or not next_step.path_points:
                break

            if not _is_same_direction(sequence[-1], next_step, threshold=direction_cosine_threshold):
                break

            sequence.append(next_step)
            inter_waits.append(pending_wait)
            trailing_waits = []
            pending_wait = 0.0
            accumulated_gap = 0.0
            j += 1

        if len(sequence) >= 2:
            result.append(combine_path_sequence(sequence, step_type, inter_waits))
            result.extend(trailing_waits)
        else:
            result.append(step)
            result.extend(trailing_waits)
        i = j

    return result


def _is_same_direction(
    a: MouseMoveStep, b: MouseMoveStep, *, threshold: float = 0.5,
) -> bool:
    """判断两个路径步骤方向是否一致（向量余弦相似度）。"""
    ax, ay = a.offset_x, a.offset_y
    bx, by = b.offset_x, b.offset_y
    mag_a = math.hypot(ax, ay)
    mag_b = math.hypot(bx, by)
    if mag_a < 1e-6 or mag_b < 1e-6:
        return True
    cosine = (ax * bx + ay * by) / (mag_a * mag_b)
    return cosine > threshold


def merge_wait_sequences(steps: list[BaseStep]) -> list[BaseStep]:
    """后处理: 合并连续 WAIT 步骤。"""
    if len(steps) < 2:
        return steps

    result: list[BaseStep] = []
    i = 0

    while i < len(steps):
        step = steps[i]

        if step.action_type != ActionType.WAIT or not isinstance(step, WaitStep):
            result.append(step)
            i += 1
            continue

        total_wait = step.wait_seconds
        total_duration = step.recorded_duration
        j = i + 1

        while j < len(steps):
            ws = steps[j]
            if ws.action_type != ActionType.WAIT or not isinstance(ws, WaitStep):
                break
            total_wait += ws.wait_seconds
            total_duration += ws.recorded_duration
            j += 1

        if j > i + 1:
            result.append(WaitStep(
                wait_seconds=round(total_wait, 2),
                recorded_duration=round(total_duration, 4),
            ))
        else:
            result.append(step)
        i = j

    return result


def combine_path_sequence(
    sequence: list[MouseMoveStep], step_type: ActionType,
    inter_waits: list[float] | None = None,
) -> BaseStep:
    """将同类型路径步骤合并为一个，拼接路径点。"""
    combined_points: list[tuple[int, int, float]] = []
    total_duration = 0.0
    total_dx = 0
    total_dy = 0
    time_offset = 0.0
    waits = inter_waits or []

    for idx, step in enumerate(sequence):
        pts = step.path_points
        start = 1 if idx > 0 and pts and combined_points else 0
        for px, py, pt in pts[start:]:
            combined_points.append((px, py, round(pt + time_offset, 4)))
        time_offset += step.recorded_duration
        total_duration += step.recorded_duration
        total_dx += step.offset_x
        total_dy += step.offset_y
        if idx < len(waits):
            time_offset += waits[idx]
            total_duration += waits[idx]

    return MouseMoveStep(
        offset_x=total_dx,
        offset_y=total_dy,
        path_points=_simplify_path(combined_points),
        recorded_duration=round(total_duration, 4),
        button=sequence[0].button,
    )
