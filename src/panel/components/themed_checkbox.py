"""ThemedCheckbox — 向后兼容 Shim，委托给 DNAToggle(mode="checkbox")。"""

from __future__ import annotations

from typing import Any, Callable

from src.panel.components.dna_toggle import DNAToggle


class ThemedCheckbox(DNAToggle):
    """Canvas 自绘圆角勾选框 — 委托给 DNAToggle。"""

    def __init__(
        self,
        parent,
        text: str = "",
        variable=None,
        command: Callable[[], None] | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(
            parent, text=text, mode="checkbox",
            variable=variable, command=command, **kw,
        )
