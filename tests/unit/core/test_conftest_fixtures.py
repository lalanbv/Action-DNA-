"""conftest.py 共享 fixture 验证测试。

确保每个 fixture 返回正确的类型和默认行为。
"""

import numpy as np
import pytest
from unittest.mock import MagicMock

from src.core.action import ActionType
from src.core.variables.pool import VariablePool
from _helpers import ActionChain


class TestPoolFixture:
    """pool fixture 验证。"""

    def test_pool_is_fresh_instance(self, pool):
        assert isinstance(pool, VariablePool)

    def test_pool_get_undeclared_raises(self, pool):
        with pytest.raises(KeyError):
            pool.get("nonexistent")


class TestMockCaptureFixture:
    """mock_capture fixture 验证。"""

    def test_returns_ndarray(self, mock_capture):
        result = mock_capture.grab()
        assert isinstance(result, np.ndarray)

    def test_grab_shape(self, mock_capture):
        result = mock_capture.grab()
        assert result.shape == (120, 160, 3)

    def test_grab_reuse_shape(self, mock_capture):
        result = mock_capture.grab_reuse()
        assert result.shape == (120, 160, 3)

    def test_is_mock(self, mock_capture):
        assert isinstance(mock_capture, MagicMock)

    def test_to_logical_identity(self, mock_capture):
        assert mock_capture.to_logical(100, 200) == (100, 200)

    def test_get_screen_size(self, mock_capture):
        assert mock_capture.get_screen_size() == (1920, 1080)

    def test_is_screen_black_default_false(self, mock_capture):
        assert mock_capture.is_screen_black() is False

    def test_scale_factor(self, mock_capture):
        assert mock_capture.scale_factor == 1.0


class TestMockMatcherFixture:
    """mock_matcher fixture 验证。"""

    def test_default_find_returns_none(self, mock_matcher):
        result = mock_matcher.find(np.zeros((100, 100, 3), dtype=np.uint8), "test.png")
        assert result is None

    def test_is_mock(self, mock_matcher):
        assert isinstance(mock_matcher, MagicMock)

    def test_side_effect_override(self, mock_matcher):
        mock_matcher.find.return_value = (50, 100, 200, 150)
        result = mock_matcher.find(np.zeros((100, 100, 3), dtype=np.uint8), "test.png")
        assert result == (50, 100, 200, 150)

    def test_find_all_default_empty(self, mock_matcher):
        assert mock_matcher.find_all(np.zeros((100, 100, 3), dtype=np.uint8), "t.png") == []


class TestMockInputFixture:
    """mock_input fixture 验证。"""

    def test_is_mock(self, mock_input):
        assert isinstance(mock_input, MagicMock)

    def test_click_records_call(self, mock_input):
        mock_input.click(100, 200)
        mock_input.click.assert_called_once_with(100, 200)

    def test_press_key_records_call(self, mock_input):
        mock_input.press_key("a")
        mock_input.press_key.assert_called_once_with("a")

    def test_move_to_returns_tuple(self, mock_input):
        result = mock_input.move_to(347, 519)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_wait_interruptible_returns_false(self, mock_input):
        assert mock_input.wait_interruptible(1.0, lambda: False) is False

    def test_key_hold_interruptible_returns_false(self, mock_input):
        assert mock_input.key_hold_interruptible("a", 1.0) is False


class TestSampleChainFixture:
    """sample_chain fixture 验证。"""

    def test_is_action_chain(self, sample_chain):
        assert isinstance(sample_chain, ActionChain)

    def test_has_two_steps(self, sample_chain):
        assert len(sample_chain.steps) == 2

    def test_first_step_is_wait(self, sample_chain):
        assert sample_chain.steps[0].action_type == ActionType.WAIT

    def test_second_step_is_click_pos(self, sample_chain):
        assert sample_chain.steps[1].action_type == ActionType.CLICK_POS

    def test_no_loop(self, sample_chain):
        assert sample_chain.loop is False


class TestSampleChainWithImageFixture:
    """sample_chain_with_image fixture 验证。"""

    def test_is_action_chain(self, sample_chain_with_image):
        assert isinstance(sample_chain_with_image, ActionChain)

    def test_has_one_step(self, sample_chain_with_image):
        assert len(sample_chain_with_image.steps) == 1

    def test_step_is_click_image(self, sample_chain_with_image):
        assert sample_chain_with_image.steps[0].action_type == ActionType.CLICK_IMAGE

    def test_image_path_set(self, sample_chain_with_image):
        assert sample_chain_with_image.steps[0].image_path == "test_template.png"

    def test_threshold_set(self, sample_chain_with_image):
        assert sample_chain_with_image.steps[0].threshold == 0.8
