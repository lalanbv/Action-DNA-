"""TkActionChainProfileMixin — 动作链页面的配置文件 CRUD + 区域选择 + 执行控制 + 事件处理。

要求宿主类提供:
  - self.model: ChainModel
  - self.controller: ActionChainController
  - self.step_ring: StepRing | None
  - self.step_props: StepPropertyPanel
  - self.loop_controls: LoopControls
  - self.run_controls: RunControls
  - self.var_status: tk.StringVar
  - self.status_bar: StatusBar
  - self.profile_bar: ProfileBar
  - self.region_bar: RegionBar
  - self.mon_tree: ttk.Treeview
  - self._mon_count_var: tk.StringVar
  - self._btn_mon_edit, _btn_mon_toggle, _btn_mon_delete
  - self._paned: tk.PanedWindow
  - self._ring_log: RingBufferLog
  - self.app: PanelApp
  - self._on_step_selected()
  - self._refresh_profile_list()
  - self._refresh_monitor_list()
  - self._pick_region(callback)
  - self.frame: tk.Frame
"""

from __future__ import annotations

import copy
import logging
import os
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import TYPE_CHECKING

from src.core.exporter import FlowExporter
from src.core.importer import FlowImporter
from src.core.monitor import MonitorConfig
from src.core.flow import NodeType
from src.core.events.event_names import EventName
from src.panel.models.chain_model import ExecutorState
from src.panel.pages.profile_ops_mixin import ProfileOpsMixin
from src.utils.i18n import t
from src.utils.paths import get_profiles_dir

if TYPE_CHECKING:
    from tkinter import ttk

    from src.panel.app import PanelApp
    from src.panel.components.loop_controls import LoopControls
    from src.panel.components.status_bar import StatusBar
    from src.panel.controllers.action_chain_controller import ActionChainController
    from src.panel.execution_status import ExecutionStatusTicker
    from src.panel.models.chain_model import ChainModel
    from src.utils.step_ring import StepRing

logger = logging.getLogger(__name__)


class TkActionChainProfileMixin(ProfileOpsMixin):
    """配置文件操作 + 区域选择 + 执行控制 + 事件回调 Mixin。"""

    # 宿主类提供的属性（仅类型声明，运行时由宿主 __init__ 赋值；见模块 docstring 契约）
    model: ChainModel
    controller: ActionChainController
    step_ring: StepRing | None
    loop_controls: LoopControls
    status_bar: StatusBar
    mon_tree: ttk.Treeview
    app: PanelApp
    _exec_ticker: ExecutionStatusTicker

    profile_i18n_prefix = "chain"

    def _refresh_profiles(self):
        self._refresh_profile_list()

    def _get_selected_profile_name(self):
        return self.profile_bar.get_selected()

    def _ask_string(self, title, prompt):
        result = simpledialog.askstring(title, prompt, parent=self.app.root)
        return (result, result is not None)

    def _show_info(self, title, message):
        messagebox.showinfo(title, message)

    def _show_error(self, title, message):
        messagebox.showerror(title, message)

    def _ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    def _pre_save_hook(self):
        self._sync_loop_config()

    # ── 配置文件导入导出 ──

    def _on_export_profile(self):
        from tkinter import filedialog

        path = filedialog.asksaveasfilename(
            title=t("chain.msg.export_title"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
            initialfile=f"{self.model.graph.name or 'flow'}.json",
        )
        if not path:
            return
        temp_name = f"__export_{id(self)}"
        try:
            self._sync_loop_config()
            profile_dir = self.controller.save_profile_to_dir(temp_name, self.model.graph)
            data = FlowExporter.export(self.model.graph, profile_dir)
            FlowExporter.save_file(data, path)
            self._append_log(t("chain.msg.exported", path=path))
        except (OSError, ValueError, RuntimeError) as e:
            messagebox.showerror(t("chain.msg.export_failed"), str(e))
        finally:
            try:
                self.controller.delete_profile(temp_name)
            except (OSError, RuntimeError):
                pass

    def _on_import_profile(self):
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title=t("chain.msg.import_title"),
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if not path:
            return
        try:
            base_name = os.path.splitext(os.path.basename(path))[0]
            target_dir = os.path.join(get_profiles_dir(), base_name)
            os.makedirs(target_dir, exist_ok=True)

            graph = FlowImporter.import_from_file(path, target_dir)
            self.controller.clear_matcher_cache()
            self.model.load_graph(graph, base_name)
            self._append_log(t("chain.msg.imported", name=base_name))
        except (OSError, ValueError, RuntimeError) as e:
            messagebox.showerror(t("chain.msg.import_failed"), str(e))

    # ── 区域选择 ──

    def _on_pick_region(self):
        def callback(left, top, width, height):
            self.controller.set_region(left, top, width, height)

        self._pick_region(callback)

    # ── 执行控制 ──

    def _sync_loop_config(self):
        self.model.graph.loop = self.loop_controls.loop
        self.model.graph.loop_count = self.loop_controls.loop_count

    def _on_start(self):
        try:
            self._sync_loop_config()
            self.controller.start_chain()
        except ValueError as e:
            # 用户可纠正的输入问题(如未添加步骤)→ 提示框
            messagebox.showwarning(t("common.hint"), str(e))
        except Exception as e:  # noqa: BLE001 — 启动路径任何异常都必须可见
            # 关键: 绝不再静默吞掉。executor 缺失/服务未就绪/其它异常一律弹错误框 + 写日志,
            # 否则在打包 exe(无控制台)中表现为「点启动完全无反应」无从排查。
            logger.exception("启动动作链失败")
            messagebox.showerror(t("workflow.msg.start_failed"), str(e))

    def _on_pause(self):
        self.controller.pause_chain()

    def _on_resume(self):
        self.controller.resume_chain()

    def _on_stop(self):
        self.controller.stop_chain()

    # ── 事件回调 ──

    def _on_steps_changed(self, **_kw):
        # 动作链是线性 ACTION 序列：只同步 ACTION 步骤，使 tree 行索引与
        # model 的 ACTION 索引一致（reorder/duplicate/move_to_index 都基于 ACTION 索引）。
        # 避免旧实现 sync_nodes(ordered_nodes) 把 CONDITION/MERGE/LOOP 也显示，
        # 导致 tree 行索引 ≠ ACTION 索引而重排错位。
        if self.step_ring and self.step_ring.is_alive():
            self.step_ring.sync_steps(self.model.get_steps())

    def _on_chain_loaded(self, **_kw):
        self._on_steps_changed()
        self.loop_controls.set_from_model(self.model.graph.loop, self.model.graph.loop_count)
        self._refresh_profile_list()
        self._refresh_monitor_list()

    def _on_monitors_changed(self, **_kw):
        self._refresh_monitor_list()

    def _on_executor_state(self, state=None, **_kw):
        self.run_controls.set_state(state or ExecutorState.IDLE)

        labels = {
            ExecutorState.RUNNING: t("chain.status.running"),
            ExecutorState.PAUSED: t("chain.status.paused"),
            ExecutorState.IDLE: t("chain.status.stopped"),
        }
        self.var_status.set(labels.get(state, t("chain.status.ready")))
        status_state = state or ExecutorState.IDLE
        self.status_bar.set_status_dot(status_state)
        self.status_bar.set_right(labels.get(state, ""))
        if state == ExecutorState.IDLE and self.step_ring and self.step_ring.is_alive():
            self.step_ring.reset_execution()

        # 执行进度段: 启停 tick + 刷新
        if status_state == ExecutorState.RUNNING:
            self._refresh_execution_status()
            self._exec_ticker.start()
        else:
            self._exec_ticker.stop()
            self._refresh_execution_status()

    # ── 执行进度段(循环次数 / 当前步骤 / 执行时间)──────────────

    def _refresh_execution_status(self) -> None:
        """从执行器读值并刷新状态栏 3 个执行段。"""
        executor = self.app.executor
        if not executor or not getattr(self, "status_bar", None):
            return
        from src.panel.execution_status import compose_execution_status

        segs = compose_execution_status(executor, self.model.graph)
        self.status_bar.set_segment("exec_loop", segs.loop_text)
        self.status_bar.set_segment("exec_step", segs.step_text)
        self.status_bar.set_segment("exec_time", segs.time_text)

    def _on_step_highlight(self, step_index=None, iteration=None, **_kw):
        if self.model.executor_state == ExecutorState.IDLE:
            return
        if self.step_ring:
            self.step_ring.highlight(step_index if step_index is not None else -1)
        self._refresh_execution_status()

    def _on_round_started(self, _iteration=None, **_kw):
        if self.step_ring and self.step_ring.is_alive():
            self.step_ring.reset_execution()
        self._refresh_execution_status()

    def _on_region_changed(self, mode=None, rect=None, **_kw):
        self.region_bar.set_mode(mode or "fullscreen")
        if rect:
            left, top, w, h = rect
            self.var_status.set(t("chain.status.region_set", left=left, top=top, w=w, h=h))
        else:
            self.var_status.set(t("chain.status.region_fullscreen"))

    # ── 执行器状态同步 ──

    def _sync_executor_state(self) -> None:
        result = super()._restore_executor_state()
        state = result.state
        if result.graph_copied:
            self._on_steps_changed()
            self.loop_controls.set_from_model(self.model.graph.loop, self.model.graph.loop_count)

        self._on_executor_state(state=state)

        if state in (ExecutorState.RUNNING, ExecutorState.PAUSED) and self.step_ring:
            executor = self.app.executor
            if executor:
                step_idx = executor.current_step_index
                if step_idx >= 0:
                    self.step_ring.highlight(step_idx)
        self._refresh_execution_status()
        if state == ExecutorState.RUNNING:
            self._exec_ticker.start()

    # ── 监控器操作 ──

    def _on_add_monitor(self):
        from src.panel.dialogs.monitor_dialog import open_monitor_dialog
        mon = MonitorConfig()

        def on_done(result):
            self.controller.add_monitor(result)
            self._append_log(t("chain.msg.monitor_added", name=result.name))

        open_monitor_dialog(self.app.root, mon, t("chain.mon.add"), on_done)

    def _get_selected_monitor(self) -> tuple[int, list] | None:
        sel = self.mon_tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        monitors = self.controller.get_monitors()
        if idx < 0 or idx >= len(monitors):
            return None
        return idx, monitors

    def _on_edit_monitor(self):
        result = self._get_selected_monitor()
        if result is None:
            messagebox.showinfo(t("common.hint"), t("chain.msg.no_monitors"))
            return
        idx, monitors = result
        from src.panel.dialogs.monitor_dialog import open_monitor_dialog
        mon = copy.copy(monitors[idx])

        def on_done(updated):
            self.controller.update_monitor(idx, updated)
            self._append_log(t("chain.msg.monitor_updated", name=updated.name))

        open_monitor_dialog(self.app.root, mon, t("common.edit"), on_done)

    def _on_delete_monitor(self):
        result = self._get_selected_monitor()
        if result is None:
            return
        idx, monitors = result
        if messagebox.askyesno(
            t("common.confirm"), t("chain.msg.confirm_delete_monitor", name=monitors[idx].name)
        ):
            self.controller.remove_monitor(idx)

    def _on_toggle_monitor(self):
        result = self._get_selected_monitor()
        if result is None:
            return
        idx, monitors = result
        mon = copy.copy(monitors[idx])
        mon.enabled = not mon.enabled
        self.controller.update_monitor(idx, mon)

    def _on_monitor_select(self):
        has_sel = bool(self.mon_tree.selection())
        self._btn_mon_edit.config(state=tk.NORMAL if has_sel else tk.DISABLED)
        self._btn_mon_toggle.config(state=tk.NORMAL if has_sel else tk.DISABLED)
        self._btn_mon_delete.config(state=tk.NORMAL if has_sel else tk.DISABLED)

    def _refresh_monitor_list(self):
        monitors = self.controller.get_monitors()
        count = len(monitors)
        enabled = sum(1 for m in monitors if m.enabled)

        sel_iid = None
        if self.mon_tree:
            cur = self.mon_tree.selection()
            sel_iid = cur[0] if cur else None
            self.mon_tree.delete(*self.mon_tree.get_children())

            for i, m in enumerate(monitors):
                action_text = m.handler_action.value if hasattr(m.handler_action, "value") else str(m.handler_action)
                self.mon_tree.insert("", tk.END, iid=str(i), values=(
                    "✓" if m.enabled else "--",
                    m.name,
                    m.image_path or "",
                    action_text,
                    f"{m.check_interval}s",
                    str(m.priority),
                ))

            if sel_iid and self.mon_tree.exists(sel_iid):
                self.mon_tree.selection_set(sel_iid)

        self._mon_count_var.set(t("chain.mon.count_format", enabled=enabled, total=count))
