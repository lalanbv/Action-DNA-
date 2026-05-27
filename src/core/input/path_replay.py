"""录制路径回放 + 鼠标微抖动 Mixin。"""

from __future__ import annotations

import math
import time

from src.core.input.easing import ALL_EASING_FUNCTIONS
from src.core.input.randomizer import ease_in_out
from src.utils.timing import human_like_duration


class PathReplayMixin:
    """路径回放 Mixin。

    要求宿主类提供:
      - self._backend: PlatformBackend
      - self._rng: SeededRandomizer
      - self._get_mouse_pos() -> tuple[int, int]
      - self._ensure_safe_position()
    """

    def replay_path(
        self,
        path_points: list[tuple[int, int, float]],
        time_scale: float = 1.0,
        jitter_px: int = 1,
        speed_multiplier: float = 1.0,
        easing_name: str | None = None,
    ) -> tuple[int, int]:
        """沿录制的真人路径回放鼠标移动。"""
        if not path_points:
            return self._get_mouse_pos()

        self._ensure_safe_position()

        effective_scale = time_scale / speed_multiplier

        easing_func = None
        if easing_name:
            easing_func = ALL_EASING_FUNCTIONS.get(easing_name)

        start_x, start_y, _ = path_points[0]
        self._backend.move(start_x, start_y)

        if len(path_points) < 2:
            return start_x, start_y

        prev_x, prev_y, prev_time = start_x, start_y, 0.0

        for i in range(1, len(path_points)):
            tgt_x, tgt_y, tgt_rel_time = path_points[i]
            seg_distance = math.hypot(tgt_x - prev_x, tgt_y - prev_y)

            if seg_distance < 5:
                prev_x, prev_y, prev_time = tgt_x, tgt_y, tgt_rel_time
                continue

            seg_duration = (tgt_rel_time - prev_time) * effective_scale
            seg_duration = max(0.005, seg_duration)

            n_steps = max(2, int(seg_distance / 15))

            dx = tgt_x - prev_x
            dy = tgt_y - prev_y

            seg_deadline = time.monotonic() + seg_duration

            for s in range(1, n_steps + 1):
                t = s / n_steps
                if easing_func is not None:
                    t_smooth = easing_func(t)
                else:
                    t_smooth = ease_in_out(t)

                ix = prev_x + dx * t_smooth + self._rng.randint(-jitter_px, jitter_px)
                iy = prev_y + dy * t_smooth + self._rng.randint(-jitter_px, jitter_px)

                self._backend.move(int(ix), int(iy))

                remaining_steps = n_steps - s
                if remaining_steps > 0:
                    remaining_time = seg_deadline - time.monotonic()
                    speed_factor = 0.5 + 0.5 * math.sin(math.pi * t)
                    weight = 1.4 - 0.8 * speed_factor
                    adjusted = (remaining_time / remaining_steps) * weight
                    time.sleep(max(0.001, human_like_duration(adjusted)))

            prev_x, prev_y, prev_time = tgt_x, tgt_y, tgt_rel_time

        ox = self._rng.randint(-2, 2)
        oy = self._rng.randint(-2, 2)
        final_x, final_y = prev_x + ox, prev_y + oy
        self._backend.move(final_x, final_y)
        return final_x, final_y

    def mouse_jitter(self, duration: float, intensity: int = 3) -> None:
        """鼠标微抖动，持续时间内做小幅度随机移动，模拟 idle 手部微动。"""
        self._ensure_safe_position()
        deadline = time.monotonic() + duration
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sub_wait = self._rng.uniform(0.3, 0.8)
            time.sleep(min(sub_wait, remaining))

            cx, cy = self._get_mouse_pos()
            ox = self._rng.randint(-intensity, intensity)
            oy = self._rng.randint(-intensity, intensity)
            micro_dur = self._rng.uniform(0.05, 0.12)
            self._backend.move(cx + ox, cy + oy)
            time.sleep(micro_dur)
