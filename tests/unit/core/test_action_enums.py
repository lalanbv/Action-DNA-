"""MatchStrategy / ThresholdMode 枚举测试。"""

from src.core.action import MatchStrategy, ThresholdMode


def test_match_strategy_members():
    """MatchStrategy 三个成员,值为大写枚举名。"""
    assert MatchStrategy.ADAPTIVE.value == "ADAPTIVE"
    assert MatchStrategy.FIRST_MATCH.value == "FIRST_MATCH"
    assert MatchStrategy.BEST_CONFIDENCE.value == "BEST_CONFIDENCE"


def test_threshold_mode_members():
    """ThresholdMode 三个成员,值为大写枚举名。"""
    assert ThresholdMode.AUTO.value == "AUTO"
    assert ThresholdMode.GLOBAL.value == "GLOBAL"
    assert ThresholdMode.PER_TEMPLATE.value == "PER_TEMPLATE"


def test_enums_are_hashable_and_comparable():
    """枚举可哈希、可比较(用于 set/dict 与 dataclass 默认值)。"""
    assert MatchStrategy.ADAPTIVE != MatchStrategy.FIRST_MATCH
    assert ThresholdMode.AUTO in {ThresholdMode.AUTO, ThresholdMode.GLOBAL}
