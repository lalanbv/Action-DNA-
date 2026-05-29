"""MacroRecorder — 输入事件捕获器

macOS: Quartz CGEventTap 监听系统级事件
Windows: 预留（Phase 7）
"""

from __future__ import annotations

import logging
import math
import threading
import time
from collections import deque
from dataclasses import dataclass

from src.utils.platform import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordedEvent:
    """录制的输入事件（不可变）。

    Attributes:
        event_type: 事件类型
            - 鼠标: "mouse_move", "mouse_down", "mouse_up", "mouse_scroll", "mouse_drag"
            - 键盘: "key_down", "key_up"
        x: 鼠标 X 坐标（键盘事件为 0）
        y: 鼠标 Y 坐标（键盘事件为 0）
        key: 按键名称（鼠标事件为空字符串）
        button: 鼠标按钮 "left"/"right"/"middle"（键盘事件为空字符串）
        timestamp: 事件绝对时间戳 (time.time())
        delta_time: 距上一个事件的时间差（秒），首个事件为 0.0
    """

    event_type: str
    x: int = 0
    y: int = 0
    key: str = ""
    button: str = ""
    scroll_delta: int = 0
    scroll_delta_x: int = 0
    timestamp: float = 0.0
    delta_time: float = 0.0
    flags: int = 0
    is_repeat: bool = False

    @property
    def is_mouse_event(self) -> bool:
        return self.event_type.startswith("mouse_")

    @property
    def is_key_event(self) -> bool:
        return self.event_type.startswith("key_")


class MacroRecorder:
    """宏录制器。

    使用平台底层 API 捕获鼠标/键盘事件，线程安全。
    鼠标坐标可相对录制区域偏移。

    使用方式:
        recorder = MacroRecorder(region=(100, 50, 800, 600))
        recorder.start()
        # ... 用户操作 ...
        events = recorder.stop()
    """

    _DEDUP_DISTANCE_THRESHOLD_SQ: float = 1.0  # 1.0px² → 距离 < 1px 视为抖动

    def __init__(self, region: tuple[int, int, int, int] | None = None) -> None:
        self._events: deque[RecordedEvent] = deque()
        self._lock = threading.Lock()
        self._is_recording: bool = False
        self._start_time: float = 0.0
        self._last_event_time: float = 0.0
        self._region = region
        self._capture_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._modifier_state: dict[str, bool] = {}
        self._run_loop = None
        self._last_mouse_move_pos: tuple[int, int] | None = None

    # ---- 公开接口 ----

    def _set_recording(self, value: bool) -> None:
        """线程安全地设置 _is_recording 标志。"""
        with self._lock:
            self._is_recording = value

    def start(self) -> None:
        """开始录制（清空之前的事件，启动捕获线程）。"""
        if self.is_recording:
            self.stop()

        with self._lock:
            self._events.clear()
            self._is_recording = True
            self._start_time = time.time()
            self._last_event_time = self._start_time
            self._modifier_state.clear()
            self._last_mouse_move_pos = None
        self._stop_event.clear()

        self._capture_thread = threading.Thread(
            target=self._capture_loop,
            name="MacroRecorder",
            daemon=True,
        )
        self._capture_thread.start()
        logger.info("宏录制已开始")

    def stop(self) -> list[RecordedEvent]:
        """停止录制，返回事件列表副本。"""
        self._stop_event.set()
        with self._lock:
            self._is_recording = False

        if self._run_loop is not None:
            try:
                from Quartz import CFRunLoopStop
                CFRunLoopStop(self._run_loop)
            except Exception:
                pass
            self._run_loop = None

        if self._capture_thread and self._capture_thread.is_alive():
            self._capture_thread.join(timeout=2.0)

        with self._lock:
            events = list(self._events)
        move_count = sum(1 for e in events if e.event_type == "mouse_move")
        drag_count = sum(1 for e in events if e.event_type == "mouse_drag")
        scroll_count = sum(1 for e in events if e.event_type == "mouse_scroll")
        click_count = sum(1 for e in events if e.event_type in ("mouse_down", "mouse_up"))
        key_count = sum(1 for e in events if e.event_type.startswith("key_"))
        logger.info(
            "宏录制已停止，共 %d 事件 (移动:%d 拖拽:%d 滚轮:%d 点击:%d 按键:%d)",
            len(events), move_count, drag_count, scroll_count, click_count, key_count,
        )
        return events

    @property
    def is_recording(self) -> bool:
        with self._lock:
            return self._is_recording

    @property
    def event_count(self) -> int:
        with self._lock:
            return len(self._events)

    @property
    def duration(self) -> float:
        with self._lock:
            if not self._is_recording:
                return 0.0
            return time.time() - self._start_time

    def snapshot_events(self) -> list[RecordedEvent]:
        """返回当前已捕获事件列表的线程安全副本。"""
        with self._lock:
            return list(self._events)

    # ---- 事件回调（线程安全）----

    def _on_mouse_event(
        self,
        event_type: str,
        x: int,
        y: int,
        button: str,
        timestamp: float,
        delta_time: float,
        flags: int = 0,
    ) -> None:
        if not self._is_recording:
            return
        with self._lock:
            if not self._is_recording:
                return

            # Dedup only mouse_move — O(1) comparison with cached last position
            if event_type == "mouse_move":
                if self._last_mouse_move_pos is not None:
                    lx, ly = self._last_mouse_move_pos
                    dx, dy = x - lx, y - ly
                    if dx * dx + dy * dy < self._DEDUP_DISTANCE_THRESHOLD_SQ:
                        return

            self._events.append(RecordedEvent(
                event_type=event_type,
                x=x,
                y=y,
                button=button,
                timestamp=timestamp,
                delta_time=delta_time,
                flags=flags,
            ))
            self._last_event_time = timestamp
            if event_type == "mouse_move":
                self._last_mouse_move_pos = (x, y)

    def _on_key_event(
        self,
        event_type: str,
        key: str,
        timestamp: float,
        delta_time: float,
        flags: int = 0,
        is_repeat: bool = False,
    ) -> None:
        if not self._is_recording:
            return
        with self._lock:
            if not self._is_recording:
                return
            self._events.append(RecordedEvent(
                event_type=event_type,
                key=key,
                timestamp=timestamp,
                delta_time=delta_time,
                flags=flags,
                is_repeat=is_repeat,
            ))
            self._last_event_time = timestamp

    def _on_scroll_event(
        self,
        x: int,
        y: int,
        delta: int,
        timestamp: float,
        delta_time: float,
        flags: int = 0,
        delta_x: int = 0,
    ) -> None:
        if not self._is_recording:
            return
        with self._lock:
            if not self._is_recording:
                return

            self._events.append(RecordedEvent(
                event_type="mouse_scroll",
                x=x,
                y=y,
                scroll_delta=delta,
                scroll_delta_x=delta_x,
                timestamp=timestamp,
                delta_time=delta_time,
                flags=flags,
            ))
            self._last_event_time = timestamp

    # ---- 平台捕获循环 ----

    def _capture_loop(self) -> None:
        if IS_MACOS:
            self._capture_loop_macos()
        elif IS_WINDOWS:
            self._capture_loop_windows()
        else:
            logger.error("不支持的平台: Linux")
            self._set_recording(False)

    def _capture_loop_macos(self) -> None:
        """macOS: Quartz CGEventTap 监听系统级输入事件。"""
        try:
            from Quartz import (
                CGEventTapCreate,
                kCGSessionEventTap,
                kCGHeadInsertEventTap,
                kCGEventTapOptionListenOnly,
                kCGEventMouseMoved,
                kCGEventLeftMouseDown,
                kCGEventLeftMouseUp,
                kCGEventRightMouseDown,
                kCGEventRightMouseUp,
                kCGEventOtherMouseDown,
                kCGEventOtherMouseUp,
                kCGEventLeftMouseDragged,
                kCGEventRightMouseDragged,
                kCGEventOtherMouseDragged,
                kCGEventKeyDown,
                kCGEventKeyUp,
                kCGEventScrollWheel,
                kCGEventFlagsChanged,
                kCGKeyboardEventKeycode,
                kCGKeyboardEventAutorepeat,
                kCGScrollWheelEventDeltaAxis1,
                kCGScrollWheelEventDeltaAxis2,
                kCGScrollWheelEventIsContinuous,
                kCGScrollWheelEventPointDeltaAxis1,
                kCGScrollWheelEventPointDeltaAxis2,
                kCGEventFlagMaskShift,
                kCGEventFlagMaskControl,
                kCGEventFlagMaskAlternate,
                kCGEventFlagMaskCommand,
                CGEventGetIntegerValueField,
                CGEventGetLocation,
                CGEventGetFlags,
                CGEventTapEnable,
                CFMachPortInvalidate,
                CFRunLoopGetCurrent,
                CFRunLoopRun,
                CFRunLoopStop,
                CFMachPortCreateRunLoopSource,
                CFRunLoopAddSource,
                kCFRunLoopCommonModes,
            )
        except ImportError:
            logger.error(
                "macOS 需要 pyobjc-framework-Quartz 库。"
                "安装命令: pip install pyobjc-framework-Quartz"
            )
            self._set_recording(False)
            return

        MOUSE_EVENT_MAP: dict[int, tuple[str, str]] = {
            kCGEventMouseMoved: ("mouse_move", ""),
            kCGEventLeftMouseDown: ("mouse_down", "left"),
            kCGEventLeftMouseUp: ("mouse_up", "left"),
            kCGEventRightMouseDown: ("mouse_down", "right"),
            kCGEventRightMouseUp: ("mouse_up", "right"),
            kCGEventOtherMouseDown: ("mouse_down", "middle"),
            kCGEventOtherMouseUp: ("mouse_up", "middle"),
            kCGEventLeftMouseDragged: ("mouse_drag", "left"),
            kCGEventRightMouseDragged: ("mouse_drag", "right"),
            kCGEventOtherMouseDragged: ("mouse_drag", "middle"),
        }

        KEYCODE_MAP: dict[int, str] = {
            0: "a", 1: "s", 2: "d", 3: "f", 4: "h", 5: "g",
            6: "z", 7: "x", 8: "c", 9: "v", 11: "b", 12: "q",
            13: "w", 14: "e", 15: "r", 16: "y", 17: "t",
            18: "1", 19: "2", 20: "3", 21: "4", 22: "6",
            23: "5", 24: "=", 25: "9", 26: "7", 27: "-",
            28: "8", 29: "0", 30: "]", 31: "o", 32: "u",
            33: "[", 34: "i", 35: "p", 36: "enter", 37: "l",
            38: "j", 39: "'", 40: "k", 41: ";", 42: "\\",
            43: ",", 44: "/", 45: "n", 46: "m", 47: ".",
            48: "tab", 49: "space", 50: "`", 51: "backspace",
            53: "escape",
            55: "cmd", 56: "shift", 57: "capslock", 58: "alt",
            59: "ctrl",
            122: "f1", 120: "f2", 99: "f3", 118: "f4", 96: "f5",
            97: "f6", 98: "f7", 100: "f8", 101: "f9", 109: "f10",
            103: "f11", 111: "f12",
            115: "home", 119: "end", 116: "pageup", 121: "pagedown",
            117: "forwarddelete",
            123: "left", 124: "right", 125: "down", 126: "up",
            65: "numpad_decimal", 67: "numpad_multiply", 69: "numpad_plus",
            75: "numpad_divide", 78: "numpad_minus", 71: "numpad_clear",
            81: "numpad_equals", 76: "numpad_enter",
            83: "numpad_0", 84: "numpad_1", 85: "numpad_2",
            86: "numpad_3", 87: "numpad_4", 88: "numpad_5",
            89: "numpad_6", 91: "numpad_7", 92: "numpad_8",
            93: "numpad_9",
        }

        _MODIFIER_KEYCODES: dict[int, str] = {
            55: "cmd", 56: "shift", 58: "alt", 59: "ctrl",
        }
        _FLAG_BITS: dict[str, int] = {
            "shift": kCGEventFlagMaskShift,
            "ctrl": kCGEventFlagMaskControl,
            "alt": kCGEventFlagMaskAlternate,
            "cmd": kCGEventFlagMaskCommand,
        }

        modifier_state = self._modifier_state
        last_flags = [0]

        # mach_absolute_time → seconds conversion
        try:
            from Quartz import (
                CGEventGetTimestamp,
                mach_absolute_time,
                mach_timebase_info,
            )
            _timebase_info = mach_timebase_info()
            _timebase_numer = _timebase_info[0]
            _timebase_denom = _timebase_info[1]

            def _event_timestamp_to_seconds(cg_event) -> float:
                nanos = (
                    CGEventGetTimestamp(cg_event) * _timebase_numer
                    / _timebase_denom
                )
                return nanos / 1_000_000_000.0

            _start_mach = mach_absolute_time()
            _start_wall = time.time()
            _mach_to_wall_offset = _start_wall - (
                _start_mach * _timebase_numer / _timebase_denom / 1_000_000_000.0
            )

            def _get_event_time(cg_event) -> float:
                return _event_timestamp_to_seconds(cg_event) + _mach_to_wall_offset

        except ImportError:
            def _get_event_time(cg_event) -> float:
                return time.time()

        run_loop = CFRunLoopGetCurrent()
        self._run_loop = run_loop

        _cb_count = [0]
        _first_of_type: dict[int, bool] = {}
        tap_ref = [None]

        def callback(proxy, event_type, event, refcon):
            if self._stop_event.is_set():
                CFRunLoopStop(run_loop)
                return event

            if event_type == 0xFFFFFFFF:
                logger.warning("CGEventTap 被系统超时禁用，尝试重新启用")
                if tap_ref[0] is not None:
                    CGEventTapEnable(tap_ref[0], True)
                return event

            _cb_count[0] += 1
            if event_type not in _first_of_type:
                _first_of_type[event_type] = True
                etype_name = MOUSE_EVENT_MAP.get(event_type, (str(event_type), ""))[0]
                if event_type == kCGEventScrollWheel:
                    etype_name = "scroll"
                elif event_type in (kCGEventKeyDown, kCGEventKeyUp):
                    etype_name = "key"
                elif event_type == kCGEventFlagsChanged:
                    etype_name = "flags_changed"
                logger.info("CGEvent 首次捕获: type=%d (%s)", event_type, etype_name)

            now = _get_event_time(event)
            delta = now - self._last_event_time
            current_flags = int(CGEventGetFlags(event))

            if event_type in MOUSE_EVENT_MAP:
                etype, button = MOUSE_EVENT_MAP[event_type]
                loc = CGEventGetLocation(event)
                x = int(loc.x)
                y = int(loc.y)

                if self._region:
                    x -= self._region[0]
                    y -= self._region[1]

                self._on_mouse_event(etype, x, y, button, now, delta, current_flags)

            elif event_type in (kCGEventKeyDown, kCGEventKeyUp):
                etype = "key_down" if event_type == kCGEventKeyDown else "key_up"
                keycode = CGEventGetIntegerValueField(
                    event, kCGKeyboardEventKeycode,
                )

                # 修饰键由 kCGEventFlagsChanged 统一处理，跳过以避免重复事件
                if keycode in _MODIFIER_KEYCODES:
                    last_flags[0] = current_flags
                    return event

                key_name = KEYCODE_MAP.get(keycode, f"key_{keycode}")

                is_repeat = bool(CGEventGetIntegerValueField(
                    event, kCGKeyboardEventAutorepeat,
                ))

                self._on_key_event(
                    etype, key_name, now, delta,
                    flags=current_flags, is_repeat=is_repeat,
                )

                last_flags[0] = current_flags

            elif event_type == kCGEventFlagsChanged:
                keycode = CGEventGetIntegerValueField(
                    event, kCGKeyboardEventKeycode,
                )
                key_name = KEYCODE_MAP.get(keycode, f"key_{keycode}")

                if keycode in _MODIFIER_KEYCODES:
                    mod_name = _MODIFIER_KEYCODES[keycode]
                    flag_bit = _FLAG_BITS.get(mod_name, 0)
                    is_now_held = bool(current_flags & flag_bit)
                    was_held = modifier_state.get(mod_name, False)

                    if is_now_held and not was_held:
                        self._on_key_event(
                            "key_down", key_name, now, delta,
                            flags=current_flags,
                        )
                        modifier_state[mod_name] = True
                    elif was_held and not is_now_held:
                        self._on_key_event(
                            "key_up", key_name, now, delta,
                            flags=current_flags,
                        )
                        modifier_state[mod_name] = False

                last_flags[0] = current_flags

            elif event_type == kCGEventScrollWheel:
                is_continuous = CGEventGetIntegerValueField(
                    event, kCGScrollWheelEventIsContinuous,
                )
                if is_continuous:
                    scroll_delta = CGEventGetIntegerValueField(
                        event, kCGScrollWheelEventPointDeltaAxis1,
                    )
                    scroll_delta_x = CGEventGetIntegerValueField(
                        event, kCGScrollWheelEventPointDeltaAxis2,
                    )
                else:
                    scroll_delta = CGEventGetIntegerValueField(
                        event, kCGScrollWheelEventDeltaAxis1,
                    )
                    scroll_delta_x = CGEventGetIntegerValueField(
                        event, kCGScrollWheelEventDeltaAxis2,
                    )
                if scroll_delta == 0 and scroll_delta_x == 0:
                    return event
                loc = CGEventGetLocation(event)
                sx, sy = int(loc.x), int(loc.y)
                if self._region:
                    sx -= self._region[0]
                    sy -= self._region[1]
                self._on_scroll_event(sx, sy, scroll_delta, now, delta, current_flags, delta_x=scroll_delta_x)

            return event

        event_mask = (
            (1 << kCGEventMouseMoved)
            | (1 << kCGEventLeftMouseDown) | (1 << kCGEventLeftMouseUp)
            | (1 << kCGEventRightMouseDown) | (1 << kCGEventRightMouseUp)
            | (1 << kCGEventOtherMouseDown) | (1 << kCGEventOtherMouseUp)
            | (1 << kCGEventLeftMouseDragged)
            | (1 << kCGEventRightMouseDragged)
            | (1 << kCGEventOtherMouseDragged)
            | (1 << kCGEventKeyDown) | (1 << kCGEventKeyUp)
            | (1 << kCGEventFlagsChanged)
            | (1 << kCGEventScrollWheel)
        )

        tap_ref[0] = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            event_mask,
            callback,
            None,
        )

        if tap_ref[0] is None:
            logger.error("无法创建 CGEventTap — 请检查辅助功能权限")
            self._set_recording(False)
            return

        source = CFMachPortCreateRunLoopSource(None, tap_ref[0], 0)
        CFRunLoopAddSource(run_loop, source, kCFRunLoopCommonModes)

        logger.info("macOS CGEventTap 已启动，开始捕获事件")
        CFRunLoopRun()

        CFMachPortInvalidate(tap_ref[0])
        self._run_loop = None
        logger.info("macOS CGEventTap 已停止")

    def _capture_loop_windows(self) -> None:
        """Windows: pynput 监听系统级输入事件。"""
        try:
            from pynput import keyboard as kb, mouse as ms
        except ImportError:
            logger.error(
                "Windows 宏录制需要 pynput 库。"
                "安装命令: pip install pynput"
            )
            self._set_recording(False)
            return

        listeners: list[object] = []

        def on_click(x, y, button, pressed):
            if self._stop_event.is_set():
                return False
            btn_map = {
                ms.Button.left: "left",
                ms.Button.right: "right",
                ms.Button.middle: "middle",
            }
            btn = btn_map.get(button, "left")
            etype = "mouse_down" if pressed else "mouse_up"
            rx, ry = x, y
            if self._region:
                rx -= self._region[0]
                ry -= self._region[1]
            now = time.time()
            self._on_mouse_event(etype, int(rx), int(ry), btn, now, now - self._last_event_time)
            return True

        def on_move(x, y):
            if self._stop_event.is_set():
                return False
            rx, ry = x, y
            if self._region:
                rx -= self._region[0]
                ry -= self._region[1]
            now = time.time()
            self._on_mouse_event("mouse_move", int(rx), int(ry), "", now, now - self._last_event_time)
            return True

        def on_scroll(x, y, dx, dy):
            if self._stop_event.is_set():
                return False
            rx, ry = x, y
            if self._region:
                rx -= self._region[0]
                ry -= self._region[1]
            now = time.time()
            self._on_scroll_event(int(rx), int(ry), int(dy), now, now - self._last_event_time, delta_x=int(dx))
            return True

        def on_key_press(key):
            if self._stop_event.is_set():
                return False
            now = time.time()
            try:
                key_name = key.char if hasattr(key, "char") and key.char else str(key).replace("Key.", "").lower()
            except AttributeError:
                key_name = str(key).replace("Key.", "").lower()
            self._on_key_event("key_down", key_name, now, now - self._last_event_time)
            return True

        def on_key_release(key):
            if self._stop_event.is_set():
                return False
            now = time.time()
            try:
                key_name = key.char if hasattr(key, "char") and key.char else str(key).replace("Key.", "").lower()
            except AttributeError:
                key_name = str(key).replace("Key.", "").lower()
            self._on_key_event("key_up", key_name, now, now - self._last_event_time)
            return True

        try:
            mouse_listener = ms.Listener(
                on_move=on_move,
                on_click=on_click,
                on_scroll=on_scroll,
            )
            keyboard_listener = kb.Listener(
                on_press=on_key_press,
                on_release=on_key_release,
            )
            listeners = [mouse_listener, keyboard_listener]

            mouse_listener.start()
            keyboard_listener.start()

            logger.info("Windows pynput 监听已启动，开始捕获事件")
            self._stop_event.wait()
        except Exception as e:
            logger.error("Windows 宏录制启动失败: %s", e)
        finally:
            for l in listeners:
                try:
                    l.stop()
                except Exception:
                    pass
            self._set_recording(False)
            logger.info("Windows pynput 监听已停止")
