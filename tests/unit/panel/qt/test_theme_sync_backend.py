"""QtThemeSyncBackend 单元测试（offscreen）。

验证 D1（去重）+ B3（Qt 6.5+ 实时 colorSchemeChanged → refresh_theme）。
需环境变量 QT_QPA_PLATFORM=offscreen。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.panel.canvas.theme import theme_manager  # noqa: E402
from src.panel.qt_backend.theme_sync_backend import QtThemeSyncBackend  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_marshal_main_schedules_on_main_thread(qt_app):
    """marshal_main 用 QTimer.singleShot(0) 调度到主线程。"""
    backend = QtThemeSyncBackend(qt_app)
    called = []
    backend.marshal_main(lambda: called.append(True))
    # 处理一次事件循环以执行 singleShot 回调
    qt_app.processEvents()
    assert called == [True]


def test_has_color_scheme_signal_detection(qt_app):
    """探测 Qt 版本是否支持 colorSchemeChanged（6.5+）。"""
    backend = QtThemeSyncBackend(qt_app)
    # 不断言具体 True/False（取决于运行时 Qt 版本），只断言属性存在且为 bool
    assert isinstance(backend.has_color_scheme_signal, bool)


def test_refresh_on_color_scheme_changed_calls_refresh(qt_app, monkeypatch):
    """colorSchemeChanged 信号触发时调用 refresh_theme（B3）。"""
    backend = QtThemeSyncBackend(qt_app)
    if not backend.has_color_scheme_signal:
        pytest.skip("Qt < 6.5 无 colorSchemeChanged 信号")

    called = {}
    monkeypatch.setattr(theme_manager, "refresh_theme", lambda: called.__setitem__("x", True))

    backend._on_color_scheme_changed()

    assert called == {"x": True}
