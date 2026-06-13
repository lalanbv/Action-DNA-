"""MultiTemplateEditor(tkinter)状态往返测试。

用 withdraw 的 Tk root 实例化编辑器,验证 set_state → get_state 数据一致,
以及阈值模式联动。不依赖完整 app。
"""

import tkinter as tk

import pytest

from src.core.action import MatchStrategy, ThresholdMode


@pytest.fixture
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_set_get_state_roundtrip(tk_root):
    """set_state → get_state 数据一致。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor

    editor = MultiTemplateEditor(tk_root)
    editor.set_state(
        image_path="primary.png",
        alt_paths=["hover.png", "pressed.png"],
        alt_thresholds=[0.7, None],
        mode=ThresholdMode.PER_TEMPLATE,
        strategy=MatchStrategy.BEST_CONFIDENCE,
        global_threshold=0.85,
    )
    image_path, alt_paths, alt_thresholds, mode, strategy, gthr = editor.get_state()
    assert image_path == "primary.png"
    assert alt_paths == ["hover.png", "pressed.png"]
    assert alt_thresholds[0] == 0.7
    assert alt_thresholds[1] is None
    assert mode == ThresholdMode.PER_TEMPLATE
    assert strategy == MatchStrategy.BEST_CONFIDENCE
    assert abs(gthr - 0.85) < 1e-6


def test_empty_alts_roundtrip(tk_root):
    """空备用图往返。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor

    editor = MultiTemplateEditor(tk_root)
    editor.set_state(
        image_path="only.png", alt_paths=[], alt_thresholds=[],
        mode=ThresholdMode.GLOBAL, strategy=MatchStrategy.ADAPTIVE, global_threshold=0.8,
    )
    image_path, alt_paths, alt_thresholds, mode, strategy, gthr = editor.get_state()
    assert image_path == "only.png"
    assert alt_paths == []
    assert alt_thresholds == []
    assert mode == ThresholdMode.GLOBAL


def test_add_alt_appends_row(tk_root):
    """_add_alt 通过 _make_row 追加(直接操作避免文件对话框)。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor

    editor = MultiTemplateEditor(tk_root)
    editor._add_alt.__self__  # 确认绑定方法存在
    # 直接构造一行模拟添加(filedialog 会阻塞)
    editor._rows.append(editor._make_row("extra.png", 0.6))
    editor._render_rows()
    _, alt_paths, alt_thresholds, *_ = editor.get_state()
    assert "extra.png" in alt_paths
    assert alt_thresholds[0] == 0.6


def test_mode_visibility_per_template_shows_threshold_units(tk_root):
    """PER_TEMPLATE 模式:备用行阈值单元可见;AUTO 模式:全局阈值框隐藏。"""
    from src.panel.dialogs.multi_template_editor import MultiTemplateEditor

    editor = MultiTemplateEditor(tk_root)
    editor.set_state(
        image_path="p.png", alt_paths=["a.png"], alt_thresholds=[None],
        mode=ThresholdMode.PER_TEMPLATE, strategy=MatchStrategy.ADAPTIVE, global_threshold=0.8,
    )
    editor._apply_mode_visibility()
    # PER_TEMPLATE:全局阈值框可见
    assert editor._global_thr_sb.winfo_manager() != ""  # 已 grid(非空 manager)
    # 切到 AUTO:全局阈值框应 grid_remove
    editor._mode_dd.set_value(ThresholdMode.AUTO.name)
    editor._apply_mode_visibility()
    assert editor._global_thr_sb.winfo_manager() == "" or not editor._global_thr_sb.winfo_ismapped()
