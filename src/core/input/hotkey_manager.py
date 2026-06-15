"""HotkeyManager — 跨平台快捷键管理器。"""

from __future__ import annotations

import contextlib
import logging
import threading
from dataclasses import dataclass
from typing import Callable

from src.core.input.global_hotkey_backend import BackendType, GlobalHotkeyBackend, create_backend
from src.utils.i18n import t

logger = logging.getLogger(__name__)


@dataclass
class HotkeyBinding:
    """快捷键绑定。"""

    key_combination: str
    action_name: str
    callback: Callable[[], None]
    description: str = ""
    enabled: bool = True
    use_global: bool = True


class HotkeyManager:
    """跨平台快捷键管理器。

    策略：
    1. 全局模式：通过 pynput（优先）或 keyboard 库注册系统级热键
    2. 应用内模式：通过 tkinter bind() 或 Qt QShortcut 绑定

    线程安全：全局热键回调在后台线程触发，
    通过 ``root.after(0, callback)`` 调度到 tkinter 主线程执行，
    或通过 ``QMetaObject.invokeMethod()`` 调度到 Qt 主线程执行。
    """

    def __init__(self, use_global: bool = True) -> None:
        self._use_global = use_global
        self._bindings: dict[str, HotkeyBinding] = {}
        self._key_to_action: dict[str, str] = {}
        self._tk_root: object | None = None
        self._qt_shortcuts: dict[str, object] = {}
        self._main_thread_schedule: Callable[[int, Callable], None] | None = None
        self._backend: GlobalHotkeyBackend | None = None
        self._lock = threading.Lock()

        if self._use_global:
            self._backend = create_backend()

    @property
    def keyboard_available(self) -> bool:
        return self._backend is not None

    @property
    def backend_name(self) -> str:
        if self._backend is not None:
            return self._backend.backend_type.value
        return BackendType.NONE.value

    # ---- 注册 ----

    def register(
        self,
        action_name: str,
        key_combination: str,
        callback: Callable[[], None],
        description: str = "",
        use_global: bool = True,
    ) -> bool:
        """注册快捷键绑定，返回 True 表示成功。"""
        key_combo = self._normalize_key(key_combination)

        if key_combo in self._key_to_action:
            existing = self._key_to_action[key_combo]
            if existing != action_name:
                logger.warning(
                    "快捷键冲突: '%s' 已绑定到 '%s'",
                    key_combo,
                    existing,
                )
                return False

        if action_name in self._bindings:
            self.unregister(action_name)

        binding = HotkeyBinding(
            key_combination=key_combo,
            action_name=action_name,
            callback=callback,
            description=description,
            use_global=use_global,
        )

        with self._lock:
            self._bindings[action_name] = binding
            self._key_to_action[key_combo] = action_name

        self._activate_binding(binding)

        logger.debug(t("input.log.hotkey_registered", key_combo=key_combo, action=action_name, description=description))
        return True

    def unregister(self, action_name: str) -> None:
        """注销快捷键。"""
        with self._lock:
            binding = self._bindings.pop(action_name, None)
            if binding:
                self._key_to_action.pop(binding.key_combination, None)
        if binding:
            self._deactivate_binding(binding)

    def set_enabled(self, action_name: str, enabled: bool) -> None:
        """启用/禁用单条绑定。"""
        with self._lock:
            binding = self._bindings.get(action_name)
            if not binding:
                return

            was_enabled = binding.enabled
            binding.enabled = enabled

        if was_enabled and not enabled:
            self._deactivate_binding(binding)
        elif not was_enabled and enabled:
            self._activate_binding(binding)

    def set_use_global(self, action_name: str, use_global: bool) -> None:
        """动态切换全局/应用内模式。"""
        with self._lock:
            binding = self._bindings.get(action_name)
            if not binding:
                return

            was_global = binding.use_global
            binding.use_global = use_global

        if was_global != use_global and binding.enabled:
            self._deactivate_binding(binding)
            self._activate_binding(binding)

    # ---- 内置快捷键 ----

    def register_defaults(
        self,
        on_start_stop: Callable[[], None],
        on_pause: Callable[[], None],
        on_step: Callable[[], None],
        on_emergency_stop: Callable[[], None],
        config: object | None = None,
    ) -> None:
        """注册内置快捷键。可选传入 HotkeyConfig 自定义键位。"""

        if config is not None:
            items = [
                (
                    "start_stop", on_start_stop, "hotkey.start_stop",
                    config.start_stop.key_combination,
                    config.start_stop.enabled,
                    config.start_stop.use_global,
                ),
                (
                    "pause", on_pause, "hotkey.pause",
                    config.pause.key_combination,
                    config.pause.enabled,
                    config.pause.use_global,
                ),
                (
                    "step", on_step, "hotkey.step",
                    config.step.key_combination,
                    config.step.enabled,
                    config.step.use_global,
                ),
                (
                    "emergency_stop", on_emergency_stop, "hotkey.emergency_stop",
                    config.emergency_stop.key_combination,
                    config.emergency_stop.enabled,
                    config.emergency_stop.use_global,
                ),
            ]
        else:
            items = [
                ("start_stop", on_start_stop, "hotkey.start_stop", "ctrl+shift+f5", True, True),
                ("pause", on_pause, "hotkey.pause", "ctrl+shift+f6", True, True),
                ("step", on_step, "hotkey.step", "ctrl+shift+f7", True, True),
                ("emergency_stop", on_emergency_stop, "hotkey.emergency_stop", "ctrl+shift+f12", True, True),
            ]

        if self._backend is not None and hasattr(self._backend, "begin_batch"):
            self._backend.begin_batch()
        try:
            for action_name, callback, desc_key, key_combo, enabled, use_global in items:
                self.register(action_name, key_combo, callback, t(desc_key), use_global=use_global)
                if not enabled:
                    self.set_enabled(action_name, False)
        finally:
            if self._backend is not None and hasattr(self._backend, "end_batch"):
                self._backend.end_batch()

    def reregister(self, action_name: str, new_key: str) -> bool:
        """重新绑定已有动作到新快捷键。"""
        binding = self._bindings.get(action_name)
        if not binding:
            return False
        callback = binding.callback
        description = binding.description
        use_global = binding.use_global
        self.unregister(action_name)
        return self.register(action_name, new_key, callback, description, use_global=use_global)

    # ---- tkinter 集成 ----

    def bind_to_tkinter(self, root: object) -> None:
        """绑定到 tkinter 窗口（全局快捷键不可用或 use_global=False 时的方案）。"""
        self._tk_root = root
        for binding in self._bindings.values():
            if binding.enabled and not binding.use_global:
                self._register_tkinter(binding)

    # ---- Qt 集成 ----

    def bind_to_qt(self, schedule_fn: Callable[[int, Callable], None]) -> None:
        """绑定到 Qt 应用（全局快捷键不可用或 use_global=False 时的方案）。

        Args:
            schedule_fn: 主线程调度函数，签名为 schedule_fn(ms, callback)。
        """
        self._main_thread_schedule = schedule_fn
        for binding in self._bindings.values():
            if binding.enabled and not binding.use_global:
                self._register_qt(binding)

    # ---- 查询 ----

    def get_all_bindings(self) -> list[HotkeyBinding]:
        """获取所有绑定。"""
        return list(self._bindings.values())

    def get_binding(self, action_name: str) -> HotkeyBinding | None:
        """获取指定动作的绑定。"""
        return self._bindings.get(action_name)

    # ---- 内部方法 ----

    @staticmethod
    def _normalize_key(key_combo: str) -> str:
        """标准化快捷键表示（排序 + 小写）。"""
        parts = [p.strip().lower() for p in key_combo.split("+")]
        return "+".join(sorted(parts))

    def _make_threadsafe_callback(self, callback: Callable[[], None]) -> Callable[[], None]:
        """包装回调，确保在 GUI 主线程执行。"""
        def wrapper() -> None:
            if (
                self._tk_root is not None
                and hasattr(self._tk_root, "winfo_exists")
                and self._tk_root.winfo_exists()
            ):
                self._tk_root.after(0, callback)
            elif self._main_thread_schedule is not None:
                self._main_thread_schedule(0, callback)
            else:
                callback()

        return wrapper

    def _activate_binding(self, binding: HotkeyBinding) -> None:
        """激活绑定：根据 use_global 选择注册方式。"""
        if not binding.enabled:
            return

        if binding.use_global and self._backend is not None:
            self._register_global(binding)
        elif self._qt_shortcuts is not None and self._main_thread_schedule is not None:
            self._register_qt(binding)
        else:
            self._register_tkinter(binding)

    def _deactivate_binding(self, binding: HotkeyBinding) -> None:
        """停用绑定：从当前激活的后端注销。"""
        if binding.use_global and self._backend is not None:
            self._unregister_global(binding)
        elif self._qt_shortcuts is not None and self._main_thread_schedule is not None:
            self._unregister_qt(binding)
        else:
            self._unregister_tkinter(binding)

    def _register_global(self, binding: HotkeyBinding) -> None:
        """使用全局后端注册热键。"""
        if not binding.enabled or self._backend is None:
            return
        try:
            safe_cb = self._make_threadsafe_callback(binding.callback)
            self._backend.register(binding.key_combination, safe_cb)
        except Exception as e:
            logger.error(t("input.log.global_hotkey_register_failed", key_combo=binding.key_combination, error=e))

    def _unregister_global(self, binding: HotkeyBinding) -> None:
        """注销全局热键。"""
        if self._backend is None:
            return
        with contextlib.suppress(Exception):
            self._backend.unregister(binding.key_combination)

    def _register_tkinter(self, binding: HotkeyBinding) -> None:
        """使用 tkinter 绑定快捷键。"""
        if self._tk_root is None or not binding.enabled:
            return
        tk_key = self._to_tkinter_key(binding.key_combination)
        try:
            self._tk_root.bind(tk_key, lambda e: binding.callback())
        except Exception as e:
            logger.error(t("input.log.tkinter_bind_failed", tk_key=tk_key, error=e))

    def _unregister_tkinter(self, binding: HotkeyBinding) -> None:
        """注销 tkinter 快捷键。"""
        if self._tk_root is None:
            return
        tk_key = self._to_tkinter_key(binding.key_combination)
        with contextlib.suppress(Exception):
            self._tk_root.unbind(tk_key)

    def _register_qt(self, binding: HotkeyBinding) -> None:
        """使用 QShortcut 绑定快捷键。"""
        if not binding.enabled:
            return
        try:
            from PySide6.QtGui import QKeySequence, QShortcut
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if not isinstance(app, QApplication):
                return

            qt_key = self._to_qt_key_sequence(binding.key_combination)
            parent = app.activeWindow()
            if parent is None and app.topLevelWidgets():
                parent = app.topLevelWidgets()[0]
            if parent is None:
                return
            shortcut = QShortcut(QKeySequence(qt_key), parent)
            shortcut.activated.connect(binding.callback)
            self._qt_shortcuts[binding.key_combination] = shortcut
        except ImportError:
            logger.debug(t("input.log.pyside6_unavailable"))
        except Exception as e:
            logger.error(t("input.log.qt_bind_failed", key_combo=binding.key_combination, error=e))

    def _unregister_qt(self, binding: HotkeyBinding) -> None:
        """注销 Qt 快捷键。"""
        shortcut = self._qt_shortcuts.pop(binding.key_combination, None)
        if shortcut is not None:
            try:
                shortcut.setEnabled(False)
                shortcut.deleteLater()
            except Exception:
                pass

    @staticmethod
    def _to_qt_key_sequence(key_combo: str) -> str:
        """转换为 QKeySequence 格式。"""
        modifier_map = {
            "ctrl": "Ctrl",
            "shift": "Shift",
            "alt": "Alt",
            "cmd": "Meta",
            "alt_gr": "AltGr",
        }
        special_map = {
            "enter": "Return",
            "return": "Return",
            "tab": "Tab",
            "space": "Space",
            "backspace": "Backspace",
            "escape": "Escape",
            "esc": "Escape",
            "home": "Home",
            "end": "End",
            "pageup": "PgUp",
            "pagedown": "PgDown",
            "insert": "Insert",
            "delete": "Delete",
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
            "capslock": "CapsLock",
        }
        parts = key_combo.split("+")
        result: list[str] = []
        for p in parts:
            p = p.strip()
            if p in modifier_map:
                result.append(modifier_map[p])
            elif p in special_map:
                result.append(special_map[p])
            elif p.startswith("f") and p[1:].isdigit():
                result.append(p.upper())
            else:
                result.append(p.capitalize())
        return "+".join(result)

    @staticmethod
    def _to_tkinter_key(key_combo: str) -> str:
        """转换为 tkinter 快捷键格式。"""
        modifier_map = {
            "ctrl": "Control",
            "shift": "Shift",
            "alt": "Alt",
            "cmd": "Command",
        }
        parts = key_combo.split("+")
        modifiers: list[str] = []
        keys: list[str] = []
        for p in parts:
            if p in modifier_map:
                modifiers.append(modifier_map[p])
            else:
                keys.append(p.capitalize())
        return "<" + "-".join(modifiers + keys) + ">"

    # ---- 生命周期 ----

    def shutdown(self) -> None:
        """关闭，清理所有注册。"""
        with self._lock:
            if self._backend is not None:
                with contextlib.suppress(Exception):
                    self._backend.stop()
            for shortcut in self._qt_shortcuts.values():
                with contextlib.suppress(Exception):
                    shortcut.setEnabled(False)
                    shortcut.deleteLater()
            self._qt_shortcuts.clear()
            self._bindings.clear()
            self._key_to_action.clear()
