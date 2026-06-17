"""原生 Listbox/Text 主题刷新回归测试。

根因回归: ``src/panel/widgets.py`` 的 ``_WIDGET_THEME_MAP`` 曾遗漏
``Listbox`` / ``Text`` 控件类,导致 ``apply_theme_recursive`` 在主题切换时
跳过它们 —— 这些原生内容控件保留 tkinter 系统默认浅色背景,表现为
深色模式下出现刺眼的白色色块(典型: 插件详情 Text、条件对话框 Listbox、
按键选择器 Listbox 等)。

本测试断言: 深色主题下,经 ``apply_theme_recursive`` 后,Listbox/Text
的背景/前景/选区色应等于主题令牌,而非系统默认值。
"""

from __future__ import annotations

import pytest

# tkinter 在 Tk9 + Py3.14 下多 root 易崩溃,本文件仅用单个 withdraw root。
tk = pytest.importorskip("tkinter")


@pytest.fixture
def tk_root():
    """withdraw 的 Tk root,与既有 panel 测试同形态。"""
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_listbox_refreshed_to_theme(tk_root):
    """Listbox 经 apply_theme_recursive 后背景应等于 theme.bg_surface。

    修复前: Listbox 不在 _WIDGET_THEME_MAP → 跳过 → bg 保持系统默认 → 断言失败。
    """
    from src.panel.canvas.theme import current_theme, set_theme_mode
    from src.panel.widgets import apply_theme_recursive

    set_theme_mode("dark")
    try:
        th = current_theme()
        lb = tk.Listbox(tk_root)  # 创建即为系统默认(浅)色
        apply_theme_recursive(lb, th)
        # 背景须跟随深色主题令牌,而非 tkinter 默认 SystemButtonFace/白
        assert str(lb.cget("bg")) == th.bg_surface
        assert str(lb.cget("fg")) == th.text_primary
        assert str(lb.cget("selectbackground")) == th.accent_blue
    finally:
        set_theme_mode("system")


def test_text_refreshed_to_theme(tk_root):
    """Text 经 apply_theme_recursive 后应采用 input_bg/input_fg + 深色光标。"""
    from src.panel.canvas.theme import current_theme, set_theme_mode
    from src.panel.widgets import apply_theme_recursive

    set_theme_mode("dark")
    try:
        th = current_theme()
        txt = tk.Text(tk_root)  # 默认白色背景
        apply_theme_recursive(txt, th)
        assert str(txt.cget("bg")) == th.input_bg
        assert str(txt.cget("fg")) == th.input_fg
        # 光标颜色随主题,避免深色背景上看不见浅色光标
        assert str(txt.cget("insertbackground")) == th.text_primary
    finally:
        set_theme_mode("system")


def test_theme_switch_updates_listbox(tk_root):
    """切换 light → dark 后,Listbox 背景必须随之改变(端到端刷新链路)。"""
    from src.panel.canvas.theme import current_theme, set_theme_mode
    from src.panel.widgets import apply_theme_recursive

    set_theme_mode("light")
    try:
        lb = tk.Listbox(tk_root)
        apply_theme_recursive(lb, current_theme())
        light_bg = str(lb.cget("bg"))

        set_theme_mode("dark")
        apply_theme_recursive(lb, current_theme())
        dark_bg = str(lb.cget("bg"))

        assert light_bg != dark_bg, "Listbox 未随主题切换更新背景"
        assert dark_bg == current_theme().bg_surface
    finally:
        set_theme_mode("system")
