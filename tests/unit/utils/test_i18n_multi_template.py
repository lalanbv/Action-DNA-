"""多模板相关 i18n key 双语齐备测试。"""

from src.utils.i18n import t


REQUIRED_KEYS = [
    "dialog.multi_template.primary",
    "dialog.multi_template.alt",
    "dialog.multi_template.add",
    "dialog.multi_template.hint_order",
    "dialog.multi_template.delete",
    "dialog.multi_template.move_up",
    "dialog.multi_template.move_down",
    "dialog.multi_template.custom_threshold",
    "dialog.multi_template.inherit",
    "dialog.multi_template.no_preview",
    "dialog.threshold_mode.auto",
    "dialog.threshold_mode.global",
    "dialog.threshold_mode.per_template",
    "dialog.match_strategy.adaptive",
    "dialog.match_strategy.first_match",
    "dialog.match_strategy.best_confidence",
    "dialog.label.global_threshold",
    "dialog.label.match_strategy",
    "dialog.label.threshold_mode",
]


def test_all_keys_resolve_nonempty():
    """所有多模板 i18n key 在当前语言下都有非空翻译(未 fallback 到 key 自身)。"""
    for key in REQUIRED_KEYS:
        val = t(key)
        assert val, f"i18n key 缺失或为空: {key}"
        assert val != key, f"i18n key 未翻译(fallback 到 key 自身): {key}"


def test_alt_key_supports_placeholder():
    """alt key 支持 {n} 占位。"""
    val = t("dialog.multi_template.alt", n=2)
    assert "2" in val
