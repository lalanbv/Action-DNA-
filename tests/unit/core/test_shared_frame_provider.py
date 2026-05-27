"""SharedFrameProvider 单元测试。"""

import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from src.core.shared_frame_provider import SharedFrameProvider


@pytest.fixture
def mock_capture():
    capture = MagicMock()
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    capture.grab_reuse.return_value = frame.copy()
    capture.grab.return_value = frame.copy()
    return capture


@pytest.fixture
def provider(mock_capture):
    return SharedFrameProvider(mock_capture, cache_ttl=0.05)


class TestGetFrame:
    def test_returns_ndarray(self, provider):
        result = provider.get_frame()
        assert isinstance(result, np.ndarray)

    def test_calls_grab_reuse_on_first_request(self, provider, mock_capture):
        provider.get_frame()
        assert mock_capture.grab_reuse.call_count == 1

    def test_uses_cache_within_ttl(self, provider, mock_capture):
        provider.get_frame()
        provider.get_frame()
        assert mock_capture.grab_reuse.call_count == 1

    def test_regrabs_after_ttl_expires(self, provider, mock_capture):
        provider.get_frame()
        time.sleep(0.06)
        provider.get_frame()
        assert mock_capture.grab_reuse.call_count == 2

    def test_returns_copy_within_ttl(self, provider):
        a = provider.get_frame()
        b = provider.get_frame()
        assert a is not b
        np.testing.assert_array_equal(a, b)


class TestGetFrameReuse:
    def test_returns_same_reference_within_ttl(self, provider, mock_capture):
        mock_capture.grab_reuse.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        a = provider.get_frame_reuse()
        b = provider.get_frame_reuse()
        assert a is b

    def test_calls_grab_reuse(self, provider, mock_capture):
        mock_capture.grab_reuse.return_value = np.zeros((100, 200, 3), dtype=np.uint8)
        provider.get_frame_reuse()
        mock_capture.grab_reuse.assert_called_once()


class TestInvalidate:
    def test_invalidate_forces_regrab(self, provider, mock_capture):
        provider.get_frame()
        provider.invalidate()
        provider.get_frame()
        assert mock_capture.grab_reuse.call_count == 2


class TestCacheAge:
    def test_infinite_when_no_cache(self, mock_capture):
        p = SharedFrameProvider(mock_capture, cache_ttl=1.0)
        assert p.cache_age == float("inf")

    def test_age_increases_over_time(self, provider):
        provider.get_frame()
        age1 = provider.cache_age
        time.sleep(0.02)
        age2 = provider.cache_age
        assert age2 > age1
