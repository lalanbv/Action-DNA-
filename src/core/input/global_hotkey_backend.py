"""跨平台全局热键后端 — 封装 pynput 和 keyboard 两种实现。"""

from __future__ import annotations

import contextlib
import enum
import logging
import threading
from typing import Callable, Protocol

from src.utils.i18n import t
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
        # listener 启动异步化状态:
        # - _restart_gen: 重启世代号,并发重启时仅最新一次提交生效
        # - _stopped:     终态标志,stop() 后拒绝再启动(backend 进入废弃态)
        # - _exec_lock:   串行化 _do_restart_listener 全流程,消除并发双 listener 窗口
        self._restart_gen: int = 0
        self._stopped: bool = False
        self._exec_lock = threading.Lock()

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
            # 标记终态:在途的后台 _do_restart_listener 提交阶段会据此丢弃新 listener,
            # 避免 stop 之后被一次迟到的 start()「复活」。
            self._stopped = True
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
        """请求重启 listener —— 后台异步执行,调用线程立即返回。

        pynput 的 ``GlobalHotKeys.start()`` 在 Windows 主线程会同步等待 listener
        线程安装 ``WH_KEYBOARD_LL`` 全局键盘钩子;打包 exe / 特定桌面会话 /
        安全软件介入下 ``SetWindowsHookEx`` 挂起,会冻结调用线程 → Qt 事件循环
        卡死(窗口出现但无响应、无日志 —— 阻塞非异常,excepthook/try-except 全失效)。
        故 listener 启动整体移到后台 daemon 线程。多次重启请求用世代号去重,
        仅最新一次提交生效,调用线程绝不等待 ``start()`` 返回。
        """
        with self._lock:
            self._restart_gen += 1
            my_gen = self._restart_gen
        threading.Thread(
            target=self._do_restart_listener,
            args=(my_gen,),
            name="pynput-restart",
            daemon=True,
        ).start()

    def _do_restart_listener(self, my_gen: int) -> None:
        """后台线程:停止旧 listener 并启动新 listener(实际工作)。

        ``_exec_lock`` 把整个 restart 流程串行化 —— 同时只有一个线程在
        stop-old / start / commit,从根上消除「并发 restart 致两个 listener 短暂
        共存、热键被双触发」的窗口。``_exec_lock`` 只在后台线程获取,主线程的
        ``_restart_listener`` / ``register`` / ``stop`` 都不碰它,故不引入主线程
        阻塞;即便某次 ``start()`` 挂起,也只会让后续 restart 请求在后台排队,
        不影响 UI 事件循环。

        ``start()`` 仍放在 ``self._lock`` 之外(避免持 state 锁阻塞 start),
        ``self._lock`` 只保护瞬间的状态读写。锁序:_exec_lock 外、self._lock 内,
        其余路径仅获取 self._lock,无反向嵌套 → 无死锁。
        """
        from pynput.keyboard import GlobalHotKeys

        with self._exec_lock:
            # 1. 锁内:停止旧 listener、快照绑定、判断是否仍需启动
            with self._lock:
                if self._listener is not None:
                    with contextlib.suppress(Exception):
                        self._listener.stop()
                    self._listener = None
                if self._stopped or my_gen != self._restart_gen:
                    return
                bindings_snapshot = dict(self._bindings)
                if not bindings_snapshot:
                    return

            # 2. 锁外(但 _exec_lock 内):创建并 start —— 可能阻塞(hang),但不持
            #    self._lock,故不阻塞 register/stop;_exec_lock 保证此段串行。
            #    诊断心跳:start 前后各打一行。若历史卡死复发,日志最后一行会停在
            #    「即将 start」之后,直接定位到 pynput 钩子安装环节。
            logger.info(
                "[boot] 即将启动 pynput listener(bindings=%d,线程=%s)",
                len(bindings_snapshot), threading.current_thread().name,
            )
            try:
                listener = GlobalHotKeys(bindings_snapshot)
                listener.start()
            except Exception as e:  # noqa: BLE001 — pynput 启动失败降级,不拖垮调用方
                logger.error(t("input.log.pynput_start_failed", error=e))
                return
            logger.info("[boot] pynput listener 启动完成")

            # 3. 锁内:提交新 listener;期间若有更新的 restart 或 stop 取代则丢弃
            with self._lock:
                if self._stopped or self._restart_gen != my_gen:
                    with contextlib.suppress(Exception):
                        listener.stop()
                    return
                self._listener = listener
                logger.debug(t("input.log.pynput_restarted", binding_count=len(self._bindings)))


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
            logger.error(t("input.log.keyboard_register_failed", key_combo=key_combo, error=e))
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
        logger.info(t("input.log.backend_pynput"))
        return backend

    backend = KeyboardBackend()
    if backend.is_available():
        logger.info(t("input.log.backend_keyboard"))
        return backend

    logger.info(t("input.log.backend_unavailable_fallback_tkinter"))
    return None
