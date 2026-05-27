"""FAIL-SAFE 机制单元测试。"""

import pytest

from src.core.fail_safe import FailSafeMonitor, FailSafeTriggered


class TestFailSafeMonitor:
    def test_corner_top_left(self):
        m = FailSafeMonitor()
        with pytest.raises(FailSafeTriggered):
            m.check(2, 3, 1920, 1080)

    def test_corner_top_right(self):
        m = FailSafeMonitor()
        with pytest.raises(FailSafeTriggered):
            m.check(1918, 2, 1920, 1080)

    def test_corner_bottom_left(self):
        m = FailSafeMonitor()
        with pytest.raises(FailSafeTriggered):
            m.check(3, 1078, 1920, 1080)

    def test_corner_bottom_right(self):
        m = FailSafeMonitor()
        with pytest.raises(FailSafeTriggered):
            m.check(1919, 1079, 1920, 1080)

    def test_center_no_trigger(self):
        m = FailSafeMonitor()
        m.check(960, 540, 1920, 1080)  # 不应抛出

    def test_edge_no_trigger(self):
        m = FailSafeMonitor()
        m.check(10, 0, 1920, 1080)  # 边上但不在角落 5px 内

    def test_disabled(self):
        m = FailSafeMonitor(enabled=False)
        m.check(0, 0, 1920, 1080)  # 禁用后不触发

    def test_just_outside_corner(self):
        m = FailSafeMonitor()
        m.check(6, 6, 1920, 1080)  # 刚好在 5px 之外

    def test_custom_screen_size(self):
        m = FailSafeMonitor()
        with pytest.raises(FailSafeTriggered):
            m.check(2, 2, 100, 100)
