"""主题管理器 — 模式切换/缓存/回调 + 注册式更新"""

from __future__ import annotations

import logging
from typing import Callable, Protocol

from src.panel.canvas.theme.tokens import CanvasTheme
from src.panel.canvas.theme.font_detection import detect_font_family, detect_mono_font
from src.panel.canvas.theme.dark_theme import build_dark_theme
from src.panel.canvas.theme.light_theme import build_light_theme
from src.panel.canvas.theme.platform_theme import detect_system_theme

logger = logging.getLogger(__name__)

_VALID_THEME_MODES = ("dark", "light", "system")


# ── 可主题化协议 ──


class Themeable(Protocol):
    """可主题化控件的协议 — 实现 apply_theme 以接收主题更新"""
    def apply_theme(self, theme: CanvasTheme) -> None: ...


# ── 注册式主题更新（取代递归遍历） ──


class ThemeRegistry:
    """主题注册表 — Themeable 控件的适配层，委托给 on_theme_change 全局回调系统。"""

    def register(self, widget: Themeable) -> int:
        """注册可主题化控件，返回回调 ID（与 on_theme_change 共享 ID 空间）。"""
        def _notify() -> None:
            try:
                # 检查 widget 是否仍然存活（tkinter 用 winfo_exists，Qt 用 isVisible）
                if hasattr(widget, 'winfo_exists') and not widget.winfo_exists():
                    return
                if hasattr(widget, 'isVisible') and not widget.isVisible():
                    return
                widget.apply_theme(current_theme())
            except Exception:
                pass

        return on_theme_change(_notify)

    def unregister(self, theme_id: int) -> None:
        """注销控件（委托给 remove_theme_change）。"""
        remove_theme_change(theme_id)


# ── 安全回调 Mixin（消除 _destroyed + safe-wrapper + unregister 重复代码） ──


class ThemeCallbackMixin:
    """主题回调安全守卫 Mixin。

    子类在 __init__ 中调用 _init_theme_guard(callback, exc_type)，
    在 destroy 中调用 _unregister_theme_callback()。

    _destroyed 防止快照竞争：set_theme_mode 遍历回调快照时，
    已注销的回调可能仍在快照中，_destroyed 确保其成为空操作。
    """

    _destroyed: bool
    _theme_cb_id: int | None

    def _init_theme_guard(
        self, target: Callable[[], None], exc_type: type = RuntimeError,
    ) -> None:
        self._destroyed = False
        safe = self._make_safe(target, exc_type)
        self._theme_cb_id: int | None = on_theme_change(safe)

    def _make_safe(self, fn: Callable[[], None], exc_type: type) -> Callable[[], None]:
        def safe() -> None:
            if self._destroyed:
                return
            try:
                fn()
            except exc_type:
                self._destroyed = True
        return safe

    def _unregister_theme_callback(self) -> None:
        if self._theme_cb_id is not None:
            remove_theme_change(self._theme_cb_id)
            self._theme_cb_id = None
        self._destroyed = True


# ── 全局单例 ──

_registry = ThemeRegistry()

_current_theme: CanvasTheme | None = None
_theme_mode: str = "system"
_theme_callbacks: dict[int, Callable[[], None]] = {}
_next_cb_id: int = 0


def theme_registry() -> ThemeRegistry:
    """获取全局主题注册表"""
    return _registry


# ── 公开 API（向后兼容） ──


def on_theme_change(callback: Callable[[], None]) -> int:
    """注册主题切换回调，返回回调 ID"""
    global _next_cb_id
    cb_id = _next_cb_id
    _next_cb_id += 1
    _theme_callbacks[cb_id] = callback
    return cb_id


def remove_theme_change(callback_or_id: Callable[[], None] | int) -> None:
    """取消注册主题切换回调（接受回调函数或 ID）"""
    if isinstance(callback_or_id, int):
        _theme_callbacks.pop(callback_or_id, None)
        return
    dead_ids = [cid for cid, cb in _theme_callbacks.items() if cb is callback_or_id]
    for cid in dead_ids:
        _theme_callbacks.pop(cid, None)


def current_theme() -> CanvasTheme:
    """获取当前主题（懒加载，缓存）"""
    global _current_theme
    if _current_theme is None:
        _current_theme = _build_theme()
    return _current_theme


def current_theme_mode() -> str:
    """获取当前主题模式（原始存储值）: 'dark' | 'light' | 'system'"""
    return _theme_mode


def resolved_theme_mode() -> str:
    """获取实际解析后的主题: 'dark' | 'light'。system 模式会解析为系统实际值"""
    if _theme_mode == "system":
        return detect_system_theme()
    return _theme_mode


def set_theme_mode(mode: str) -> None:
    """切换主题模式: 'dark' | 'light' | 'system'"""
    global _theme_mode, _current_theme
    if mode not in _VALID_THEME_MODES:
        logger.warning("Invalid theme mode %r, falling back to 'system'", mode)
        mode = "system"

    # Skip rebuild when mode and cached theme are unchanged (avoids subprocess + widget cascade).
    if mode == _theme_mode and _current_theme is not None:
        return

    _theme_mode = mode
    _current_theme = None

    # Rebuild theme cache, then notify all subscribers through a single callback loop.
    current_theme()

    dead_ids: list[int] = []
    # Snapshot items — callbacks may call remove_theme_change() during iteration.
    for cb_id, cb in list(_theme_callbacks.items()):
        try:
            cb()
        except Exception:
            dead_ids.append(cb_id)
    for cb_id in dead_ids:
        _theme_callbacks.pop(cb_id, None)


def refresh_theme() -> None:
    """强制重建当前主题并通知所有订阅。

    用于 system 模式下 OS 实际主题发生变化：不改变 ``_theme_mode``，
    仅清除缓存、重建主题、触发全部回调，从而绕过 :func:`set_theme_mode`
    在"模式未变"时的 skip 逻辑（B5 修复）。

    必须在 UI 主线程调用（由 :class:`theme_sync.SystemThemeSync` 通过
    ``ThemeSyncBackend.marshal_main`` 保证）。
    """
    global _current_theme
    _current_theme = None
    current_theme()  # 重建缓存

    dead_ids: list[int] = []
    # 快照遍历 —— 回调可能在迭代中调用 remove_theme_change。
    for cb_id, cb in list(_theme_callbacks.items()):
        try:
            cb()
        except Exception:
            dead_ids.append(cb_id)
    for cb_id in dead_ids:
        _theme_callbacks.pop(cb_id, None)


def restore_from_config(cfg) -> None:
    """从持久化配置恢复主题模式（D2 去重，供两后端共用）。

    读取 ``cfg.editor.theme_mode``，合法值（dark/light/system）恢复，
    非法或缺省回退到 ``system``。

    Args:
        cfg: 配置对象，需有 ``editor.theme_mode`` 属性。
    """
    mode = getattr(getattr(cfg, "editor", None), "theme_mode", None)
    if mode in _VALID_THEME_MODES:
        set_theme_mode(mode)
    else:
        set_theme_mode("system")


def _build_theme() -> CanvasTheme:
    """根据模式构建主题"""
    family = detect_font_family()
    mono = detect_mono_font()
    effective = _theme_mode
    if effective == "system":
        effective = detect_system_theme()
    # Deferred: scale_manager → scale.py → theme.py circular import
    from src.panel.canvas.scale import scale_manager
    sf = scale_manager().s_font
    if effective == "light":
        return build_light_theme(family, mono, sf)
    return build_dark_theme(family, mono, sf)
