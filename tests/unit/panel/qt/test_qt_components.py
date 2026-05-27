"""Unit tests for Qt shared components (base, indicators, log_viewer, monitor_status)."""

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

from src.panel.qt_backend.components.base import QtDNAWidget
from src.panel.qt_backend.components.indicators import QtBadge
from src.panel.qt_backend.components.monitor_status_widget import (
    QtMonitorStatusWidget,
    _format_elapsed,
)
from src.panel.canvas.theme import remove_theme_change


class TestQtDNAWidget:
    def test_registers_theme_callback(self):
        w = QtDNAWidget()
        assert w._theme_cb_id is not None

    def test_destroy_removes_callback(self):
        w = QtDNAWidget()
        cb_id = w._theme_cb_id
        w.destroy_widget()
        assert w._theme_cb_id is None
        # Verify the callback was unregistered (removing again should not raise)
        remove_theme_change(cb_id)  # already removed, no-op


class TestQtBadge:
    def test_creates_neutral(self):
        badge = QtBadge(None, "v1.0")
        assert badge._variant == "neutral"

    def test_set_text(self):
        badge = QtBadge(None, "old")
        badge.set_text("new")
        assert badge._label.text() == "new"

    def test_set_variant(self):
        badge = QtBadge(None, "ok", variant="success")
        assert badge._variant == "success"

    def test_configure(self):
        badge = QtBadge(None, "x")
        badge.configure(text="y", variant="error")
        assert badge._label.text() == "y"
        assert badge._variant == "error"


class TestFormatElapsed:
    def test_seconds(self):
        assert _format_elapsed(30) == "30s ago"

    def test_minutes(self):
        assert _format_elapsed(120) == "2m ago"

    def test_hours(self):
        assert _format_elapsed(7200) == "2h ago"

    def test_zero(self):
        assert _format_elapsed(0) == "0s ago"


class TestQtMonitorStatusWidget:
    def test_creates_empty(self):
        w = QtMonitorStatusWidget()
        assert len(w._cards) == 0

    def test_apply_theme(self):
        w = QtMonitorStatusWidget()
        w.apply_theme()  # should not raise
