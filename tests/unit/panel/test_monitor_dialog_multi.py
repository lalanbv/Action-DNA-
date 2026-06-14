"""monitor_dialog 多模板集成测试(免渲染:校验可导入 + MonitorConfig 多模板字段)。"""

import pytest

pytest.importorskip("tkinter")


def test_monitor_dialog_module_imports():
    """模块可导入即说明集成完成(无语法/导入错误)。"""
    import src.panel.dialogs.monitor_dialog as mod
    assert hasattr(mod, "open_monitor_dialog")


def test_monitor_config_multi_fields_visible():
    """MonitorConfig 多模板字段可正确构造(触发图 + 处理图备用)。"""
    from src.core.action import MatchStrategy, ThresholdMode
    from src.core.monitor import MonitorConfig
    m = MonitorConfig(
        name="m", image_path="t.png", handler_image_path="h.png",
        alt_image_paths=["t2.png"], alt_handler_image_paths=["h2.png"],
        match_strategy=MatchStrategy.BEST_CONFIDENCE, threshold_mode=ThresholdMode.PER_TEMPLATE,
    )
    assert m.alt_image_paths == ["t2.png"]
    assert m.alt_handler_image_paths == ["h2.png"]
