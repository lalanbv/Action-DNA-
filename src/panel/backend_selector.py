"""后端选择器 — 通过环境变量或配置切换 PySide6 / tkinter 后端。

使用方式:
  python main.py                       # 默认使用 PySide6 后端
  DNA_GUI_BACKEND=tk python main.py    # 使用 tkinter 后端（回退）
"""

from __future__ import annotations

import os


def use_qt_backend() -> bool:
    """判断是否使用 Qt (PySide6) 后端。

    检查顺序:
    1. 环境变量 DNA_GUI_BACKEND
    2. 默认 PySide6
    """
    backend = os.environ.get("DNA_GUI_BACKEND", "qt").lower().strip()
    return backend in ("qt", "pyside6", "pyqt6")


def use_tk_backend() -> bool:
    """判断是否使用 tkinter 后端（默认）。"""
    return not use_qt_backend()
