"""Log viewer shared utilities — 类型颜色映射 + 行背景着色 + 过滤分组。

被 tkinter LogViewer 和 QtLogViewer 共用。
"""

from __future__ import annotations

from src.core.debug.ring_buffer_log import LogEventType
from src.panel.canvas.theme import current_theme, mix_colors
from src.utils.i18n import t


FILTER_GROUPS: list[tuple[str, list[LogEventType] | None]] = [
    ("workflow.log.filter_all", None),
    ("workflow.log.filter_error", [LogEventType.NODE_ERROR]),
    ("workflow.log.filter_info", [
        LogEventType.NODE_ENTER, LogEventType.NODE_EXIT,
        LogEventType.EXECUTION_START, LogEventType.EXECUTION_END,
    ]),
    ("workflow.log.filter_other", [
        LogEventType.NODE_SKIP, LogEventType.VARIABLE_CHANGE,
        LogEventType.BREAKPOINT, LogEventType.CUSTOM,
    ]),
]

# Cache: rebuild mapping only when theme object changes
_cached_theme_id: int = 0
_cached_mapping: dict[LogEventType, str] = {}


def _type_mapping() -> dict[LogEventType, str]:
    global _cached_theme_id, _cached_mapping
    th = current_theme()
    tid = id(th)
    if tid != _cached_theme_id:
        _cached_theme_id = tid
        _cached_mapping = {
            LogEventType.NODE_ENTER: th.accent_blue,
            LogEventType.NODE_EXIT: th.accent_green,
            LogEventType.NODE_ERROR: th.accent_red,
            LogEventType.NODE_SKIP: th.text_muted,
            LogEventType.VARIABLE_CHANGE: th.accent_orange,
            LogEventType.BREAKPOINT: th.accent_mauve,
            LogEventType.EXECUTION_START: th.accent_green,
            LogEventType.EXECUTION_END: th.accent_green,
            LogEventType.CUSTOM: th.text_muted,
        }
    return _cached_mapping


def type_color(event_type: LogEventType) -> str:
    mapping = _type_mapping()
    th = current_theme()
    return mapping.get(event_type, th.text_muted)


def tint_for(event_type: LogEventType) -> str:
    th = current_theme()
    color = _type_mapping().get(event_type, th.text_muted)
    return mix_colors(th.bg_primary, color, 0.1)


# LogEventType → 本地化类型标签 i18n 键(供"类型"列展示人可读标签,而非裸枚举值)。
_TYPE_LABEL_KEYS: dict[LogEventType, str] = {
    LogEventType.NODE_ENTER: "panel.execlog.type_node_enter",
    LogEventType.NODE_EXIT: "panel.execlog.type_node_exit",
    LogEventType.NODE_ERROR: "panel.execlog.type_node_error",
    LogEventType.NODE_SKIP: "panel.execlog.type_node_skip",
    LogEventType.VARIABLE_CHANGE: "panel.execlog.type_variable_change",
    LogEventType.BREAKPOINT: "panel.execlog.type_breakpoint",
    LogEventType.EXECUTION_START: "panel.execlog.type_execution_start",
    LogEventType.EXECUTION_END: "panel.execlog.type_execution_end",
    LogEventType.CUSTOM: "panel.execlog.type_custom",
}


def type_label(event_type: LogEventType) -> str:
    """返回事件类型的本地化标签(用于"类型"列)。

    未映射的类型回退到枚举原始 value,保证总有可读文本。
    """
    key = _TYPE_LABEL_KEYS.get(event_type)
    if key is None:
        return event_type.value
    return t(key)

