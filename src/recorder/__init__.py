"""宏录制模块 — 事件捕获与智能合并"""

from src.recorder.recorder import RecordedEvent, MacroRecorder
from src.recorder.event_merger import EventMerger

__all__ = [
    "RecordedEvent",
    "MacroRecorder",
    "EventMerger",
]
