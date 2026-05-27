"""macOS Quartz CGEvent 后端 — HID 级事件模拟。

使用 Quartz CGEvent 直接发送 HID 级事件：
  - kCGEventSourceStateHIDSystemState → 事件源看起来像真实 HID 设备
  - 正确管理 OS 级点击计数（双击/三击检测）
  - 鼠标压力模拟（mouseDown > 0, mouseUp = 0）
  - 点击前 ±1px 微抖动（人手稳定过程）
  - kCGHIDEventTap → 事件通过 HID 系统事件栈发送
"""

from __future__ import annotations

import math
import random
import time
from collections.abc import Callable

from src.core.input.backends import PlatformBackend
from src.core.input.randomizer import KEY_MAP_MACOS, ease_in_out
from src.core.logger import log
from src.utils.i18n import t

try:
    import Quartz
except ImportError:
    raise


class QuartzBackend(PlatformBackend):
    """macOS Quartz CGEvent backend."""

    _BTN_MAP = {"left": "Left", "right": "Right", "center": "Other"}

    def __init__(self) -> None:
        source = Quartz.CGEventSourceCreate(
            Quartz.kCGEventSourceStateHIDSystemState
        )
        if source is None:
            raise RuntimeError("CGEventSourceCreate returned None")
        self._source = source
        self._click_count: int = 0
        self._last_click_time: float = 0.0
        self._last_click_pos: tuple[float, float] = (0.0, 0.0)
        try:
            self._dblclick_interval: float = float(
                Quartz.NSEvent.doubleClickInterval()
            )
        except Exception:
            self._dblclick_interval = 0.5

    def move(self, x: int, y: int) -> None:
        event = Quartz.CGEventCreateMouseEvent(
            self._source,
            Quartz.kCGEventMouseMoved,
            (x, y),
            Quartz.kCGMouseButtonLeft,
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def move_anim(
        self, x: int, y: int, duration: float,
        get_pos: Callable[[], tuple[int, int]],
        ensure_safe: Callable[[], None],
    ) -> None:
        ensure_safe()
        if duration < 0.01:
            self.move(x, y)
            return
        sx, sy = get_pos()
        dx, dy = x - sx, y - sy
        if math.hypot(dx, dy) < 2:
            self.move(x, y)
            return
        n = max(5, int(duration * 60))
        dt = duration / n
        for i in range(1, n + 1):
            t = ease_in_out(i / n)
            self.move(int(sx + dx * t), int(sy + dy * t))
            time.sleep(dt)

    def _click_state(self, x: int, y: int) -> int:
        now = time.monotonic()
        elapsed = now - self._last_click_time
        ddx = abs(x - self._last_click_pos[0])
        ddy = abs(y - self._last_click_pos[1])
        if elapsed < self._dblclick_interval and ddx < 5 and ddy < 5:
            self._click_count = min(self._click_count + 1, 3)
        else:
            self._click_count = 1
        self._last_click_time = now
        self._last_click_pos = (float(x), float(y))
        return self._click_count

    def mouse_down(self, x: int, y: int, button: str) -> int:
        b = self._BTN_MAP.get(button, "Left")
        click_num = self._click_state(x, y)
        event = Quartz.CGEventCreateMouseEvent(
            self._source,
            getattr(Quartz, f"kCGEvent{b}MouseDown"),
            (x, y),
            getattr(Quartz, f"kCGMouseButton{b}"),
        )
        Quartz.CGEventSetIntegerValueField(
            event, Quartz.kCGMouseEventClickState, click_num
        )
        Quartz.CGEventSetDoubleValueField(
            event, Quartz.kCGMouseEventPressure, random.uniform(0.7, 1.0)
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        return click_num

    def mouse_up(
        self, x: int, y: int, button: str, click_num: int | None,
    ) -> None:
        b = self._BTN_MAP.get(button, "Left")
        event = Quartz.CGEventCreateMouseEvent(
            self._source,
            getattr(Quartz, f"kCGEvent{b}MouseUp"),
            (x, y),
            getattr(Quartz, f"kCGMouseButton{b}"),
        )
        Quartz.CGEventSetIntegerValueField(
            event, Quartz.kCGMouseEventClickState, click_num or 1
        )
        Quartz.CGEventSetDoubleValueField(
            event, Quartz.kCGMouseEventPressure, 0.0
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

    def key_down(self, key: str) -> None:
        keycode = KEY_MAP_MACOS.get(key.lower())
        if keycode is not None:
            event = Quartz.CGEventCreateKeyboardEvent(self._source, keycode, True)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            return
        if len(key) == 1:
            event = Quartz.CGEventCreateKeyboardEvent(self._source, 0, True)
            Quartz.CGEventKeyboardSetUnicodeString(event, 1, key)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            return
        log.warning(t("input.log.unsupported_key", key_name=key))

    def key_up(self, key: str) -> None:
        keycode = KEY_MAP_MACOS.get(key.lower())
        if keycode is not None:
            event = Quartz.CGEventCreateKeyboardEvent(self._source, keycode, False)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            return
        if len(key) == 1:
            event = Quartz.CGEventCreateKeyboardEvent(self._source, 0, False)
            Quartz.CGEventKeyboardSetUnicodeString(event, 1, key)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            return
        log.warning(t("input.log.unsupported_key", key_name=key))

    def scroll(self, clicks: int) -> None:
        for _ in range(abs(clicks)):
            amount = random.randint(3, 5)
            if clicks < 0:
                amount = -amount
            event = Quartz.CGEventCreateScrollWheelEvent(
                self._source,
                Quartz.kCGScrollEventUnitLine,
                1,
                amount,
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(random.uniform(0.02, 0.06))

    def scroll_horizontal(self, clicks: int) -> None:
        for _ in range(abs(clicks)):
            amount = random.randint(3, 5)
            if clicks < 0:
                amount = -amount
            event = Quartz.CGEventCreateScrollWheelEvent(
                self._source,
                Quartz.kCGScrollEventUnitLine,
                2,
                0,
                amount,
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
            time.sleep(random.uniform(0.02, 0.06))

    def get_mouse_pos(self) -> tuple[int, int]:
        loc = Quartz.NSEvent.mouseLocation()
        # NSEvent 坐标系 Y 轴从底部开始，CGEvent 从顶部开始
        screen_h = Quartz.CGDisplayPixelsHigh(Quartz.CGMainDisplayID())
        return (int(loc.x), int(screen_h - loc.y))

    def micro(self, x: int, y: int) -> None:
        for _ in range(random.randint(1, 2)):
            self.move(
                x + random.choice([-1, 0, 0, 1]),
                y + random.choice([-1, 0, 0, 1]),
            )
            time.sleep(random.uniform(0.005, 0.015))
        self.move(x, y)

    def hold_drift(
        self, px: int, py: int, button: str = "left", *,
        clamp: tuple[int, int, int, int] | None = None,
    ) -> tuple[int, int]:
        b = self._BTN_MAP.get(button, "Left")
        rx, ry = px, py
        drift_count = 0 if random.random() < 0.2 else (1 if random.random() < 0.7 else 2)
        for _ in range(drift_count):
            time.sleep(random.uniform(0.01, 0.03))
            rx = px + random.randint(-2, 2)
            ry = py + random.randint(-2, 2)
            if clamp is not None:
                rx = max(clamp[0], min(clamp[2], rx))
                ry = max(clamp[1], min(clamp[3], ry))
            drift_event = Quartz.CGEventCreateMouseEvent(
                self._source,
                getattr(Quartz, f"kCGEvent{b}MouseDragged"),
                (rx, ry),
                getattr(Quartz, f"kCGMouseButton{b}"),
            )
            Quartz.CGEventSetIntegerValueField(
                drift_event, Quartz.kCGMouseEventClickState, 1,
            )
            Quartz.CGEventSetDoubleValueField(
                drift_event, Quartz.kCGMouseEventPressure,
                random.uniform(0.6, 1.0),
            )
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, drift_event)
        return rx, ry

    def reset_click_state(self) -> None:
        self._click_count = 0
        self._last_click_time = 0.0
        self._last_click_pos = (0.0, 0.0)
