"""执行阻断哨兵 — ComfyUI ExecutionBlocker 模式。

节点返回此对象表示「跳过」，区别于错误（异常）和无结果（None）。
引擎检测到 ExecutionBlocker 时跳过下游节点，不触发错误处理管道。
"""

from __future__ import annotations


class ExecutionBlocker:
    """执行阻断哨兵。

    典型用法：
    - 模板匹配未找到且配置为 "skip" 时
    - 条件不满足时跳过分支
    - 前置条件未满足时跳过
    """

    __slots__ = ("_reason",)

    def __init__(self, reason: str = "") -> None:
        self._reason = reason

    @property
    def reason(self) -> str:
        return self._reason

    def __repr__(self) -> str:
        return f"ExecutionBlocker(reason={self.reason!r})"

    def __bool__(self) -> bool:
        """布尔上下文中为 False，方便 if-not 检查。"""
        return False

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ExecutionBlocker):
            return NotImplemented
        return self.reason == other.reason

    def __hash__(self) -> int:
        return hash(("ExecutionBlocker", self.reason))
