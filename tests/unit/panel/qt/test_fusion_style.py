"""验证 Qt 后端全局 Fusion style(修复表头不跟随深色主题的 BUG)。

根因:macOS 默认 QMacStyle 对 QHeaderView::section 原生渐变绘制,
忽略 QSS background-color,导致深色主题下表格表头仍是系统浅灰。
Fusion 是唯一跨平台且完全尊重 QSS 的内置 style,与 tkinter 端
``style.theme_use('clam')`` 对等。

需环境变量 QT_QPA_PLATFORM=offscreen。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QStyleFactory  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    """复用全局 QApplication 单例,避免重复创建导致冲突。"""
    return QApplication.instance() or QApplication([])


def test_ensure_fusion_style_returns_true(qt_app):
    """ensure_fusion_style() 在 QApplication 存在时应返回 True。"""
    from src.panel.qt_backend.app import ensure_fusion_style

    result = ensure_fusion_style()
    assert result is True


def test_ensure_fusion_style_sets_application_style(qt_app):
    """设置后,QApplication 的 style 必须是 Fusion。"""
    from src.panel.qt_backend.app import ensure_fusion_style

    ensure_fusion_style()
    # QStyleFactory 创建的 Fusion,其 objectName 为 "Fusion"(大小写随平台)。
    assert qt_app.style().objectName().lower() == "fusion"


def test_ensure_fusion_style_idempotent(qt_app):
    """多次调用应幂等(不抛异常,仍为 Fusion)。"""
    from src.panel.qt_backend.app import ensure_fusion_style

    ensure_fusion_style()
    result = ensure_fusion_style()
    assert result is True
    assert qt_app.style().objectName().lower() == "fusion"


def test_fusion_available_on_platform(qt_app):
    """前置条件:当前 Qt 构建必须支持 Fusion(所有官方发行版均支持)。"""
    assert "Fusion" in QStyleFactory.keys()
