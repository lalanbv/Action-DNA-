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
    themed_checkbutton,
    themed_radiobutton,
    themed_combobox,
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
        assert btn.styleSheet()

    def test_primary_style(self):
        btn = themed_button(None, "OK", style="primary")
        assert "accent_blue" not in btn.styleSheet() or "background" in btn.styleSheet()

    def test_danger_style(self):
        btn = themed_button(None, "Delete", style="danger")
        assert btn.styleSheet()

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
        assert e.styleSheet()

    def test_initial_text(self):
        e = themed_entry(None, text="initial")
        assert e.text() == "initial"


class TestThemedSpinbox:
    def test_creates_spinbox(self):
        s = themed_spinbox(None, minimum=0, maximum=100, value=50)
        assert s.value() == 50
        assert s.minimum() == 0
        assert s.maximum() == 100


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


class TestThemedLabelframe:
    def test_creates_group(self):
        gb = themed_labelframe(None, "Section")
        assert gb.title() == "Section"
        assert gb.styleSheet()


class TestThemedTreeview:
    def test_creates_tree(self):
        tree = themed_treeview(None, columns=["Name", "Value"])
        assert tree.headerItem().text(0) == "Name"
        assert tree.styleSheet()

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
