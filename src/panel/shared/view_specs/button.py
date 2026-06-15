"""按钮契约 — 两后端必须支持这些语义（Phase 2，规格 §5.1）。

tk 实现：``src.panel.widgets.themed_button`` 工厂（DNAButton）。
Qt 实现：``src.panel.qt_backend.widgets.themed_button`` 工厂（QPushButton + dnaBtnStyle property）。

校验：``tests/unit/panel/test_view_specs.py`` 断言两后端工厂接受下述 props。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

#: 按钮变体（两后端 _BUTTON_STYLES 共用的 style 键）。
ButtonVariant = Literal["primary", "secondary", "danger", "ghost"]


@dataclass(frozen=True)
class ButtonSpec:
    """按钮契约 —— 两后端 ``themed_button`` 必须支持的 props。"""

    text: str = ""
    variant: ButtonVariant = "secondary"
    enabled: bool = True
    # 事件 on_click 在 View 层绑定（tk: command / Qt: command callback）。
    # 尺寸取自 tokens（pad_md / pad_xs）+ scale_manager，不在契约中硬编码。


#: 两后端 ``themed_button`` 工厂必须接受的关键字参数（props 契约）。
BUTTON_PROPS: tuple[str, ...] = ("text", "command", "style")
