"""Qt 动作链页面的配置文件 CRUD + 区域选择 + 执行控制 + 事件处理。"""

from __future__ import annotations

import logging
import os

from PySide6.QtWidgets import QFileDialog

from src.panel.models.chain_model import ExecutorState
from src.panel.pages.profile_ops_mixin import ProfileOpsMixin
from src.utils.i18n import t

logger = logging.getLogger(__name__)


class QtActionChainProfileMixin(ProfileOpsMixin):
    """配置文件操作 + 区域选择 + 执行控制 Mixin。

    要求宿主类提供:
      - self._controller: ActionChainController
      - self._model: ChainModel
      - self._loop_combo: QComboBox (三模式: single/infinite/finite)
      - self._loop_count_spin: QSpinBox
      - self._loop_container: QFrame
      - self._profile_combo: QComboBox
      - self._step_tree: QTreeWidget
      - self._append_log(msg)
      - self._refresh_profile_list()
      - self._refresh_step_list()
      - self._refresh_monitor_list()
      - self._show_empty_props()
      - self._sync_executor_state()
      - self._on_executor_state(state)
      - self._on_step_selected()
      - self._selected_step_idx: int | None
      - self.app: QtPanelApp
      - self.schedule(ms, cb)
      - self._loop_mode() -> str
      - self._set_loop_mode(mode, count)
    """

    profile_i18n_prefix = "chain"

    def _refresh_profiles(self):
        self._refresh_profile_list()

    def _get_selected_profile_name(self):
        return self._profile_combo.currentText() or None

    def _pre_save_hook(self):
        self._sync_loop_config()

    # ── 配置文件操作 ──────────────────────────────────────────

    def _on_export_profile(self):
        from src.core.exporter import FlowExporter

        path, _ = QFileDialog.getSaveFileName(
            self, t("chain.msg.export_title"),
            f"{self._model.graph.name or 'flow'}.json",
            "JSON (*.json);;All (*)",
        )
        if not path:
            return
        temp_name = f"__export_{id(self)}"
        try:
            self._sync_loop_config()
            profile_dir = self._controller.save_profile_to_dir(temp_name, self._model.graph)
            data = FlowExporter.export(self._model.graph, profile_dir)
            FlowExporter.save_file(data, path)
            self._append_log(t("chain.msg.exported", path=path))
        except Exception as e:
            self._show_error(t("chain.msg.export_failed"), str(e))
        finally:
            try:
                self._controller.delete_profile(temp_name)
            except (OSError, RuntimeError):
                pass

    def _on_import_profile(self):
        from src.core.importer import FlowImporter
        from src.utils.paths import get_profiles_dir

        path, _ = QFileDialog.getOpenFileName(
            self, t("chain.msg.import_title"), "", "JSON (*.json);;All (*)",
        )
        if not path:
            return
        try:
            base_name = os.path.splitext(os.path.basename(path))[0]
            target_dir = os.path.join(get_profiles_dir(), base_name)
            os.makedirs(target_dir, exist_ok=True)

            graph = FlowImporter.import_from_file(path, target_dir)
            self._controller.clear_matcher_cache()
            self._model.load_graph(graph, base_name)
            self._append_log(t("chain.msg.imported", name=base_name))
        except Exception as e:
            self._show_error(t("chain.msg.import_failed"), str(e))

    # ── 区域选择 ──────────────────────────────────────────

    def _on_pick_region(self):
        from src.panel.qt_backend.region_picker import show_region_picker

        def on_region(left, top, width, height):
            self._controller.set_region(left, top, width, height)
            self._append_log(t("chain.status.region_set", left=left, top=top, w=width, h=height))

        show_region_picker(self.window(), self.app.capture, on_region)

    def _on_fullscreen(self):
        self._controller.set_fullscreen()
        self._append_log(t("chain.status.region_fullscreen"))

    # ── 执行控制 ──────────────────────────────────────────

    def _sync_loop_config(self):
        mode = self._loop_mode()
        if mode == "single":
            self._model.graph.loop = False
            self._model.graph.loop_count = 1
        elif mode == "infinite":
            self._model.graph.loop = True
            self._model.graph.loop_count = 0
        else:  # finite
            self._model.graph.loop = True
            self._model.graph.loop_count = max(1, self._loop_count_spin.value())

    def _on_start(self):
        try:
            self._sync_loop_config()
            self._controller.start_chain()
        except ValueError as e:
            # 用户可纠正的输入问题(如未添加步骤)→ 提示框
            self._show_warning(t("common.hint"), str(e))
        except Exception as e:  # noqa: BLE001 — 启动路径任何异常都必须可见
            # 关键: 绝不再静默吞掉。executor 缺失/服务未就绪/其它异常一律弹错误框 + 写日志,
            # 否则在打包 exe(无控制台)中表现为「点启动完全无反应」无从排查。
            logger.exception("启动动作链失败")
            self._show_error(t("workflow.msg.start_failed"), str(e))

    def _on_pause(self):
        self._controller.pause_chain()

    def _on_resume(self):
        self._controller.resume_chain()

    def _on_stop(self):
        self._controller.stop_chain()

    # ── 事件回调 ──────────────────────────────────────────

    def _on_steps_changed(self, **_kw):
        self._refresh_step_list()

    def _on_chain_loaded(self, **_kw):
        self._refresh_step_list()
        graph = self._model.graph
        if not graph.loop:
            self._set_loop_mode("single")
        elif graph.loop_count == 0:
            self._set_loop_mode("infinite")
        else:
            self._set_loop_mode("finite", graph.loop_count)
        self._refresh_profile_list()
        self._refresh_monitor_list()

    def _on_monitors_changed(self, **_kw):
        self._refresh_monitor_list()

    # ── 事件处理 ──────────────────────────────────────────

    def _on_executor_state(self, state=None, **_kw):
        labels = {
            ExecutorState.RUNNING: t("chain.status.running"),
            ExecutorState.PAUSED: t("chain.status.paused"),
            ExecutorState.IDLE: t("chain.status.stopped"),
        }
        text = labels.get(state, t("chain.status.ready"))
        if hasattr(self, "_status_label"):
            self._status_label.setText(text)
        if hasattr(self, "_status_left"):
            self._status_left.setText(text)

        status_state = state or ExecutorState.IDLE
        if status_state == ExecutorState.RUNNING:
            self._refresh_execution_status()
            self._start_exec_tick()
        else:
            self._stop_exec_tick()
            self._refresh_execution_status()

    # ── 执行进度段(循环次数 / 当前步骤 / 执行时间)──────────────

    def _refresh_execution_status(self) -> None:
        """从执行器读值并刷新 3 个执行 QLabel。"""
        executor = self.app.executor
        if not executor:
            return
        from src.panel.execution_status import compose_execution_status

        segs = compose_execution_status(executor, self._model.graph)
        if hasattr(self, "_exec_loop_lbl"):
            self._exec_loop_lbl.setText(segs.loop_text)
        if hasattr(self, "_exec_step_lbl"):
            self._exec_step_lbl.setText(segs.step_text)
        if hasattr(self, "_exec_time_lbl"):
            self._exec_time_lbl.setText(segs.time_text)

    def _start_exec_tick(self) -> None:
        """启动每秒轮询(仅 RUNNING 时持续)。"""
        self._stop_exec_tick()
        self._exec_tick_token = self.schedule(1000, self._exec_tick)

    def _exec_tick(self) -> None:
        self._exec_tick_token = None
        self._refresh_execution_status()
        if self._model.executor_state == ExecutorState.RUNNING:
            self._exec_tick_token = self.schedule(1000, self._exec_tick)

    def _stop_exec_tick(self) -> None:
        token = getattr(self, "_exec_tick_token", None)
        if token is not None:
            try:
                self._timer.cancel(token)
            except Exception:  # noqa: BLE001 — token 失效无害
                pass
            self._exec_tick_token = None

    def _on_step_highlight(self, step_index=None, iteration=None, **_kw):
        if self._model.executor_state == ExecutorState.IDLE:
            return
        if step_index is not None:
            item = self._step_tree.topLevelItem(step_index)
            if item:
                self._step_tree.setCurrentItem(item)
            self._selected_step_idx = step_index
        self._refresh_execution_status()

    def _on_round_started(self, **_kw):
        if hasattr(self, "_step_tree") and self._step_tree:
            self._step_tree.clearSelection()
        if hasattr(self, "_selected_step_idx"):
            self._selected_step_idx = None
        self._refresh_execution_status()

    def _on_region_changed(self, mode=None, rect=None, **_kw):
        if rect:
            left, top, w, h = rect
            self._append_log(t("chain.status.region_set", left=left, top=top, w=w, h=h))
        else:
            self._append_log(t("chain.status.region_fullscreen"))

    def _sync_executor_state(self) -> None:
        result = super()._restore_executor_state()
        state = result.state
        if result.graph_copied:
            self._refresh_step_list()
            graph = self._model.graph
            if not graph.loop:
                self._set_loop_mode("single")
            elif graph.loop_count == 0:
                self._set_loop_mode("infinite")
            else:
                self._set_loop_mode("finite", graph.loop_count)

        self._on_executor_state(state=state)

        if state in (ExecutorState.RUNNING, ExecutorState.PAUSED):
            executor = self.app.executor
            if executor:
                step_idx = executor.current_step_index
                if step_idx >= 0:
                    item = self._step_tree.topLevelItem(step_idx)
                    if item:
                        self._step_tree.setCurrentItem(item)
                    self._selected_step_idx = step_idx
