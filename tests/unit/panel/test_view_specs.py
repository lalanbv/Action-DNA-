"""Phase 2 组件契约一致性测试（规格 §5.1）。

遍历 shared/view_specs/ 下的契约，断言两后端（tk / Qt）工厂接受相同 props、
返回各自控件类型。缺失 prop 或异常 → 测试失败。

tk 真实 root（withdraw），Qt offscreen —— 与既有 panel 测试同形态。
"""

from __future__ import annotations

import inspect

import pytest

from src.panel.shared.view_specs import button as btn_spec
from src.panel.shared.view_specs import checkbox as cb_spec
from src.panel.shared.view_specs import entry as entry_spec

#: 契约 → (props 列表)。
CONTRACTS = {
    "button": btn_spec.BUTTON_PROPS,
    "entry": entry_spec.ENTRY_PROPS,
    "checkbox": cb_spec.CHECKBOX_PROPS,
}


# ---- tk 后端契约校验 ----

tk = pytest.importorskip("tkinter")


@pytest.fixture
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_tk_factory_signatures_accept_contract_props(tk_root):
    """tk 工厂函数签名包含契约要求的 props（text/command/style 等）。"""
    from src.panel import widgets as tkw

    factories = {
        "button": tkw.themed_button,
        "entry": tkw.themed_entry,
        "checkbox": tkw.themed_checkbutton,
    }
    for name, fn in factories.items():
        params = set(inspect.signature(fn).parameters)
        # 契约 prop 要么是具名参数，要么工厂接受 **kw（都算兼容）
        accepts_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in inspect.signature(fn).parameters.values()
        )
        for prop in CONTRACTS[name]:
            assert prop in params or accepts_kw, (
                f"tk {name} 工厂不接受契约 prop {prop!r}"
            )


def test_tk_button_accepts_all_variants(tk_root):
    """tk themed_button 接受全部 ButtonVariant。"""
    from src.panel.widgets import themed_button

    for variant in ("primary", "secondary", "danger", "ghost"):
        btn = themed_button(tk_root, text="x", style=variant)
        assert btn is not None


# ---- Qt 后端契约校验 ----

pytest.importorskip("PySide6")


@pytest.fixture(scope="module")
def qt_app():
    os_env = __import__("os")
    os_env.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def test_qt_factory_signatures_accept_contract_props(qt_app):
    """Qt 工厂函数签名包含契约要求的 props。"""
    from PySide6.QtWidgets import QWidget

    from src.panel.qt_backend import widgets as qtw

    factories = {
        "button": qtw.themed_button,
        "entry": qtw.themed_entry,
        "checkbox": qtw.themed_checkbutton,
    }
    parent = QWidget()
    for name, fn in factories.items():
        params = set(inspect.signature(fn).parameters)
        accepts_kw = any(
            p.kind == inspect.Parameter.VAR_KEYWORD
            for p in inspect.signature(fn).parameters.values()
        )
        for prop in CONTRACTS[name]:
            assert prop in params or accepts_kw, (
                f"Qt {name} 工厂不接受契约 prop {prop!r}"
            )
    parent.deleteLater()
    qt_app.processEvents()


def test_qt_button_accepts_all_variants(qt_app):
    """Qt themed_button 接受全部 ButtonVariant 并设 dnaBtnStyle property。"""
    from PySide6.QtWidgets import QPushButton, QWidget

    from src.panel.qt_backend.widgets import themed_button

    parent = QWidget()
    for variant in ("primary", "secondary", "danger", "ghost"):
        btn = themed_button(parent, text="x", style=variant)
        assert isinstance(btn, QPushButton)
    parent.deleteLater()
    qt_app.processEvents()
