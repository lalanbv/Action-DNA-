"""MultiTemplateEditor.show_match_settings 参数测试(tk,免渲染:校验可构造 + API)。"""

import pytest

pytest.importorskip("tkinter")


def _make_root():
    """构造隐藏的 Tk root(测试用)。"""
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    return root


def test_editor_accepts_show_match_settings_false():
    """show_match_settings=False → 不渲染模式/策略控件。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
    root = _make_root()
    try:
        editor = MultiTemplateEditor(root, show_match_settings=False)
        # 控制区不渲染 → mode/strategy 控件为 None
        assert getattr(editor, "_mode_dd", None) is None
        assert getattr(editor, "_strategy_dd", None) is None
    finally:
        root.destroy()


def test_editor_default_show_match_settings_true():
    """默认 show_match_settings=True → 渲染控件(向后兼容 ClickImage)。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
    root = _make_root()
    try:
        editor = MultiTemplateEditor(root)
        assert getattr(editor, "_mode_dd", None) is not None
        assert getattr(editor, "_strategy_dd", None) is not None
    finally:
        root.destroy()


def test_editor_hidden_settings_get_state_returns_valid():
    """show_match_settings=False:get_state 仍返回合法 mode/strategy(默认值)。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor
    from src.core.action import MatchStrategy, ThresholdMode
    root = _make_root()
    try:
        editor = MultiTemplateEditor(root, show_match_settings=False)
        editor.set_state("a.png", ["b.png"], [0.7], ThresholdMode.GLOBAL, MatchStrategy.ADAPTIVE, 0.8)
        img, alts, thr, mode, strategy, gthr = editor.get_state()
        assert img == "a.png"
        assert alts == ["b.png"]
        assert mode == ThresholdMode.GLOBAL
        assert strategy == MatchStrategy.ADAPTIVE
    finally:
        root.destroy()
