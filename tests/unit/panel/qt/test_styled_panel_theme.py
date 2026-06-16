"""验证 _styled_panel 根治修复:用 objectName + 全局 QSS 取代隔离 stylesheet。

根因:action_chain 等页面的 _styled_panel() 给容器 QFrame 设了独立
setStyleSheet，形成样式上下文隔离。主题切换时全局 QSS 重新设置，隔离
子树内的 QTreeWidget 内容区(viewport)不重新解析 → 内容区停留旧主题色。

修复:_styled_panel 用 objectName("dnaStyledPanel") 引用全局 QSS 的
QFrame#dnaStyledPanel 规则，消除隔离源，内容区随主题刷新。

需环境变量 QT_QPA_PLATFORM=offscreen。
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _restore_theme_mode():
    """恢复全局 _theme_mode，避免污染后续测试。

    本文件的测试调用 set_theme_mode('dark'/'light')，会修改模块级全局状态。
    test_theme_sync 依赖 _theme_mode=='system'（poll 在非 system 模式下跳过），
    故必须在此恢复，否则全量测试中 test_theme_sync 失败。
    """
    from src.panel.canvas.theme import theme_manager
    original = theme_manager.current_theme_mode()
    yield
    theme_manager.set_theme_mode(original)


def test_qss_includes_styled_panel_rule(qt_app):
    """全局 QSS 必须含 QFrame#dnaStyledPanel 规则（随主题刷新，非隔离）。"""
    from src.panel.canvas.theme import current_theme, set_theme_mode
    from src.panel.qt_backend.theme import theme_to_qss

    for mode in ("dark", "light"):
        set_theme_mode(mode)
        qss = theme_to_qss(current_theme())
        assert "dnaStyledPanel" in qss, f"{mode} 主题 QSS 缺少 dnaStyledPanel 规则"
        # 规则用主题色（深/浅不同），确认颜色 token 被插入
        assert "background-color" in qss


def test_styled_panel_uses_objectname(qt_app):
    """_styled_panel 的 frame 必须用 objectName，而非隔离的局部 stylesheet。"""
    from src.panel.qt_backend.pages.action_chain_page import QtActionChainPage
    from src.panel.qt_backend.scale import qt_scale_manager

    qt_scale_manager().detect()
    frame, _layout = QtActionChainPage._styled_panel()

    assert frame.objectName() == "dnaStyledPanel"
    # 关键不变量：frame 不得重新引入隔离 stylesheet（会复活 BUG）。
    # 样式应来自全局 QSS 的 #dnaStyledPanel 规则，frame 自身 styleSheet 应为空。
    assert frame.styleSheet() == "", (
        "_styled_panel 重新引入了局部 stylesheet，会隔离子树 item view → 内容区不跟随主题"
    )
