"""Input 模块 — 输入控制与快捷键管理。"""

from src.core.input.controller import InputController
from src.core.input.hotkey_manager import HotkeyBinding, HotkeyManager

__all__ = ["HotkeyBinding", "HotkeyManager", "InputController"]
