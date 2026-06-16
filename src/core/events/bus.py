"""类型化事件总线 — 发布/订阅模式，线程安全，错误隔离。

支持优先级排序和谓词过滤：高优先级（数值小）的处理器先执行，
predicate 不满足时跳过该处理器。
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable, TypeVar

from src.core.events.events import BaseEvent
from src.utils.i18n import t

logger = logging.getLogger(__name__)

_E = TypeVar("_E", bound=BaseEvent)


@dataclass(frozen=True)
class Subscription:
    """订阅记录 — 绑定 handler 与其优先级和过滤谓词。"""

    handler: Callable
    priority: int = 0
    predicate: Callable[[Any], bool] | None = None


class TypedEventBus:
    """
    类型化事件总线：按事件类型（dataclass class）订阅和发布。

    核心特性：
    - 类型安全：订阅者按 event_type 注册，IDE 可自动补全
    - 错误隔离：每个订阅者独立 try/catch，一个出错不影响其他
    - 线程安全：所有共享状态操作用 Lock 保护
    - 审计日志：可选的事件历史记录，用于调试
    """

    def __init__(self) -> None:
        self._subscribers: dict[type[BaseEvent], list[Subscription]] = {}
        self._ui_queue: deque[tuple[Callable, BaseEvent]] = deque(maxlen=1000)
        self._ui_handlers: set[Callable] = set()
        self._ui_handlers_snapshot: frozenset[Callable] = frozenset()
        self._ui_handlers_dirty: bool = False
        self._lock = threading.Lock()
        self._audit_log: deque[tuple[float, str, Any]] = deque(maxlen=5000)
        self._audit_enabled: bool = False
        self._legacy_listeners: dict[str, list[Callable]] = {}

    # ---- 订阅管理 ----

    def subscribe(
        self,
        event_type: type[_E],
        handler: Callable[[_E], None],
        *,
        priority: int = 0,
        predicate: Callable[[_E], bool] | None = None,
    ) -> None:
        """订阅特定类型的事件。

        参数:
            event_type: 事件类型（dataclass class）
            handler: 事件回调
            priority: 优先级（数值越小越先执行，默认 0）
            predicate: 过滤谓词，返回 False 时跳过该 handler
        """
        sub = Subscription(handler=handler, priority=priority, predicate=predicate)
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            # 防止同一 handler 重复订阅
            for existing in self._subscribers[event_type]:
                if existing.handler is handler:
                    return
            self._subscribers[event_type].append(sub)
            self._subscribers[event_type].sort(key=lambda s: s.priority)

    def unsubscribe(self, event_type: type[_E], handler: Callable[[_E], None]) -> None:
        """取消订阅。"""
        with self._lock:
            if event_type in self._subscribers:
                self._subscribers[event_type] = [
                    s for s in self._subscribers[event_type]
                    if s.handler is not handler
                ]
                if not self._subscribers[event_type]:
                    del self._subscribers[event_type]
            self._ui_handlers.discard(handler)
            self._ui_handlers_dirty = True

    def subscribe_ui(self, event_type: type[_E], handler: Callable[[_E], None]) -> None:
        """订阅为 UI 处理器，回调在主线程 drain_ui_events() 中执行。"""
        self.subscribe(event_type, handler)
        with self._lock:
            self._ui_handlers.add(handler)
            self._ui_handlers_dirty = True

    # ---- 事件发布 ----

    def publish(self, event: BaseEvent) -> None:
        """
        发布事件，每个订阅者独立 try/catch（错误隔离）。

        按优先级排序分发，predicate 返回 False 时跳过。
        无订阅者时静默忽略，不抛异常。
        """
        event_type = type(event)

        with self._lock:
            if self._audit_enabled:
                self._audit_log.append((time.time(), event_type.__name__, event))
            subs = list(self._subscribers.get(event_type, []))
            has_ui = bool(self._ui_handlers)
            if has_ui and self._ui_handlers_dirty:
                self._ui_handlers_snapshot = frozenset(self._ui_handlers)
                self._ui_handlers_dirty = False
            ui_handlers = self._ui_handlers_snapshot if has_ui else frozenset()

        if not subs:
            return

        # 收集 UI 事件，最后一次性入队，减少锁竞争
        pending_ui: list[tuple[Callable, BaseEvent]] = [] if has_ui else None

        for sub in subs:
            if sub.predicate is not None and not sub.predicate(event):
                continue
            try:
                if has_ui and sub.handler in ui_handlers:
                    pending_ui.append((sub.handler, event))
                else:
                    sub.handler(event)
            except Exception:  # pylint: disable=broad-exception-caught
                name = getattr(sub.handler, "__name__", str(sub.handler))
                logger.error(
                    t("engine.log.event_handler_error", handler=name, event_type=event_type.__name__),
                    exc_info=True,
                )

        # 批量入队 UI 事件（单次锁获取）
        if pending_ui:
            with self._lock:
                self._ui_queue.extend(pending_ui)

    # ---- UI 事件排空 ----

    def drain_ui_events(self) -> int:
        """在主线程中执行排队的 UI 事件，返回处理数量。"""
        with self._lock:
            pending = list(self._ui_queue)
            self._ui_queue.clear()

        for handler, event in pending:
            try:
                handler(event)
            except Exception:  # pylint: disable=broad-exception-caught
                logger.error(t("events.log.ui_handler_error"), exc_info=True)

        return len(pending)

    # ---- 字符串事件兼容 API ----

    def on(self, event_name: str, handler: Callable) -> None:
        """订阅字符串事件（兼容旧 EventBus 接口）。"""
        with self._lock:
            if event_name not in self._legacy_listeners:
                self._legacy_listeners[event_name] = []
            if handler not in self._legacy_listeners[event_name]:
                self._legacy_listeners[event_name].append(handler)

    def off(self, event_name: str, handler: Callable) -> None:
        """取消订阅字符串事件。"""
        with self._lock:
            if event_name in self._legacy_listeners:
                self._legacy_listeners[event_name] = [
                    h for h in self._legacy_listeners[event_name] if h != handler
                ]
                if not self._legacy_listeners[event_name]:
                    del self._legacy_listeners[event_name]

    def emit(self, event_name: str, **kwargs: Any) -> None:
        """发布字符串事件（兼容旧 EventBus 接口）。"""
        with self._lock:
            handlers = list(self._legacy_listeners.get(event_name, []))

        for handler in handlers:
            try:
                handler(**kwargs)
            except Exception:  # pylint: disable=broad-exception-caught
                name = getattr(handler, "__name__", str(handler))
                logger.error(
                    t("engine.log.string_event_handler_error", handler=name, event_name=event_name),
                    exc_info=True,
                )

    # ---- 审计与调试 ----

    def enable_audit(self, enabled: bool = True) -> None:
        """启用/禁用审计日志，禁用时清空已有记录。"""
        with self._lock:
            self._audit_enabled = enabled
            if not enabled:
                self._audit_log.clear()

    def get_audit_log(self) -> list[tuple[float, str, Any]]:
        """返回审计日志的副本：[(timestamp, event_type_name, event)]。"""
        with self._lock:
            return list(self._audit_log)

    # ---- 管理 ----

    def clear_subscriptions(self) -> None:
        """清空所有订阅和审计日志（测试用）。"""
        with self._lock:
            self._subscribers.clear()
            self._ui_handlers.clear()
            self._ui_queue.clear()
            self._audit_log.clear()
            self._audit_enabled = False
            self._legacy_listeners.clear()

    def subscriber_count(self, event_type: type[BaseEvent] | None = None) -> int:
        """获取订阅者数量（按类型或总计）。"""
        with self._lock:
            if event_type is not None:
                return len(self._subscribers.get(event_type, []))
            return sum(len(subs) for subs in self._subscribers.values())
