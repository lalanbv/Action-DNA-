"""ClickImageDialog 多模板集成测试:populate → get_result 往返。

用 withdraw 的 Tk root 实例化真实对话框,验证多模板字段经编辑器正确进出。
"""

import tkinter as tk

import pytest

from src.core.action import MatchStrategy, ThresholdMode
from src.core.step_types import ClickImageStep


@pytest.fixture
def tk_root():
    root = tk.Tk()
    root.withdraw()
    yield root
    root.destroy()


def test_dialog_roundtrip_multi_template_fields(tk_root):
    """带多模板字段的 step 经对话框往返后字段一致。"""
    from src.panel.dialogs.click_image_dialog import ClickImageDialog

    original = ClickImageStep(
        image_path="primary.png",
        alt_image_paths=["hover.png", "pressed.png"],
        alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE,
        threshold_mode=ThresholdMode.PER_TEMPLATE,
        threshold=0.85,
    )
    dlg = ClickImageDialog(tk_root, "test", action=original)
    result = dlg._get_result()
    assert result.image_path == "primary.png"
    assert result.alt_image_paths == ["hover.png", "pressed.png"]
    assert result.alt_thresholds[0] == 0.7
    assert result.alt_thresholds[1] is None
    assert result.match_strategy == MatchStrategy.BEST_CONFIDENCE
    assert result.threshold_mode == ThresholdMode.PER_TEMPLATE
    assert abs(result.threshold - 0.85) < 1e-6
    dlg.destroy()


def test_dialog_roundtrip_defaults_for_new_step(tk_root):
    """新建步骤(默认 ClickImageStep)经对话框往返后,多模板字段为默认值。"""
    from src.panel.dialogs.click_image_dialog import ClickImageDialog

    # app 打开"新建"对话框时总传一个默认 step(base_dialog 仅在 action 真值时 populate)
    dlg = ClickImageDialog(tk_root, "test", action=ClickImageStep())
    result = dlg._get_result()
    assert isinstance(result, ClickImageStep)
    assert result.alt_image_paths == []
    assert result.alt_thresholds == []
    assert result.match_strategy == MatchStrategy.ADAPTIVE
    assert result.threshold_mode in {ThresholdMode.GLOBAL, ThresholdMode.AUTO}
    dlg.destroy()
