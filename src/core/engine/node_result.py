"""节点执行结果 — 所有 NodeDescriptor.execute() 的返回类型。

success/failure 由 success 字段区分；skip 语义由 ExecutionBlocker 承载，
不混入 NodeResult 以保持职责清晰。

支持降级结果：is_partial=True 表示部分成功，warnings 记录降级原因。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class NodeResult:
    """节点执行结果。

    字段说明：
    - success:      执行是否成功
    - output_vars:  输出变量（写入 VariablePool）
    - next_label:   指定下一条边的标签（用于 CONDITION、LOOP 等）
    - error:        执行中的异常（success=False 时可能有值）
    - cooldown:     执行后冷却时间（秒，由 AntiDetectLayer 使用）
    - is_partial:   部分成功标志（成功但有降级）
    - warnings:     降级警告列表
    """

    success: bool
    output_vars: dict[str, Any] = field(default_factory=dict)
    next_label: str | None = None
    error: Exception | None = None
    cooldown: float = 0.0
    is_partial: bool = False
    warnings: tuple[str, ...] = ()

    _FIELD_NAMES: ClassVar[frozenset[str]] = frozenset({
        "success", "output_vars", "next_label", "error", "cooldown",
        "is_partial", "warnings",
    })

    def __post_init__(self) -> None:
        if self.cooldown < 0:
            raise ValueError(f"cooldown must be non-negative, got {self.cooldown}")

    # ---- 工厂方法 ----

    @classmethod
    def ok(cls, **output_vars: Any) -> NodeResult:
        """创建成功结果。"""
        clashes = set(output_vars.keys()) & cls._FIELD_NAMES
        if clashes:
            raise ValueError(f"ok() kwargs clash with fields: {clashes}")
        return cls(success=True, output_vars=output_vars)

    @classmethod
    def fail(cls, error: Exception | str) -> NodeResult:
        """创建失败结果。"""
        if isinstance(error, str):
            error = RuntimeError(error)
        return cls(success=False, error=error)

    @classmethod
    def branch(cls, label: str, success: bool = True, **output_vars: Any) -> NodeResult:
        """创建分支结果（指定下一条边标签）。"""
        if not label:
            raise ValueError("branch label must be a non-empty string")
        clashes = set(output_vars.keys()) & cls._FIELD_NAMES
        if clashes:
            raise ValueError(f"branch() kwargs clash with fields: {clashes}")
        return cls(success=success, next_label=label, output_vars=output_vars)

    @classmethod
    def degraded(cls, *warnings: str, **output_vars: Any) -> NodeResult:
        """创建降级结果（部分成功，带警告）。"""
        clashes = set(output_vars.keys()) & cls._FIELD_NAMES
        if clashes:
            raise ValueError(f"degraded() kwargs clash with fields: {clashes}")
        return cls(
            success=True,
            is_partial=True,
            warnings=warnings,
            output_vars=output_vars,
        )
