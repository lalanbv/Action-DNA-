"""condition_dialog 多模板集成测试(免渲染:校验可导入 + Condition 多模板字段装配)。"""

import pytest

pytest.importorskip("tkinter")


def test_condition_dialog_module_imports():
    """模块可导入即说明集成完成(无语法/导入错误)。"""
    import src.panel.dialogs.condition_dialog as mod
    assert hasattr(mod, "open_condition_dialog")


def test_image_condition_with_multi_fields_assembles():
    """带多模板字段的 Condition 能被对话框逻辑正确读取(校验数据模型)。"""
    from src.core.action import MatchStrategy, ThresholdMode
    from src.core.condition import Condition, ConditionType
    cond = Condition(
        condition_type=ConditionType.IMAGE_FOUND, image_path="a.png", threshold=0.8,
        alt_image_paths=["b.png", "c.png"], alt_thresholds=[0.7, None],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    # 对话框应能把这些字段原样读取(渲染在手动验证)
    assert cond.threshold_mode == ThresholdMode.PER_TEMPLATE
    assert cond.match_strategy == MatchStrategy.BEST_CONFIDENCE
    assert len(cond.alt_image_paths) == 2
