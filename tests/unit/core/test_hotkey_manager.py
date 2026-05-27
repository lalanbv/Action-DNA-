"""HotkeyManager 单元测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.input.hotkey_manager import HotkeyBinding, HotkeyManager


class TestNormalizeKey:
    def test_sorts_parts(self) -> None:
        assert HotkeyManager._normalize_key("shift+ctrl+f5") == "ctrl+f5+shift"

    def test_lowercases(self) -> None:
        assert HotkeyManager._normalize_key("Ctrl+Shift+F5") == "ctrl+f5+shift"

    def test_strips_whitespace(self) -> None:
        assert HotkeyManager._normalize_key(" ctrl + f5 ") == "ctrl+f5"

    def test_single_key(self) -> None:
        assert HotkeyManager._normalize_key("f9") == "f9"


class TestToTkinterKey:
    def test_ctrl_shift_combo(self) -> None:
        result = HotkeyManager._to_tkinter_key("ctrl+f5+shift")
        assert result == "<Control-Shift-F5>"

    def test_single_key(self) -> None:
        result = HotkeyManager._to_tkinter_key("f9")
        assert result == "<F9>"

    def test_cmd_key(self) -> None:
        result = HotkeyManager._to_tkinter_key("cmd+c")
        assert result == "<Command-C>"

    def test_alt_key(self) -> None:
        result = HotkeyManager._to_tkinter_key("alt+f4")
        assert result == "<Alt-F4>"


class TestRegister:
    def test_register_success(self) -> None:
        mgr = HotkeyManager(use_global=False)
        cb = MagicMock()
        result = mgr.register("test", "ctrl+z", cb, "测试")
        assert result is True
        binding = mgr.get_binding("test")
        assert binding is not None
        assert binding.callback is cb
        assert binding.description == "测试"

    def test_register_normalizes_key(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.register("test", "Shift+Ctrl+F5", MagicMock())
        binding = mgr.get_binding("test")
        assert binding is not None
        assert binding.key_combination == "ctrl+f5+shift"

    def test_register_conflict_returns_false(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.register("action_a", "ctrl+z", MagicMock())
        result = mgr.register("action_b", "ctrl+z", MagicMock())
        assert result is False

    def test_register_same_action_replaces(self) -> None:
        mgr = HotkeyManager(use_global=False)
        cb1 = MagicMock()
        cb2 = MagicMock()
        mgr.register("action", "ctrl+z", cb1)
        mgr.register("action", "ctrl+y", cb2)
        binding = mgr.get_binding("action")
        assert binding is not None
        assert binding.callback is cb2
        assert binding.key_combination == "ctrl+y"

    def test_unregister(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.register("test", "ctrl+z", MagicMock())
        mgr.unregister("test")
        assert mgr.get_binding("test") is None

    def test_unregister_nonexistent_no_error(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.unregister("nonexistent")  # should not raise


class TestSetEnabled:
    def test_toggle_enabled(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.register("test", "f9", MagicMock())
        mgr.set_enabled("test", False)
        binding = mgr.get_binding("test")
        assert binding is not None
        assert binding.enabled is False

        mgr.set_enabled("test", True)
        assert binding.enabled is True


class TestRegisterDefaults:
    def test_registers_four_defaults(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.register_defaults(
            on_start_stop=MagicMock(),
            on_pause=MagicMock(),
            on_step=MagicMock(),
            on_emergency_stop=MagicMock(),
        )
        bindings = mgr.get_all_bindings()
        assert len(bindings) == 4
        names = {b.action_name for b in bindings}
        assert names == {"start_stop", "pause", "step", "emergency_stop"}


class TestGetAllBindings:
    def test_returns_copy(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.register("a", "f1", MagicMock())
        bindings = mgr.get_all_bindings()
        bindings.clear()
        assert mgr.get_binding("a") is not None


class TestShutdown:
    def test_clears_all(self) -> None:
        mgr = HotkeyManager(use_global=False)
        mgr.register("a", "f1", MagicMock())
        mgr.register("b", "f2", MagicMock())
        mgr.shutdown()
        assert mgr.get_all_bindings() == []
        assert mgr.get_binding("a") is None


class TestBindToTkinter:
    def test_binds_to_root(self) -> None:
        mgr = HotkeyManager(use_global=False)
        cb = MagicMock()
        mgr.register("test", "f9", cb, use_global=False)
        root = MagicMock()
        mgr.bind_to_tkinter(root)
        assert root.bind.call_count == 1
        args = root.bind.call_args
        assert args[0][0] == "<F9>"
