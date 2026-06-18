"""Qt 浮点数值框 + 等待秒数 + 步骤等待列 回归测试。

锁定三个根因修复:
- A: _add_labeled_spinbox 浮点字段失效(QSpinBox 半截 ×1000 缩放 → 改用 QDoubleSpinBox)
     表现: 等待/长按/移动速度等所有浮点字段改了不生效, 显示被钳到 100。
- B: 步骤列表等待列用错属性名 wait_time(应为 wait_seconds / wait_min+max)→ 永远空白。

修复前这些用例全部失败, 修复后全绿。
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

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox  # noqa: E402

from src.core.step_types import (  # noqa: E402
    MouseScrollStep,
    PressKeyStep,
    WaitRandomStep,
    WaitStep,
)


@pytest.fixture
def qt_parent():
    """对话框父窗口(每个用例独立)。"""
    from PySide6.QtWidgets import QWidget

    parent = QWidget()
    yield parent
    parent.deleteLater()
    _qt_app.processEvents()


# ── 根因 A: 浮点数值框 ────────────────────────────────────────


def test_wait_dialog_seconds_roundtrip(qt_parent):
    """等待对话框: wait_seconds=2.5 populate→get_result 不变形(不被钳到 100)。"""
    from src.panel.qt_backend.dialogs.wait_dialog import QtWaitDialog

    step = WaitStep(wait_seconds=2.5)
    dlg = QtWaitDialog(qt_parent, "test", step, None)
    result = dlg._get_result()
    assert result.wait_seconds == pytest.approx(2.5), (
        f"wait_seconds roundtrip 失败: 期望 2.5, 实际 {result.wait_seconds}"
    )
    dlg.deleteLater()
    _qt_app.processEvents()


def test_wait_dialog_user_change_persists(qt_parent):
    """模拟用户把秒数改成 5.0 → _get_result 返回 5.0(原 bug: 返回 100)。"""
    from src.panel.qt_backend.dialogs.wait_dialog import QtWaitDialog

    step = WaitStep(wait_seconds=1.0)
    dlg = QtWaitDialog(qt_parent, "test", step, None)
    dlg._vars["wait_seconds"].setValue(5.0)
    result = dlg._get_result()
    assert result.wait_seconds == pytest.approx(5.0), (
        f"用户修改未生效: 期望 5.0, 实际 {result.wait_seconds}"
    )
    dlg.deleteLater()
    _qt_app.processEvents()


def test_wait_dialog_spinbox_is_double_with_real_range(qt_parent):
    """wait_seconds 控件应为 QDoubleSpinBox, 且 min=0.1/max=300/value 正确(非 ×1000)。"""
    from src.panel.qt_backend.dialogs.wait_dialog import QtWaitDialog

    step = WaitStep(wait_seconds=1.0)
    dlg = QtWaitDialog(qt_parent, "test", step, None)
    spin = dlg._vars["wait_seconds"]
    assert isinstance(spin, QDoubleSpinBox), (
        "wait_seconds 应为 QDoubleSpinBox(支持小数), 当前为 "
        f"{type(spin).__name__}"
    )
    assert spin.minimum() == pytest.approx(0.1), (
        f"minimum 应为 0.1, 实际 {spin.minimum()}"
    )
    assert spin.maximum() == pytest.approx(300.0), (
        f"maximum 应为 300.0, 实际 {spin.maximum()}"
    )
    assert spin.value() == pytest.approx(1.0), (
        f"value 应为 1.0(回填正确, 不被钳), 实际 {spin.value()}"
    )
    dlg.deleteLater()
    _qt_app.processEvents()


def test_wait_random_dialog_range_correct(qt_parent):
    """wait_min/wait_max 浮点框范围与值正确(覆盖另一浮点对话框)。"""
    from src.panel.qt_backend.dialogs.wait_random_dialog import QtWaitRandomDialog

    step = WaitRandomStep(wait_min=0.5, wait_max=2.0)
    dlg = QtWaitRandomDialog(qt_parent, "test", step, None)
    spin_min = dlg._vars["wait_min"]
    assert isinstance(spin_min, QDoubleSpinBox)
    assert spin_min.value() == pytest.approx(0.5), (
        f"wait_min 回填应为 0.5, 实际 {spin_min.value()}"
    )
    result = dlg._get_result()
    assert result.wait_min == pytest.approx(0.5)
    assert result.wait_max == pytest.approx(2.0)
    dlg.deleteLater()
    _qt_app.processEvents()


def test_integer_spinbox_still_uses_qspinbox(qt_parent):
    """整数字段(increment>=1)应保持 QSpinBox, 不误转为 QDoubleSpinBox。"""
    from src.panel.qt_backend.dialogs.scroll_dialog import QtScrollDialog

    step = MouseScrollStep(scroll_clicks=3)
    dlg = QtScrollDialog(qt_parent, "test", step, None)
    spin = dlg._vars["scroll_clicks"]
    assert isinstance(spin, QSpinBox), "整数字段应保持 QSpinBox"
    assert not isinstance(spin, QDoubleSpinBox), "整数字段不应是 QDoubleSpinBox"
    result = dlg._get_result()
    assert result.scroll_clicks == 3
    dlg.deleteLater()
    _qt_app.processEvents()


# ── 根因 B: 步骤列表等待列(共享 wait_text, Qt/tk 统一) ─────────


def test_step_wait_text_wait_step():
    """WaitStep → '{seconds}s'。"""
    from src.panel.components.step_param_view import wait_text

    assert wait_text(WaitStep(wait_seconds=2.5)) == "2.5s"


def test_step_wait_text_wait_random_step():
    """WaitRandomStep → '{min}~{max}s'。"""
    from src.panel.components.step_param_view import wait_text

    text = wait_text(WaitRandomStep(wait_min=0.5, wait_max=2.0))
    assert text == "0.5~2s", f"期望 '0.5~2s', 实际 {text!r}"


def test_step_wait_text_other_step_is_empty():
    """非等待类步骤 → ''(时间信息由 describe() 详情列承载)。"""
    from src.panel.components.step_param_view import wait_text

    assert wait_text(PressKeyStep(key="a")) == ""
