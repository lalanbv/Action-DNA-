"""Qt 版多模板管理器测试(需 PySide6;未安装时整体 SKIP)。

本项目 venv 当前未装 PySide6,故本测试在此环境 SKIP。
在安装 PySide6 的环境运行可验证:导入、set_state/get_state 往返、模式联动。
"""

import pytest

pyside6 = pytest.importorskip("PySide6")  # 未装则 SKIP 整个模块


def test_qt_editor_importable():
    from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
    assert MultiTemplateEditorQt is not None


def test_qt_editor_state_roundtrip():
    """set_state → get_state 数据一致(用 QCoreApplication 不显示窗口)。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
    from src.core.action import MatchStrategy, ThresholdMode

    editor = MultiTemplateEditorQt(parent=None)
    editor.set_state(
        image_path="a.png",
        alt_paths=["b.png", "c.png"],
        alt_thresholds=[0.7, None],
        mode=ThresholdMode.PER_TEMPLATE,
        strategy=MatchStrategy.BEST_CONFIDENCE,
        global_threshold=0.8,
    )
    image_path, alt_paths, alt_thresholds, mode, strategy, gthr = editor.get_state()
    assert image_path == "a.png"
    assert alt_paths == ["b.png", "c.png"]
    assert alt_thresholds[0] == 0.7
    assert alt_thresholds[1] is None
    assert mode == ThresholdMode.PER_TEMPLATE
    assert strategy == MatchStrategy.BEST_CONFIDENCE


def test_qt_editor_strategy_first_match_roundtrip():
    """strategy=FIRST_MATCH 也能正确 roundtrip（覆盖非默认值，防 _on_mode_changed 污染）。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
    from src.core.action import MatchStrategy, ThresholdMode

    editor = MultiTemplateEditorQt(parent=None)
    editor.set_state(
        "a.png", [], [],
        ThresholdMode.PER_TEMPLATE, MatchStrategy.FIRST_MATCH, 0.8,
    )
    _, _, _, _, strategy, _ = editor.get_state()
    assert strategy == MatchStrategy.FIRST_MATCH


def test_qt_editor_strategy_persists_after_mode_change():
    """set_state 后手动改 mode combo，strategy 仍取自 strategy combo（非污染）。"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
    from src.core.action import MatchStrategy, ThresholdMode

    editor = MultiTemplateEditorQt(parent=None)
    editor.set_state(
        "a.png", [], [],
        ThresholdMode.PER_TEMPLATE, MatchStrategy.BEST_CONFIDENCE, 0.8,
    )
    # 用户改 mode combo（应只影响 mode，strategy 来自 strategy combo）
    editor._mode_cb.setCurrentIndex(editor._mode_cb.findData(ThresholdMode.AUTO))
    _, _, _, _, strategy, _ = editor.get_state()
    assert strategy == MatchStrategy.BEST_CONFIDENCE
