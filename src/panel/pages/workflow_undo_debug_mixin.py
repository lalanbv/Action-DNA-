"""撤销/重做视觉更新 + 调试控制 + 执行/导出操作。"""

from __future__ import annotations

import tkinter as tk

from src.core.debug.debugger import DebuggerState
from src.core.editor.commands.add_node_command import AddNodeCommand
from src.core.editor.commands.remove_node_command import RemoveNodeCommand
from src.core.editor.commands.add_edge_command import AddEdgeCommand
from src.core.editor.commands.remove_edge_command import RemoveEdgeCommand
from src.core.editor.commands.auto_insert_command import AutoInsertCommand
from src.core.editor.commands.move_node_command import MoveNodeCommand
from src.core.editor.commands.reconnect_edge_command import ReconnectEdgeCommand
from src.core.editor.commands.edit_property_command import EditPropertyCommand
from src.core.editor.commands.edit_edge_property_command import EditEdgePropertyCommand
from src.core.editor.commands.composite_command import CompositeCommand
from src.core.flow import ensure_loop_edge, remove_loop_edge
from src.core.logger import log
from src.utils.i18n import t


class WorkflowUndoDebugMixin:
    """撤销/重做 + 调试控制 Mixin。

    要求宿主类提供:
      - self._controller: WorkflowController
      - self._model: ChainModel
      - self._canvas: GraphCanvas
      - self._debugger: Debugger
      - self._selected_node_id: str | None
      - self._show_toast(message)
      - self._update_status_bar()
      - self._append_log(msg)
      - self._show_node_properties(node_id)
      - self.app: PanelApp
    """

    # ── 撤销 / 重做 ──────────────────────────────────────────

    def _on_undo(self):
        cmd = self._controller.undo()
        if cmd:
            self._apply_command_visual(cmd, is_undo=True)
            self._show_toast(t("workflow.msg.undo"))
            self._update_status_bar()

    def _on_redo(self):
        cmd = self._controller.redo()
        if cmd:
            self._apply_command_visual(cmd, is_undo=False)
            self._show_toast(t("workflow.msg.redo"))
            self._update_status_bar()

    def _apply_command_visual(self, cmd, *, is_undo: bool) -> None:
        """根据命令类型做增量画布更新，避免全量 render_graph"""
        graph = self._model.graph

        if isinstance(cmd, CompositeCommand):
            for sub in cmd.commands:
                self._apply_command_visual(sub, is_undo=is_undo)
            return

        if isinstance(cmd, AddNodeCommand):
            if is_undo:
                self._canvas.remove_node_visual(cmd.node_id)
            else:
                node = graph.get_node(cmd.node_id)
                if node:
                    self._canvas.add_node_visual(node)
            return

        if isinstance(cmd, RemoveNodeCommand):
            if is_undo:
                node = graph.get_node(cmd.node_id)
                if node:
                    self._canvas.add_node_visual(node)
                    for edge in graph.edges:
                        if edge.from_node == cmd.node_id or edge.to_node == cmd.node_id:
                            self._canvas.add_edge_visual(edge)
            else:
                self._canvas.remove_node_visual(cmd.node_id)
            return

        if isinstance(cmd, AddEdgeCommand):
            if is_undo:
                self._canvas.remove_edge_visual(cmd.edge_id)
            else:
                edge = graph.get_edge(cmd.edge_id)
                if edge:
                    self._canvas.add_edge_visual(edge)
            return

        if isinstance(cmd, RemoveEdgeCommand):
            if is_undo:
                edge = graph.get_edge(cmd.edge_id)
                if edge:
                    self._canvas.add_edge_visual(edge)
            else:
                self._canvas.remove_edge_visual(cmd.edge_id)
            return

        if isinstance(cmd, ReconnectEdgeCommand):
            edge = graph.get_edge(cmd.edge_id)
            if edge:
                self._canvas.remove_edge_visual(cmd.edge_id)
                self._canvas.add_edge_visual(edge)
            return

        if isinstance(cmd, AutoInsertCommand):
            self._canvas.render_graph(graph)
            return

        if isinstance(cmd, MoveNodeCommand):
            self._canvas.update_node_visual(cmd.node_id)
            return

        if isinstance(cmd, EditEdgePropertyCommand):
            if cmd.edge_id:
                self._canvas.refresh_edge_visual(cmd.edge_id)
            return

        if isinstance(cmd, EditPropertyCommand):
            if cmd.node_id:
                self._canvas.update_node_visual(cmd.node_id)
            return

        self._canvas.render_graph(graph)

    def _on_undo_state_changed(self):
        can_undo = self._controller.undo_manager.can_undo
        can_redo = self._controller.undo_manager.can_redo
        if hasattr(self, "_btn_undo"):
            self._btn_undo.configure(state=tk.NORMAL if can_undo else tk.DISABLED)
        if hasattr(self, "_btn_redo"):
            self._btn_redo.configure(state=tk.NORMAL if can_redo else tk.DISABLED)

    # ── 调试控制 ──────────────────────────────────────────

    def _on_debug_toggle(self):
        state = self._debugger.state
        if state == DebuggerState.IDLE:
            self._debugger.start()
            self._append_log(t("workflow.debug.on"))
        else:
            self._debugger.stop()
            self._append_log(t("workflow.debug.off"))
        self._update_debug_buttons()

    def _on_toggle_breakpoint(self):
        node_id = self._selected_node_id
        if not node_id:
            return
        bp = self._debugger.breakpoints.get_breakpoint(node_id)
        if bp:
            self._debugger.breakpoints.remove_breakpoint(node_id)
            self._append_log(t("workflow.debug.breakpoint_removed", node_id=node_id))
        else:
            self._debugger.breakpoints.add_breakpoint(node_id)
            self._append_log(t("workflow.debug.breakpoint_set", node_id=node_id))
        self._canvas.update_node_visual(node_id)

    def _on_debug_step(self):
        self._debugger.step_over()
        self._update_debug_buttons()

    def _on_debug_resume(self):
        self._debugger.resume()
        self._update_debug_buttons()

    def _on_debug_stop(self):
        self._debugger.stop()
        self._update_debug_buttons()

    def _on_debugger_state_changed(self, _old_state: DebuggerState, _new_state: DebuggerState):
        self.app.root.after(0, self._update_debug_buttons)

    def _on_debugger_breakpoint_hit(self, node_id: str):
        self.app.root.after(0, self._highlight_debug_node, node_id)

    def _highlight_debug_node(self, node_id: str):
        self._canvas.highlight_node(node_id)
        self._selected_node_id = node_id
        self._show_node_properties(node_id)
        self._append_log(t("workflow.debug.breakpoint_hit", node_id=node_id))

    def _update_debug_buttons(self):
        state = self._debugger.state
        is_active = state != DebuggerState.IDLE
        is_paused = state == DebuggerState.PAUSED

        if hasattr(self, "_btn_debug_toggle"):
            self._btn_debug_toggle.configure(
                text=t("workflow.debug.stop") if is_active else t("workflow.debug.toggle"),
            )
        if hasattr(self, "_btn_step"):
            self._btn_step.configure(state=tk.NORMAL if is_paused else tk.DISABLED)
        if hasattr(self, "_btn_debug_resume"):
            self._btn_debug_resume.configure(state=tk.NORMAL if is_paused else tk.DISABLED)
        if hasattr(self, "_btn_debug_stop"):
            self._btn_debug_stop.configure(state=tk.NORMAL if is_active else tk.DISABLED)

    # ── 执行控制 ──────────────────────────────────────────

    def _on_start(self):  # pylint: disable=broad-exception-caught
        try:
            self._model.graph.loop = self._loop_var.get()
            self._model.graph.loop_count = 0 if self._loop_var.get() else 1
            self._controller.start_chain()
        except Exception as e:
            from tkinter import messagebox
            messagebox.showerror(t("workflow.msg.start_failed"), str(e))

    def _on_pause(self):
        self._controller.pause_chain()

    def _on_resume(self):
        self._controller.resume_chain()

    def _on_stop(self):
        self._controller.stop_chain()

    # ── 脚本导出 ──────────────────────────────────────────

    def _on_export_script(self):  # pylint: disable=broad-exception-caught
        from pathlib import Path
        from tkinter import filedialog, messagebox
        from src.core.io.script_exporter import ScriptExporter

        graph = self._model.graph
        if not graph or not graph.nodes:
            messagebox.showwarning(
                t("chain.export"), t("workflow.msg.start_failed"),
            )
            return

        name = self._model.current_profile_name or "untitled"
        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python", "*.py"), ("All", "*.*")],
            initialfile=f"{name}.py",
            title=t("chain.msg.export_title"),
        )
        if not path:
            return

        try:
            exporter = ScriptExporter()
            result = exporter.export(graph, Path(path), profile_name=name)
            self._append_log(
                t("chain.msg.exported").format(path=str(result.output_path))
            )
        except Exception as e:
            log.error(t("workflow.log.export_failed", error=e))
            messagebox.showerror(t("chain.export"), t("chain.msg.export_failed"))

    # ── 循环边控制 ──────────────────────────────────────────

    def _on_loop_toggled(self, *_):
        if not self._loop_var.get():
            remove_loop_edge(self._model.graph)
        else:
            ensure_loop_edge(self._model.graph)
        self._canvas.render_graph(self._model.graph)
