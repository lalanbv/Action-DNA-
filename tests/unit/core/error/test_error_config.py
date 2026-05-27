"""ErrorConfig + RetryPolicy + ErrorStrategy 单元测试。"""

from __future__ import annotations

import pytest

from src.core.error.error_config import ErrorConfig, ErrorStrategy, RetryPolicy


# ---- ErrorStrategy ----


class TestErrorStrategy:
    """枚举成员和属性。"""

    def test_five_members(self) -> None:
        assert len(ErrorStrategy) == 5

    def test_values(self) -> None:
        assert ErrorStrategy.FAIL_FAST.value == "fail_fast"
        assert ErrorStrategy.RETRY.value == "retry"
        assert ErrorStrategy.SKIP.value == "skip"
        assert ErrorStrategy.FALLBACK.value == "fallback"
        assert ErrorStrategy.IGNORE.value == "ignore"

    def test_description_returns_string(self) -> None:
        for s in ErrorStrategy:
            assert isinstance(s.description, str)
            assert len(s.description) > 0

    def test_severity_ordering(self) -> None:
        assert ErrorStrategy.IGNORE.severity < ErrorStrategy.SKIP.severity
        assert ErrorStrategy.SKIP.severity < ErrorStrategy.RETRY.severity
        assert ErrorStrategy.RETRY.severity < ErrorStrategy.FALLBACK.severity
        assert ErrorStrategy.FALLBACK.severity < ErrorStrategy.FAIL_FAST.severity


# ---- RetryPolicy ----


class TestRetryPolicy:
    """重试策略：默认值、退避计算、可重试判断、序列化、工厂方法。"""

    def test_defaults(self) -> None:
        p = RetryPolicy()
        assert p.max_retries == 3
        assert p.base_delay == 1.0
        assert p.max_delay == 30.0
        assert p.jitter_factor == 0.5
        assert RuntimeError in p.retryable_exceptions

    def test_frozen(self) -> None:
        p = RetryPolicy()
        with pytest.raises(AttributeError):
            p.max_retries = 99  # type: ignore[misc]

    def test_calculate_delay_increases(self) -> None:
        p = RetryPolicy(base_delay=1.0, max_delay=60.0, jitter_factor=0)
        delays = [p.calculate_delay(i) for i in range(5)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]

    def test_calculate_delay_capped(self) -> None:
        p = RetryPolicy(base_delay=1.0, max_delay=5.0, jitter_factor=0)
        assert p.calculate_delay(10) == 5.0

    def test_calculate_delay_with_jitter(self) -> None:
        p = RetryPolicy(base_delay=1.0, max_delay=30.0, jitter_factor=0.5)
        delay = p.calculate_delay(0)
        assert 1.0 <= delay <= 1.5

    def test_is_retryable_true(self) -> None:
        p = RetryPolicy()
        assert p.is_retryable(RuntimeError("x")) is True
        assert p.is_retryable(TimeoutError("x")) is True
        assert p.is_retryable(ConnectionError("x")) is True
        assert p.is_retryable(OSError("x")) is True

    def test_is_retryable_false(self) -> None:
        p = RetryPolicy()
        assert p.is_retryable(ValueError("x")) is False
        assert p.is_retryable(TypeError("x")) is False

    def test_is_retryable_custom_exceptions(self) -> None:
        p = RetryPolicy(retryable_exceptions=(ValueError,))
        assert p.is_retryable(ValueError("x")) is True
        assert p.is_retryable(RuntimeError("x")) is False

    def test_get_schedule_length(self) -> None:
        p = RetryPolicy(max_retries=4)
        schedule = p.get_schedule()
        assert len(schedule) == 4

    def test_to_dict_roundtrip(self) -> None:
        p = RetryPolicy(max_retries=5, base_delay=2.0, max_delay=60.0, jitter_factor=0.3)
        d = p.to_dict()
        assert d["max_retries"] == 5
        assert d["base_delay"] == 2.0
        assert d["max_delay"] == 60.0
        assert d["jitter_factor"] == 0.3
        assert "RuntimeError" in d["retryable_exceptions"]

    def test_from_dict_roundtrip(self) -> None:
        original = RetryPolicy(max_retries=7, base_delay=0.5)
        restored = RetryPolicy.from_dict(original.to_dict())
        assert restored.max_retries == 7
        assert restored.base_delay == 0.5

    def test_from_dict_defaults(self) -> None:
        restored = RetryPolicy.from_dict({})
        assert restored.max_retries == 3
        assert restored.base_delay == 1.0

    def test_from_dict_resolves_exception_names(self) -> None:
        d = {"retryable_exceptions": ["ValueError", "TypeError"]}
        p = RetryPolicy.from_dict(d)
        assert ValueError in p.retryable_exceptions
        assert TypeError in p.retryable_exceptions

    def test_from_dict_ignores_unknown_exception_names(self) -> None:
        d = {"retryable_exceptions": ["ValueError", "NotARealException"]}
        p = RetryPolicy.from_dict(d)
        assert ValueError in p.retryable_exceptions

    def test_fast_factory(self) -> None:
        p = RetryPolicy.fast()
        assert p.base_delay == 0.5
        assert p.max_delay == 5.0
        assert p.jitter_factor == 0.2

    def test_gentle_factory(self) -> None:
        p = RetryPolicy.gentle()
        assert p.base_delay == 3.0
        assert p.max_delay == 60.0
        assert p.jitter_factor == 1.0

    def test_aggressive_factory(self) -> None:
        p = RetryPolicy.aggressive()
        assert p.base_delay == 0.2
        assert p.max_delay == 10.0
        assert p.jitter_factor == 0.1


# ---- ErrorConfig ----


class TestErrorConfig:
    """错误配置：默认值、工厂方法、不可变、序列化。"""

    def test_defaults(self) -> None:
        c = ErrorConfig()
        assert c.strategy == ErrorStrategy.IGNORE
        assert c.retry_policy is None
        assert c.exhausted_strategy is None
        assert c.fallback_label == "fallback"
        assert c.error_message is None

    def test_frozen(self) -> None:
        c = ErrorConfig()
        with pytest.raises(AttributeError):
            c.strategy = ErrorStrategy.FAIL_FAST  # type: ignore[misc]

    def test_fail_fast_factory(self) -> None:
        c = ErrorConfig.fail_fast("boom")
        assert c.strategy == ErrorStrategy.FAIL_FAST
        assert c.error_message == "boom"

    def test_fail_fast_factory_no_message(self) -> None:
        c = ErrorConfig.fail_fast()
        assert c.error_message is None

    def test_retry_factory(self) -> None:
        c = ErrorConfig.retry(max_retries=5, base_delay=2.0)
        assert c.strategy == ErrorStrategy.RETRY
        assert c.retry_policy is not None
        assert c.retry_policy.max_retries == 5
        assert c.retry_policy.base_delay == 2.0

    def test_retry_factory_with_exhausted(self) -> None:
        c = ErrorConfig.retry(exhausted_strategy=ErrorStrategy.SKIP)
        assert c.exhausted_strategy == ErrorStrategy.SKIP

    def test_skip_factory(self) -> None:
        c = ErrorConfig.skip()
        assert c.strategy == ErrorStrategy.SKIP

    def test_fallback_factory(self) -> None:
        c = ErrorConfig.fallback(label="alt")
        assert c.strategy == ErrorStrategy.FALLBACK
        assert c.fallback_label == "alt"

    def test_fallback_factory_default_label(self) -> None:
        c = ErrorConfig.fallback()
        assert c.fallback_label == "fallback"

    def test_ignore_factory(self) -> None:
        c = ErrorConfig.ignore()
        assert c.strategy == ErrorStrategy.IGNORE

    def test_to_dict_basic(self) -> None:
        c = ErrorConfig(strategy=ErrorStrategy.SKIP)
        d = c.to_dict()
        assert d == {"strategy": "skip"}

    def test_to_dict_with_retry(self) -> None:
        c = ErrorConfig.retry(max_retries=3)
        d = c.to_dict()
        assert d["strategy"] == "retry"
        assert "retry_policy" in d
        assert d["retry_policy"]["max_retries"] == 3

    def test_to_dict_with_exhausted(self) -> None:
        c = ErrorConfig(strategy=ErrorStrategy.RETRY, exhausted_strategy=ErrorStrategy.SKIP)
        d = c.to_dict()
        assert d["exhausted_strategy"] == "skip"

    def test_to_dict_with_fallback(self) -> None:
        c = ErrorConfig.fallback(label="custom")
        d = c.to_dict()
        assert d["fallback_label"] == "custom"

    def test_to_dict_with_error_message(self) -> None:
        c = ErrorConfig.fail_fast("oops")
        d = c.to_dict()
        assert d["error_message"] == "oops"

    def test_from_dict_basic(self) -> None:
        c = ErrorConfig.from_dict({"strategy": "fail_fast"})
        assert c is not None
        assert c.strategy == ErrorStrategy.FAIL_FAST

    def test_from_dict_with_retry_policy(self) -> None:
        c = ErrorConfig.from_dict({
            "strategy": "retry",
            "retry_policy": {"max_retries": 5, "base_delay": 2.0},
        })
        assert c is not None
        assert c.retry_policy is not None
        assert c.retry_policy.max_retries == 5

    def test_from_dict_with_exhausted(self) -> None:
        c = ErrorConfig.from_dict({
            "strategy": "retry",
            "exhausted_strategy": "skip",
        })
        assert c is not None
        assert c.exhausted_strategy == ErrorStrategy.SKIP

    def test_from_dict_with_fallback_label(self) -> None:
        c = ErrorConfig.from_dict({
            "strategy": "fallback",
            "fallback_label": "alt",
        })
        assert c is not None
        assert c.fallback_label == "alt"

    def test_from_dict_from_string(self) -> None:
        c = ErrorConfig.from_dict("skip")
        assert c is not None
        assert c.strategy == ErrorStrategy.SKIP

    def test_from_dict_from_none(self) -> None:
        assert ErrorConfig.from_dict(None) is None

    def test_from_dict_invalid_type_returns_none(self) -> None:
        assert ErrorConfig.from_dict(123) is None  # type: ignore[arg-type]

    def test_roundtrip(self) -> None:
        original = ErrorConfig.retry(max_retries=5, base_delay=2.0, exhausted_strategy=ErrorStrategy.IGNORE)
        restored = ErrorConfig.from_dict(original.to_dict())
        assert restored is not None
        assert restored.strategy == original.strategy
        assert restored.retry_policy is not None
        assert restored.retry_policy.max_retries == 5
        assert restored.exhausted_strategy == ErrorStrategy.IGNORE


# ---- 5 种策略完整行为覆盖 ----


class TestStrategyBehavior:
    """每种策略的端到端行为验证：创建 → 序列化 → 反序列化 → 属性。"""

    @pytest.mark.parametrize("strategy", list(ErrorStrategy))
    def test_each_strategy_roundtrip(self, strategy: ErrorStrategy) -> None:
        config = ErrorConfig(strategy=strategy)
        d = config.to_dict()
        assert d["strategy"] == strategy.value
        restored = ErrorConfig.from_dict(d)
        assert restored is not None
        assert restored.strategy == strategy

    @pytest.mark.parametrize("strategy", list(ErrorStrategy))
    def test_each_strategy_has_unique_severity(self, strategy: ErrorStrategy) -> None:
        severities = [s.severity for s in ErrorStrategy if s != strategy]
        assert strategy.severity not in severities

    @pytest.mark.parametrize("strategy", list(ErrorStrategy))
    def test_each_strategy_description_non_empty(self, strategy: ErrorStrategy) -> None:
        assert len(strategy.description) > 0

    def test_ignore_strategy_default_behavior(self) -> None:
        """IGNORE: 默认策略，无重试，无降级。"""
        c = ErrorConfig.ignore()
        assert c.strategy == ErrorStrategy.IGNORE
        assert c.retry_policy is None
        assert c.exhausted_strategy is None
        d = c.to_dict()
        assert d == {"strategy": "ignore"}

    def test_skip_strategy_no_retry(self) -> None:
        """SKIP: 跳过节点，无重试策略。"""
        c = ErrorConfig.skip()
        assert c.strategy == ErrorStrategy.SKIP
        assert c.retry_policy is None
        d = c.to_dict()
        assert d == {"strategy": "skip"}

    def test_retry_strategy_with_full_config(self) -> None:
        """RETRY: 完整配置 — 重试次数、退避、耗尽后策略。"""
        c = ErrorConfig.retry(
            max_retries=5,
            base_delay=2.0,
            max_delay=60.0,
            exhausted_strategy=ErrorStrategy.FAIL_FAST,
        )
        assert c.strategy == ErrorStrategy.RETRY
        assert c.retry_policy is not None
        assert c.retry_policy.max_retries == 5
        assert c.retry_policy.base_delay == 2.0
        assert c.retry_policy.max_delay == 60.0
        assert c.exhausted_strategy == ErrorStrategy.FAIL_FAST

        d = c.to_dict()
        assert d["strategy"] == "retry"
        assert d["retry_policy"]["max_retries"] == 5
        assert d["exhausted_strategy"] == "fail_fast"

        restored = ErrorConfig.from_dict(d)
        assert restored is not None
        assert restored.retry_policy is not None
        assert restored.retry_policy.max_retries == 5
        assert restored.exhausted_strategy == ErrorStrategy.FAIL_FAST

    def test_fallback_strategy_with_custom_label(self) -> None:
        """FALLBACK: 降级到指定标签节点。"""
        c = ErrorConfig.fallback(label="emergency_exit")
        assert c.strategy == ErrorStrategy.FALLBACK
        assert c.fallback_label == "emergency_exit"
        d = c.to_dict()
        assert d["fallback_label"] == "emergency_exit"

    def test_fail_fast_strategy_with_message(self) -> None:
        """FAIL_FAST: 立即终止并携带错误消息。"""
        c = ErrorConfig.fail_fast("critical_failure")
        assert c.strategy == ErrorStrategy.FAIL_FAST
        assert c.error_message == "critical_failure"
        d = c.to_dict()
        assert d["error_message"] == "critical_failure"

    def test_retry_exhausted_strategies(self) -> None:
        """RETRY 耗尽后可降级为 SKIP/IGNORE/FAIL_FAST/FALLBACK。"""
        for exhausted in ErrorStrategy:
            c = ErrorConfig.retry(max_retries=1, exhausted_strategy=exhausted)
            d = c.to_dict()
            restored = ErrorConfig.from_dict(d)
            assert restored is not None
            assert restored.exhausted_strategy == exhausted


class TestRetryPolicyBehavior:
    """RetryPolicy 退避算法精确验证。"""

    def test_exponential_backoff_values(self) -> None:
        """无抖动时，delay 应严格等于 min(base * 2^attempt, max)。"""
        p = RetryPolicy(base_delay=1.0, max_delay=60.0, jitter_factor=0)
        assert p.calculate_delay(0) == 1.0
        assert p.calculate_delay(1) == 2.0
        assert p.calculate_delay(2) == 4.0
        assert p.calculate_delay(3) == 8.0
        assert p.calculate_delay(4) == 16.0

    def test_max_delay_capping(self) -> None:
        """delay 不超过 max_delay。"""
        p = RetryPolicy(base_delay=10.0, max_delay=20.0, jitter_factor=0)
        assert p.calculate_delay(0) == 10.0
        assert p.calculate_delay(1) == 20.0
        assert p.calculate_delay(10) == 20.0

    def test_jitter_within_range(self) -> None:
        """抖动值在预期范围内。"""
        p = RetryPolicy(base_delay=1.0, max_delay=100.0, jitter_factor=0.5)
        for attempt in range(5):
            delay = p.calculate_delay(attempt)
            base = min(1.0 * (2 ** attempt), 100.0)
            assert base <= delay <= base + 0.5

    def test_schedule_respects_max_retries(self) -> None:
        """get_schedule 返回 max_retries 个延迟值。"""
        for n in [1, 3, 5, 10]:
            p = RetryPolicy(max_retries=n, jitter_factor=0)
            schedule = p.get_schedule()
            assert len(schedule) == n

    def test_zero_retries(self) -> None:
        """max_retries=0 时 get_schedule 为空。"""
        p = RetryPolicy(max_retries=0)
        assert p.get_schedule() == []

    def test_custom_retryable_exceptions_subclasses(self) -> None:
        """自定义可重试异常支持子类匹配。"""
        p = RetryPolicy(retryable_exceptions=(OSError,))
        assert p.is_retryable(OSError("x")) is True
        assert p.is_retryable(ConnectionError("x")) is True
        assert p.is_retryable(RuntimeError("x")) is False

    def test_aggressive_retries_fast(self) -> None:
        """aggressive 工厂应产生更短的延迟。"""
        aggressive = RetryPolicy.aggressive()
        gentle = RetryPolicy.gentle()
        assert aggressive.base_delay < gentle.base_delay
        assert aggressive.max_delay < gentle.max_delay
