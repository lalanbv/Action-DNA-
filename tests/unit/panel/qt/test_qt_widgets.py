"""Unit tests for Qt widgets factory and shared components."""

from __future__ import annotations

import os
import sys

import pytest

try:
    from PySide6.QtWidgets import QApplication
except ImportError:
    pytest.skip("PySide6 not installed", allow_module_level=True)

os.environ["DNA_GUI_BACKEND"] = "qt"

_qt_app = QApplication.instance() or QApplication(sys.argv)

from src.panel.qt_backend.widgets import (
    themed_button,
    themed_label,
    themed_entry,
    themed_spinbox,
    themed_doublespinbox,
    themed_checkbutton,
    themed_radiobutton,
    themed_combobox,
    themed_dropdown,
    themed_labelframe,
    themed_treeview,
    themed_separator,
    _derive_hover_bg,
)


class TestDeriveHoverBg:
    def test_light_color_darkens(self):
        result = _derive_hover_bg("#ffffff")
        assert result.startswith("#")
        assert result != "#ffffff"

    def test_dark_color_lightens(self):
        result = _derive_hover_bg("#000000")
        assert result.startswith("#")
        assert result != "#000000"

    def test_invalid_returns_input(self):
        assert _derive_hover_bg("not-a-color") == "not-a-color"

    def test_short_hex_returns_input(self):
        assert _derive_hover_bg("#ff") == "#ff"


class TestThemedButton:
    def test_creates_button(self):
        btn = themed_button(None, "Click me")
        assert btn.text() == "Click me"
        # Secondary buttons rely on global QSS, no inline style needed
        assert btn.property("dnaBtnStyle") is None or btn.property("dnaBtnStyle") == ""

    def test_primary_style(self):
        btn = themed_button(None, "OK", style="primary")
        assert btn.styleSheet()
        assert btn.property("dnaBtnStyle") == "primary"

    def test_danger_style(self):
        btn = themed_button(None, "Delete", style="danger")
        assert btn.styleSheet()
        assert btn.property("dnaBtnStyle") == "danger"

    def test_command_connected(self):
        called = [False]
        btn = themed_button(None, "Go", command=lambda: called.__setitem__(0, True))
        btn.click()
        assert called[0]


class TestThemedLabel:
    def test_creates_label(self):
        lbl = themed_label(None, "Hello")
        assert lbl.text() == "Hello"

    def test_title_style(self):
        lbl = themed_label(None, "Title", style="title")
        assert lbl.font().bold()


class TestThemedEntry:
    def test_creates_entry(self):
        e = themed_entry(None, placeholder="type here")
        assert e.placeholderText() == "type here"

    def test_initial_text(self):
        e = themed_entry(None, text="initial")
        assert e.text() == "initial"


class TestThemedSpinbox:
    def test_creates_spinbox(self):
        s = themed_spinbox(None, minimum=0, maximum=100, value=50)
        assert s.value() == 50
        assert s.minimum() == 0
        assert s.maximum() == 100


class TestThemedDoubleSpinbox:
    """QDoubleSpinBox 浮点数值框(根因 A 修复:支持小数秒数/时长)。"""

    def test_creates_doublespinbox(self):
        from PySide6.QtWidgets import QDoubleSpinBox

        s = themed_doublespinbox(
            None, minimum=0.1, maximum=300.0, value=2.5, single_step=0.1, decimals=2,
        )
        assert isinstance(s, QDoubleSpinBox)
        assert s.value() == 2.5
        assert s.minimum() == 0.1
        assert s.maximum() == 300.0
        assert s.singleStep() == 0.1
        assert s.decimals() == 2

    def test_default_decimals_when_unspecified(self):
        from PySide6.QtWidgets import QDoubleSpinBox

        s = themed_doublespinbox(None, minimum=0.0, maximum=10.0, value=1.0)
        assert isinstance(s, QDoubleSpinBox)
        assert s.value() == 1.0


class TestThemedCheckbutton:
    def test_creates_unchecked(self):
        cb = themed_checkbutton(None, "Option")
        assert cb.text() == "Option"
        assert not cb.isChecked()

    def test_creates_checked(self):
        cb = themed_checkbutton(None, "On", checked=True)
        assert cb.isChecked()


class TestThemedRadiobutton:
    def test_creates_radio(self):
        rb = themed_radiobutton(None, "Choice A")
        assert rb.text() == "Choice A"


class TestThemedCombobox:
    def test_creates_with_items(self):
        cb = themed_combobox(None, items=["a", "b", "c"])
        assert cb.count() == 3
        assert cb.itemText(0) == "a"


class TestThemedDropdown:
    """themed_dropdown —— i18n 对齐 tk 语义（options=[(value, i18n_key)]）。

    规格 §5.2 U2：统一 dropdown/combobox 命名 + props。Qt dropdown 接受
    (value, i18n_key) 元组，t() 渲染显示文本、itemData 存 value，
    currentData() 取 value（与 tk get_value() 语义一致）。
    """

    def test_accepts_options_tuples_and_translates_display(self):
        from src.utils.i18n import t

        cb = themed_dropdown(
            None,
            options=[
                ("left", "action.key.mouse_left"),
                ("right", "action.key.mouse_right"),
            ],
        )
        assert cb.count() == 2
        # 显示文本是 i18n key 的翻译，不是裸 key
        assert cb.itemText(0) == t("action.key.mouse_left")
        assert cb.itemText(1) == t("action.key.mouse_right")

    def test_item_data_stores_value_not_display(self):
        """itemData 存 value，currentData() 返回 value（非翻译文本）。"""
        cb = themed_dropdown(
            None,
            options=[("left", "action.key.mouse_left"), ("right", "action.key.mouse_right")],
        )
        assert cb.itemData(0) == "left"
        assert cb.itemData(1) == "right"
        cb.setCurrentIndex(1)
        assert cb.currentData() == "right"

    def test_find_data_locates_value(self):
        """findData 按 value 定位（替代旧 findText）。"""
        cb = themed_dropdown(
            None,
            options=[("left", "action.key.mouse_left"), ("right", "action.key.mouse_right")],
        )
        idx = cb.findData("right")
        assert idx == 1

    def test_initial_value_selects_correct_item(self):
        """value= 指定初始选中项（按 value，非显示文本）。"""
        cb = themed_dropdown(
            None,
            options=[("left", "action.key.mouse_left"), ("right", "action.key.mouse_right")],
            value="right",
        )
        assert cb.currentData() == "right"


class TestThemedLabelframe:
    def test_creates_group(self):
        gb = themed_labelframe(None, "Section")
        assert gb.title() == "Section"


class TestThemedTreeview:
    def test_creates_tree(self):
        tree = themed_treeview(None, columns=["Name", "Value"])
        assert tree.headerItem().text(0) == "Name"

    def test_alternating_colors(self):
        tree = themed_treeview(None)
        assert tree.alternatingRowColors()


from PySide6.QtWidgets import QFrame

class TestThemedSeparator:
    def test_horizontal(self):
        sep = themed_separator(None, orient="horizontal")
        assert sep.frameShape() == QFrame.Shape.HLine

    def test_vertical(self):
        sep = themed_separator(None, orient="vertical")
        assert sep.frameShape() == QFrame.Shape.VLine
