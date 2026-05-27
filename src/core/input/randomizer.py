"""输入随机化工具 — 缓动函数、延迟加载 pyautogui。"""

import math
import threading

from src.utils.i18n import t
from src.utils.platform import IS_MACOS


def ease_in_out(value: float) -> float:
    """Cosine ease-in-out: 0→1 smoothly with slow start/end."""
    return 0.5 - 0.5 * math.cos(math.pi * value)


_pyautogui = None


def get_pyautogui():
    """延迟加载 pyautogui，仅在需要时导入并配置。

    macOS 上 import pyautogui 会加载 _pyautogui_osx 模块，
    其内部的 ctypes 初始化可能触发 HIToolbox 的
    TSMGetInputSourceProperty（仅允许主线程调用）。
    延迟加载确保 macOS + Quartz 路径下 pyautogui 永远不被加载。
    """
    if IS_MACOS and threading.current_thread() is not threading.main_thread():
        raise RuntimeError(
            t("input.log.pyautogui_thread_error")
        )
    global _pyautogui
    if _pyautogui is None:
        import pyautogui as _pa
        _pa.PAUSE = 0
        _pa.FAILSAFE = True
        _pyautogui = _pa
    return _pyautogui


# ── macOS Quartz keycode 映射 ────────────────────────────────────

KEY_MAP_MACOS: dict[str, int] = {
    "a": 0x00, "s": 0x01, "d": 0x02, "f": 0x03, "h": 0x04,
    "g": 0x05, "z": 0x06, "x": 0x07, "c": 0x08, "v": 0x09,
    "b": 0x0B, "q": 0x0C, "w": 0x0D, "e": 0x0E, "r": 0x0F,
    "y": 0x10, "t": 0x11, "1": 0x12, "2": 0x13, "3": 0x14,
    "4": 0x15, "6": 0x16, "5": 0x17, "=": 0x18, "9": 0x19,
    "7": 0x1A, "-": 0x1B, "8": 0x1C, "0": 0x1D, "]": 0x1E,
    "o": 0x1F, "u": 0x20, "[": 0x21, "i": 0x22, "p": 0x23,
    "return": 0x24, "enter": 0x24, "l": 0x25, "j": 0x26,
    "'": 0x27, "k": 0x28, ";": 0x29, "\\": 0x2A, ",": 0x2B,
    "/": 0x2C, "n": 0x2D, "m": 0x2E, ".": 0x2F, "tab": 0x30,
    "space": 0x31, "grave": 0x32, "`": 0x32, "delete": 0x33,
    "backspace": 0x33, "escape": 0x35, "esc": 0x35,
    "ctrl": 0x3B, "control": 0x3B,
    "alt": 0x3A, "option": 0x3A, "alt_gr": 0x3A, "alt_gr_l": 0x3A,
    "cmd": 0x37, "command": 0x37, "win": 0x37, "windows": 0x37,
    "shift": 0x38, "right_shift": 0x3C, "capslock": 0x39,
    "up": 0x7E, "down": 0x7D, "left": 0x7B, "right": 0x7C,
    "home": 0x73, "end": 0x77, "pageup": 0x74, "pagedown": 0x79,
    "deleteforward": 0x75, "forwarddelete": 0x75,
    "f1": 0x7A, "f2": 0x78, "f3": 0x63, "f4": 0x76,
    "f5": 0x60, "f6": 0x61, "f7": 0x62, "f8": 0x64,
    "f9": 0x65, "f10": 0x6D, "f11": 0x67, "f12": 0x6F,
}

# ── Windows VK code 映射 ─────────────────────────────────────────

KEY_MAP_WINDOWS: dict[str, int] = {
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59,
    "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "return": 0x0D, "enter": 0x0D,
    "escape": 0x1B, "esc": 0x1B,
    "backspace": 0x08, "delete": 0x2E, "deleteforward": 0x2E,
    "forwarddelete": 0x2E,
    "tab": 0x09, "space": 0x20,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "insert": 0x2D,
    "shift": 0x10, "ctrl": 0x11, "control": 0x11,
    "alt": 0x12, "option": 0x12,
    "cmd": 0x5B, "command": 0x5B, "win": 0x5B, "windows": 0x5B,
    "capslock": 0x14,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "grave": 0xC0, "`": 0xC0,
    "=": 0xBB, "-": 0xBD, "]": 0xDD, "[": 0xDB,
    "\\": 0xDC, "/": 0xBF, "'": 0xDE, ";": 0xBA,
    ",": 0xBC, ".": 0xBE,
}
