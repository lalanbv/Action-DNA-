"""执行上下文 — 传递给每个节点的不可变环境。

包含所有执行所需的外部依赖（依赖注入）。
frozen=True 确保不可变性；需要更新时使用 dataclasses.replace() 创建新实例。
extra 和 loop_counts 使用 MappingProxyType 包装，确保真正的不可变。
"""

from __future__ import annotations

import threading
import types
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.condition import ConditionEvaluator
    from src.core.events.bus import TypedEventBus
    from src.core.flow import FlowGraph, FlowNode
    from src.core.input import InputController
    from src.core.variables.pool import VariablePool
    from src.core.vision import ScreenCapture, TemplateMatcher


def _frozen_dict(data: dict[str, Any]) -> types.MappingProxyType:
    """创建只读字典视图。"""
    return types.MappingProxyType(data)


@dataclass(frozen=True)
class ExecutionContext:
    """执行上下文 — 真正不可变，通过 dataclasses.replace() 创建新版本。

    extra 和 loop_counts 使用 MappingProxyType 包装，防止就地修改。
    每个节点看到一致的上下文快照。所有变更通过 CoW 方法创建新实例。
    """

    graph: FlowGraph
    current_node: FlowNode
    variables: VariablePool
    capture: ScreenCapture
    matcher: TemplateMatcher
    input_ctrl: InputController
    gen: int
    stop_event: threading.Event
    pause_event: threading.Event
    event_bus: TypedEventBus | None = None
    evaluator: ConditionEvaluator | None = None
    step_index: int = 0
    loop_counts: types.MappingProxyType = field(default_factory=lambda: _frozen_dict({}))
    extra: types.MappingProxyType = field(default_factory=lambda: _frozen_dict({}))

    @property
    def is_stopping(self) -> bool:
        """检查是否收到停止信号。"""
        return self.stop_event.is_set()

    @property
    def is_paused(self) -> bool:
        """检查是否处于暂停状态。"""
        return self.pause_event.is_set()

    def with_node(
        self, node: FlowNode, *, increment_step: bool = True,
    ) -> ExecutionContext:
        """创建更新了当前节点的新上下文。

        increment_step: 仅 ACTION 节点递增 step_index，其他节点保持不变。
        """
        new_idx = self.step_index + 1 if increment_step else self.step_index
        return replace(self, current_node=node, step_index=new_idx)

    def with_loop_count(self, node_id: str, count: int) -> ExecutionContext:
        """创建更新了循环节点计数的新上下文（CoW）。"""
        return replace(self, loop_counts=_frozen_dict({**self.loop_counts, node_id: count}))

    def with_extra(self, key: str, value: Any) -> ExecutionContext:
        """创建更新了 extra 的新上下文（CoW）。

        不修改原始上下文，返回新实例。用于 Layer 间传递数据。
        """
        return replace(self, extra=_frozen_dict({**self.extra, key: value}))

    def without_extra(self, key: str) -> ExecutionContext:
        """创建移除了 extra 中指定键的新上下文（CoW）。"""
        new_extra = {k: v for k, v in self.extra.items() if k != key}
        return replace(self, extra=_frozen_dict(new_extra))

    def get_loop_count(self, node_id: str) -> int:
        """获取指定节点的循环计数。"""
        return self.loop_counts.get(node_id, 0)

    def get_extra(self, key: str, default: Any = None) -> Any:
        """获取 extra 中指定键的值。"""
        return self.extra.get(key, default)

    def flatten_variables(self) -> dict[str, Any]:
        """展平所有作用域的变量为一个字典。"""
        try:
            return {
                k: v
                for scope in self.variables.snapshot().values()
                for k, v in scope.items()
            }
        except Exception:
            from src.core.logger import log
            log.warning("flatten_variables failed", exc_info=True)
            return {}
