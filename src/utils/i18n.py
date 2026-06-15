"""i18n — 多语言支持模块

使用方式::

    from src.utils.i18n import t
    label = t("workflow.title")  # → "工作流编辑器" (中文) / "Workflow Editor" (英文)
    msg = t("workflow.msg.profile_loaded", name="test")  # 支持格式化参数

语言切换通知::

    from src.utils.i18n import on_language_change
    def on_lang_changed(lang: str) -> None:
        label.config(text=t("some.key"))
    on_language_change(on_lang_changed)
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
from typing import Callable

from src.utils.platform import IS_FROZEN

_logger = logging.getLogger(__name__)

# ── 模块内部状态（线程安全） ──────────────────────────────────

_lock = threading.Lock()

_current_lang: str = ""
_translations: dict[str, str] = {}
_fallback_translations: dict[str, str] = {}
_initialized: bool = False
_cache: dict[str, dict[str, str]] = {}
_pending_validations: list[tuple[str, str]] = []
_observers: list[Callable[[str], None]] = []
_observer_lock = threading.Lock()


# ── 公共 API ──────────────────────────────────────────────────


def init(language: str = "zh") -> None:
    """初始化语言系统。"""
    global _current_lang, _initialized
    with _lock:
        _current_lang = language
        _load_unlocked(language)
        _initialized = True
        _flush_pending_validations_unlocked()


def set_language(language: str) -> None:
    """切换语言并通知所有观察者。"""
    global _current_lang, _initialized
    with _lock:
        if language == _current_lang and _initialized:
            return
        _current_lang = language
        _load_unlocked(language)
        _initialized = True
        _flush_pending_validations_unlocked()
    _notify_observers(language)


def get_language() -> str:
    """获取当前语言代码。"""
    if not _initialized:
        init("zh")
    return _current_lang


def t(key: str, **kwargs: object) -> str:
    """获取翻译文本，支持 format 参数。

    查找顺序: 当前语言 → zh 回退 → 返回 key 本身。
    """
    if not _initialized:
        init("zh")

    with _lock:
        translations = _translations
        fallback = _fallback_translations

    text = translations.get(key)
    if text is None:
        text = fallback.get(key, key)
    try:
        text = text.format(**kwargs)
    except (KeyError, IndexError, ValueError) as exc:
        # 安全降级：不崩、不静默。记录 warning + 返回带占位符的原文本（开发者可见）
        _logger.warning("i18n format failed for key %r: %s", key, exc)
    return text


def has_key(key: str) -> bool:
    """检查翻译 key 是否存在。"""
    if not _initialized:
        init("zh")
    with _lock:
        return key in _translations or key in _fallback_translations


def all_keys() -> set[str]:
    """返回当前语言 + 回退语言的所有 key 并集。"""
    if not _initialized:
        init("zh")
    with _lock:
        return set(_translations) | set(_fallback_translations)


def get_available_languages() -> list[str]:
    """返回 translations/ 目录下所有可用语言代码(如 ['en', 'zh']),排序去重。

    供设置页动态渲染语言下拉框。
    """
    if IS_FROZEN:
        base = os.path.join(getattr(sys, "_MEIPASS", ""), "src", "utils", "translations")
    else:
        base = os.path.join(os.path.dirname(__file__), "translations")
    langs: set[str] = set()
    try:
        for entry in os.listdir(base):
            if entry.endswith(".json"):
                langs.add(entry[:-5])
    except OSError:
        pass
    return sorted(langs)


def detect_system_locale() -> str:
    """检测系统首选语言,映射到支持的 i18n 语言码。

    映射规则:``zh* → zh, en* → en, 其他 → zh(默认)``。检测失败返回 ``'zh'``。
    供 init() 首次启动且 settings 未指定语言时使用。
    """
    try:
        import locale
        loc = locale.getlocale()[0]
        if not loc:
            # getdefaultlocale 在 3.11 起弃用(3.15 移除),作为 getlocale 返回空时的 fallback
            loc = locale.getdefaultlocale()[0]  # noqa: DEPRECATED
        if loc:
            low = loc.lower()
            if low.startswith("zh"):
                return "zh"
            if low.startswith("en"):
                return "en"
    except Exception:
        pass
    return "zh"


def refresh() -> None:
    """清除缓存并重新加载当前语言（用于热重载翻译文件）。"""
    with _lock:
        _cache.clear()
        _load_unlocked(_current_lang)


def on_language_change(callback: Callable[[str], None]) -> None:
    """注册语言切换回调。callback 接收新语言代码。"""
    with _observer_lock:
        _observers.append(callback)


def remove_language_observer(callback: Callable[[str], None]) -> None:
    """移除已注册的语言切换回调。"""
    with _observer_lock:
        try:
            _observers.remove(callback)
        except ValueError:
            pass


def schedule_validation(key: str, context: str) -> None:
    """延迟校验 i18n key — 未初始化时暂存，初始化后立即校验。"""
    with _lock:
        if _initialized:
            _check_key(key, context)
        else:
            _pending_validations.append((key, context))


# ── 内部实现 ──────────────────────────────────────────────────


def _read_json(lang: str) -> dict[str, str]:
    """从 JSON 文件读取翻译（带内存缓存）。"""
    cached = _cache.get(lang)
    if cached is not None:
        return cached

    if IS_FROZEN:
        base = os.path.join(getattr(sys, "_MEIPASS", ""), "src", "utils")
    else:
        base = os.path.dirname(__file__)
    path = os.path.join(base, "translations", f"{lang}.json")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data: dict[str, str] = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        _logger.warning("Failed to load translations from %s: %s", path, exc)
        return {}

    _cache[lang] = data
    return data


def _load_unlocked(lang: str) -> None:
    """从 JSON 文件加载翻译（调用方持有 _lock）。"""
    global _translations, _fallback_translations
    _translations = _read_json(lang)
    if lang == "zh":
        _fallback_translations = _translations
    elif not _fallback_translations:
        _fallback_translations = _read_json("zh")


def _flush_pending_validations_unlocked() -> None:
    """处理所有延迟校验（调用方持有 _lock）。"""
    global _pending_validations
    for key, context in _pending_validations:
        _check_key(key, context)
    _pending_validations = []


def _check_key(key: str, context: str) -> None:
    """校验 key 是否存在。调用方需持有 _lock（或不在锁内时使用 has_key）。"""
    if key and key not in _translations and key not in _fallback_translations:
        _logger.warning("i18n key %r not found (used by %s)", key, context)


def _notify_observers(lang: str) -> None:
    """通知所有观察者语言已切换。"""
    with _observer_lock:
        callbacks = list(_observers)
    for cb in callbacks:
        try:
            cb(lang)
        except Exception:
            _logger.exception("Language change observer error")
