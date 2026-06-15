"""输入框契约（Phase 2，规格 §5.1）。

tk：``themed_entry``。Qt：``themed_entry``。两后端都接受文本预设。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EntrySpec:
    """输入框契约 —— 两后端 ``themed_entry`` 必须支持预设文本。"""

    text: str = ""
    placeholder: str = ""
    enabled: bool = True


#: 两后端 ``themed_entry`` 工厂必须接受的关键字参数。
ENTRY_PROPS: tuple[str, ...] = ("text", "placeholder")
