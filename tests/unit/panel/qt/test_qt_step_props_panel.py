"""Qt 步骤详情面板渲染冒烟测试。

锁定选中步骤后详情面板渲染了：
- describe 摘要（修历史漏渲染 bug）
- 关键参数表（key_fields 驱动）
- 全部字段折叠区（QToolButton 标题）
- 「移动到序号」行（多步时显示，单步时隐藏）
- 复制按钮
"""

from __future__ import annotations

import os
import sys

import pytest

try:
    from PySide6.QtWidgets import (
        QApplication, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget,
    )
except ImportError:
    pytest.skip("PySide6 not installed", allow_module_level=True)

os.environ.setdefault("DNA_GUI_BACKEND", "qt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_qt_app = QApplication.instance() or QApplication(sys.argv)

from src.core.action import ActionType  # noqa: E402
from src.core.step_types import STEP_CLASSES  # noqa: E402
from src.panel.qt_backend.pages.action_chain_props_mixin import QtActionChainPropsMixin  # noqa: E402


class _FakePage(QtActionChainPropsMixin):
    """最小宿主：只提供 props_mixin 要求的属性 / 回调。"""

    def __init__(self) -> None:
        self._host = QWidget()
        self._props_layout = QVBoxLayout(self._host)
        self._selected_step_idx = 0
        self._controller = None
        self._on_step_enabled_change = lambda: None
        self._on_move_up = lambda: None
        self._on_move_down = lambda: None
        self._on_edit_step = lambda: None
        self._on_delete_step = lambda: None

    def _on_duplicate(self) -> None:  # 由测试覆盖
        pass

    def _on_move_to_index(self, target: int) -> None:  # 由测试覆盖
        pass

    def _labels(self) -> list[str]:
        return [w.text() for w in self._host.findChildren(QLabel)]

    def _buttons(self) -> list[str]:
        return [w.text() for w in self._host.findChildren(QPushButton)]

    def _toolbuttons(self) -> list[str]:
        return [w.text() for w in self._host.findChildren(QToolButton)]


@pytest.fixture
def page() -> _FakePage:
    return _FakePage()


def test_renders_summary_key_params_and_all_fields(page: _FakePage) -> None:
    step = STEP_CLASSES[ActionType.CLICK_IMAGE]()
    step.image_path = "/x/y/btn.png"
    page._show_step_props(step, 0, 2)

    labels = page._labels()
    assert any("关键参数" in t for t in labels)
    assert any("btn.png" in t for t in labels)  # 关键参数值含 basename
    # 「全部字段」是折叠按钮（QToolButton）
    assert any("全部字段" in t for t in page._toolbuttons())


def test_move_to_row_shown_when_multiple_steps(page: _FakePage) -> None:
    step = STEP_CLASSES[ActionType.WAIT]()
    page._show_step_props(step, 0, 3)
    assert any("移动到序号" in t for t in page._labels())


def test_move_to_row_hidden_when_single_step(page: _FakePage) -> None:
    step = STEP_CLASSES[ActionType.WAIT]()
    page._show_step_props(step, 0, 1)
    assert not any("移动到序号" in t for t in page._labels())


def test_duplicate_button_present(page: _FakePage) -> None:
    step = STEP_CLASSES[ActionType.WAIT]()
    page._show_step_props(step, 0, 2)
    assert any("复制" in b for b in page._buttons())


def test_describe_summary_rendered(page: _FakePage) -> None:
    """修 bug 核心：describe 摘要必须出现（此前 Qt 端漏渲染）。"""
    step = STEP_CLASSES[ActionType.WAIT](wait_seconds=2.0)
    page._show_step_props(step, 0, 2)
    labels = page._labels()
    assert any("2" in t for t in labels)  # describe 含 wait 秒数
