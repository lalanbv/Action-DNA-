"""WorkflowActionsMixin — 节点/边 CRUD、上下文菜单、监控器、复制/粘贴、搜索。"""

from __future__ import annotations

import copy
from dataclasses import replace
from tkinter import ttk
from typing import TYPE_CHECKING

import tkinter as tk
from tkinter import simpledialog

from src.core.action import ActionType
from src.core.step_types import BaseStep, STEP_CLASSES
from src.core.flow import FlowGraph, FlowNode, NodeType
from src.panel.canvas.node_shared import (
    LAYOUT_SPACING_Y,
    LAYOUT_START_X,
    LAYOUT_START_Y,
    NODE_SPECS,
    node_size,
)
from src.panel.canvas.search_dialog import SearchBar
from src.panel.dialogs.node_creation_popup import NodeCreationPopup
from src.panel.dialogs.condition_dialog import open_condition_dialog
from src.panel.dialogs.monitor_dialog import open_monitor_dialog
from src.panel.dialogs import open_step_dialog
from src.panel.models.enums import EdgeLabel
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.panel.canvas.graph_canvas import GraphCanvas
    from src.panel.canvas.floating_controls import FloatingZoomControls
    from src.panel.components.property_panel import PropertyPanel
    from src.panel.controllers.workflow_controller import WorkflowController
    from src.panel.models.chain_model import ChainModel


class WorkflowActionsMixin:
    """节点/边操作相关方法，供 WorkflowPage 继承。

    依赖 self 属性:
        _model, _canvas, _controller, _selected_node_id, _prop_panel,
        _clipboard, _paste_offset, _search_bar, loop_controls, _monitor_tree,
        _palette_btn_widgets, _ring_log, _current_zoom, _floating_zoom,
        _debugger, _btn_undo, _btn_redo
    """

    if TYPE_CHECKING:
        _canvas: GraphCanvas
        _clipboard: list[FlowNode]
        _controller: WorkflowController
        _current_zoom: float
        _floating_zoom: FloatingZoomControls
        _model: ChainModel
        _monitor_tree: ttk.Treeview
        _paste_offset: int
        _prop_panel: PropertyPanel
        _search_bar: SearchBar | None
        _selected_node_id: str | None

        frame: tk.Frame

        def _append_log(self, msg: str) -> None: ...
        def _on_redo(self) -> None: ...
        def _on_undo(self) -> None: ...
        def _show_node_properties(self, node_id: str) -> None: ...
        def _update_status_bar(self) -> None: ...

    # ── 画布事件回调 ──────────────────────────────────────

    def _on_canvas_event(self, event_type: str, **kwargs):
        match event_type:
            case "node_selected":
                node_id = kwargs.get("node_id")
                if node_id is not None:
                    self._selected_node_id = node_id
                    self._show_node_properties(node_id)
                self._update_status_bar()
            case "node_moved":
                self._controller.update_node_position(
                    kwargs["node_id"], kwargs["x"], kwargs["y"]
                )
            case "node_double_clicked":
                node_id = kwargs.get("node_id")
                node = self._model.graph.get_node(node_id) if node_id else None
                if node and node_id is not None:
                    if node.node_type == NodeType.ACTION:
                        self._edit_node_action(node_id)
                    elif node.node_type == NodeType.CONDITION:
                        self._edit_node_condition(node_id)
            case "edge_created":
                graph = self._model.graph
                ok, _reason = graph.can_connect(
                    kwargs["from_id"], kwargs["to_id"], kwargs.get("label", EdgeLabel.DEFAULT),
                )
                if not ok:
                    self._append_log(t("workflow.msg.edge_failed"))
                    return
                edge = self._controller.add_edge(
                    kwargs["from_id"], kwargs["to_id"], kwargs.get("label", EdgeLabel.DEFAULT)
                )
                if edge is None:
                    self._append_log(t("workflow.msg.edge_failed"))
                else:
                    self._canvas.add_edge_visual(edge)
                self._update_status_bar()
            case "edge_removed":
                self._controller.remove_edge(kwargs["edge_id"])
                self._update_status_bar()
            case "edge_context_menu":
                self._show_edge_context_menu(
                    kwargs["edge_id"], kwargs["screen_x"], kwargs["screen_y"]
                )
            case "canvas_deselected" | "nodes_selected":
                self._selected_node_id = None
                self._prop_panel.show_empty()
                self._update_status_bar()
            case "delete_selected":
                self._delete_selected_nodes(kwargs.get("node_ids", []))
            case "delete_edge":
                self._on_delete_edge(kwargs.get("edge_id", ""))
            case "edge_selected":
                self._selected_node_id = None
                self._show_edge_properties(kwargs["edge_id"])
            case "node_context_menu":
                self._show_node_context_menu(
                    kwargs["node_id"], kwargs["screen_x"], kwargs["screen_y"]
                )
            case "canvas_context_menu":
                self._show_canvas_context_menu(
                    kwargs["screen_x"], kwargs["screen_y"],
                    kwargs.get("canvas_x"), kwargs.get("canvas_y"),
                )
            case "zoom_changed":
                self._current_zoom = kwargs["zoom"]
                self._update_status_bar()
                if hasattr(self, "_floating_zoom"):
                    self._floating_zoom.update_zoom_display()
            case "copy_selected":
                self._on_copy(kwargs.get("node_ids", []))
            case "paste":
                self._on_paste()
            case "duplicate_selected":
                self._on_duplicate_selected(kwargs.get("node_ids", []))
            case "undo":
                self._on_undo()
            case "redo":
                self._on_redo()
            case "search":
                self._open_search()
            case "escape":
                self._close_search()
            case "edge_reconnected":
                self._on_edge_reconnected(**kwargs)
            case "auto_insert":
                self._on_auto_insert(**kwargs)

    # ── 节点操作 ──────────────────────────────────────────

    def _add_node_at(
        self,
        node_type: NodeType,
        x: float,
        y: float,
        action_type: ActionType | None = None,
    ) -> None:
        new_node = self._controller.add_node(node_type, int(x), int(y), action_type)
        self._canvas.add_node_visual(new_node)
        self._append_log(f"+ {new_node.describe()}")
        self._update_status_bar()

    def _on_add_action_node(self, action_type: ActionType):
        if self._controller.is_executor_running:
            return
        cx, cy = self._canvas.viewport_center()
        cx, cy = self._find_free_position(cx, cy, NodeType.ACTION)
        self._add_node_at(NodeType.ACTION, cx, cy, action_type)

    def _find_free_position(
        self, x: float, y: float, node_type: NodeType = NodeType.ACTION,
    ) -> tuple[float, float]:
        """返回不与现有节点重叠的空闲位置（向下偏移）。"""
        graph = self._model.graph
        new_w, new_h = NODE_SPECS.get(node_type, NODE_SPECS[NodeType.ACTION])[:2]
        changed = True
        while changed:
            changed = False
            for node in graph.nodes.values():
                nw, nh = node_size(node)
                if (node.pos_x < x + new_w and node.pos_x + nw > x
                        and node.pos_y < y + new_h and node.pos_y + nh > y):
                    y = node.pos_y + nh
                    changed = True
        return x, y

    def _import_steps(self, steps: list[BaseStep]) -> None:
        if not steps:
            return

        graph = self._model.graph

        # Find the insertion point: the node immediately before End.
        # NOTE: assumes a linear chain — branch graphs may need per-branch insertion.
        end_incoming = graph.get_incoming_edges("end")
        last_node_id = "start"
        for e in end_incoming:
            if e.from_node != "start":
                last_node_id = e.from_node

        # Remove the edge from insertion point → End so we can insert
        # new nodes in between, then reconnect at the end.
        for e in graph.get_outgoing_edges(last_node_id):
            if e.to_node == "end":
                self._controller.remove_edge(e.edge_id)
                self._canvas.remove_edge_visual(e.edge_id)

        # Layout: position new nodes below the insertion point
        anchor = graph.get_node(last_node_id)
        base_x = anchor.pos_x if anchor and anchor.pos_x else LAYOUT_START_X
        base_y = anchor.pos_y if anchor and anchor.pos_y else LAYOUT_START_Y
        first_y = base_y + LAYOUT_SPACING_Y

        prev_id: str = last_node_id

        for i, step in enumerate(steps):
            ny = first_y + i * LAYOUT_SPACING_Y
            node = self._controller.add_node(NodeType.ACTION, int(base_x), int(ny), step.action_type)
            self._controller.update_node_action(node.node_id, replace(step))
            self._canvas.add_node_visual(node)

            edge = self._controller.add_edge(prev_id, node.node_id)
            if edge:
                self._canvas.add_edge_visual(edge)

            prev_id = node.node_id

        # Connect last imported node → End
        edge = self._controller.add_edge(prev_id, "end")
        if edge:
            self._canvas.add_edge_visual(edge)

        # Move End below the last imported node (immutable update)
        end_node = graph.get_node("end")
        if end_node:
            updated_end = replace(
                end_node,
                pos_x=int(base_x),
                pos_y=first_y + len(steps) * LAYOUT_SPACING_Y,
            )
            graph.nodes["end"] = updated_end
            self._canvas.update_node_visual("end")

        self._update_status_bar()

    def _on_add_node(self, node_type: NodeType):
        if self._controller.is_executor_running:
            return
        cx, cy = self._canvas.viewport_center()
        cx, cy = self._find_free_position(cx, cy, node_type)
        self._add_node_at(node_type, cx, cy)

    def _edit_node_action(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return

        step = copy.deepcopy(node.action) if node.action else STEP_CLASSES[ActionType.CLICK_IMAGE]()

        def on_done(updated):
            self._controller.update_node_action(node_id, updated)
            self._canvas.update_node_visual(node_id)

        open_step_dialog(
            self.frame,
            step,
            f"{t('workflow.properties.edit_action')} — {node_id}",
            on_done=on_done,
        )

    def _edit_node_condition(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return

        condition = copy.deepcopy(node.condition) if node.condition else None

        def on_done(updated):
            self._controller.update_node_condition(node_id, updated)
            self._canvas.update_node_visual(node_id)

        open_condition_dialog(
            self.frame,
            condition,
            f"{t('workflow.properties.edit_condition')} — {node_id}",
            on_done=on_done,
        )

    def _edit_node_loop(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return
        result = simpledialog.askinteger(
            t("common.loop_count_label"),
            t("workflow.properties.loop_count_prompt"),
            parent=self.frame,
            initialvalue=node.loop_count,
            minvalue=0,
            maxvalue=9999,
        )
        if result is not None:
            node.loop_count = result
            self._canvas.update_node_visual(node_id)
            self._show_node_properties(node_id)
            self._append_log(
                t("workflow.msg.loop_set", node_id=node_id, count=result if result > 0 else "∞")
            )

    def _delete_node(self, node_id: str):
        if self._controller.is_executor_running:
            return
        self._canvas.remove_node_visual(node_id)
        self._controller.remove_node(node_id)
        if self._selected_node_id == node_id:
            self._selected_node_id = None
            self._prop_panel.show_empty()
        self._append_log(f"- {node_id}")
        self._update_status_bar()

    def _delete_selected_nodes(self, node_ids: list[str]):
        if self._controller.is_executor_running:
            return
        for nid in node_ids:
            self._canvas.remove_node_visual(nid)
            self._controller.remove_node(nid)
        self._selected_node_id = None
        self._prop_panel.show_empty()
        self._append_log(f"- {len(node_ids)} nodes")
        self._update_status_bar()

    # ── 右键菜单 ──────────────────────────────────────────

    def _close_active_popup(self) -> None:
        """关闭当前活跃的 NodeCreationPopup（非模态弹窗），防止堆积。"""
        popup = getattr(self, "_active_popup", None)
        if popup is not None:
            try:
                popup.destroy()
            except tk.TclError:
                pass
            self._active_popup = None

    def _popup_menu(self, menu: tk.Menu, screen_x: int, screen_y: int) -> None:
        """显示模态右键菜单（tk_popup 是阻塞的，无需跟踪生命周期）。"""
        try:
            menu.tk_popup(screen_x, screen_y)
        finally:
            menu.grab_release()

    def _show_node_context_menu(self, node_id: str, screen_x: int, screen_y: int):
        selected = self._canvas.get_selected_nodes()
        # 多选节点右键菜单
        if node_id in selected and len(selected) > 1:
            self._show_multi_select_context_menu(selected, screen_x, screen_y)
            return

        node = self._model.graph.get_node(node_id)
        if not node:
            return

        menu = tk.Menu(self.frame, tearoff=0)
        if node.node_type == NodeType.ACTION:
            menu.add_command(
                label=t("workflow.context.edit_action"),
                command=lambda: self._edit_node_action(node_id),
            )
        elif node.node_type == NodeType.CONDITION:
            menu.add_command(
                label=t("workflow.context.edit_condition"),
                command=lambda: self._edit_node_condition(node_id),
            )
        elif node.node_type == NodeType.LOOP:
            menu.add_command(
                label=t("workflow.context.edit_loop"),
                command=lambda: self._edit_node_loop(node_id),
            )

        menu.add_separator()
        state_text = (
            t("common.disable") if node.enabled else t("common.enable")
        )
        menu.add_command(
            label=state_text,
            command=lambda: (
                self._controller.toggle_node_enabled(node_id),
                self._canvas.update_node_visual(node_id),
                self._show_node_properties(node_id),
            ),
        )

        if node.node_type not in (NodeType.START, NodeType.END):
            menu.add_command(
                label=t("workflow.context.duplicate"),
                command=lambda: self._on_duplicate_node(node_id),
            )
            menu.add_separator()
            menu.add_command(
                label=t("common.delete"),
                command=lambda: self._delete_node(node_id),
            )

        self._popup_menu(menu, screen_x, screen_y)

    def _show_multi_select_context_menu(self, node_ids: set[str], screen_x: int, screen_y: int):
        """多选节点右键菜单"""
        menu = tk.Menu(self.frame, tearoff=0)
        ids = list(node_ids)
        menu.add_command(
            label=t("workflow.context.copy_nodes", count=len(ids)),
            command=lambda: self._on_copy(ids),
        )
        menu.add_command(
            label=t("workflow.context.duplicate_nodes", count=len(ids)),
            command=lambda: self._on_duplicate_selected(ids),
        )
        menu.add_separator()
        menu.add_command(
            label=t("workflow.context.delete_nodes", count=len(ids)),
            command=lambda: self._delete_selected_nodes(ids),
        )
        self._popup_menu(menu, screen_x, screen_y)

    def _on_duplicate_node(self, node_id: str):
        if self._controller.is_executor_running:
            return
        new_node = self._controller.duplicate_node(node_id)
        if new_node:
            self._canvas.add_node_visual(new_node)
            self._update_status_bar()

    def _show_canvas_context_menu(self, screen_x: int, screen_y: int,
                                   canvas_x: int | None = None,
                                   canvas_y: int | None = None):
        self._close_active_popup()

        if self._controller.is_executor_running:
            return

        wx, wy = (canvas_x, canvas_y) if canvas_x is not None else self._canvas.viewport_center()
        try:
            world_x, world_y = self._canvas.screen_to_world(wx, wy)
        except Exception:
            world_x, world_y = self._canvas.viewport_center()

        popup = NodeCreationPopup(
            self.frame, screen_x, screen_y,
            on_create_action=lambda at: self._create_action_at(at, world_x, world_y),
            on_create_flow=lambda nt: self._create_flow_at(nt, world_x, world_y),
        )
        self._active_popup = popup

    def _create_action_at(self, action_type: ActionType, wx: float, wy: float):
        self._add_node_at(NodeType.ACTION, wx, wy, action_type)

    def _create_flow_at(self, node_type: NodeType, wx: float, wy: float):
        self._add_node_at(node_type, wx, wy)

    def _show_edge_context_menu(self, edge_id: str, screen_x: int, screen_y: int):
        menu = tk.Menu(self.frame, tearoff=0)
        menu.add_command(
            label=t("workflow.context.delete_edge"),
            command=lambda: self._on_delete_edge(edge_id),
        )
        self._popup_menu(menu, screen_x, screen_y)

    def _on_delete_edge(self, edge_id: str):
        if self._controller.is_executor_running:
            return
        self._canvas.remove_edge_visual(edge_id)
        self._controller.remove_edge(edge_id)
        self._append_log(f"- edge:{edge_id}")
        self._prop_panel.show_empty()
        self._update_status_bar()

    # ── 监控器 ──────────────────────────────────────────────

    def _on_add_monitor(self):
        if self._controller.is_executor_running:
            return
        from src.core.monitor import MonitorConfig

        monitor = MonitorConfig(name=t("workflow.msg.new_monitor"))
        open_monitor_dialog(
            self.frame,
            monitor,
            t("workflow.msg.add_monitor"),
            on_done=lambda m: (
                self._controller.add_monitor(m),
                self._refresh_monitor_list(),
            ),
        )

    def _refresh_monitor_list(self):
        self._monitor_tree.delete(*self._monitor_tree.get_children())
        for i, m in enumerate(self._controller.get_monitors()):
            action_text = m.handler_action.value if hasattr(m.handler_action, "value") else str(m.handler_action)
            self._monitor_tree.insert("", tk.END, iid=str(i), values=(
                "✓" if m.enabled else "--",
                m.name,
                action_text,
                f"{m.check_interval}s",
            ))

    def _on_edit_monitor(self):
        sel = self._monitor_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        monitors = self._controller.get_monitors()
        if idx < 0 or idx >= len(monitors):
            return
        mon = copy.copy(monitors[idx])
        open_monitor_dialog(
            self.frame, mon, t("common.edit"),
            on_done=lambda result: (
                self._controller.update_monitor(idx, result),
                self._refresh_monitor_list(),
            ),
        )

    def _on_delete_monitor(self):
        sel = self._monitor_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        monitors = self._controller.get_monitors()
        if idx < 0 or idx >= len(monitors):
            return
        from tkinter import messagebox as _mb
        if _mb.askyesno(
            t("common.confirm"), t("chain.msg.confirm_delete_monitor", name=monitors[idx].name)
        ):
            self._controller.remove_monitor(idx)
            self._refresh_monitor_list()

    def _on_toggle_monitor(self):
        sel = self._monitor_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        monitors = self._controller.get_monitors()
        if idx < 0 or idx >= len(monitors):
            return
        mon = copy.copy(monitors[idx])
        mon.enabled = not mon.enabled
        self._controller.update_monitor(idx, mon)
        self._refresh_monitor_list()

    # ── 复制/粘贴 ──────────────────────────────────────────

    def _on_copy(self, node_ids: list[str]) -> None:
        if not node_ids:
            return
        self._clipboard = self._controller.copy_nodes(node_ids)
        self._paste_offset = 0

    def _on_paste(self) -> None:
        if not self._clipboard:
            return
        self._paste_offset += 1
        offset = self._paste_offset * self._controller.PASTE_OFFSET
        new_nodes = self._controller.paste_nodes(self._clipboard, offset_x=offset, offset_y=offset)
        for n in new_nodes:
            self._canvas.add_node_visual(n)
        self._update_status_bar()

    def _on_duplicate_selected(self, node_ids: list[str]) -> None:
        if not node_ids or self._controller.is_executor_running:
            return
        nodes = self._controller.copy_nodes(node_ids)
        new_nodes = self._controller.paste_nodes(
            nodes,
            offset_x=self._controller.DUPLICATE_OFFSET_X,
            offset_y=self._controller.DUPLICATE_OFFSET_Y,
        )
        for n in new_nodes:
            self._canvas.add_node_visual(n)
        self._update_status_bar()

    # ── Blender 风格交互 ──────────────────────────────────────

    def _on_edge_reconnected(self, edge_id: str, side: str,
                             new_node_id: str, new_port: str, **_kw) -> None:
        """处理边端点拖拽重连"""
        if self._controller.is_executor_running:
            return
        graph = self._model.graph
        edge = graph.get_edge(edge_id)
        if not edge:
            return
        # 源端重连: 新端口标签决定新的边标签; 目标端重连: 保持原有边标签
        if side == "source":
            edge_label = FlowGraph.port_label_to_edge_label(new_port)
        else:
            edge_label = edge.label
        from_id = new_node_id if side == "source" else edge.from_node
        to_id = new_node_id if side == "target" else edge.to_node
        ok, _reason = graph.can_connect(from_id, to_id, edge_label)
        if not ok:
            return
        cmd = self._controller.reconnect_edge(edge_id, side, new_node_id, new_port)
        if cmd:
            self._canvas.remove_edge_visual(edge_id)
            edge = self._model.graph.get_edge(edge_id)
            if edge:
                self._canvas.add_edge_visual(edge)
            self._append_log(t("workflow.msg.edge_reconnected", edge_id=edge_id))
        self._update_status_bar()

    def _on_auto_insert(self, edge_id: str, node_id: str,
                        x: int, y: int, **_kw) -> None:
        """处理拖拽节点到连线上自动插入"""
        if self._controller.is_executor_running:
            return
        # 更新节点位置（直接修改，不创建独立 undo 条目）
        node = self._model.graph.get_node(node_id)
        if node:
            node.pos_x = x
            node.pos_y = y
        # 移除旧边视觉
        self._canvas.remove_edge_visual(edge_id)
        # 执行自动插入命令
        cmd = self._controller.auto_insert(edge_id, node_id)
        if cmd:
            # 更新节点视觉位置（不重建边，因为新边尚未添加）
            self._canvas.update_node_visual(node_id)
            # 添加两条新边视觉 + 收集邻接节点
            graph = self._model.graph
            neighbor_ids: set[str] = set()
            for edge in graph.get_edges_for_node(node_id):
                if not self._canvas.has_edge_visual(edge.edge_id):
                    self._canvas.add_edge_visual(edge)
                neighbor_ids.add(edge.from_node)
                neighbor_ids.add(edge.to_node)
            for nid in neighbor_ids:
                self._canvas.update_node_visual(nid)
            self._append_log(
                t("workflow.msg.auto_insert", node_id=node_id, edge_id=edge_id)
            )
        else:
            # 插入失败，恢复旧边视觉
            edge = self._model.graph.get_edge(edge_id)
            if edge:
                self._canvas.add_edge_visual(edge)
        self._update_status_bar()

    # ── 搜索 ──────────────────────────────────────────────

    def _open_search(self) -> None:
        if self._search_bar is None:
            self._search_bar = SearchBar(self._canvas, self._on_search_navigate)
        self._search_bar.update_graph(self._model.graph)
        self._search_bar.place(relx=0.5, y=4, anchor=tk.N)
        self._search_bar.grab_focus()

    def _close_search(self) -> None:
        if self._search_bar:
            self._search_bar.place_forget()

    def _on_search_navigate(self, node_id: str) -> None:
        self._close_search()
        if not node_id:
            return
        self._selected_node_id = node_id
        self._canvas.highlight_node(node_id)
        node = self._model.graph.get_node(node_id)
        if node:
            self._canvas.navigate_to_center(node.pos_x, node.pos_y)
        self._show_node_properties(node_id)
