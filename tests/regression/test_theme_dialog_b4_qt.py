"""B4 回归测试（Qt）— 打开的步骤对话框在切主题时必须同步更新。

需 PySide6；未装则整体 SKIP。offscreen 模式无头运行。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from src.panel.canvas.theme import theme_manager  # noqa: E402
from src.panel.canvas.theme.theme_manager import set_theme_mode  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_theme_state():
    saved_mode = theme_manager._theme_mode
    saved_theme = theme_manager._current_theme
    saved_cbs = dict(theme_manager._theme_callbacks)
    theme_manager._current_theme = None
    yield
    theme_manager._theme_mode = saved_mode
    theme_manager._current_theme = saved_theme
    theme_manager._theme_callbacks.clear()
    theme_manager._theme_callbacks.update(saved_cbs)


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def _make_minimal_dialog(parent):
    from src.panel.qt_backend.dialogs.base_dialog import QtStepDialogBase

    class _ProbeDialog(QtStepDialogBase):
        def _build_content(self) -> None:
            pass

        def _get_result(self):
            return None

    return _ProbeDialog(parent, "probe")


def test_qt_dialog_has_apply_theme(qt_app):
    """QtStepDialogBase 提供 apply_theme（B4：可被主题切换通知）。"""
    parent = QWidget()
    dlg = _make_minimal_dialog(parent)
    try:
        assert callable(getattr(dlg, "apply_theme", None))
    finally:
        dlg.deleteLater()
        parent.deleteLater()
        qt_app.processEvents()


def test_qt_dialog_registers_theme_callback(qt_app):
    """对话框打开后注册了主题回调；关闭后注销（防泄漏）。"""
    parent = QWidget()
    cbs_before = len(theme_manager._theme_callbacks)
    dlg = _make_minimal_dialog(parent)
    try:
        assert len(theme_manager._theme_callbacks) == cbs_before + 1
    finally:
        dlg.deleteLater()
        parent.deleteLater()
        qt_app.processEvents()


def test_qt_dialog_apply_theme_rebuilds_button_qss(qt_app):
    """apply_theme 后，带 dnaBtnStyle 的按钮用新主题色重建 stylesheet。"""
    from src.panel.qt_backend.widgets import themed_button
    from src.panel.canvas.theme import current_theme

    set_theme_mode("dark")
    parent = QWidget()
    dlg = _make_minimal_dialog(parent)
    # 加一个 primary 按钮（非 secondary → 有本地 stylesheet + dnaBtnStyle property）
    btn = themed_button(dlg._content_frame, text="ok", style="primary")
    dark_qss = btn.styleSheet()
    try:
        set_theme_mode("light")
        dlg.apply_theme()
        # 按钮的 stylesheet 应随新主题重建（颜色变化）
        assert btn.styleSheet() != dark_qss
    finally:
        dlg.deleteLater()
        parent.deleteLater()
        qt_app.processEvents()
