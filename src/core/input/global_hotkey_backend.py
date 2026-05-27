"""跨平台全局热键后端 — 封装 pynput 和 keyboard 两种实现。"""

from __future__ import annotations

import contextlib
import enum
import logging
import threading
from typing import Callable, Protocol

from src.utils.platform import IS_MACOS

logger = logging.getLogger(__name__)


def _patch_pynput_darwin() -> None:
    """修补 pynput 的 keycode_context，防止后台线程调用 HIToolbox 导致崩溃。

    macOS 上 TISCopyCurrentKeyboardInputSource / TSMGetInputSourceProperty
    必须在主线程调用。pynput 的 Listener._run() 在后台线程调用
    keycode_context()，在 tkinter mainloop 运行时会触发 SIGTRAP。
    修补后：主线程使用原始实现，后台线程返回虚拟上下文（GlobalHotKeys
    仅按虚拟键码匹配，不需要字符串转换）。

    同时从主线程预解析 HIServices.AXIsProcessTrusted，避免 pyobjc
    lazy import 在后台线程中的 funcmap 竞争导致 KeyError。
    """
    if not IS_MACOS:
        return
    try:
        from pynput._util import darwin as _du
        import pynput.keyboard._darwin as _kd
    except ImportError:
        return

    if not hasattr(_du, "keycode_context") or not hasattr(_kd, "keycode_context"):
        logger.warning("pynput monkey-patch target missing — HIToolbox crash may occur")
        return

    _original = _du.keycode_context

    # GlobalHotKeys only matches by virtual keycode — the unicode context
    # (char_count, unicode_bytes) is never used, so a dummy tuple is safe.
    _DUMMY_KEYCODE_CTX = (0, b"")

    @contextlib.contextmanager
    def _safe_keycode_context():
        if threading.current_thread() is threading.main_thread():
            with _original() as ctx:
                yield ctx
        else:
            yield _DUMMY_KEYCODE_CTX

    _du.keycode_context = _safe_keycode_context
    _kd.keycode_context = _safe_keycode_context

    # 修补 pynput darwin _handler 中 media/special key 分支
    # 缺少 injected 参数的 bug（pynput 1.8.1 on macOS + Python 3.14）
    try:
        import pynput.keyboard._darwin as _kd

        _orig_handler = _kd.Listener._handle_message

        def _patched_handle_message(self, _proxy, event_type, event, _refcon, injected):
            orig_on_press = self.on_press
            orig_on_release = self.on_release

            def _safe_on_press(key, _injected=None):
                orig_on_press(key, _injected if _injected is not None else False)

            def _safe_on_release(key, _injected=None):
                orig_on_release(key, _injected if _injected is not None else False)

            self.on_press = _safe_on_press
            self.on_release = _safe_on_release
            try:
                return _orig_handler(self, _proxy, event_type, event, _refcon, injected)
            finally:
                self.on_press = orig_on_press
                self.on_release = orig_on_release

        _kd.Listener._handle_message = _patched_handle_message
    except (ImportError, AttributeError):
        pass

    # 预解析 pyobjc lazy import，防止后台线程 funcmap 竞争
    try:
        import HIServices
        HIServices.AXIsProcessTrusted()
    except (ImportError, OSError):
        pass


# 在模块加载时（主线程）执行修补
_patch_pynput_darwin()


class BackendType(enum.Enum):
    """全局热键后端类型。"""
    PYNPUT = "pynput"
    KEYBOARD = "keyboard"
    NONE = "none"


class GlobalHotkeyBackend(Protocol):
    """全局热键后端接口。"""

    @property
    def backend_type(self) -> BackendType: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def register(self, key_combo: str, callback: Callable[[], None]) -> bool: ...
    def unregister(self, key_combo: str) -> None: ...
    def is_available(self) -> bool: ...


# ---- 内部格式 ↔ pynput 格式转换 ----

_MODIFIER_NAMES = frozenset({"ctrl", "shift", "alt", "cmd", "alt_gr", "alt_gr_l"})

_SPECIAL_KEY_MAP: dict[str, str] = {
    "enter": "<enter>",
    "tab": "<tab>",
    "space": "<space>",
    "backspace": "<backspace>",
    "escape": "<escape>",
    "home": "<home>",
    "end": "<end>",
    "pageup": "<page_up>",
    "pagedown": "<page_down>",
    "insert": "<insert>",
    "delete": "<delete>",
    "up": "<up>",
    "down": "<down>",
    "left": "<left>",
    "right": "<right>",
    "capslock": "<caps_lock>",
}


def _to_pynput_key(name: str) -> str:
    """将单个键名转换为 pynput 格式。

    内部: ctrl, shift, f5, a, enter
    pynput: <ctrl>, <shift>, <f5>, a, <enter>
    """
    if name in _MODIFIER_NAMES:
        return f"<{name}>"
    if name.startswith("f") and name[1:].isdigit():
        return f"<{name}>"
    return _SPECIAL_KEY_MAP.get(name, name)


def _to_pynput_combo(key_combo: str) -> str:
    """将内部格式快捷键组合转换为 pynput 格式。

    内部: "ctrl+shift+f5" → pynput: "<ctrl>+<shift>+<f5>"
    """
    parts = key_combo.split("+")
    return "+".join(_to_pynput_key(p.strip()) for p in parts)


# ---- Pynput 后端 ----


class PynputBackend:
    """基于 pynput.keyboard.GlobalHotKeys 的全局热键后端。"""

    @property
    def backend_type(self) -> BackendType:
        return BackendType.PYNPUT

    def __init__(self) -> None:
        self._available: bool = False
        self._listener: object | None = None
        self._bindings: dict[str, Callable[[], None]] = {}
        self._lock = threading.Lock()
        self._batching: bool = False

        try:
            from pynput.keyboard import GlobalHotKeys  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def start(self) -> None:
        self._restart_listener()

    def stop(self) -> None:
        with self._lock:
            if self._listener is not None:
                with contextlib.suppress(Exception):
                    self._listener.stop()
                self._listener = None
            self._bindings.clear()
            self._batching = False

    def register(self, key_combo: str, callback: Callable[[], None]) -> bool:
        pynput_combo = _to_pynput_combo(key_combo)
        with self._lock:
            self._bindings[pynput_combo] = callback
        if not self._batching:
            self._restart_listener()
        return True

    def begin_batch(self) -> None:
        """Defer listener restarts until end_batch()."""
        self._batching = True

    def end_batch(self) -> None:
        """Apply all pending registrations in a single listener restart."""
        self._batching = False
        self._restart_listener()

    def unregister(self, key_combo: str) -> None:
        pynput_combo = _to_pynput_combo(key_combo)
        with self._lock:
            self._bindings.pop(pynput_combo, None)
        self._restart_listener()

    def _restart_listener(self) -> None:
        """停止旧 listener 并用当前绑定创建新 listener。"""
        from pynput.keyboard import GlobalHotKeys

        with self._lock:
            if self._listener is not None:
                with contextlib.suppress(Exception):
                    self._listener.stop()
                self._listener = None

            if not self._bindings:
                return

            try:
                self._listener = GlobalHotKeys(dict(self._bindings))
                self._listener.start()
                logger.debug("pynput GlobalHotKeys 已重启，绑定数: %d", len(self._bindings))
            except Exception as e:
                logger.error("pynput GlobalHotKeys 启动失败: %s", e)
                self._listener = None


# ---- Keyboard 后端（回退） ----


class KeyboardBackend:
    """基于 keyboard 库的全局热键后端（回退方案）。"""

    @property
    def backend_type(self) -> BackendType:
        return BackendType.KEYBOARD

    def __init__(self) -> None:
        self._available: bool = False

        try:
            import keyboard  # noqa: F401

            self._available = True
        except ImportError:
            self._available = False

    def is_available(self) -> bool:
        return self._available

    def start(self) -> None:
        pass  # keyboard 库无需显式启动

    def stop(self) -> None:
        try:
            import keyboard

            keyboard.unhook_all()
        except Exception:
            pass

    def register(self, key_combo: str, callback: Callable[[], None]) -> bool:
        try:
            import keyboard

            keyboard.add_hotkey(key_combo, callback, suppress=True)
            return True
        except Exception as e:
            logger.error("keyboard 注册热键失败 '%s': %s", key_combo, e)
            return False

    def unregister(self, key_combo: str) -> None:
        try:
            import keyboard

            keyboard.remove_hotkey(key_combo)
        except Exception:
            pass


# ---- 工厂函数 ----


def create_backend() -> GlobalHotkeyBackend | None:
    """按优先级选择可用的全局热键后端：pynput → keyboard → None。"""
    backend = PynputBackend()
    if backend.is_available():
        logger.info("全局热键后端: pynput")
        return backend

    backend = KeyboardBackend()
    if backend.is_available():
        logger.info("全局热键后端: keyboard")
        return backend

    logger.info("全局热键不可用，回退到 tkinter 绑定")
    return None
