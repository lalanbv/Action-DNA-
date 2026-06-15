"""Qt 步骤对话框 dropdown 改造回归测试（Phase 2 §5.2 U2）。

锁定：themed_dropdown 改造后，Qt 对话框 _populate_fields → _get_result 的
枚举/字符串 value roundtrip 不变形（currentData 取 value，非翻译文本）。
"""

from __future__ import annotations

import os
import sys

import pytest

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PySide6 not installed", allow_module_level=True)

os.environ.setdefault("DNA_GUI_BACKEND", "qt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_qt_app = QApplication.instance() or QApplication(sys.argv)

from src.core.step_types import ClickPosStep, MouseDragStep


@pytest.fixture
def qt_parent():
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    yield parent
    parent.deleteLater()
    _qt_app.processEvents()


def test_click_pos_dialog_button_roundtrip(qt_parent):
    """click_pos: button value 在 populate→get_result 不变（非翻译文本）。"""
    from src.panel.qt_backend.dialogs.click_pos_dialog import QtClickPosDialog

    step = ClickPosStep(pos_x=100, pos_y=200, button="right")
    dlg = QtClickPosDialog(qt_parent, "test", step, None)
    dlg._populate_fields(step)
    result = dlg._get_result()
    assert result.button == "right", (
        f"button roundtrip 失败：期望 'right'，实际 {result.button!r}（可能存了翻译文本）"
    )
    dlg.deleteLater()
    _qt_app.processEvents()


def test_click_pos_dialog_button_middle_roundtrip(qt_parent):
    """click_pos: middle button 也能正确 roundtrip。"""
    from src.panel.qt_backend.dialogs.click_pos_dialog import QtClickPosDialog

    step = ClickPosStep(button="middle")
    dlg = QtClickPosDialog(qt_parent, "test", step, None)
    dlg._populate_fields(step)
    result = dlg._get_result()
    assert result.button == "middle"
    dlg.deleteLater()
    _qt_app.processEvents()


def test_mouse_drag_dialog_button_roundtrip(qt_parent):
    """mouse_drag: button value roundtrip 不变。"""
    from src.panel.qt_backend.dialogs.mouse_drag_dialog import QtMouseDragDialog

    step = MouseDragStep(button="right")
    dlg = QtMouseDragDialog(qt_parent, "test", step, None)
    dlg._populate_fields(step)
    result = dlg._get_result()
    assert result.button == "right"
    dlg.deleteLater()
    _qt_app.processEvents()
