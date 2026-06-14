"""Qt condition/monitor 多模板集成(无 PySide6 则 SKIP)。"""

import pytest

qtw = pytest.importorskip("PySide6")  # noqa: F841 — venv 当前无 PySide6 → 整文件 SKIP


def test_qt_condition_dialog_imports():
    from src.panel.qt_backend.dialogs.condition_dialog import QtConditionDialog
    assert QtConditionDialog is not None


def test_qt_monitor_dialog_imports():
    from src.panel.qt_backend.dialogs.monitor_dialog import QtMonitorDialog
    assert QtMonitorDialog is not None
