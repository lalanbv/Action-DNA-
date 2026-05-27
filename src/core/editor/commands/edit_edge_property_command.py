"""EditEdgePropertyCommand — 编辑连线属性命令。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.core.editor.commands.edit_property_command import EditPropertyCommand

EdgePropertyName = Literal["label", "priority"]


@dataclass
class EditEdgePropertyCommand(EditPropertyCommand):
    """编辑连线属性命令。通过 _resolve_entity 按 edge_id 查找连线。"""

    edge_id: str = ""

    def _resolve_entity(self) -> Any:
        return self.graph.get_edge(self.edge_id)

    @property
    def description(self) -> str:
        return f"编辑连线属性 ({self.edge_id}.{self.property_path})"
