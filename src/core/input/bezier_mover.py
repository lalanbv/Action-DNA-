"""Bezier 曲线鼠标移动 Mixin。"""

from __future__ import annotations

import math
import time

from src.core.input.randomizer import ease_in_out
from src.core.input.seeded_randomizer import SeededRandomizer


class BezierMixin:
    """Bezier 曲线鼠标移动 Mixin。

    要求宿主类提供:
      - self._backend: PlatformBackend
      - self._rng: SeededRandomizer
      - self._get_mouse_pos() -> tuple[int, int]
      - self._ensure_safe_position()
      - self._move_config: MoveConfig
      - self.move_to(x, y, duration) -> tuple[int, int]
      - self._fitts_duration(distance) -> float
    """

    def move_to_bezier(
        self,
        x: int,
        y: int,
        duration: float | None = None,
        curve_intensity: float = 0.3,
    ) -> tuple[int, int]:
        """沿多段 Bezier 曲线移动鼠标到 (x, y)，模拟真人非线性轨迹。"""
        self._ensure_safe_position()
        sx, sy = self._get_mouse_pos()
        dx, dy = x - sx, y - sy
        distance = math.hypot(dx, dy)

        if distance < 5:
            return self.move_to(x, y, duration=duration)

        if duration is None:
            duration = self._fitts_duration(distance)

        rng = self._rng
        cfg = self._move_config
        overshoot = (
            distance > 100
            and rng.random() < cfg.overshoot_probability
        )

        if overshoot:
            overshoot_dist = distance * cfg.overshoot_distance_factor
            angle = math.atan2(dy, dx)
            angle += rng.uniform(-0.3, 0.3)
            overshoot_x = x + int(overshoot_dist * math.cos(angle))
            overshoot_y = y + int(overshoot_dist * math.sin(angle))

            self._move_bezier_raw(
                overshoot_x, overshoot_y,
                duration=duration,
                curve_intensity=curve_intensity,
                rng=rng,
            )

            recenter_dur = cfg.overshoot_recenter_duration * rng.uniform(0.8, 1.2)
            ox = rng.randint(-2, 2)
            oy = rng.randint(-2, 2)
            actual_x, actual_y = x + ox, y + oy
            self._backend.move_anim(
                actual_x, actual_y, recenter_dur,
                self._get_mouse_pos, self._ensure_safe_position,
            )
            return actual_x, actual_y

        return self._move_bezier_raw(
            x, y, duration=duration,
            curve_intensity=curve_intensity,
            rng=rng,
        )

    def _move_bezier_raw(
        self,
        x: int,
        y: int,
        duration: float,
        curve_intensity: float = 0.3,
        rng: SeededRandomizer | None = None,
    ) -> tuple[int, int]:
        """Bezier 曲线移动核心实现（无过冲）。"""
        if rng is None:
            rng = self._rng

        sx, sy = self._get_mouse_pos()
        dx, dy = x - sx, y - sy
        distance = math.hypot(dx, dy)

        if distance < 5:
            ox = rng.randint(-2, 2)
            oy = rng.randint(-2, 2)
            actual_x, actual_y = x + ox, y + oy
            self._backend.move(actual_x, actual_y)
            return actual_x, actual_y

        if distance < 100:
            n_ctrl = 1
        elif distance < 500:
            n_ctrl = 2
        else:
            n_ctrl = 3

        nx, ny = -dy / distance, dx / distance

        ctrl_points: list[tuple[float, float]] = []
        for k in range(n_ctrl):
            frac = (k + 1) / (n_ctrl + 1)
            base_x = sx + dx * frac
            base_y = sy + dy * frac
            sign = 1 if k % 2 == 0 else -1
            offset = sign * rng.uniform(0.2, curve_intensity) * distance
            ctrl_points.append((base_x + nx * offset, base_y + ny * offset))

        all_points = [(float(sx), float(sy))] + ctrl_points + [(float(x), float(y))]

        n_points = max(15, int(distance / 30)) + rng.randint(-3, 3)
        n_points = max(10, n_points)

        deadline = time.monotonic() + duration

        n = len(all_points) - 1
        binom_cache = [1] * (n + 1)
        for k in range(1, n + 1):
            binom_cache[k] = binom_cache[k - 1] * (n - k + 1) // k

        px = [p[0] for p in all_points]
        py = [p[1] for p in all_points]

        for i in range(1, n_points + 1):
            progress = i / n_points
            t_smooth = ease_in_out(progress)
            s = 1.0 - t_smooth

            bx = 0.0
            by = 0.0
            s_pow = 1.0
            t_pow = t_smooth ** n
            for k in range(n + 1):
                b = binom_cache[k] * s_pow * t_pow
                bx += b * px[k]
                by += b * py[k]
                s_pow *= s
                t_pow /= t_smooth if t_smooth > 0 else 1.0

            bx += rng.randint(-1, 1)
            by += rng.randint(-1, 1)

            self._backend.move(int(bx), int(by))

            remaining_points = n_points - i
            if remaining_points > 0:
                remaining_time = deadline - time.monotonic()
                speed_factor = 0.5 + 0.5 * math.sin(math.pi * progress)
                weight = (1.4 - 0.8 * speed_factor)
                adjusted_sleep = (remaining_time / remaining_points) * weight
                time.sleep(max(0.0, adjusted_sleep * rng.uniform(0.85, 1.15)))

        ox = rng.randint(-2, 2)
        oy = rng.randint(-2, 2)
        actual_x, actual_y = x + ox, y + oy
        self._backend.move(actual_x, actual_y)
        return actual_x, actual_y

    def move_relative_bezier(
        self,
        dx: int,
        dy: int,
        duration: float | None = None,
        curve_intensity: float = 0.3,
    ) -> tuple[int, int]:
        """相对位移的 Bezier 曲线移动，用于镜头转向。"""
        sx, sy = self._get_mouse_pos()
        return self.move_to_bezier(
            sx + dx, sy + dy, duration=duration, curve_intensity=curve_intensity
        )
