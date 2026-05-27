"""i18n — 多语言支持模块

使用方式:
    from src.utils.i18n import t
    label = t("workflow.title")  # → "工作流编辑器" (中文) / "Workflow Editor" (英文)
    msg = t("workflow.msg.profile_loaded", name="test")  # 支持格式化参数
"""

import json
import logging
import os
import sys

from src.utils.platform import IS_FROZEN

_current_lang: str = ""
_translations: dict[str, str] = {}
_fallback_translations: dict[str, str] = {}
_initialized: bool = False
_cache: dict[str, dict[str, str]] = {}
_pending_validations: list[tuple[str, str]] = []

_logger = logging.getLogger(__name__)


def init(language: str = "zh") -> None:
    """初始化语言系统"""
    global _current_lang, _initialized
    _current_lang = language
    _load(language)
    _initialized = True
    _flush_pending_validations()


def set_language(language: str) -> None:
    """切换语言（需要重建 UI 才能生效）"""
    global _current_lang, _initialized
    if language == _current_lang and _initialized:
        return
    _current_lang = language
    _load(language)
    _initialized = True
    _flush_pending_validations()


def get_language() -> str:
    """获取当前语言代码"""
    if not _initialized:
        init("zh")
    return _current_lang


def t(key: str, **kwargs) -> str:
    """获取翻译文本，支持 format 参数

    查找顺序: 当前语言 → zh 回退 → 返回 key 本身
    """
    if not _initialized:
        init("zh")

    text = _translations.get(key)
    if text is None:
        text = _fallback_translations.get(key, key)
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def has_key(key: str) -> bool:
    """检查翻译 key 是否存在"""
    if not _initialized:
        init("zh")
    return key in _translations or key in _fallback_translations


def _read_json(lang: str) -> dict[str, str]:
    """从 JSON 文件读取翻译，返回字典（带内存缓存）"""
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


def schedule_validation(key: str, context: str) -> None:
    """延迟校验 i18n key — 未初始化时暂存，初始化后立即校验。"""
    if _initialized:
        _check_key(key, context)
    else:
        _pending_validations.append((key, context))


def _flush_pending_validations() -> None:
    """处理所有延迟校验。"""
    global _pending_validations
    for key, context in _pending_validations:
        _check_key(key, context)
    _pending_validations = []


def _check_key(key: str, context: str) -> None:
    if key and not has_key(key):
        _logger.warning("i18n key %r not found (used by %s)", key, context)


def _load(lang: str) -> None:
    """从 JSON 文件加载翻译"""
    global _translations, _fallback_translations
    _translations = _read_json(lang)
    if lang == "zh":
        _fallback_translations = _translations
    elif not _fallback_translations:
        _fallback_translations = _read_json("zh")
