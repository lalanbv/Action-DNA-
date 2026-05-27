"""字体检测 — 跨平台最佳字体发现"""

import tkinter as tk
import tkinter.font as tkFont

from src.utils.platform import IS_MACOS, IS_WINDOWS

_detected_family: str | None = None
_detected_mono: str | None = None
_available_families: set[str] | None = None


def _get_available_families() -> set[str]:
    """枚举系统可用字体族（仅首次调用时枚举，结果缓存）"""
    global _available_families
    if _available_families is not None:
        return _available_families
    root = tk._default_root
    if root is None:
        return set()
    _available_families = set(tkFont.families(root))
    return _available_families


def _pick_first_available(candidates: list[str], fallback: str) -> str:
    """从候选列表中返回首个可用字体，均不可用时回退"""
    available = _get_available_families()
    for name in candidates:
        if name in available:
            return name
    return fallback


def detect_font_family() -> str:
    """检测平台最佳字体（结果缓存）"""
    global _detected_family
    if _detected_family is not None:
        return _detected_family
    if IS_MACOS:
        candidates = ["SF Pro Text"]
    elif IS_WINDOWS:
        candidates = ["Segoe UI"]
    else:
        candidates = ["Noto Sans"]
    _detected_family = _pick_first_available(candidates, "Arial")
    return _detected_family


def detect_mono_font() -> str:
    """检测平台最佳等宽字体（结果缓存）"""
    global _detected_mono
    if _detected_mono is not None:
        return _detected_mono
    if IS_MACOS:
        candidates = ["SF Mono", "Menlo"]
    elif IS_WINDOWS:
        candidates = ["Consolas", "Courier New"]
    else:
        candidates = ["DejaVu Sans Mono", "Courier New"]
    _detected_mono = _pick_first_available(candidates, "Courier")
    return _detected_mono


def build_font_kwargs(family: str, mono: str, sf) -> dict:
    """构建 13 个 font_* 关键字参数（dark/light 共用）"""
    return dict(
        font_family=family,
        font_node_title=(family, sf(10), "bold"),
        font_node_subtitle=(family, sf(8)),
        font_node_type_label=(family, sf(7)),
        font_port_label=(family, sf(7)),
        font_edge_label=(family, sf(9), "bold"),
        font_toolbar=(family, sf(9)),
        font_status=(family, sf(8)),
        font_page_title=(family, sf(20), "bold"),
        font_section_title=(family, sf(13), "bold"),
        font_dialog_title=(family, sf(14), "bold"),
        font_body=(family, sf(10)),
        font_small=(family, sf(8)),
        font_mono=(mono, sf(10)),
    )
