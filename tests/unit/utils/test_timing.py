"""timing 工具测试 — format_duration_human 智能时长格式化。"""

from __future__ import annotations

import pytest

from src.utils import i18n
from src.utils.timing import format_duration_human


@pytest.fixture(autouse=True)
def _zh():
    """锁定中文,避免受其它测试语言切换影响。"""
    i18n.set_language("zh")


class TestFormatDurationHuman:
    def test_seconds(self) -> None:
        assert format_duration_human(45) == "45秒"

    def test_zero(self) -> None:
        assert format_duration_human(0) == "0秒"

    def test_negative_clamps_to_zero(self) -> None:
        assert format_duration_human(-5) == "0秒"

    def test_minutes_seconds(self) -> None:
        assert format_duration_human(134) == "2分14秒"

    def test_exact_minute(self) -> None:
        assert format_duration_human(60) == "1分0秒"

    def test_hours_minutes(self) -> None:
        # 3900s = 1h5m
        assert format_duration_human(3900) == "1小时5分"

    def test_days_hours(self) -> None:
        # 97200s = 1d3h
        assert format_duration_human(97200) == "1天3小时"
