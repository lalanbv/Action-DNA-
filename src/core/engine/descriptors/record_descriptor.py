"""RecordDescriptor — 录制到动作链的桥接工具。

将 MacroRecorder 捕获的事件流通过 EventMerger 合并为 ActionStep 列表，
可直接插入到动作链或 FlowGraph 中。
"""

from __future__ import annotations

import logging

from src.core.step_types import BaseStep
from src.recorder.event_merger import EventMerger
from src.recorder.recorder import MacroRecorder, RecordedEvent
from src.utils.i18n import t

logger = logging.getLogger(__name__)

__all__ = ["RecordBridge"]


class RecordBridge:
    """录制→动作链桥接器。

    使用方式:
        bridge = RecordBridge()
        bridge.start_recording()
        # ... 用户操作 ...
        steps = bridge.stop_and_convert()
    """

    def __init__(self, region: tuple[int, int, int, int] | None = None) -> None:
        self._recorder = MacroRecorder(region=region)
        self._merger = EventMerger()

    def start_recording(self) -> None:
        """开始录制。"""
        self._recorder.start()

    def stop_and_convert(self) -> list[BaseStep]:
        """停止录制并返回合并后的步骤列表。"""
        events = self._recorder.stop()
        steps = self._merger.merge(events)
        logger.info(t("engine.log.record_converted", events=len(events), steps=len(steps)))
        return steps

    def convert_events(self, events: list[RecordedEvent]) -> list[BaseStep]:
        """将已有事件列表转换为步骤（不触发录制）。"""
        return self._merger.merge(events)

    @property
    def is_recording(self) -> bool:
        return self._recorder.is_recording

    @property
    def event_count(self) -> int:
        return self._recorder.event_count

    @property
    def duration(self) -> float:
        return self._recorder.duration

    def snapshot_events(self) -> list[RecordedEvent]:
        """返回当前录制中的事件快照（线程安全）。"""
        return self._recorder.snapshot_events()
