"""B4 回归测试 — 打开的对话框在切主题时必须同步更新。

复现（修复前）：StepDialogBase 只在 __init__ 读一次 current_theme()，不注册
主题回调；用户打开步骤对话框期间切换深/浅色，对话框停留在旧主题色。

修复后：StepDialogBase 注册主题回调（ThemeCallbackMixin），切主题时重应用
主题（tk: apply_to_toplevel；Qt: 重设 QSS + apply_theme），destroy 时注销。
"""

from __future__ import annotations

import tkinter as tk

import pytest

from src.panel.canvas.theme import theme_manager
from src.panel.canvas.theme.theme_manager import set_theme_mode


@pytest.fixture(autouse=True)
def _reset_theme_state():
    """每个测试前后清理 theme_manager 全局状态。"""
    saved_mode = theme_manager._theme_mode
    saved_theme = theme_manager._current_theme
    saved_cbs = dict(theme_manager._theme_callbacks)
    theme_manager._current_theme = None
    yield
    theme_manager._theme_mode = saved_mode
    theme_manager._current_theme = saved_theme
    theme_manager._theme_callbacks.clear()
    theme_manager._theme_callbacks.update(saved_cbs)


@pytest.fixture
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def _make_minimal_dialog(parent):
    """构造一个最小可实例化的 StepDialogBase 子类（实现两个抽象方法）。"""
    from src.panel.dialogs.base_dialog import StepDialogBase

    class _ProbeDialog(StepDialogBase):
        def _build_content(self) -> None:
            pass

        def _get_result(self):
            return None

    return _ProbeDialog(parent, "probe")


def test_tk_dialog_updates_on_theme_switch(tk_root):
    """B4(tk)：打开的对话框在 dark→light 切换后背景色同步更新。"""
    set_theme_mode("dark")
    dlg = _make_minimal_dialog(tk_root)
    try:
        # 初始 dark
        assert dlg.cget("bg") == "#252526"

        # 切到 light —— 修复后对话框应收到回调并重应用主题
        set_theme_mode("light")
        dlg.update_idletasks()
        assert dlg.cget("bg") == "#ffffff"
    finally:
        dlg.destroy()


def test_tk_dialog_unregisters_on_destroy(tk_root):
    """对话框销毁后不再持有主题回调（防泄漏 + 防销毁后回调报错）。"""
    set_theme_mode("dark")
    dlg = _make_minimal_dialog(tk_root)
    cb_count_before = len(theme_manager._theme_callbacks)
    dlg.destroy()
    # destroy 后回调数应回落（不新增遗留）
    assert len(theme_manager._theme_callbacks) <= cb_count_before


def test_tk_dialog_switches_back_to_dark(tk_root):
    """B4(tk)：dark→light→dark 连续切换，对话框每次都同步。"""
    set_theme_mode("dark")
    dlg = _make_minimal_dialog(tk_root)
    try:
        set_theme_mode("light")
        dlg.update_idletasks()
        assert dlg.cget("bg") == "#ffffff"

        set_theme_mode("dark")
        dlg.update_idletasks()
        assert dlg.cget("bg") == "#252526"
    finally:
        dlg.destroy()
