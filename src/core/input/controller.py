"""InputController — 输入控制门面。

组合平台后端（Quartz / SendInput / pyautogui）提供统一的高级输入 API：
  - Fitts's Law 鼠标移动时长
  - Bezier 曲线鼠标轨迹（BezierMixin）
  - 自然漂移点击、长按、拖拽
  - 键盘模拟（单键、组合键、逐字输入）
  - 可中断等待
  - 输入策略切换（拟人化 / 精准 / 混合）
  - 录制路径回放（PathReplayMixin）
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable
from enum import Enum

from typing import NamedTuple, TypeVar

from src.core.input.backends import PlatformBackend, PyAutoGUIBackend
from src.core.input.bezier_mover import BezierMixin
from src.core.input.path_replay import PathReplayMixin
from src.core.input.seeded_randomizer import SeededRandomizer
from src.core.logger import log
from src.utils.i18n import t
from src.utils.platform import IS_MACOS, IS_WINDOWS

T = TypeVar("T")


class InputStrategy(Enum):
    """输入策略 — 控制鼠标移动和点击的拟人化程度。"""

    NATURAL_FIRST = "natural_first"   # 优先拟人化，失败回退精准
    PRECISE_FIRST = "precise_first"   # 优先精准，失败回退拟人化
    NATURAL_ONLY = "natural_only"     # 仅拟人化（Bezier + 随机延迟）
    PRECISE_ONLY = "precise_only"     # 仅精准（线性 + 最小延迟）


class MoveConfig(NamedTuple):
    """鼠标移动配置 — 过冲行为和种子控制。"""

    overshoot_probability: float = 0.2
    overshoot_distance_factor: float = 0.15
    overshoot_recenter_duration: float = 0.12
    seed: int | None = None


class TypingConfig(NamedTuple):
    """打字节奏配置 — 思考停顿和标点延迟。"""

    thinking_pause_interval: int = 7
    thinking_pause_range: tuple[float, float] = (0.3, 0.5)
    punctuation_multiplier: float = 1.35


_PUNCTUATION = frozenset(".,;:!?\"')-")


class InputController(BezierMixin, PathReplayMixin):
    """模拟人类操作的输入控制器

    所有鼠标操作分两步：先移动到目标位置，再在当前位置执行点击/按键。
    move_to 返回实际落点坐标（含随机偏移），后续操作基于该坐标。

    平台后端在 __init__ 时一次性选择，所有原语通过 self._backend 分发。
    """

    def __init__(
        self,
        move_config: MoveConfig | None = None,
        typing_config: TypingConfig | None = None,
        strategy: InputStrategy = InputStrategy.NATURAL_ONLY,
    ) -> None:
        self._backend: PlatformBackend
        self._move_config = move_config or MoveConfig()
        self._typing_config = typing_config or TypingConfig()
        self._strategy = strategy
        self._rng = SeededRandomizer(seed=self._move_config.seed)

        if IS_MACOS:
            try:
                from src.core.input.platform_darwin import QuartzBackend
                self._backend = QuartzBackend()
                log.info(t("input.log.mode_quartz"))
            except Exception as e:
                log.warning(t("input.log.quartz_init_failed", error=e))
                self._backend = PyAutoGUIBackend()
        elif IS_WINDOWS:
            try:
                from src.core.input.platform_windows import SendInputBackend
                self._backend = SendInputBackend()
                log.info(t("input.log.mode_sendinput"))
            except Exception as e:
                log.warning(t("input.log.sendinput_init_failed", error=e))
                self._backend = PyAutoGUIBackend()
        else:
            self._backend = PyAutoGUIBackend()
            log.info(t("input.log.mode_pyautogui"))

    # ── 线程安全的鼠标位置获取 ──────────────────────────────────

    def _get_mouse_pos(self) -> tuple[int, int]:
        """获取当前鼠标位置（线程安全）。"""
        return self._backend.get_mouse_pos()

    def get_mouse_position(self) -> tuple[int, int]:
        return self._get_mouse_pos()

    # ── 策略查询 ──────────────────────────────────────────────

    @property
    def strategy(self) -> InputStrategy:
        """当前输入策略。"""
        return self._strategy

    @strategy.setter
    def strategy(self, value: InputStrategy) -> None:
        self._strategy = value
        log.info(t("input.log.strategy_switched", strategy=value.value))

    def _is_precise(self) -> bool:
        """当前是否使用精准模式。"""
        return self._strategy in (InputStrategy.PRECISE_ONLY, InputStrategy.PRECISE_FIRST)

    def _execute_with_fallback(
        self,
        primary_fn: Callable[[], T],
        fallback_fn: Callable[[], T],
    ) -> T:
        """双路径降级执行 — primary 失败自动切 fallback。"""
        try:
            return primary_fn()
        except Exception as exc:
            log.warning(t("input.log.fallback_triggered", error=exc))
            return fallback_fn()

    # ── Fail-Safe 角落逃生 ──────────────────────────────────────

    def _ensure_safe_position(self) -> None:
        """如果鼠标在 (0,0) fail-safe 角落，用底层 API 移开"""
        try:
            cur_x, cur_y = self._get_mouse_pos()
        except Exception:
            return
        if cur_x != 0 or cur_y != 0:
            return

        log.warning(t("input.log.failsafe_corner"))
        self._backend.move(100, 100)

    # ── 公共键盘 API ─────────────────────────────────────────────────

    def key_down(self, key: str) -> None:
        self._backend.key_down(key)

    def key_up(self, key: str) -> None:
        self._backend.key_up(key)

    # ── 公共鼠标按钮 API ──────────────────────────────────────────

    def mouse_down(self, x: int, y: int, button: str) -> int | None:
        return self._backend.mouse_down(x, y, button)

    def mouse_up(
        self, x: int, y: int, button: str, click_num: int | None = None,
    ) -> None:
        self._backend.mouse_up(x, y, button, click_num)

    # ── 移动 ──────────────────────────────────────────────────────

    def _fitts_duration(self, distance: float) -> float:
        """基于 Fitts's Law 计算移动时长"""
        if distance < 10:
            return self._rng.uniform(0.08, 0.15)
        w = 20.0
        idx = math.log2(2 * distance / w)
        base = 0.10 + 0.06 * idx
        return min(0.8, max(0.12, base + self._rng.gauss(0, 0.03)))

    def move_to(
        self,
        x: int,
        y: int,
        duration: float | None = None,
    ) -> tuple[int, int]:
        """移动鼠标到 (x, y) 附近，返回实际落点坐标。

        精准模式下无随机偏移、线性移动；拟人模式下保持 Bezier + Fitts。
        NATURAL_FIRST/PRECISE_FIRST 策略自动降级。
        """
        if self._strategy == InputStrategy.NATURAL_FIRST:
            return self._execute_with_fallback(
                lambda: self._move_to_natural(x, y, duration),
                lambda: self._move_to_precise(x, y, duration),
            )
        if self._strategy == InputStrategy.PRECISE_FIRST:
            return self._execute_with_fallback(
                lambda: self._move_to_precise(x, y, duration),
                lambda: self._move_to_natural(x, y, duration),
            )
        if self._is_precise():
            return self._move_to_precise(x, y, duration)
        return self._move_to_natural(x, y, duration)

    def _move_to_precise(
        self, x: int, y: int, duration: float | None,
    ) -> tuple[int, int]:
        actual_x, actual_y = x, y
        if duration is None:
            sx, sy = self._get_mouse_pos()
            distance = math.hypot(actual_x - sx, actual_y - sy)
            duration = min(0.3, max(0.05, distance / 2000))
        self._backend.move_anim(actual_x, actual_y, duration, self._get_mouse_pos, self._ensure_safe_position)
        return actual_x, actual_y

    def _move_to_natural(
        self, x: int, y: int, duration: float | None,
    ) -> tuple[int, int]:
        ox = self._rng.randint(-2, 2)
        oy = self._rng.randint(-2, 2)
        actual_x, actual_y = x + ox, y + oy
        if duration is None:
            sx, sy = self._get_mouse_pos()
            distance = math.hypot(actual_x - sx, actual_y - sy)
            duration = self._fitts_duration(distance)
        self._backend.move_anim(actual_x, actual_y, duration, self._get_mouse_pos, self._ensure_safe_position)
        return actual_x, actual_y

    # ── 点击操作（基于当前位置）──────────────────────────────────────

    def _click_at(
        self, x: int, y: int, button: str = "left", clicks: int = 1,
        *, clamp: tuple[int, int, int, int] | None = None,
    ) -> None:
        """在当前位置执行点击：按下 → 自然漂移 → 抬起"""
        pre_delay = 0.01 if self._is_precise() else self._rng.uniform(0.02, 0.08)
        time.sleep(pre_delay)
        for i in range(clicks):
            if self._is_precise():
                px, py = x, y
            else:
                px = x + self._rng.choice([-1, 0, 0, 1])
                py = y + self._rng.choice([-1, 0, 0, 1])

            if clamp is not None:
                px = max(clamp[0], min(clamp[2], px))
                py = max(clamp[1], min(clamp[3], py))

            self._backend.micro(px, py)
            cn = self._backend.mouse_down(px, py, button)
            hold_delay = 0.01 if self._is_precise() else self._rng.uniform(0.02, 0.05)
            time.sleep(hold_delay)
            if self._is_precise():
                rx, ry = px, py
            else:
                rx, ry = self._backend.hold_drift(px, py, button, clamp=clamp)
            self._backend.mouse_up(rx, ry, button, cn)
            if i < clicks - 1:
                multi_delay = 0.02 if self._is_precise() else self._rng.uniform(0.08, 0.16)
                time.sleep(multi_delay)
        log.info(t("input.log.click", x=x, y=y, button=button, clicks=clicks))

    def left_click(self, x: int, y: int) -> None:
        """左键点击"""
        self._click_at(x, y, button="left", clicks=1)

    def right_click(self, x: int, y: int) -> None:
        """右键点击"""
        self._click_at(x, y, button="right", clicks=1)

    def left_double_click(self, x: int, y: int) -> None:
        """左键双击"""
        self._click_at(x, y, button="left", clicks=2)

    def right_double_click(self, x: int, y: int) -> None:
        """右键双击"""
        self._click_at(x, y, button="right", clicks=2)

    def long_press(
        self,
        x: int,
        y: int,
        duration: float = 1.0,
        stop_check: Callable[[], bool] | None = None,
        *,
        clamp: tuple[int, int, int, int] | None = None,
    ) -> None:
        """长按：按下鼠标 → 等待 → 松开（可中断）。"""
        time.sleep(self._rng.uniform(0.02, 0.08))
        if self._is_precise():
            px, py = x, y
        else:
            px = x + self._rng.choice([-1, 0, 0, 1])
            py = y + self._rng.choice([-1, 0, 0, 1])
        if clamp is not None:
            px = max(clamp[0], min(clamp[2], px))
            py = max(clamp[1], min(clamp[3], py))
        self._backend.micro(px, py)
        cn = self._backend.mouse_down(px, py, "left")
        log.info(t("input.log.long_press", x=x, y=y, duration=f"{duration:.1f}"))
        try:
            deadline = time.monotonic() + duration
            while True:
                if stop_check and stop_check():
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))
        finally:
            self._backend.mouse_up(px, py, "left", cn)

    def drag_to(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float | None = None,
    ) -> None:
        """从 (x1,y1) 拖拽到 (x2,y2)"""
        if duration is None:
            duration = self._rng.uniform(0.3, 0.6)
        ox = self._rng.randint(-2, 2)
        oy = self._rng.randint(-2, 2)
        ax, ay = self.move_to(x1, y1, duration=self._rng.uniform(0.15, 0.3))
        time.sleep(self._rng.uniform(0.05, 0.15))
        cn = self._backend.mouse_down(ax, ay, "left")
        self._backend.move_anim(x2 + ox, y2 + oy, duration, self._get_mouse_pos, self._ensure_safe_position)
        self._backend.mouse_up(x2 + ox, y2 + oy, "left", cn)
        log.info(t("input.log.drag", x1=x1, y1=y1, x2=x2, y2=y2))

    def click_rect_center(
        self,
        rect: tuple[int, int, int, int],
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> None:
        """点击匹配区域中心（带随机偏移）"""
        x, y, w, h = rect
        cx = x + w // 2 + self._rng.randint(-w // 6, w // 6) + offset_x
        cy = y + h // 2 + self._rng.randint(-h // 6, h // 6) + offset_y
        ax, ay = self.move_to(cx, cy)
        self._click_at(ax, ay, button="left", clicks=1)

    # ── 兼容旧调用 ──────────────────────────────────────────────

    def click(
        self,
        x: int,
        y: int,
        button: str = "left",
        clicks: int = 1,
        move_duration: float | None = None,
        *,
        clamp: tuple[int, int, int, int] | None = None,
    ) -> None:
        """移动到 (x, y) 并点击。clamp: (min_x, min_y, max_x, max_y) 按钮边界约束。"""
        ax, ay = self.move_to(x, y, duration=move_duration)
        self._click_at(ax, ay, button=button, clicks=clicks, clamp=clamp)

    # ── 键盘 ──────────────────────────────────────────────────────

    def press_key(self, key: str) -> None:
        """按下并释放一个键"""
        self._ensure_safe_position()
        time.sleep(self._rng.uniform(0.01, 0.05))
        self._backend.key_down(key)
        time.sleep(self._rng.uniform(0.03, 0.07))
        self._backend.key_up(key)
        log.debug(t("input.log.key_press", key_name=key))

    def click_current_pos(
        self, button: str = "left",
        *, clamp: tuple[int, int, int, int] | None = None,
    ) -> None:
        """在当前鼠标位置点击指定按钮（左/中/右），带自然漂移。"""
        x, y = self._get_mouse_pos()
        self._click_at(x, y, button=button, clamp=clamp)

    def type_string(self, text: str, interval: float | None = None) -> None:
        """逐字输入字符串（仅支持 ASCII，中文需使用剪贴板方案）"""
        self._ensure_safe_position()
        tcfg = self._typing_config
        word_count = 0

        for ch in text:
            self._backend.key_down(ch)
            time.sleep(self._rng.uniform(0.03, 0.07))
            self._backend.key_up(ch)

            if interval is not None:
                time.sleep(interval)
            else:
                wait = self._rng.gammavariate(2.0, 0.04)
                delay = max(0.03, min(0.25, wait))

                if ch in _PUNCTUATION:
                    delay *= tcfg.punctuation_multiplier

                time.sleep(delay)

            if ch == " ":
                word_count += 1
                if (
                    tcfg.thinking_pause_interval > 0
                    and word_count % tcfg.thinking_pause_interval == 0
                ):
                    pause = self._rng.uniform(*tcfg.thinking_pause_range)
                    time.sleep(pause)

    def type_text(
        self, text: str, char_delay: tuple[float, float] = (0.03, 0.15)
    ) -> None:
        """逐字符输入文本，随机延迟模拟人类打字。"""
        import subprocess

        paste_key = "cmd" if IS_MACOS else "ctrl"

        non_ascii_buf: list[str] = []

        def flush_non_ascii() -> None:
            if not non_ascii_buf:
                return
            payload = "".join(non_ascii_buf)
            non_ascii_buf.clear()
            if IS_WINDOWS:
                with subprocess.Popen(["clip"], stdin=subprocess.PIPE) as proc:
                    proc.communicate(payload.encode("utf-16-le"))
            else:
                with subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE) as proc:
                    proc.communicate(payload.encode("utf-8"))
            time.sleep(0.02)
            self._key_combo_quick([paste_key, "v"])

        for ch in text:
            if ord(ch) > 127:
                non_ascii_buf.append(ch)
            else:
                flush_non_ascii()
                if ch == " ":
                    self.press_key("space")
                elif ch == "\n":
                    self.press_key("enter")
                elif ch == "\t":
                    self.press_key("tab")
                elif ch.isupper():
                    self._key_combo_quick(["shift", ch.lower()])
                else:
                    self.press_key(ch)
            time.sleep(self._rng.uniform(*char_delay))

        flush_non_ascii()

    def _key_combo_quick(self, keys: list[str]) -> None:
        """快速组合键：按下所有键 → 松开所有键"""
        self._ensure_safe_position()
        try:
            for key in keys:
                self._backend.key_down(key)
                time.sleep(self._rng.uniform(0.02, 0.05))
            time.sleep(self._rng.uniform(0.03, 0.07))
        finally:
            for key in reversed(keys):
                self._backend.key_up(key)

    def scroll(self, clicks: int, horizontal: bool = False) -> None:
        """滚轮操作，带随机延迟防检测。horizontal=True 时水平滚动。"""
        time.sleep(self._rng.uniform(0.02, 0.08))
        if horizontal:
            self._backend.scroll_horizontal(clicks)
        else:
            self._backend.scroll(clicks)
        direction = t("input.log.scroll_up") if clicks > 0 else t("input.log.scroll_down")
        log.debug(t("input.log.scroll", direction=direction, clicks=abs(clicks)))

    def key_hold(self, key: str, duration: float) -> None:
        """按住按键指定时长，确保异常时也能松开"""
        self._ensure_safe_position()
        time.sleep(self._rng.uniform(0.01, 0.03))
        try:
            self._backend.key_down(key)
            time.sleep(duration)
        finally:
            self._backend.key_up(key)
        log.debug(t("input.log.key_hold", key_name=key, duration=f"{duration:.1f}"))

    def key_hold_interruptible(
        self,
        key: str,
        duration: float,
        stop_check: Callable[[], bool] | None = None,
        interval: float = 0.05,
    ) -> bool:
        """可中断的按键按住，轮询检测 stop_check，返回 True 表示被中断"""
        self._ensure_safe_position()
        time.sleep(self._rng.uniform(0.01, 0.04))
        try:
            self._backend.key_down(key)
            deadline = time.monotonic() + duration
            while True:
                if stop_check and stop_check():
                    return True
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(interval, remaining))
        finally:
            self._backend.key_up(key)
        return False

    def key_combo_staggered(
        self,
        keys_hold: list[str],
        keys_tap: list[str],
        hold_duration: float = 1.0,
        tap_interval: float | None = None,
        stop_check: Callable[[], bool] | None = None,
    ) -> bool:
        """组合键执行器：交错按下 hold 键 → tap 键 → 持续按住 → 交错松开"""
        self._ensure_safe_position()
        keys_tap_pressed: list[str] = []
        try:
            for i, key in enumerate(keys_hold):
                self._backend.key_down(key)
                log.debug(t("input.log.key_down", key_name=key))
                if i < len(keys_hold) - 1:
                    time.sleep(self._rng.uniform(0.03, 0.08))

            if keys_hold:
                time.sleep(self._rng.uniform(0.05, 0.12))

            for i, key in enumerate(keys_tap):
                if stop_check and stop_check():
                    log.debug(t("input.log.combo_interrupted_tap"))
                    return True
                self._backend.key_down(key)
                keys_tap_pressed.append(key)
                time.sleep(self._rng.uniform(0.03, 0.07))
                self._backend.key_up(key)
                keys_tap_pressed.pop()
                log.debug(t("input.log.combo_tap", key_name=key))
                if i < len(keys_tap) - 1:
                    interval = tap_interval or self._rng.uniform(0.08, 0.20)
                    time.sleep(interval)

            if keys_hold and hold_duration > 0:
                deadline = time.monotonic() + hold_duration
                while True:
                    if stop_check and stop_check():
                        log.debug(t("input.log.combo_interrupted_hold"))
                        return True
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    time.sleep(min(0.05, remaining))
        finally:
            for key in reversed(keys_tap_pressed):
                self._backend.key_up(key)
                log.debug(t("input.log.combo_release_tap", key_name=key))
            for i, key in enumerate(reversed(keys_hold)):
                self._backend.key_up(key)
                log.debug(t("input.log.key_up", key_name=key))
                if i < len(keys_hold) - 1:
                    time.sleep(self._rng.uniform(0.02, 0.06))

        log.info(t("input.log.combo_summary", keys_hold=keys_hold, keys_tap=keys_tap))
        return False

    def reset_click_state(self) -> None:
        """重置点击计数（切换窗口或长时间暂停后调用）"""
        self._backend.reset_click_state()

    # ── 等待方法（无平台差异）───────────────────────────────────────

    @staticmethod
    def wait(seconds: float) -> None:
        """精确等待（使用绝对时间戳避免 sleep 超时累积漂移）"""
        if seconds <= 0:
            log.warning(t("input.log.wait_invalid", seconds=f"{seconds:.2f}"))
            return
        log.info(t("input.log.wait_fixed", seconds=f"{seconds:.2f}"))
        time.sleep(seconds)

    @staticmethod
    def wait_random(min_sec: float, max_sec: float) -> None:
        """在 [min_sec, max_sec] 范围内随机等待"""
        if min_sec > max_sec:
            min_sec, max_sec = max_sec, min_sec
        delay = random.uniform(min_sec, max_sec)
        if delay <= 0:
            log.warning(t("input.log.random_wait_invalid", min=f"{min_sec:.2f}", max=f"{max_sec:.2f}", actual=f"{delay:.2f}"))
            return
        log.info(t("input.log.random_wait", actual=f"{delay:.2f}", min=f"{min_sec:.2f}", max=f"{max_sec:.2f}"))
        deadline = time.monotonic() + delay
        remaining = delay
        while remaining > 0:
            time.sleep(remaining)
            remaining = deadline - time.monotonic()

    @staticmethod
    def wait_interruptible(
        seconds: float, stop_check: Callable[[], bool] | None = None, interval: float = 0.1
    ) -> bool:
        """可中断等待，每 interval 秒检查一次 stop_check，返回 True 表示被中断"""
        if seconds <= 0:
            log.warning(t("input.log.wait_invalid", seconds=f"{seconds}"))
            return False
        log.info(t("input.log.wait_fixed", seconds=f"{seconds:.2f}"))
        deadline = time.monotonic() + seconds
        while True:
            if stop_check is not None and stop_check():
                return True
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            time.sleep(min(interval, remaining))
        return False

    def wait_random_interruptible(
        self, min_sec: float, max_sec: float, stop_check: Callable[[], bool] | None = None
    ) -> bool:
        """随机可中断等待，返回 True 表示被中断"""
        if min_sec > max_sec:
            min_sec, max_sec = max_sec, min_sec
        delay = random.uniform(min_sec, max_sec)
        if delay <= 0:
            log.warning(t("input.log.random_wait_invalid", min=f"{min_sec}", max=f"{max_sec}", actual=f"{delay:.2f}"))
            return False
        log.info(t("input.log.random_wait", actual=f"{delay:.2f}", min=f"{min_sec}", max=f"{max_sec}"))
        return self.wait_interruptible(delay, stop_check)
