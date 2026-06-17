"""ExecutionLogBridge — EventBus 执行事件 → RingBufferLog 桥接器。

把 ActionExecutor 经 EventBus 发布的生命周期事件(启动/停止/暂停/恢复/
结束/安全停止/轮次)翻译成结构化执行日志条目,写入共享 RingBufferLog,
供执行日志面板实时显示。

与 LoggingLayer(节点级,在执行线程内直接写 ring_log)互补:
- LoggingLayer 覆盖: 图开始/结束、节点开始/完成/异常(带节点标签 + 成败详情)
- 本桥接器覆盖: 执行启动/停止/暂停/恢复/结束/安全停止/轮次(facade 级事件,
  在 ActionExecutor 中发射,不经过 GraphEngine 的 Layer 钩子)

tkinter 与 Qt 双后端共用本类(纯逻辑,无 UI 依赖),满足双框架同步规则。
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from src.core.debug.ring_buffer_log import LogEventType, RingBufferLog
from src.core.events.event_names import EventName
from src.utils.i18n import t

logger = logging.getLogger(__name__)


class ExecutionLogBridge:
    """EventBus → RingBufferLog 执行日志桥接器(生命周期事件)。

    在 PanelApp 中创建单例,连接共享 event_bus 与共享 ring_log。
    应用退出时需调用 ``destroy()`` 取消订阅,防回调泄漏。
    """

    def __init__(self, event_bus, ring_log: RingBufferLog) -> None:
        self._bus = event_bus
        self._log = ring_log
        self._subscriptions: list[tuple[str, Callable]] = []
        self._subscribe()

    # ── 订阅管理 ──────────────────────────────────────────

    def _subscribe(self) -> None:
        """注册所有执行器生命周期事件的翻译回调。"""
        subs = [
            (EventName.EXECUTOR_STARTED, self._on_started),
            (EventName.EXECUTOR_STOPPED, self._on_stopped),
            (EventName.EXECUTOR_PAUSED, self._on_paused),
            (EventName.EXECUTOR_RESUMED, self._on_resumed),
            (EventName.EXECUTOR_FINISHED, self._on_finished),
            (EventName.EXECUTOR_FAILSAFE, self._on_failsafe),
            (EventName.EXECUTOR_ROUND_STARTED, self._on_round_started),
        ]
        for event, cb in subs:
            self._bus.on(event, cb)
            self._subscriptions.append((event, cb))

    def destroy(self) -> None:
        """取消所有订阅,防止应用退出后回调泄漏。"""
        for event, cb in self._subscriptions:
            try:
                self._bus.off(event, cb)
            except Exception:  # noqa: BLE001 — 清理不得抛
                logger.debug("ExecutionLogBridge 取消订阅失败(忽略)", exc_info=True)
        self._subscriptions.clear()

    # ── 写入辅助 ──────────────────────────────────────────

    def _write(
        self,
        event_type: LogEventType,
        message: str,
        node_id: str = "",
        data: dict | None = None,
    ) -> None:
        """写入一条执行日志。

        executor 经 ``_schedule_main`` 桥接,EventBus 回调已在主线程触发;
        RingBufferLog.append 自带锁,故此处线程安全。
        """
        try:
            self._log.append(
                node_id=node_id,
                event_type=event_type,
                message=message,
                data=data,
            )
        except Exception:  # noqa: BLE001 — 日志写入不得影响事件流
            logger.debug("ExecutionLogBridge 写入失败(忽略)", exc_info=True)

    # ── 事件翻译 ──────────────────────────────────────────

    def _on_started(self, **kwargs) -> None:
        self._write(LogEventType.EXECUTION_START, t("panel.execlog.started"))

    def _on_stopped(self, **kwargs) -> None:
        self._write(LogEventType.CUSTOM, t("panel.execlog.stopped"))

    def _on_paused(self, **kwargs) -> None:
        self._write(LogEventType.CUSTOM, t("panel.execlog.paused"))

    def _on_resumed(self, **kwargs) -> None:
        self._write(LogEventType.CUSTOM, t("panel.execlog.resumed"))

    def _on_finished(self, rounds=None, **kwargs) -> None:
        self._write(
            LogEventType.EXECUTION_END,
            t("panel.execlog.finished", rounds=rounds if rounds is not None else 0),
        )

    def _on_failsafe(self, **kwargs) -> None:
        self._write(LogEventType.NODE_ERROR, t("panel.execlog.failsafe"))

    def _on_round_started(self, iteration=None, **kwargs) -> None:
        """executor 在第 2 轮起发布 ROUND_STARTED(iteration 从 0 计);
        面板用 1-based 展示"第 N 轮"。"""
        round_idx = (iteration + 1) if iteration is not None else 1
        self._write(LogEventType.CUSTOM, t("panel.execlog.round", round_idx=round_idx))
