"""ThemedRadio — 向后兼容 Shim，委托给 DNAToggle(mode="radio")。"""

from __future__ import annotations

from typing import Any, Callable

from src.panel.components.dna_toggle import DNAToggle


class ThemedRadio(DNAToggle):
    """Canvas 自绘圆形单选按钮 — 委托给 DNAToggle。"""

    def __init__(
        self,
        parent,
        text: str = "",
        variable=None,
        value: Any = None,
        command: Callable[[], None] | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(
            parent, text=text, mode="radio",
            variable=variable, value=value, command=command, **kw,
        )
