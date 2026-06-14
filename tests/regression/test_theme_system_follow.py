"""B5 回归测试 — system 模式下 OS 深浅色切换后主题必须重建。

复现链（修复前）：OS dark→light → 轮询检测到 → set_theme_mode("system")
命中 skip 逻辑 → 不重建 → 界面卡旧主题。

修复后：SystemThemeSync._poll 检测到变化 → marshal refresh_theme → 重建 + 通知。
"""

from __future__ import annotations

import pytest

from src.panel.canvas.theme import theme_manager, theme_sync
from src.panel.canvas.theme.theme_manager import current_theme, set_theme_mode
from src.panel.canvas.theme.theme_sync import SystemThemeSync


class _RecordingBackend:
    """同步执行 marshal 的假后端（测试用）。"""

    def __init__(self) -> None:
        self.marshaled = []

    def marshal_main(self, fn):
        # 模拟主线程立即执行（测试中同步）
        self.marshaled.append(fn)
        fn()

    def start_timer(self, interval_ms, fn):
        return "handle"

    def stop_timer(self, handle):
        pass


@pytest.fixture(autouse=True)
def _reset():
    saved_mode = theme_manager._theme_mode
    saved_theme = theme_manager._current_theme
    saved_cbs = dict(theme_manager._theme_callbacks)
    theme_manager._theme_mode = "system"
    theme_manager._current_theme = None
    yield
    theme_manager._theme_mode = saved_mode
    theme_manager._current_theme = saved_theme
    theme_manager._theme_callbacks.clear()
    theme_manager._theme_callbacks.update(saved_cbs)


def test_system_mode_os_switch_rebuilds_theme(monkeypatch):
    """OS dark→light：refresh_theme 被调用，current_theme() 反映新主题。"""
    # 用可辨识的假主题区分 dark/light
    dark_theme = object()
    light_theme = object()

    def fake_build():
        return light_theme if theme_sync.detect_system_theme() == "light" else dark_theme

    monkeypatch.setattr(theme_manager, "_build_theme", fake_build)

    # 初始 OS = dark
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "dark")
    set_theme_mode("system")
    assert current_theme() is dark_theme

    # 注册一个订阅，验证它会收到通知
    notified = []
    theme_manager.on_theme_change(lambda: notified.append(True))

    # 启动同步，初始 resolved = dark
    sync = SystemThemeSync()
    backend = _RecordingBackend()
    sync.start(backend)
    assert sync._last_resolved == "dark"

    # OS 切到 light，worker 线程探测
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    sync._poll()

    # B5 修复断言：主题已重建为新主题，订阅已通知
    assert current_theme() is light_theme
    assert notified == [True]
    assert sync._last_resolved == "light"

    sync.stop()


def test_explicit_dark_mode_ignores_os_change(monkeypatch):
    """显式 dark 模式：OS 变化不触发刷新（用户已固定模式）。"""
    fixed = object()
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: fixed)
    theme_manager._theme_mode = "dark"
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "dark")
    set_theme_mode("dark")
    assert current_theme() is fixed

    sync = SystemThemeSync()
    backend = _RecordingBackend()
    sync.start(backend)

    # OS 切 light，但因模式非 system，_poll 不应 marshal
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    sync._poll()

    assert backend.marshaled == []
    assert current_theme() is fixed  # 仍是原主题
    sync.stop()
