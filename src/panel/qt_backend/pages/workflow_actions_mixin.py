"""QtWorkflowActionsMixin — PySide6 canvas events, CRUD, context menus, copy/paste, search.

替代 tkinter WorkflowActionsMixin，使用 QMenu + QtGraphCanvas API。
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint
from PySide6.QtWidgets import QMenu, QTreeWidgetItem

from src.core.action import ActionType
from src.core.flow import FlowNode, NodeType
from src.core.step_types import STEP_CLASSES
from src.panel.canvas.node_shared import node_size
from src.panel.models.enums import EdgeLabel
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.panel.qt_backend.canvas.graph_canvas import QtGraphCanvas
    from src.panel.controllers.workflow_controller import WorkflowController
    from src.panel.models.chain_model import ChainModel


class QtWorkflowActionsMixin:
    """Canvas event dispatch + node/edge CRUD + context menus.

    Required self attributes:
        _model, _canvas, _controller, _selected_node_id,
        _clipboard, _paste_offset, _ring_log
    """

    if TYPE_CHECKING:
        _canvas: QtGraphCanvas
        _clipboard: list[FlowNode]
        _controller: WorkflowController
        _model: ChainModel
        _paste_offset: int
        _selected_node_id: str | None

        def _append_log(self, msg: str) -> None: ...
        def _on_redo(self) -> None: ...
        def _on_undo(self) -> None: ...
        def _show_node_properties(self, node_id: str) -> None: ...
        def _show_edge_properties(self, edge_id: str) -> None: ...
        def _clear_props(self) -> None: ...
        def _update_status_bar(self) -> None: ...

    # ── Canvas event callback ──────────────────────────────

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
                    kwargs["node_id"], kwargs["world_x"], kwargs["world_y"],
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
                edge = self._controller.add_edge(
                    kwargs["from_node"], kwargs["to_node"], kwargs.get("label", EdgeLabel.DEFAULT),
                )
                if edge is None:
                    self._append_log(t("workflow.msg.edge_failed"))
                else:
                    self._canvas.render_graph(self._model.graph)
                self._update_status_bar()
            case "edge_context_menu":
                self._show_edge_context_menu(
                    kwargs["edge_id"], kwargs["screen_x"], kwargs["screen_y"],
                )
            case "canvas_deselected" | "nodes_selected":
                self._selected_node_id = None
                self._clear_props()
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
                    kwargs["node_id"], kwargs["screen_x"], kwargs["screen_y"],
                )
            case "canvas_context_menu":
                self._show_canvas_context_menu(
                    kwargs["screen_x"], kwargs["screen_y"],
                )
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
            case "toggle_minimap":
                pass

    # ── Node operations ────────────────────────────────────

    def _add_node_at(
        self,
        node_type: NodeType,
        x: float,
        y: float,
        action_type: ActionType | None = None,
    ) -> None:
        new_node = self._controller.add_node(node_type, int(x), int(y), action_type)
        self._canvas.render_graph(self._model.graph)
        self._append_log(f"+ {new_node.describe()}")
        self._update_status_bar()

    def _viewport_center(self) -> tuple[float, float]:
        rect = self._canvas.mapToScene(self._canvas.viewport().rect()).boundingRect()
        c = rect.center()
        return c.x(), c.y()

    def _on_add_action_node(self, action_type: ActionType):
        if self._controller.is_executor_running:
            return
        cx, cy = self._viewport_center()
        x, y = self._find_free_position(cx, cy)
        self._add_node_at(NodeType.ACTION, x, y, action_type)

    def _on_add_node(self, node_type: NodeType):
        if self._controller.is_executor_running:
            return
        cx, cy = self._viewport_center()
        x, y = self._find_free_position(cx, cy)
        self._add_node_at(node_type, x, y)

    _PLACEMENT_OFFSET_X = 30
    _PLACEMENT_OFFSET_Y = 20

    def _find_free_position(self, base_x: float, base_y: float) -> tuple[float, float]:
        """Shift position down/right if overlapping existing nodes."""
        x, y = base_x, base_y
        nodes = self._model.graph.nodes.values() if self._model.graph.nodes else []

        for _ in range(50):
            overlap = False
            for n in nodes:
                nw, nh = node_size(n)
                if (abs(x - n.pos_x) < max(nw, 80) and abs(y - n.pos_y) < max(nh, 60)):
                    overlap = True
                    break
            if not overlap:
                return x, y
            x += self._PLACEMENT_OFFSET_X
            y += self._PLACEMENT_OFFSET_Y

        return x, y

    _DEFAULT_NODE_X = 300
    _DEFAULT_NODE_Y = 40
    _NODE_SPACING_Y = 100

    def _import_steps(self, steps) -> None:
        if not steps:
            return

        graph = self._model.graph
        end_incoming = graph.get_incoming_edges("end")
        last_node_id = "start"
        for e in end_incoming:
            if e.from_node != "start":
                last_node_id = e.from_node

        for e in graph.get_outgoing_edges(last_node_id):
            if e.to_node == "end":
                self._controller.remove_edge(e.edge_id)

        anchor = graph.get_node(last_node_id)
        base_x = anchor.pos_x if anchor and anchor.pos_x else self._DEFAULT_NODE_X
        base_y = anchor.pos_y if anchor and anchor.pos_y else self._DEFAULT_NODE_Y
        first_y = base_y + self._NODE_SPACING_Y

        prev_id: str = last_node_id

        for i, step in enumerate(steps):
            ny = first_y + i * self._NODE_SPACING_Y
            node = self._controller.add_node(NodeType.ACTION, int(base_x), int(ny), step.action_type)
            self._controller.update_node_action(node.node_id, replace(step))

            edge = self._controller.add_edge(prev_id, node.node_id)
            prev_id = node.node_id

        edge = self._controller.add_edge(prev_id, "end")

        end_node = graph.get_node("end")
        if end_node:
            updated_end = replace(
                end_node,
                pos_x=int(base_x),
                pos_y=first_y + len(steps) * self._NODE_SPACING_Y,
            )
            graph.nodes["end"] = updated_end

        self._canvas.render_graph(graph)
        self._update_status_bar()

    def _edit_node_action(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return

        step = copy.deepcopy(node.action) if node.action else STEP_CLASSES[ActionType.CLICK_IMAGE]()

        def on_done(updated):
            self._controller.update_node_action(node_id, updated)
            self._canvas.update_node_position(node_id)

        from src.panel.qt_backend.dialogs.step_dialogs import open_step_dialog
        open_step_dialog(self, step, f"{t('workflow.properties.edit_action')} — {node_id}", on_done=on_done)

    def _edit_node_condition(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return

        condition = copy.deepcopy(node.condition) if node.condition else None

        def on_done(updated):
            self._controller.update_node_condition(node_id, updated)
            self._canvas.update_node_position(node_id)

        from src.panel.qt_backend.dialogs.condition_dialog import open_condition_dialog
        open_condition_dialog(
            self, condition,
            f"{t('workflow.properties.edit_condition')} — {node_id}",
            on_done=on_done,
        )

    def _edit_node_loop(self, node_id: str):
        node = self._model.graph.get_node(node_id)
        if not node:
            return
        result, ok = self._ask_int(
            t("common.loop_count_label"),
            t("workflow.properties.loop_count_prompt"),
            value=node.loop_count, min_val=0, max_val=9999,
        )
        if ok:
            updated = replace(node, loop_count=result)
            self._model.graph.nodes[node_id] = updated
            self._canvas.update_node_position(node_id)
            self._show_node_properties(node_id)
            self._append_log(
                t("workflow.msg.loop_set", node_id=node_id, count=result if result > 0 else "∞"),
            )

    def _delete_node(self, node_id: str):
        if self._controller.is_executor_running:
            return
        self._controller.remove_node(node_id)
        self._canvas.render_graph(self._model.graph)
        if self._selected_node_id == node_id:
            self._selected_node_id = None
            self._clear_props()
        self._append_log(f"- {node_id}")
        self._update_status_bar()

    def _delete_selected_nodes(self, node_ids: list[str]):
        if self._controller.is_executor_running:
            return
        for nid in node_ids:
            self._controller.remove_node(nid)
        self._canvas.render_graph(self._model.graph)
        self._selected_node_id = None
        self._clear_props()
        self._append_log(f"- {len(node_ids)} nodes")
        self._update_status_bar()

    # ── Context menus ──────────────────────────────────────

    def _show_node_context_menu(self, node_id: str, screen_x: int, screen_y: int):
        node = self._model.graph.get_node(node_id)
        if not node:
            return

        menu = QMenu(self)

        if node.node_type == NodeType.ACTION:
            menu.addAction(t("workflow.context.edit_action"), lambda: self._edit_node_action(node_id))
        elif node.node_type == NodeType.CONDITION:
            menu.addAction(t("workflow.context.edit_condition"), lambda: self._edit_node_condition(node_id))
        elif node.node_type == NodeType.LOOP:
            menu.addAction(t("workflow.context.edit_loop"), lambda: self._edit_node_loop(node_id))

        menu.addSeparator()
        state_text = t("common.disable") if node.enabled else t("common.enable")

        def _toggle_enabled():
            self._controller.toggle_node_enabled(node_id)
            self._canvas.update_node_position(node_id)
            self._show_node_properties(node_id)

        menu.addAction(state_text, _toggle_enabled)

        if node.node_type not in (NodeType.START, NodeType.END):
            menu.addAction(t("workflow.context.duplicate"), lambda: self._on_duplicate_node(node_id))
            menu.addSeparator()
            menu.addAction(t("common.delete"), lambda: self._delete_node(node_id))

        menu.exec(QPoint(int(screen_x), int(screen_y)))

    def _show_edge_context_menu(self, edge_id: str, screen_x: int, screen_y: int):
        menu = QMenu(self)
        menu.addAction(t("workflow.context.delete_edge"), lambda: self._on_delete_edge(edge_id))
        menu.exec(QPoint(int(screen_x), int(screen_y)))

    def _show_canvas_context_menu(self, screen_x: int, screen_y: int):
        if self._controller.is_executor_running:
            return

        from src.panel.qt_backend.dialogs.node_creation_popup import QtNodeCreationPopup

        rect = self._canvas.mapToScene(self._canvas.viewport().rect()).boundingRect()
        world_x, world_y = rect.center().x(), rect.center().y()

        popup = QtNodeCreationPopup(
            self, int(screen_x), int(screen_y),
            on_create_action=lambda at: self._create_action_at(at, world_x, world_y),
            on_create_flow=lambda nt: self._create_flow_at(nt, world_x, world_y),
        )

    def _create_action_at(self, action_type: ActionType, wx: float, wy: float):
        self._add_node_at(NodeType.ACTION, wx, wy, action_type)

    def _create_flow_at(self, node_type: NodeType, wx: float, wy: float):
        self._add_node_at(node_type, wx, wy)

    def _on_delete_edge(self, edge_id: str):
        if self._controller.is_executor_running:
            return
        self._controller.remove_edge(edge_id)
        self._canvas.render_graph(self._model.graph)
        self._append_log(f"- edge:{edge_id}")
        self._clear_props()
        self._update_status_bar()

    def _on_duplicate_node(self, node_id: str):
        if self._controller.is_executor_running:
            return
        new_node = self._controller.duplicate_node(node_id)
        if new_node:
            self._canvas.render_graph(self._model.graph)
            self._update_status_bar()

    # ── Monitors ──────────────────────────────────────────

    def _on_add_monitor(self):
        if self._controller.is_executor_running:
            return
        from src.core.monitor import MonitorConfig
        from src.panel.qt_backend.dialogs.monitor_dialog import open_monitor_dialog

        monitor = MonitorConfig(name=t("workflow.msg.new_monitor"))
        open_monitor_dialog(
            self, monitor, t("workflow.msg.add_monitor"),
            on_done=lambda m: (
                self._controller.add_monitor(m),
                self._refresh_monitor_list(),
            ),
        )

    def _get_selected_monitor_index(self) -> int | None:
        if not hasattr(self, "_monitor_tree") or self._monitor_tree is None:
            return None
        sel = self._monitor_tree.selectedItems()
        if not sel:
            return None
        idx = int(self._monitor_tree.indexOfTopLevelItem(sel[0]))
        monitors = self._controller.get_monitors()
        if idx < 0 or idx >= len(monitors):
            return None
        return idx

    def _refresh_monitor_list(self):
        if not hasattr(self, "_monitor_tree") or self._monitor_tree is None:
            return
        self._monitor_tree.clear()
        for i, m in enumerate(self._controller.get_monitors()):
            action_text = m.handler_action.value if hasattr(m.handler_action, "value") else str(m.handler_action)
            item = QTreeWidgetItem([
                "✓" if m.enabled else "--",
                m.name,
                action_text,
                f"{m.check_interval}s",
            ])
            self._monitor_tree.addTopLevelItem(item)

    def _on_edit_monitor(self):
        idx = self._get_selected_monitor_index()
        if idx is None:
            return
        monitors = self._controller.get_monitors()
        mon = copy.copy(monitors[idx])
        from src.panel.qt_backend.dialogs.monitor_dialog import open_monitor_dialog
        open_monitor_dialog(
            self, mon, t("common.edit"),
            on_done=lambda result: (
                self._controller.update_monitor(idx, result),
                self._refresh_monitor_list(),
            ),
        )

    def _on_delete_monitor(self):
        idx = self._get_selected_monitor_index()
        if idx is None:
            return
        monitors = self._controller.get_monitors()
        if self._ask_yes_no(
            t("common.confirm"),
            t("chain.msg.confirm_delete_monitor", name=monitors[idx].name),
        ):
            self._controller.remove_monitor(idx)
            self._refresh_monitor_list()

    def _on_toggle_monitor(self):
        idx = self._get_selected_monitor_index()
        if idx is None:
            return
        monitors = self._controller.get_monitors()
        mon = copy.copy(monitors[idx])
        mon.enabled = not mon.enabled
        self._controller.update_monitor(idx, mon)
        self._refresh_monitor_list()

    # ── Copy/Paste ────────────────────────────────────────

    def _on_copy(self, node_ids: list[str]) -> None:
        if not node_ids:
            return
        self._clipboard = self._controller.copy_nodes(node_ids)
        self._paste_offset = 0

    def _on_paste(self) -> None:
        if not self._clipboard:
            return
        self._paste_offset += 1
        offset = self._paste_offset * 30
        new_nodes = self._controller.paste_nodes(list(self._clipboard), offset_x=offset, offset_y=offset)
        self._canvas.render_graph(self._model.graph)
        self._update_status_bar()

    def _on_duplicate_selected(self, node_ids: list[str]) -> None:
        if not node_ids or self._controller.is_executor_running:
            return
        nodes = self._controller.copy_nodes(node_ids)
        new_nodes = self._controller.paste_nodes(nodes, offset_x=40, offset_y=40)
        self._canvas.render_graph(self._model.graph)
        self._update_status_bar()

    # ── Search ──────────────────────────────────────────────

    def _open_search(self) -> None:
        from PySide6.QtWidgets import QListWidget, QVBoxLayout, QFrame
        from src.panel.canvas.theme import current_theme
        from src.panel.qt_backend.widgets import themed_entry

        if hasattr(self, "_search_frame") and self._search_frame is not None:
            self._search_frame.show()
            self._search_entry.setFocus()
            return

        th = current_theme()
        frame = QFrame(self._canvas)
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.bg_surface};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(6, 4, 6, 4)

        entry = themed_entry(None, placeholder=t("workflow.search.placeholder"))
        layout.addWidget(entry)

        result_list = QListWidget()
        result_list.setMaximumHeight(120)
        result_list.setStyleSheet(f"""
            QListWidget {{
                background-color: {th.bg_surface};
                color: {th.text_primary};
                border: none;
                font-size: 12px;
            }}
            QListWidget::item:selected {{
                background-color: {th.accent_blue};
                color: {th.text_on_accent};
            }}
        """)
        layout.addWidget(result_list)

        self._search_frame = frame
        self._search_entry = entry
        self._search_results = result_list
        self._search_filtered: list[tuple[str, str]] = []

        entry.textChanged.connect(self._on_search_input)
        result_list.itemDoubleClicked.connect(self._on_search_result_selected)
        entry.returnPressed.connect(lambda: self._on_search_result_activated())

        self._update_search_geometry()
        self._canvas.installEventFilter(self)
        frame.show()
        entry.setFocus()

    def _update_search_geometry(self) -> None:
        if not hasattr(self, "_search_frame") or self._search_frame is None:
            return
        vw = self._canvas.viewport().width()
        self._search_frame.setGeometry(vw // 2 - 150, 4, 300, 160)

    def eventFilter(self, obj, event) -> bool:
        if obj is self._canvas and event.type() == QEvent.Type.Resize:
            self._update_search_geometry()
        return False

    def _close_search(self) -> None:
        if hasattr(self, "_search_frame") and self._search_frame is not None:
            self._search_frame.hide()
            self._canvas.removeEventFilter(self)

    def _on_search_input(self, text: str) -> None:
        if not hasattr(self, "_search_results"):
            return
        query = text.strip().lower()
        self._search_results.clear()
        self._search_filtered.clear()

        if not query or not self._model.graph:
            return

        for node in self._model.graph.nodes.values():
            desc = node.describe().lower()
            nid = node.node_id.lower()
            comment = (node.comment or "").lower()
            if query in desc or query in nid or query in comment:
                display = node.describe()
                self._search_filtered.append((node.node_id, display))
                self._search_results.addItem(display)

        if not self._search_filtered:
            self._search_results.addItem(t("workflow.search.no_results"))

    def _on_search_result_selected(self, item) -> None:
        idx = self._search_results.row(item)
        if idx < len(self._search_filtered):
            self._on_search_navigate(self._search_filtered[idx][0])

    def _on_search_result_activated(self) -> None:
        if self._search_filtered:
            self._on_search_navigate(self._search_filtered[0][0])

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
