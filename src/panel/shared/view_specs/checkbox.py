"""复选框契约（Phase 2，规格 §5.1）。

tk：``themed_checkbutton``（DNAToggle）。Qt：``themed_checkbutton``（QCheckBox）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckboxSpec:
    """复选框契约 —— 两后端 ``themed_checkbutton`` 必须支持。"""

    text: str = ""
    checked: bool = False
    enabled: bool = True


#: 两后端 ``themed_checkbutton`` 工厂必须接受的关键字参数。
CHECKBOX_PROPS: tuple[str, ...] = ("text", "checked")
