"""Windows SendInput 后端 — 内核级 HID 事件模拟。

使用 SendInput 直接发送 HID 级事件：
  - SendInput → 注入内核设备驱动输入流
  - 同时填充 wVk + wScan 确保兼容性
  - 绝对坐标用归一化 0-65535 范围
"""

from __future__ import annotations

import math
import random
import sys
import time
from collections.abc import Callable

from src.core.input.backends import PlatformBackend
from src.core.input.randomizer import KEY_MAP_WINDOWS, ease_in_out, get_pyautogui

if sys.platform != "win32":
    raise ImportError("platform_windows is only available on Windows")

import ctypes as _ctypes
from ctypes import wintypes as _wintypes

# SendInput 类型
_INPUT_MOUSE = 0
_INPUT_KEYBOARD = 1

# 键盘标志
_KEYEVENTF_KEYUP = 0x0002

# 鼠标标志
_MOUSEEVENTF_LEFTDOWN = 0x0002
_MOUSEEVENTF_LEFTUP = 0x0004
_MOUSEEVENTF_RIGHTDOWN = 0x0008
_MOUSEEVENTF_RIGHTUP = 0x0010
_MOUSEEVENTF_MIDDLEDOWN = 0x0020
_MOUSEEVENTF_MIDDLEUP = 0x0040
_MOUSEEVENTF_WHEEL = 0x0800
_MOUSEEVENTF_HWHEEL = 0x1000
_WHEEL_DELTA = 120

# 系统指标
_SM_CXSCREEN = 0
_SM_CYSCREEN = 1

# MapVirtualKey 映射类型
_MAPVK_VK_TO_VSC = 0

_ULONG_PTR = _ctypes.c_void_p


class _MOUSEINPUT(_ctypes.Structure):
    _fields_ = [
        ("dx", _ctypes.c_long),
        ("dy", _ctypes.c_long),
        ("mouseData", _ctypes.c_ulong),
        ("dwFlags", _ctypes.c_ulong),
        ("time", _ctypes.c_ulong),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _KEYBDINPUT(_ctypes.Structure):
    _fields_ = [
        ("wVk", _ctypes.c_ushort),
        ("wScan", _ctypes.c_ushort),
        ("dwFlags", _ctypes.c_ulong),
        ("time", _ctypes.c_ulong),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HARDWAREINPUT(_ctypes.Structure):
    _fields_ = [
        ("uMsg", _ctypes.c_ulong),
        ("wParamL", _ctypes.c_ushort),
        ("wParamH", _ctypes.c_ushort),
    ]


class _INPUT_UNION(_ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(_ctypes.Structure):
    _fields_ = [
        ("type", _ctypes.c_ulong),
        ("union", _INPUT_UNION),
    ]


_user32 = _ctypes.windll.user32  # type: ignore[attr-defined]
_user32.SendInput.argtypes = [
    _ctypes.c_uint, _ctypes.POINTER(_INPUT), _ctypes.c_int,
]
_user32.SendInput.restype = _ctypes.c_uint
_user32.SetCursorPos.argtypes = [_ctypes.c_int, _ctypes.c_int]
_user32.SetCursorPos.restype = _wintypes.BOOL
_user32.GetSystemMetrics.argtypes = [_ctypes.c_int]
_user32.GetSystemMetrics.restype = _ctypes.c_int
_user32.MapVirtualKeyExW.argtypes = [
    _ctypes.c_uint, _ctypes.c_uint, _ctypes.c_void_p,
]
_user32.MapVirtualKeyExW.restype = _ctypes.c_uint


def _win_send_mouse(dx: int, dy: int, flags: int, mouse_data: int = 0) -> None:
    inp = _INPUT(
        type=_INPUT_MOUSE,
        union=_INPUT_UNION(mi=_MOUSEINPUT(
            dx=dx, dy=dy, mouseData=mouse_data,
            dwFlags=flags, time=0, dwExtraInfo=0,
        )),
    )
    _user32.SendInput(1, _ctypes.byref(inp), _ctypes.sizeof(inp))


def _win_send_key(vk: int, scan: int, flags: int) -> None:
    inp = _INPUT(
        type=_INPUT_KEYBOARD,
        union=_INPUT_UNION(ki=_KEYBDINPUT(
            wVk=vk, wScan=scan, dwFlags=flags,
            time=0, dwExtraInfo=0,
        )),
    )
    _user32.SendInput(1, _ctypes.byref(inp), _ctypes.sizeof(inp))


class SendInputBackend(PlatformBackend):
    """Windows SendInput backend."""

    def move(self, x: int, y: int) -> None:
        _user32.SetCursorPos(x, y)

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

    def mouse_down(self, x: int, y: int, button: str) -> None:
        _user32.SetCursorPos(x, y)
        flag_map = {
            "left": _MOUSEEVENTF_LEFTDOWN,
            "right": _MOUSEEVENTF_RIGHTDOWN,
            "center": _MOUSEEVENTF_MIDDLEDOWN,
        }
        flag = flag_map.get(button, _MOUSEEVENTF_LEFTDOWN)
        _win_send_mouse(0, 0, flag)

    def mouse_up(
        self, x: int, y: int, button: str, click_num: int | None,
    ) -> None:
        _user32.SetCursorPos(x, y)
        flag_map = {
            "left": _MOUSEEVENTF_LEFTUP,
            "right": _MOUSEEVENTF_RIGHTUP,
            "center": _MOUSEEVENTF_MIDDLEUP,
        }
        flag = flag_map.get(button, _MOUSEEVENTF_LEFTUP)
        _win_send_mouse(0, 0, flag)

    def key_down(self, key: str) -> None:
        vk = KEY_MAP_WINDOWS.get(key.lower())
        if vk is None:
            get_pyautogui().keyDown(key)
            return
        scan = _user32.MapVirtualKeyExW(vk, _MAPVK_VK_TO_VSC, None)
        _win_send_key(vk, scan, 0)

    def key_up(self, key: str) -> None:
        vk = KEY_MAP_WINDOWS.get(key.lower())
        if vk is None:
            get_pyautogui().keyUp(key)
            return
        scan = _user32.MapVirtualKeyExW(vk, _MAPVK_VK_TO_VSC, None)
        _win_send_key(vk, scan, _KEYEVENTF_KEYUP)

    def scroll(self, clicks: int) -> None:
        for _ in range(abs(clicks)):
            amount = random.randint(3, 5) * _WHEEL_DELTA
            if clicks < 0:
                amount = -amount
            _win_send_mouse(0, 0, _MOUSEEVENTF_WHEEL, mouse_data=amount)
            time.sleep(random.uniform(0.02, 0.06))

    def scroll_horizontal(self, clicks: int) -> None:
        for _ in range(abs(clicks)):
            amount = random.randint(3, 5) * _WHEEL_DELTA
            if clicks < 0:
                amount = -amount
            _win_send_mouse(0, 0, _MOUSEEVENTF_HWHEEL, mouse_data=amount)
            time.sleep(random.uniform(0.02, 0.06))

    def get_mouse_pos(self) -> tuple[int, int]:
        return get_pyautogui().position()

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
        rx, ry = px, py
        drift_count = 0 if random.random() < 0.2 else (1 if random.random() < 0.7 else 2)
        for _ in range(drift_count):
            time.sleep(random.uniform(0.01, 0.03))
            rx = px + random.randint(-2, 2)
            ry = py + random.randint(-2, 2)
            if clamp is not None:
                rx = max(clamp[0], min(clamp[2], rx))
                ry = max(clamp[1], min(clamp[3], ry))
            _user32.SetCursorPos(rx, ry)
        return rx, ry
