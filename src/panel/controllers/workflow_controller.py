"""WorkflowController — 工作流页面的业务逻辑层"""

import copy
from collections.abc import Callable
from dataclasses import replace

from src.core.action import ActionType
from src.core.step_types import STEP_CLASSES
from src.core.editor.commands.add_edge_command import AddEdgeCommand
from src.core.editor.commands.add_node_command import AddNodeCommand
from src.core.editor.commands.edit_edge_property_command import EditEdgePropertyCommand
from src.core.editor.commands.auto_insert_command import AutoInsertCommand
from src.core.editor.commands.move_node_command import MoveNodeCommand
from src.core.editor.commands.reconnect_edge_command import ReconnectEdgeCommand
from src.core.editor.commands.loop_command import LoopChangedCommand
from src.core.editor.commands.remove_edge_command import RemoveEdgeCommand
from src.core.editor.commands.remove_node_command import RemoveNodeCommand
from src.core.editor.undo_manager import UndoManager, UndoManagerConfig
from src.core.events.event_names import EventName
from src.core.flow import FlowEdge, FlowGraph, FlowNode, NodeType
from src.panel.controllers.base_controller import BaseController
from src.panel.models.enums import EdgeLabel
from src.utils.i18n import t


class WorkflowController(BaseController):
    """处理工作流页面的用户操作，协调 Model / Executor / Profile"""

    DUPLICATE_OFFSET_X = 60
    DUPLICATE_OFFSET_Y = 40
    PASTE_OFFSET = 50

    def _event_subscriptions(self) -> list[tuple[str, Callable]]:
        return [
            (EventName.EXECUTOR_STEP_CHANGED, self._on_step_changed),
            (EventName.EXECUTOR_FINISHED, self._on_finished),
            (EventName.EXECUTOR_STARTED, self._on_started),
            (EventName.EXECUTOR_STOPPED, self._on_stopped),
            (EventName.EXECUTOR_PAUSED, self._on_paused),
            (EventName.EXECUTOR_RESUMED, self._on_resumed),
        ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.undo_manager = UndoManager(UndoManagerConfig(max_depth=100))

    # ── 执行器状态 ──────────────────────────────────────────

    @property
    def is_executor_running(self) -> bool:
        return self._executor.is_running

    # ── 图节点管理 ──────────────────────────────────────────

    def add_node(
        self, node_type: NodeType, pos_x: int, pos_y: int,
        action_type: ActionType | None = None,
    ) -> FlowNode:
        self._require_idle()
        graph = self.model.graph
        action = STEP_CLASSES[action_type]() if action_type else None
        cmd = AddNodeCommand(
            graph=graph, node_type=node_type, x=pos_x, y=pos_y, action=action,
        )
        self.undo_manager.execute(cmd)
        node = graph.get_node(cmd.node_id) if cmd.node_id else None
        if node is None:
            node = self.model.add_node_at(node_type, pos_x, pos_y, action_type)
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)
        return node

    def remove_node(self, node_id: str) -> None:
        self._require_idle()
        cmd = RemoveNodeCommand(graph=self.model.graph, node_id=node_id)
        self.undo_manager.execute(cmd)
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def add_edge(
        self, from_id: str, to_id: str, label: str = EdgeLabel.DEFAULT
    ) -> FlowEdge | None:
        self._require_idle()
        graph = self.model.graph
        if not graph.get_node(from_id) or not graph.get_node(to_id):
            return None
        cmd = AddEdgeCommand(
            graph=graph, source_id=from_id, target_id=to_id, label=label,
        )
        self.undo_manager.execute(cmd)
        if cmd.edge_id:
            return graph.get_edge(cmd.edge_id)
        return None

    def remove_edge(self, edge_id: str) -> None:
        self._require_idle()
        cmd = RemoveEdgeCommand(graph=self.model.graph, edge_id=edge_id)
        self.undo_manager.execute(cmd)
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def update_edge_property(
        self, edge_id: str, property_path: str, old_value: object, new_value: object,
    ) -> None:
        cmd = EditEdgePropertyCommand(
            graph=self.model.graph,
            edge_id=edge_id,
            property_path=property_path,
            old_value=old_value,
            new_value=new_value,
        )
        self.undo_manager.execute(cmd)

    def update_node_position(self, node_id: str, x: int, y: int) -> None:
        cmd = MoveNodeCommand(
            graph=self.model.graph, node_id=node_id, new_x=x, new_y=y,
        )
        self.undo_manager.execute(cmd)

    def reconnect_edge(
        self, edge_id: str, side: str, new_node_id: str, new_port: str,
    ) -> ReconnectEdgeCommand | None:
        self._require_idle()
        try:
            cmd = ReconnectEdgeCommand(
                graph=self.model.graph, edge_id=edge_id, side=side,
                new_node_id=new_node_id, new_port=new_port,
            )
        except ValueError:
            return None
        self.undo_manager.execute(cmd)
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)
        return cmd

    def auto_insert(self, edge_id: str, node_id: str) -> AutoInsertCommand | None:
        self._require_idle()
        try:
            cmd = AutoInsertCommand(
                graph=self.model.graph, edge_id=edge_id, insert_node_id=node_id,
            )
        except ValueError:
            return None
        self.undo_manager.execute(cmd)
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)
        return cmd

    def update_node_action(self, node_id: str, action) -> None:
        self._require_idle()
        node = self.model.graph.get_node(node_id)
        if node:
            node.action = action
            node.comment = action.comment if action else ""
            node.enabled = action.enabled if action else True
            self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def update_node_condition(self, node_id: str, condition) -> None:
        self._require_idle()
        node = self.model.graph.get_node(node_id)
        if node:
            node.condition = condition
            self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def toggle_node_enabled(self, node_id: str) -> None:
        self._require_idle()
        node = self.model.graph.get_node(node_id)
        if node:
            node.enabled = not node.enabled
            self._bus.emit(EventName.CHAIN_STEPS_CHANGED)

    def update_node_error_config(self, node_id: str, error_config) -> None:
        node = self.model.graph.get_node(node_id)
        if node:
            node.error_config = error_config

    def update_loop(self, loop: bool, loop_count: int) -> None:
        """通过 undo command 系统更新循环模式。"""
        cmd = LoopChangedCommand(
            graph=self.model.graph,
            new_loop=loop,
            new_loop_count=loop_count,
        )
        self.undo_manager.execute(cmd)

    def _clone_node(
        self, source: FlowNode, offset_x: float = 0, offset_y: float = 0,
    ) -> str:
        """深度复制节点（含 action/condition/error_config），不复制连线。

        返回新节点的 ID。调用方负责后续设置 comment 等属性。
        """
        graph = self.model.graph
        new_id = FlowGraph.new_id(
            "a" if source.node_type == NodeType.ACTION else "n"
        )
        new_node = replace(
            copy.deepcopy(source),
            node_id=new_id,
            pos_x=source.pos_x + int(offset_x),
            pos_y=source.pos_y + int(offset_y),
        )
        graph.add_node(new_node)
        return new_id

    def duplicate_node(self, node_id: str) -> FlowNode | None:
        node = self.model.graph.get_node(node_id)
        if not node:
            return None
        new_id = self._clone_node(
            node, offset_x=self.DUPLICATE_OFFSET_X,
            offset_y=self.DUPLICATE_OFFSET_Y,
        )
        new_node = self.model.graph.get_node(new_id)
        if new_node:
            new_node.comment = (node.comment + " (副本)") if node.comment else "副本"
        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)
        return new_node

    def copy_nodes(self, node_ids: list[str]) -> list[FlowNode]:
        result: list[FlowNode] = []
        for nid in node_ids:
            node = self.model.graph.get_node(nid)
            if node:
                result.append(copy.deepcopy(node))
        return result

    def paste_nodes(
        self, nodes: list[FlowNode],
        offset_x: int = PASTE_OFFSET, offset_y: int = PASTE_OFFSET,
    ) -> list[FlowNode]:
        self._require_idle()
        graph = self.model.graph
        new_nodes: list[FlowNode] = []

        for orig in nodes:
            new_id = self._clone_node(
                orig, offset_x=offset_x, offset_y=offset_y,
            )
            new_node = graph.get_node(new_id)
            if new_node:
                new_nodes.append(new_node)

        self._bus.emit(EventName.CHAIN_STEPS_CHANGED)
        return new_nodes

    # ── 执行控制 ──────────────────────────────────────────

    def start_chain(self) -> None:
        self._require_executor()
        if self._executor.is_running:
            return
        if not self.model.graph.nodes:
            raise ValueError(t("panel.exc.create_flow_nodes_first"))
        self._executor.start(self.model.graph)

    # ── 执行器事件回调（特有）──────────────────────────────

    def _on_step_changed(self, step_index=None, iteration=None, node_id=None, **kwargs):
        self._bus.emit(
            EventName.UI_NODE_HIGHLIGHT, node_id=node_id, step_index=step_index, iteration=iteration
        )

    # ── 撤销/重做 ──────────────────────────────────────────

    def undo(self):
        return self.undo_manager.undo()

    def redo(self):
        return self.undo_manager.redo()
