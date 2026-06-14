"""SystemThemeSync 单元测试 — worker 线程探测 + 主线程 marshal 编排。

验证 D1（去重）+ B1（探测不阻塞主线程，结果 marshal 回主线程）+ B5（变更调 refresh_theme）。
"""

from __future__ import annotations

import pytest

from src.panel.canvas.theme import theme_sync
from src.panel.canvas.theme.theme_sync import SystemThemeSync


class FakeBackend:
    """记录 marshal / timer 调用的假后端。"""

    def __init__(self) -> None:
        self.marshaled: list = []
        self.timers: list = []
        self.stopped: list = []

    def marshal_main(self, fn):
        self.marshaled.append(fn)

    def start_timer(self, interval_ms, fn):
        handle = ("timer", len(self.timers))
        self.timers.append((interval_ms, fn))
        return handle

    def stop_timer(self, handle):
        self.stopped.append(handle)


@pytest.fixture
def sync():
    return SystemThemeSync()


def test_start_schedules_poll_timer(sync):
    backend = FakeBackend()
    sync.start(backend)
    assert len(backend.timers) == 1
    assert backend.timers[0][0] == SystemThemeSync.POLL_INTERVAL_MS


def test_stop_cancels_timer(sync):
    backend = FakeBackend()
    sync.start(backend)
    sync.stop()
    assert backend.stopped  # 至少停止了一个 timer handle


def test_poll_detects_change_and_marshals_refresh(sync, monkeypatch):
    """OS resolved 变化时，探测结果 marshal 回主线程调 refresh_theme。"""
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    backend = FakeBackend()
    sync.start(backend)
    sync._last_resolved = "dark"  # 模拟先前 OS 是 dark

    sync._poll()

    assert len(backend.marshaled) == 1
    assert backend.marshaled[0].__name__ == "refresh_theme"


def test_poll_no_change_does_not_marshal(sync, monkeypatch):
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "dark")
    backend = FakeBackend()
    sync.start(backend)
    sync._last_resolved = "dark"

    sync._poll()

    assert backend.marshaled == []


def test_poll_records_new_resolved(sync, monkeypatch):
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    backend = FakeBackend()
    sync.start(backend)
    sync._last_resolved = "dark"

    sync._poll()

    assert sync._last_resolved == "light"


def test_poll_swallows_detection_errors(sync, monkeypatch):
    """detect_system_theme 抛异常时不崩溃、不 marshal。"""

    def boom():
        raise OSError("subprocess failed")

    monkeypatch.setattr(theme_sync, "detect_system_theme", boom)
    backend = FakeBackend()
    sync.start(backend)

    sync._poll()  # 不应抛异常

    assert backend.marshaled == []


def test_poll_ignored_when_mode_not_system(sync, monkeypatch):
    """显式 dark/light 模式下，OS 变化也不刷新（用户已固定模式）。"""
    monkeypatch.setattr(theme_sync, "current_theme_mode", lambda: "dark")
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    backend = FakeBackend()
    sync.start(backend)
    sync._last_resolved = "dark"

    sync._poll()

    assert backend.marshaled == []
