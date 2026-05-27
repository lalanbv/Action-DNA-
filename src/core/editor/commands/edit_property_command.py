"""EditPropertyCommand — 编辑属性命令。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from src.core.editor.commands.edit_command import EditCommand
from src.core.flow import FlowGraph

logger = logging.getLogger(__name__)


@dataclass
class EditPropertyCommand(EditCommand):
    """编辑实体属性命令。记录旧值和新值，通过属性路径设置。

    子类可覆盖 _resolve_entity() 以支持不同实体类型（节点/连线）。
    """

    graph: FlowGraph
    node_id: str = ""
    property_path: str = ""
    old_value: Any = None
    new_value: Any = None

    def _resolve_entity(self) -> Any:
        """返回要修改的实体对象。默认按 node_id 查找节点。"""
        return self.graph.get_node(self.node_id)

    def execute(self) -> None:
        self._set_property(self.new_value)

    def undo(self) -> None:
        self._set_property(self.old_value)

    def _set_property(self, value: Any) -> None:
        obj = self._resolve_entity()
        if obj is None:
            return
        parts = self.property_path.split(".")
        for part in parts[:-1]:
            obj = getattr(obj, part, None)
            if obj is None:
                return
        if hasattr(obj, parts[-1]):
            setattr(obj, parts[-1], value)

    @property
    def description(self) -> str:
        return f"编辑属性 ({self.node_id}.{self.property_path})"
