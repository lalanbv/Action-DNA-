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
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import (
        QApplication, QLabel, QLineEdit, QPushButton, QSpinBox, QToolButton,
        QVBoxLayout, QWidget,
    )
except ImportError:
    pytest.skip("PySide6 not installed", allow_module_level=True)

os.environ.setdefault("DNA_GUI_BACKEND", "qt")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

_qt_app = QApplication.instance() or QApplication(sys.argv)


def _flush_deletes() -> None:
    """模拟运行中事件循环：processEvents 不刷 DeferredDelete，须显式发送。

    ``deleteLater`` 投递的 DeferredDelete 事件在真实 ``app.exec()`` 循环里会被
    持续处理，但测试中 ``processEvents()`` 不会刷它 —— 必须显式
    ``sendPostedEvents(None, DeferredDelete)`` 才能真正释放 widget。
    """
    _qt_app.processEvents()
    _qt_app.sendPostedEvents(None, QEvent.Type.DeferredDelete)

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


def test_clear_props_frees_layout_item_widgets_on_rerender(page: _FakePage) -> None:
    """回归: _clear_props 必须递归释放 addLayout 子布局内的 widget。

    旧实现仅 deleteLater ``widget()`` 项，对 ``addLayout`` 加入的子布局
    （按钮行 / 移动行）返回的 layout 项（widget() 为 None）直接跳过，
    导致其内部 QPushButton/QSpinBox 在每次重渲染累积泄漏。
    """
    step = STEP_CLASSES[ActionType.WAIT]()
    # total=3 → 触发「移动到序号」行；按钮行始终存在；两者均为子布局
    page._show_step_props(step, 0, 3)
    _flush_deletes()  # 刷新首轮 deleteLater（含子布局内 widget）
    before = len(page._host.findChildren(QPushButton))

    page._show_step_props(step, 0, 3)  # 重渲染 → _clear_props 应释放上一轮全部 widget
    _flush_deletes()
    after = len(page._host.findChildren(QPushButton))

    assert before == after, f"子布局 widget 泄漏: {before} → {after}"


def test_reorderable_tree_drop_uses_half_row_block_order() -> None:
    """dropEvent 须用半行定位(drop_insert_target)+ 块 insert(build_block_insert_order)。"""
    import inspect

    from src.panel.qt_backend.pages import action_chain_page as mod

    src = inspect.getsource(mod._ReorderableTreeWidget.dropEvent)
    assert "drop_insert_target" in src, "须用 drop_insert_target 做半行定位"
    assert "build_block_insert_order" in src, "须用 build_block_insert_order 处理选中块"
    assert "_drag_rows[0]" not in src, "不得退回只移首行的旧写法"
    assert "visualItemRect" in src, "须按光标半行位置决定 before/after"


def test_props_inputs_and_buttons_use_objectname(page: _FakePage) -> None:
    """输入框/按钮走 objectName + 全局 QSS,不再用局部 setStyleSheet(_control_qss)。"""
    step = STEP_CLASSES[ActionType.CLICK_IMAGE]()
    page._show_step_props(step, 0, 3)

    inputs = page._host.findChildren(QLineEdit) + page._host.findChildren(QSpinBox)
    assert any(w.objectName() == "dnaDetailInput" for w in inputs), "备注/序号输入框须 dnaDetailInput"

    btns = page._host.findChildren(QPushButton)
    names = {w.objectName() for w in btns}
    assert "dnaDetailBtn" in names, "常规按钮须 dnaDetailBtn"
    assert "dnaDeleteBtn" in names, "删除按钮须 dnaDeleteBtn"
