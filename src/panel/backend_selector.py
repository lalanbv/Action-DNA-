"""后端选择器 — 通过环境变量、配置文件或默认值切换 PySide6 / tkinter 后端。

优先级（从高到低）：
1. 环境变量 DNA_GUI_BACKEND
2. 配置文件 editor.gui_backend
3. 默认值 qt

使用方式:
  python main.py                       # 使用配置文件或默认 Qt 后端
  DNA_GUI_BACKEND=tk python main.py    # 强制使用 tkinter 后端
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


def _get_backend_from_config() -> str | None:
    """从配置文件读取 editor.gui_backend 设置。"""
    try:
        from src.core.config import load_config
        cfg = load_config()
        backend = cfg.editor.gui_backend
        if backend in ("qt", "tk"):
            return backend
    except Exception:
        logger.debug("无法从配置文件读取 GUI 后端设置，使用默认值")
    return None


def _get_backend() -> str:
    """按优先级确定 GUI 后端：环境变量 > 配置文件 > 默认值 qt。"""
    env = os.environ.get("DNA_GUI_BACKEND", "").lower().strip()
    if env in ("qt", "pyside6", "pyqt6"):
        return "qt"
    if env in ("tk", "tkinter"):
        return "tk"

    config_backend = _get_backend_from_config()
    if config_backend is not None:
        return config_backend

    return "qt"


def use_qt_backend() -> bool:
    """判断是否使用 Qt (PySide6) 后端。"""
    return _get_backend() == "qt"


def use_tk_backend() -> bool:
    """判断是否使用 tkinter 后端。"""
    return not use_qt_backend()


def current_backend_name() -> str:
    """返回当前后端名称（"qt" 或 "tk"），用于 UI 显示。"""
    return _get_backend()
