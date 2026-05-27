"""Phase 5: Interactive operations test for all Qt pages."""

from __future__ import annotations

import os
import sys

import pytest

try:
    from PySide6.QtWidgets import (
        QApplication, QMainWindow, QPushButton, QRadioButton,
        QTreeWidget, QTextEdit, QComboBox, QToolBar, QWidget,
    )
    from PySide6.QtCore import QTimer
except ImportError:
    pytest.skip("PySide6 not installed", allow_module_level=True)

os.environ["DNA_GUI_BACKEND"] = "qt"

qt_app = QApplication.instance() or QApplication(sys.argv)

from src.panel.qt_backend.timer import QtTimerScheduler
from src.core.container.container import ServiceContainer


class _MockApp(QMainWindow):
    """Minimal mock that satisfies page dependencies via ServiceContainer."""

    def __init__(self):
        super().__init__()
        self._container = ServiceContainer()
        self._timer = QtTimerScheduler()

        # Register lightweight services pages may try to get
        from src.core.events.bus import TypedEventBus
        from src.core.engine.node_registry import NodeRegistry
        self._container.register(TypedEventBus, TypedEventBus)
        self._container.register(NodeRegistry, NodeRegistry)

    # ServiceProvider-like properties
    @property
    def event_bus(self):
        from src.core.events.bus import TypedEventBus
        return self._container.try_get(TypedEventBus)

    @property
    def executor(self):
        return None

    @property
    def capture(self):
        return None

    @property
    def matcher(self):
        return None

    @property
    def hotkey_manager(self):
        return None

    @property
    def plugin_loader(self):
        return None

    @property
    def input_ctrl(self):
        return None

    @property
    def node_registry(self):
        from src.core.engine.node_registry import NodeRegistry
        return self._container.try_get(NodeRegistry)

    @property
    def toast_manager(self):
        return None

    def navigate_to(self, page_id, **kw):
        pass

    def clear_page_cache(self):
        pass

    def get_cached_page(self, page_id):
        return None

    def get_executor_source(self):
        return None

    def set_executor_source(self, page):
        pass

    def window(self):
        return self


mock_app = _MockApp()

from src.panel.qt_backend.pages.home_page import QtHomePage
from src.panel.qt_backend.pages.action_chain_page import QtActionChainPage
from src.panel.qt_backend.pages.workflow_page import QtWorkflowPage
from src.panel.qt_backend.pages.record_page import QtRecordPage
from src.panel.qt_backend.pages.notification_page import QtNotificationPage
from src.panel.qt_backend.pages.schedule_page import QtSchedulePage
from src.panel.qt_backend.pages.settings_page import QtSettingsPage
from src.panel.qt_backend.pages.plugin_page import QtPluginPage


def _all_widgets(widget):
    result = [widget]
    for child in widget.children():
        result.extend(_all_widgets(child))
    return result


def _find(parent, wtype, text=None):
    results = []
    for w in _all_widgets(parent):
        if isinstance(w, wtype):
            if text is None:
                results.append(w)
            elif hasattr(w, "text") and text in w.text():
                results.append(w)
    return results


def _make_page(cls):
    page = cls(parent=None, app=mock_app)
    page.build()
    return page


def test_home_navigation():
    page = _make_page(QtHomePage)
    buttons = _find(page, QPushButton)
    cards = [b.text() for b in buttons if b.text() and len(b.text()) > 1]
    page.deleteLater()
    return f"cards={cards}"


def test_action_chain_add_step():
    page = _make_page(QtActionChainPage)
    combos = _find(page, QComboBox)
    if combos:
        combos[0].setCurrentIndex(0)
    add_btns = _find(page, QPushButton, "添加")
    if add_btns:
        add_btns[0].click()
    trees = _find(page, QTreeWidget)
    count = trees[0].topLevelItemCount() if trees else 0
    page.deleteLater()
    return f"tree_items={count}"


def test_workflow_canvas():
    page = _make_page(QtWorkflowPage)
    trees = _find(page, QTreeWidget)
    toolbars = _find(page, QToolBar)
    buttons = _find(page, QPushButton)
    labels = [b.text() for b in buttons if b.text()][:5]
    page.deleteLater()
    return f"trees={len(trees)}, toolbars={len(toolbars)}, btn_labels={labels}"


def test_settings_theme():
    page = _make_page(QtSettingsPage)
    radios = _find(page, QRadioButton)
    themes = [r.text() for r in radios]
    for r in radios:
        if "深色" in r.text():
            r.click()
            break
    dark_on = any("深色" in r.text() and r.isChecked() for r in radios)
    page.deleteLater()
    return f"themes={themes}, dark={dark_on}"


def test_schedule_add():
    page = _make_page(QtSchedulePage)
    btns = _find(page, QPushButton, "添加调度")
    if btns:
        btns[0].click()
    page.deleteLater()
    return "clicked"


def test_notification_add():
    page = _make_page(QtNotificationPage)
    btns = _find(page, QPushButton, "添加规则")
    if btns:
        btns[0].click()
    page.deleteLater()
    return "clicked"


def test_record_toolbar():
    page = _make_page(QtRecordPage)
    has = lambda t: len(_find(page, QPushButton, t)) > 0
    rec, stop, undo = has("录制"), has("停止"), has("撤销")
    page.deleteLater()
    return f"record={rec}, stop={stop}, undo={undo}"


def test_plugin_structure():
    page = _make_page(QtPluginPage)
    trees = _find(page, QTreeWidget)
    edits = _find(page, QTextEdit)
    page.deleteLater()
    return f"trees={len(trees)}, text_edits={len(edits)}"


TESTS = [
    ("Home", test_home_navigation),
    ("ActionChain", test_action_chain_add_step),
    ("Workflow", test_workflow_canvas),
    ("Settings", test_settings_theme),
    ("Schedule", test_schedule_add),
    ("Notification", test_notification_add),
    ("Record", test_record_toolbar),
    ("Plugin", test_plugin_structure),
]


def main():
    passed = failed = 0
    results = []
    for name, fn in TESTS:
        try:
            r = fn()
            results.append(f"  PASS {name}: {r}")
            passed += 1
        except Exception as e:
            import traceback
            results.append(f"  FAIL {name}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    print("\n=== Phase 5: Interactive Tests ===")
    for r in results:
        print(r)
    print(f"\n{passed}/{passed+failed} passed")
    if failed:
        sys.exit(1)
    print("ALL PASSED")


if __name__ == "__main__":
    main()
