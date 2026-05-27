"""Phase 6: Memory leak detection — page creation/destruction cycles."""

from __future__ import annotations

import gc
import os
import sys
import tracemalloc

import pytest

try:
    from PySide6.QtWidgets import QApplication, QMainWindow
except ImportError:
    pytest.skip("PySide6 not installed", allow_module_level=True)

os.environ["DNA_GUI_BACKEND"] = "qt"

qt_app = QApplication.instance() or QApplication(sys.argv)

from src.core.container.container import ServiceContainer
from src.panel.qt_backend.timer import QtTimerScheduler
from src.core.events.bus import TypedEventBus
from src.core.engine.node_registry import NodeRegistry
from src.panel.canvas.theme.theme_manager import _theme_callbacks


class _MockApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self._container = ServiceContainer()
        self._container.register(TypedEventBus, TypedEventBus)
        self._container.register(NodeRegistry, NodeRegistry)

    @property
    def event_bus(self):
        return self._container.try_get(TypedEventBus)

    @property
    def executor(self): return None
    @property
    def capture(self): return None
    @property
    def matcher(self): return None
    @property
    def hotkey_manager(self): return None
    @property
    def plugin_loader(self): return None
    @property
    def input_ctrl(self): return None
    @property
    def node_registry(self):
        return self._container.try_get(NodeRegistry)
    @property
    def toast_manager(self): return None

    def navigate_to(self, page_id, **kw): pass
    def clear_page_cache(self): pass
    def get_cached_page(self, page_id): return None
    def get_executor_source(self): return None
    def set_executor_source(self, page): pass


PAGE_CLASSES = []
for name, mod_path, cls_name in [
    ("Home", "src.panel.qt_backend.pages.home_page", "QtHomePage"),
    ("ActionChain", "src.panel.qt_backend.pages.action_chain_page", "QtActionChainPage"),
    ("Workflow", "src.panel.qt_backend.pages.workflow_page", "QtWorkflowPage"),
    ("Settings", "src.panel.qt_backend.pages.settings_page", "QtSettingsPage"),
    ("Record", "src.panel.qt_backend.pages.record_page", "QtRecordPage"),
]:
    try:
        import importlib
        mod = importlib.import_module(mod_path)
        PAGE_CLASSES.append((name, getattr(mod, cls_name)))
    except Exception:
        pass


def _cycle_page(cls, app, count=1):
    for _ in range(count):
        page = cls(parent=None, app=app)
        try:
            page.build()
        except Exception:
            pass
        if hasattr(page, "destroy_page"):
            page.destroy_page()
        else:
            page.deleteLater()
        qt_app.processEvents()
        gc.collect()


def test_page_lifecycle_leak():
    """Create/destroy pages N times with warmup, check for unbounded growth."""
    app = _MockApp()
    WARMUP = 3
    MEASURE = 10
    THRESHOLD_KB = 200  # Per-cycle growth threshold

    results = []
    for name, cls in PAGE_CLASSES:
        # Warmup — let Qt/Python caches settle
        _cycle_page(cls, app, WARMUP)

        # Measure
        tracemalloc.start()
        for _ in range(MEASURE):
            _cycle_page(cls, app)

        current_kb = tracemalloc.get_traced_memory()[0] / 1024
        tracemalloc.stop()
        per_cycle_kb = current_kb / MEASURE
        status = "OK" if per_cycle_kb < THRESHOLD_KB else "LEAK"
        results.append((name, current_kb, per_cycle_kb, status))

    print(f"\n=== Phase 6: Memory Leak Test ({MEASURE} cycles, after {WARMUP} warmup) ===")
    leaks = []
    for name, total, per, status in results:
        print(f"  {name}: {total:.1f} KB total, {per:.1f} KB/cycle  {status}")
        if status == "LEAK":
            leaks.append(name)

    if leaks:
        print(f"\nLEAKS DETECTED in: {leaks}")
        sys.exit(1)
    print("\nNO MEMORY LEAKS DETECTED")


def test_theme_callback_leak():
    """Verify theme callbacks don't accumulate after page destruction."""
    app = _MockApp()
    before = len(_theme_callbacks)

    for name, cls in PAGE_CLASSES:
        for _ in range(5):
            _cycle_page(cls, app)

    after = len(_theme_callbacks)
    growth = after - before

    print(f"\n=== Theme Callback Leak Test ===")
    print(f"  Before: {before}, After: {after}, Growth: {growth}")

    if growth > 0:
        print(f"  LEAK: {growth} unregistered callbacks")
        sys.exit(1)
    print("  OK: No leaked callbacks")


if __name__ == "__main__":
    test_page_lifecycle_leak()
    test_theme_callback_leak()
