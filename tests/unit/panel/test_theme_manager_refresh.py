"""theme_manager.refresh_theme / restore_from_config 单元测试。

验证 B5 修复：system 模式下强制重建主题并通知订阅，绕过 set_theme_mode 的 skip 逻辑。
"""

from __future__ import annotations

import pytest

from src.panel.canvas.theme import theme_manager
from src.panel.canvas.theme.theme_manager import refresh_theme


@pytest.fixture(autouse=True)
def _reset_theme_state():
    """每个测试前后清理 theme_manager 模块全局状态。"""
    saved_mode = theme_manager._theme_mode
    saved_theme = theme_manager._current_theme
    saved_cbs = dict(theme_manager._theme_callbacks)
    theme_manager._current_theme = None
    yield
    theme_manager._theme_mode = saved_mode
    theme_manager._current_theme = saved_theme
    theme_manager._theme_callbacks.clear()
    theme_manager._theme_callbacks.update(saved_cbs)


def test_refresh_theme_rebuilds_cache(monkeypatch):
    """refresh_theme 清除缓存并重建（即使 _theme_mode 未变）。"""
    rebuilt = {"sentinel": "dark_v2"}
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: rebuilt)

    theme_manager._theme_mode = "system"
    theme_manager._current_theme = {"sentinel": "old"}  # 旧缓存

    refresh_theme()

    assert theme_manager._current_theme is rebuilt


def test_refresh_theme_notifies_subscribers(monkeypatch):
    """refresh_theme 触发所有已注册回调。"""
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: object())
    theme_manager._theme_mode = "system"

    notified = []
    cb_id = theme_manager.on_theme_change(lambda: notified.append("called"))

    refresh_theme()

    assert notified == ["called"]
    theme_manager.remove_theme_change(cb_id)


def test_refresh_theme_skips_dead_callbacks(monkeypatch):
    """回调抛异常时被静默移除，不影响其他回调。"""
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: object())
    theme_manager._theme_mode = "system"

    good = []

    def _good():
        good.append("alive")

    def _bad():
        raise RuntimeError("dead")

    bad_id = theme_manager.on_theme_change(_bad)
    theme_manager.on_theme_change(_good)

    refresh_theme()

    assert good == ["alive"]
    # 抛异常的回调应被移除
    assert bad_id not in theme_manager._theme_callbacks


def test_refresh_theme_does_not_change_mode(monkeypatch):
    """refresh_theme 不改变 _theme_mode（system 仍是 system）。"""
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: object())
    theme_manager._theme_mode = "system"

    refresh_theme()

    assert theme_manager._theme_mode == "system"


from src.panel.canvas.theme.theme_manager import restore_from_config


class _FakeEditor:
    def __init__(self, mode: str) -> None:
        self.theme_mode = mode


class _FakeConfig:
    def __init__(self, mode: str) -> None:
        self.editor = _FakeEditor(mode)


def test_restore_from_config_valid_mode(monkeypatch):
    """合法 theme_mode 被恢复。"""
    called = {}
    monkeypatch.setattr(theme_manager, "set_theme_mode", lambda m: called.__setitem__("mode", m))

    restore_from_config(_FakeConfig("dark"))

    assert called == {"mode": "dark"}


def test_restore_from_config_invalid_mode_falls_back(monkeypatch):
    """非法 theme_mode 回退到 system。"""
    called = {}
    monkeypatch.setattr(theme_manager, "set_theme_mode", lambda m: called.__setitem__("mode", m))

    restore_from_config(_FakeConfig("hot-pink"))

    assert called == {"mode": "system"}


def test_restore_from_config_accepts_system(monkeypatch):
    called = {}
    monkeypatch.setattr(theme_manager, "set_theme_mode", lambda m: called.__setitem__("mode", m))

    restore_from_config(_FakeConfig("system"))

    assert called == {"mode": "system"}


def test_restore_from_config_missing_attr_falls_back(monkeypatch):
    """editor.theme_mode 缺失时回退到 system。"""
    called = {}
    monkeypatch.setattr(theme_manager, "set_theme_mode", lambda m: called.__setitem__("mode", m))

    class _Empty:
        pass

    restore_from_config(_Empty())

    assert called == {"mode": "system"}
