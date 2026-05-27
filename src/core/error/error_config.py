"""ErrorConfig 错误策略系统 — 每节点错误配置 + 重试策略。

五种策略覆盖从最宽松到最严格的所有场景：
FAIL_FAST / RETRY / SKIP / FALLBACK / IGNORE。

设计灵感来源：Dify ErrorConfig 模式。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum
from typing import Any

__all__ = ["ErrorConfig", "ErrorStrategy", "RetryPolicy"]


class ErrorStrategy(Enum):
    """错误处理策略。"""

    FAIL_FAST = "fail_fast"
    RETRY = "retry"
    SKIP = "skip"
    FALLBACK = "fallback"
    IGNORE = "ignore"

    @property
    def description(self) -> str:
        descriptions: dict[ErrorStrategy, str] = {
            ErrorStrategy.FAIL_FAST: "立即终止整个图执行",
            ErrorStrategy.RETRY: "重试当前节点（可配置次数和延迟）",
            ErrorStrategy.SKIP: "跳过当前节点，继续执行",
            ErrorStrategy.FALLBACK: "执行备用路径（降级节点）",
            ErrorStrategy.IGNORE: "忽略错误，继续执行",
        }
        return descriptions[self]

    @property
    def severity(self) -> int:
        severities: dict[ErrorStrategy, int] = {
            ErrorStrategy.IGNORE: 0,
            ErrorStrategy.SKIP: 1,
            ErrorStrategy.RETRY: 2,
            ErrorStrategy.FALLBACK: 3,
            ErrorStrategy.FAIL_FAST: 4,
        }
        return severities[self]


@dataclass(frozen=True)
class RetryPolicy:
    """重试策略（指数退避 + 随机抖动）。

    退避公式: delay = min(base_delay * 2^attempt, max_delay) + uniform(0, jitter_factor * base_delay)
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter_factor: float = 0.5
    retryable_exceptions: tuple[type[Exception], ...] = (
        RuntimeError,
        TimeoutError,
        OSError,
    )

    def calculate_delay(self, attempt: int) -> float:
        exponential_delay = self.base_delay * (2 ** attempt)
        jitter_value = random.uniform(0, self.jitter_factor * self.base_delay)
        return min(exponential_delay + jitter_value, self.max_delay)

    def is_retryable(self, error: Exception) -> bool:
        return isinstance(error, self.retryable_exceptions)

    def get_schedule(self) -> list[float]:
        return [self.calculate_delay(i) for i in range(self.max_retries)]

    def to_dict(self) -> dict[str, Any]:
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "jitter_factor": self.jitter_factor,
            "retryable_exceptions": [
                exc.__name__ for exc in self.retryable_exceptions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetryPolicy:
        exception_names = data.get("retryable_exceptions")
        retryable: tuple[type[Exception], ...] = (
            RuntimeError, TimeoutError, ConnectionError, OSError,
        )
        if exception_names:
            resolved = _resolve_exception_names(exception_names)
            if resolved:
                retryable = tuple(resolved)
        return cls(
            max_retries=data.get("max_retries", 3),
            base_delay=data.get("base_delay", 1.0),
            max_delay=data.get("max_delay", 30.0),
            jitter_factor=data.get("jitter_factor", 0.5),
            retryable_exceptions=retryable,
        )

    @classmethod
    def fast(cls) -> RetryPolicy:
        return cls(base_delay=0.5, max_delay=5.0, jitter_factor=0.2)

    @classmethod
    def gentle(cls) -> RetryPolicy:
        return cls(base_delay=3.0, max_delay=60.0, jitter_factor=1.0)

    @classmethod
    def aggressive(cls) -> RetryPolicy:
        return cls(base_delay=0.2, max_delay=10.0, jitter_factor=0.1)


@dataclass(frozen=True)
class ErrorConfig:
    """每节点错误配置。"""

    strategy: ErrorStrategy = ErrorStrategy.IGNORE
    retry_policy: RetryPolicy | None = None
    exhausted_strategy: ErrorStrategy | None = None
    fallback_label: str = "fallback"
    error_message: str | None = None

    @classmethod
    def fail_fast(cls, message: str | None = None) -> ErrorConfig:
        return cls(strategy=ErrorStrategy.FAIL_FAST, error_message=message)

    @classmethod
    def retry(
        cls,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exhausted_strategy: ErrorStrategy | None = None,
    ) -> ErrorConfig:
        return cls(
            strategy=ErrorStrategy.RETRY,
            retry_policy=RetryPolicy(
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
            ),
            exhausted_strategy=exhausted_strategy,
        )

    @classmethod
    def skip(cls) -> ErrorConfig:
        return cls(strategy=ErrorStrategy.SKIP)

    @classmethod
    def fallback(cls, label: str = "fallback") -> ErrorConfig:
        return cls(strategy=ErrorStrategy.FALLBACK, fallback_label=label)

    @classmethod
    def ignore(cls) -> ErrorConfig:
        return cls(strategy=ErrorStrategy.IGNORE)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"strategy": self.strategy.value}
        if self.strategy == ErrorStrategy.RETRY and self.retry_policy:
            result["retry_policy"] = self.retry_policy.to_dict()
        if self.exhausted_strategy is not None:
            result["exhausted_strategy"] = self.exhausted_strategy.value
        if self.strategy == ErrorStrategy.FALLBACK:
            result["fallback_label"] = self.fallback_label
        if self.error_message is not None:
            result["error_message"] = self.error_message
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any] | str | None) -> ErrorConfig | None:
        if data is None:
            return None
        if isinstance(data, str):
            return cls(strategy=ErrorStrategy(data))
        if isinstance(data, dict):
            strategy = ErrorStrategy(data.get("strategy", "ignore"))
            exhausted = None
            if "exhausted_strategy" in data:
                exhausted = ErrorStrategy(data["exhausted_strategy"])
            retry_policy = None
            if "retry_policy" in data:
                retry_policy = RetryPolicy.from_dict(data["retry_policy"])
            return cls(
                strategy=strategy,
                retry_policy=retry_policy,
                exhausted_strategy=exhausted,
                fallback_label=data.get("fallback_label", "fallback"),
                error_message=data.get("error_message"),
            )
        return None


def _resolve_exception_names(names: list[str]) -> list[type[Exception]]:
    import builtins
    resolved: list[type[Exception]] = []
    for name in names:
        exc = getattr(builtins, name, None)
        if exc is not None and isinstance(exc, type) and issubclass(exc, Exception):
            resolved.append(exc)
    return resolved
