"""FSM 引擎 — 图级别状态恢复的有限状态机。

核心功能：
- 转换队列 + 优先级排序
- 全局转换（状态无关触发）
- 延迟事件（定时注入）
- 安全限制（深度、超时、禁止回退 START）

FSM 默认关闭（opt-in），由 FlowNode.fsm_transitions 激活。
设计参考：DNA_Design_Scheme/13_风险与验证策略.md §2.2
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

__all__ = [
    "FSMEngine",
    "Transition",
    "GlobalTransition",
    "DelayedEvent",
]

# ---- 常量 ----

START_STATE = "START"

MAX_TRANSITION_DEPTH = 10
MAX_EVALUATION_TIME = 0.1  # 秒


# ---- 数据模型 ----


@dataclass(frozen=True)
class Transition:
    """状态转换规则 — 从 source_state 到 target_state。

    优先级数值越高越先匹配（降序排序）。
    """

    source_state: str
    target_state: str
    trigger_event: str
    condition: str | None = None
    priority: int = 0
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "source_state": self.source_state,
            "target_state": self.target_state,
            "trigger_event": self.trigger_event,
        }
        if self.condition is not None:
            result["condition"] = self.condition
        if self.priority != 0:
            result["priority"] = self.priority
        if self.label is not None:
            result["label"] = self.label
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Transition:
        return cls(
            source_state=data["source_state"],
            target_state=data["target_state"],
            trigger_event=data["trigger_event"],
            condition=data.get("condition"),
            priority=data.get("priority", 0),
            label=data.get("label"),
        )


@dataclass(frozen=True)
class GlobalTransition:
    """全局转换 — 不依赖当前状态，任何状态下都可触发。

    典型用途：弹出窗口检测、黑屏恢复等紧急事件。
    """

    trigger_event: str
    target_state: str
    condition: str | None = None
    priority: int = 0
    label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "trigger_event": self.trigger_event,
            "target_state": self.target_state,
        }
        if self.condition is not None:
            result["condition"] = self.condition
        if self.priority != 0:
            result["priority"] = self.priority
        if self.label is not None:
            result["label"] = self.label
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GlobalTransition:
        return cls(
            trigger_event=data["trigger_event"],
            target_state=data["target_state"],
            condition=data.get("condition"),
            priority=data.get("priority", 0),
            label=data.get("label"),
        )


@dataclass(frozen=True)
class DelayedEvent:
    """延迟事件 — 定时在未来某个时刻注入 FSM。"""

    event: str
    delay_seconds: float
    created_at: float = field(default_factory=time.monotonic)

    @property
    def fire_at(self) -> float:
        return self.created_at + self.delay_seconds

    @property
    def is_ready(self) -> bool:
        return time.monotonic() >= self.fire_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event,
            "delay_seconds": self.delay_seconds,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DelayedEvent:
        return cls(
            event=data["event"],
            delay_seconds=data["delay_seconds"],
            created_at=data.get("created_at", time.monotonic()),
        )


# ---- 条件求值类型 ----

ConditionEvaluator = Callable[[str], bool]


# ---- FSM 引擎 ----


class FSMEngine:
    """有限状态机引擎 — 管理图级别的状态转换。

    使用流程：
    1. 构造时传入 transitions + global_transitions
    2. 设置初始状态（默认 START_STATE）
    3. inject(event) 注入事件
    4. evaluate() 返回匹配的目标状态
    5. schedule_delayed() 调度延迟事件

    线程安全：外部加锁或单线程访问。
    """

    def __init__(
        self,
        transitions: list[Transition] | None = None,
        global_transitions: list[GlobalTransition] | None = None,
        *,
        initial_state: str = START_STATE,
        condition_evaluator: ConditionEvaluator | None = None,
    ) -> None:
        self._transitions = sorted(
            list(transitions) if transitions else [],
            key=lambda t: t.priority, reverse=True,
        )
        self._global_transitions = sorted(
            list(global_transitions) if global_transitions else [],
            key=lambda t: t.priority, reverse=True,
        )
        self._current_state = initial_state
        self._condition_evaluator = condition_evaluator
        self._delayed_events: deque[DelayedEvent] = deque()
        self._transition_count = 0

    # ---- 属性 ----

    @property
    def current_state(self) -> str:
        return self._current_state

    @property
    def transition_count(self) -> int:
        return self._transition_count

    @property
    def has_transitions(self) -> bool:
        return bool(self._transitions) or bool(self._global_transitions)

    @property
    def pending_delayed_count(self) -> int:
        return len(self._delayed_events)

    # ---- 状态管理 ----

    def reset(self, state: str = START_STATE) -> None:
        """重置 FSM 到指定状态。"""
        self._current_state = state
        self._transition_count = 0
        self._delayed_events.clear()

    def force_state(self, state: str) -> None:
        """强制设置当前状态（不触发转换）。"""
        self._current_state = state

    # ---- 事件注入 ----

    def inject(self, event: str) -> str | None:
        """注入事件并尝试转换状态。

        返回：
            - 新状态（转换成功）
            - None（无匹配转换）
        """
        target = self.evaluate(event)
        if target is not None:
            old = self._current_state
            self._current_state = target
            self._transition_count += 1
            logger.debug("FSM 转换: %s → %s (event=%s)", old, target, event)
        return target

    def evaluate(self, event: str) -> str | None:
        """评估事件是否触发转换，返回最终目标状态（不修改当前状态）。

        支持级联转换：如果目标状态有同事件的自定义转换，会继续跟随。
        安全限制：
        - MAX_TRANSITION_DEPTH: 最大级联深度 10
        - MAX_EVALUATION_TIME: 单次评估 < 100ms
        - 禁止回退到 START_STATE
        """
        start_time = time.monotonic()
        depth = 0
        probe_state = self._current_state

        while depth < MAX_TRANSITION_DEPTH:
            if time.monotonic() - start_time > MAX_EVALUATION_TIME:
                logger.warning("FSM 评估超时 (%.3fs)，终止转换", time.monotonic() - start_time)
                return None

            transition = self._find_transition_for_state(event, probe_state)
            if transition is None:
                return probe_state if depth > 0 else None

            target = self._resolve_target(transition)
            if target == START_STATE:
                logger.warning("FSM 不允许回退到 START 状态")
                return probe_state if depth > 0 else None

            depth += 1
            probe_state = target

        logger.warning("FSM 达到最大转换深度 (%d)", MAX_TRANSITION_DEPTH)
        return probe_state

    # ---- 延迟事件 ----

    _MAX_DELAYED_EVENTS = 100

    def schedule_delayed(self, event: str, delay_seconds: float) -> DelayedEvent:
        """调度延迟事件。超出上限时移除最旧的未触发事件。"""
        if len(self._delayed_events) >= self._MAX_DELAYED_EVENTS:
            self._delayed_events.popleft()
            logger.warning("延迟事件队列已满，移除最旧事件")
        delayed = DelayedEvent(event=event, delay_seconds=delay_seconds)
        self._delayed_events.append(delayed)
        logger.debug("调度延迟事件: %s (%.1fs)", event, delay_seconds)
        return delayed

    def process_delayed(self) -> list[str]:
        """处理所有已到期的延迟事件，返回触发的事件列表。"""
        ready: list[DelayedEvent] = []
        remaining: deque[DelayedEvent] = deque()

        for delayed in self._delayed_events:
            if delayed.is_ready:
                ready.append(delayed)
            else:
                remaining.append(delayed)

        self._delayed_events = remaining
        triggered: list[str] = []

        for delayed in ready:
            result = self.inject(delayed.event)
            if result is not None:
                triggered.append(delayed.event)

        return triggered

    def cancel_delayed(self, event: str | None = None) -> int:
        """取消延迟事件。event=None 时取消所有。返回取消数量。"""
        if event is None:
            count = len(self._delayed_events)
            self._delayed_events.clear()
            return count

        original = len(self._delayed_events)
        self._delayed_events = deque(d for d in self._delayed_events if d.event != event)
        return original - len(self._delayed_events)

    # ---- 转换查找 ----

    def _find_transition_for_state(
        self, event: str, state: str,
    ) -> Transition | GlobalTransition | None:
        """查找指定状态的匹配转换（全局优先，然后按优先级降序匹配状态）。"""
        global_match = self._find_global_transition(event)
        if global_match is not None:
            return global_match

        return self._find_state_transition(event, state)

    def _find_global_transition(self, event: str) -> GlobalTransition | None:
        """查找匹配的全局转换（已按优先级降序预排序，取第一个匹配）。"""
        for gt in self._global_transitions:
            if gt.trigger_event == event and self._check_condition(gt.condition):
                return gt
        return None

    def _find_state_transition(self, event: str, state: str) -> Transition | None:
        """查找匹配指定状态的转换（已按优先级降序预排序）。"""
        for t in self._transitions:
            if t.source_state == state and t.trigger_event == event and self._check_condition(t.condition):
                return t
        return None

    def _resolve_target(self, transition: Transition | GlobalTransition) -> str:
        """从转换对象中提取目标状态。"""
        return transition.target_state

    def _check_condition(self, condition: str | None) -> bool:
        """检查条件是否满足。无条件时默认 True。"""
        if condition is None:
            return True
        if self._condition_evaluator is None:
            logger.warning("FSM 条件求值器未设置，跳过条件: %s", condition)
            return True
        try:
            return self._condition_evaluator(condition)
        except Exception:  # pylint: disable=broad-exception-caught
            logger.error("FSM 条件求值失败: %s", condition, exc_info=True)
            return False

    # ---- 序列化 ----

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_state": self._current_state,
            "transition_count": self._transition_count,
            "transitions": [t.to_dict() for t in self._transitions],
            "global_transitions": [gt.to_dict() for gt in self._global_transitions],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        condition_evaluator: ConditionEvaluator | None = None,
    ) -> FSMEngine:
        transitions = [Transition.from_dict(t) for t in data.get("transitions", [])]
        global_transitions = [
            GlobalTransition.from_dict(gt) for gt in data.get("global_transitions", [])
        ]
        engine = cls(
            transitions=transitions,
            global_transitions=global_transitions,
            initial_state=data.get("current_state", data.get("initial_state", START_STATE)),
            condition_evaluator=condition_evaluator,
        )
        engine._transition_count = data.get("transition_count", 0)
        return engine

    # ---- 查询 ----

    def get_applicable_transitions(self, state: str | None = None) -> list[Transition]:
        """获取指定状态（默认当前状态）的可用转换。"""
        target_state = state if state is not None else self._current_state
        return [t for t in self._transitions if t.source_state == target_state]

    def __repr__(self) -> str:
        return (
            f"FSMEngine(state={self._current_state!r}, "
            f"transitions={len(self._transitions)}, "
            f"global={len(self._global_transitions)}, "
            f"delayed={len(self._delayed_events)})"
        )
