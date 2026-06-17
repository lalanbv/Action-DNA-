"""themed_frame 父背景继承回归测试。

根因回归: ``src/panel/widgets.py`` 的 ``themed_frame`` 曾硬编码 ``bg=page_bg``,
而 ``apply_theme_recursive`` 对原生 ``Frame`` 控件也强制刷成 ``page_bg``
(仅对 ``Label`` 做了父背景继承特判)。两层缺陷叠加,导致放置于
``themed_labelframe``(card_bg) 内的 ``themed_frame`` 容器行始终显示
``page_bg``——深色主题下 page_bg=#1e1e1e(接近黑)嵌在 card_bg=#2d2d2d(较亮)
的卡片里,表现为一块突兀的「黑色底」色块。

典型受影响场景: 设置页「外观设置」下 3 个单选按钮的容器行、
「界面样式」单选按钮容器行、热键区域的 tree_frame/btn_frame 等。

本测试断言:
1. themed_frame 在 themed_labelframe 内应继承父控件 card_bg,而非 page_bg。
2. apply_theme_recursive 后,LabelFrame 内 Frame 应保持继承父背景。
3. light↔dark 切换后,该 Frame 背景跟随 labelframe 同步更新。
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


def test_themed_frame_inherits_labelframe_bg(tk_root):
    """themed_frame 在 themed_labelframe(card_bg) 内应继承 card_bg,而非默认 page_bg(黑)。

    修复前: themed_frame 硬编码 bg=page_bg → 容器行在深色卡片内出现黑色色块。
    """
    from src.panel.canvas.theme import current_theme, set_theme_mode
    from src.panel.widgets import themed_frame, themed_labelframe

    set_theme_mode("dark")
    try:
        th = current_theme()
        # 前置断言: 深色主题下 page_bg(黑) 与 card_bg(较亮) 必须不同,否则测试无意义
        assert th.page_bg != th.card_bg

        section = themed_labelframe(tk_root, text="appearance")
        section.pack()
        radio_frame = themed_frame(section)
        radio_frame.pack()
        tk_root.update_idletasks()

        assert str(radio_frame.cget("bg")) == th.card_bg, (
            "themed_frame 应继承 LabelFrame 的 card_bg,而非硬编码 page_bg(黑色底)"
        )
    finally:
        set_theme_mode("system")


def test_frame_keeps_parent_bg_after_recursive_refresh(tk_root):
    """主题递归刷新后,LabelFrame 内 Frame 必须保持继承父背景,不被强制刷成 page_bg。

    修复前: apply_theme_recursive 对 Frame 强制 bg=page_bg(仅 Label 做了父背景继承),
    导致 light↔dark 切换后单选按钮容器行又被刷黑。
    """
    from src.panel.canvas.theme import current_theme, set_theme_mode
    from src.panel.widgets import (
        apply_theme_recursive, themed_frame, themed_labelframe,
    )

    set_theme_mode("dark")
    try:
        th = current_theme()
        section = themed_labelframe(tk_root, text="appearance")
        section.pack()
        radio_frame = themed_frame(section)
        radio_frame.pack()
        tk_root.update_idletasks()

        apply_theme_recursive(section, th)

        assert str(radio_frame.cget("bg")) == th.card_bg, (
            "递归刷新后 Frame 应保持 card_bg,而非被刷成 page_bg"
        )
    finally:
        set_theme_mode("system")


def test_frame_follows_labelframe_bg_on_theme_switch(tk_root):
    """light → dark 切换后,LabelFrame 内 Frame 背景必须跟随 labelframe 同步变化。

    端到端验证: 单选按钮容器行在主题切换后不再残留前一主题的黑色底。
    """
    from src.panel.canvas.theme import current_theme, set_theme_mode
    from src.panel.widgets import (
        apply_theme_recursive, themed_frame, themed_labelframe,
    )

    set_theme_mode("light")
    try:
        section = themed_labelframe(tk_root, text="appearance")
        section.pack()
        radio_frame = themed_frame(section)
        radio_frame.pack()
        tk_root.update_idletasks()

        apply_theme_recursive(section, current_theme())
        light_bg = str(radio_frame.cget("bg"))
        assert light_bg == current_theme().card_bg

        set_theme_mode("dark")
        apply_theme_recursive(section, current_theme())
        dark_bg = str(radio_frame.cget("bg"))

        assert light_bg != dark_bg, "Frame 未随主题切换更新背景(残留黑色底)"
        assert dark_bg == current_theme().card_bg, "切换后应等于深色 card_bg"
    finally:
        set_theme_mode("system")
