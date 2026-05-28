"""QtWorkflowPage — PySide6 workflow editor page.

替代 tkinter WorkflowPage，整合 QtGraphCanvas、面板、调试器。
MVC: WorkflowController/ChainModel 不变。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QSizePolicy, QSplitter, QTabWidget,
    QVBoxLayout, QWidget,
)

from src.core.debug.debugger import Debugger
from src.core.debug.ring_buffer_log import LogEventType, RingBufferLog
from src.core.events.event_names import EventName
from src.panel.models.enums import EdgeStyle
from src.core.flow import FlowNode, ensure_loop_edge, find_loop_edge, remove_loop_edge
from src.panel.canvas.theme import current_theme
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.qt_backend.canvas.graph_canvas import QtGraphCanvas

from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.pages.base_page import QtBasePage
from src.panel.qt_backend.pages.workflow_undo_debug_mixin import QtWorkflowUndoDebugMixin
from src.panel.pages.page_i18n import WORKFLOW_EDITOR_DESC, WORKFLOW_EDITOR_TITLE
from src.panel.qt_backend.pages.page_registry import STATE_I18N, register_page
from src.panel.qt_backend.pages.workflow_palette_mixin import QtWorkflowPaletteMixin
from src.panel.qt_backend.pages.workflow_properties_mixin import QtWorkflowPropertiesMixin
from src.panel.pages.profile_ops_mixin import ProfileOpsMixin
from src.panel.qt_backend.pages.workflow_actions_mixin import QtWorkflowActionsMixin
from src.panel.profile_manager import ProfileManager
from src.panel.controllers.workflow_controller import WorkflowController
from src.panel.models.chain_model import ChainModel, ExecutorState
from src.utils.i18n import t


@register_page("workflow_editor", label_i18n=WORKFLOW_EDITOR_TITLE, desc_i18n=WORKFLOW_EDITOR_DESC, icon="🔧", category="main")
class QtWorkflowPage(
    ProfileOpsMixin,
    QtWorkflowUndoDebugMixin,
    QtWorkflowPaletteMixin, QtWorkflowPropertiesMixin, QtWorkflowActionsMixin, QtBasePage,
):
    """可视化工作流编辑页面 — MVC View"""

    def title(self) -> str:
        return t("workflow.title")

    def build(self):
        self._init_services()
        self._build_toolbar()
        self._build_status_bar()
        self._build_main_area()
        self._build_log()
        self._subscribe_events()
        self._canvas.render_graph(self._model.graph)
        self._update_status_bar()
        self._restore_executor_state()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, '_canvas') and self._canvas:
            self._canvas.init_overlays()

    # ── 服务初始化 ──────────────────────────────────────────

    def _init_services(self):
        self._model = ChainModel(self.app.event_bus)
        self._profile_mgr = ProfileManager()
        self._controller = WorkflowController(
            model=self._model,
            executor=self.app.executor,
            capture=self.app.capture,
            matcher=self.app.matcher,
            profile_mgr=self._profile_mgr,
            event_bus=self.app.event_bus,
            main_thread_schedule=self.schedule,
        )
        self._selected_node_id: str | None = None
        self._current_zoom: float = 1.0
        self._ring_log = RingBufferLog(capacity=1000)
        self._debugger = Debugger()
        self._debugger.on_state_change(self._on_debugger_state_changed)
        self._debugger.on_breakpoint_hit(self._on_debugger_breakpoint_hit)

        self._clipboard: list[FlowNode] = []
        self._paste_offset: int = 0

        self._palette_mode: str = "full"  # Literal["full", "hidden"]
        self._props_visible: bool = False
        self._log_visible: bool = True

    # ── 工具栏 ──────────────────────────────────────────────

    def _build_toolbar(self):
        th = current_theme()
        sm = qt_scale_manager()

        btn_style = (
            f"QPushButton {{ background: transparent; border: none; "
            f"padding: 4px 8px; color: {th.text_primary}; }}"
            f"QPushButton:hover {{ background: {th.bg_surface_hover}; border-radius: 3px; }}"
            f"QPushButton:checked {{ background: {th.bg_surface_hover}; border-radius: 3px; }}"
            f"QPushButton:disabled {{ color: {th.text_muted}; }}"
        )

        def _tb(text: str, handler, checkable: bool = False, checked: bool = False) -> QPushButton:
            b = QPushButton(text)
            b.setCheckable(checkable)
            b.setChecked(checked)
            b.setStyleSheet(btn_style)
            b.clicked.connect(handler)
            return b

        def _sep() -> QFrame:
            f = QFrame()
            f.setFrameShape(QFrame.Shape.VLine)
            f.setStyleSheet(f"color: {th.border_default};")
            return f

        # 第一行：导航 + 配置 + 循环 + 区域 + 运行控制
        toolbar1 = QWidget()
        toolbar1.setObjectName("workflowToolbar1")
        toolbar1.setStyleSheet(f"QWidget#workflowToolbar1 {{ background-color: {th.panel_bg}; border: none; }}")
        lay1 = QHBoxLayout(toolbar1)
        lay1.setContentsMargins(4, 2, 4, 2)
        lay1.setSpacing(2)

        lay1.addWidget(_tb(t("common.back"), self._go_home))
        lay1.addWidget(QLabel(t("workflow.title")))
        lay1.addWidget(_sep())

        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(sm.s(120))
        self._profile_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        lay1.addWidget(self._profile_combo)

        for label, handler in [
            (t("common.load"), self._on_load_profile),
            (t("common.save"), self._on_save_profile),
            (t("common.save_as"), self._on_save_as_profile),
            (t("common.delete"), self._on_delete_profile),
            (t("chain.export"), self._on_export_script),
        ]:
            lay1.addWidget(_tb(label, handler))

        lay1.addWidget(_sep())

        self._loop_cb = QCheckBox(t("common.infinite_loop"))
        self._loop_cb.setChecked(True)
        self._loop_cb.stateChanged.connect(self._on_loop_toggled)
        lay1.addWidget(self._loop_cb)

        lay1.addWidget(_sep())

        lay1.addWidget(_tb(t("chain.region.fullscreen"), self._on_fullscreen))
        lay1.addWidget(_tb(t("chain.region.pick"), self._on_pick_region))

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        lay1.addWidget(spacer)

        self._run_actions: list[QPushButton] = []
        for label, handler in [
            (t("common.start"), self._on_start),
            (t("common.pause"), self._on_pause),
            (t("common.resume"), self._on_resume),
            (t("common.stop"), self._on_stop),
        ]:
            btn = _tb(label, handler)
            lay1.addWidget(btn)
            self._run_actions.append(btn)

        # 第二行：编辑 + 边样式 + 视图切换 + 调试
        toolbar2 = QWidget()
        toolbar2.setObjectName("workflowToolbar2")
        toolbar2.setStyleSheet(f"QWidget#workflowToolbar2 {{ background-color: {th.panel_bg}; border: none; }}")
        lay2 = QHBoxLayout(toolbar2)
        lay2.setContentsMargins(4, 2, 4, 2)
        lay2.setSpacing(2)

        self._undo_action = _tb(t("workflow.undo"), self._on_undo)
        self._undo_action.setEnabled(False)
        lay2.addWidget(self._undo_action)

        self._redo_action = _tb(t("workflow.redo"), self._on_redo)
        self._redo_action.setEnabled(False)
        lay2.addWidget(self._redo_action)

        lay2.addWidget(_sep())

        self._edge_style_combo = QComboBox()
        self._edge_style_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToContents,
        )
        for style in EdgeStyle:
            self._edge_style_combo.addItem(t(f"workflow.edge_style.{style.value}"), style)
        self._edge_style_combo.currentIndexChanged.connect(self._on_edge_style_changed)
        lay2.addWidget(self._edge_style_combo)

        lay2.addWidget(_sep())

        self._palette_action = _tb(t("workflow.toolbar.palette"), self._toggle_palette, checkable=True, checked=True)
        lay2.addWidget(self._palette_action)

        self._props_action = _tb(t("workflow.toolbar.properties"), self._toggle_props, checkable=True, checked=False)
        lay2.addWidget(self._props_action)

        self._log_action = _tb(t("common.log"), self._toggle_log, checkable=True, checked=True)
        lay2.addWidget(self._log_action)

        lay2.addWidget(_sep())

        self._debug_toggle_action = _tb(t("workflow.debug.toggle"), self._on_debug_toggle)
        lay2.addWidget(self._debug_toggle_action)

        self._breakpoint_action = _tb(t("workflow.debug.breakpoint"), self._on_toggle_breakpoint)
        lay2.addWidget(self._breakpoint_action)

        self._step_action = _tb(t("workflow.debug.step_over"), self._on_debug_step)
        self._step_action.setEnabled(False)
        lay2.addWidget(self._step_action)

        self._debug_resume_action = _tb(t("workflow.debug.resume"), self._on_debug_resume)
        self._debug_resume_action.setEnabled(False)
        lay2.addWidget(self._debug_resume_action)

        self._debug_stop_action = _tb(t("workflow.debug.stop"), self._on_debug_stop)
        self._debug_stop_action.setEnabled(False)
        lay2.addWidget(self._debug_stop_action)

        self._controller.undo_manager.on_change(self._on_undo_state_changed)
        self._on_undo_state_changed()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(toolbar1)
        layout.addWidget(toolbar2)

        self._toolbar1 = toolbar1
        self._toolbar2 = toolbar2

    # ── 状态栏 ──────────────────────────────────────────────

    def _build_status_bar(self):
        self._build_qt_status_bar(center_label=True)
        self.layout().addWidget(self._status_bar)

    def _update_status_bar(self):
        if not hasattr(self, "_status_left"):
            return
        graph = self._model.graph
        nodes = len(graph.nodes) if graph else 0
        edges = len(graph.edges) if graph else 0
        self._status_left.setText(t("workflow.status.nodes_edges", nodes=nodes, edges=edges))
        self._status_right.setText(f"{self._current_zoom:.0%}")

    # ── 面板切换 ──────────────────────────────────────────────

    def _toggle_palette(self) -> None:
        new_mode = "hidden" if self._palette_mode == "full" else "full"
        self._palette_mode = new_mode
        if self._palette_widget is not None:
            self._palette_widget.setVisible(new_mode != "hidden")
        self._palette_action.setChecked(new_mode != "hidden")
        self._redistribute_hsplitter()

    def _toggle_props(self) -> None:
        self._props_visible = not self._props_visible
        if self._props_scroll is not None:
            self._props_scroll.setVisible(self._props_visible)
        self._props_action.setChecked(self._props_visible)
        self._redistribute_hsplitter()

    def _toggle_log(self) -> None:
        self._log_visible = not self._log_visible
        if self._log_container is not None:
            self._log_container.setVisible(self._log_visible)
        self._log_action.setChecked(self._log_visible)
        self._redistribute_vsplitter()

    def _redistribute_hsplitter(self) -> None:
        """重新分配水平分割器空间：隐藏的面板设为 0，画布占据剩余空间。"""
        if not hasattr(self, "_hsplitter"):
            return
        sizes = []
        palette_w = 0 if self._palette_mode == "hidden" else self._palette_widget.sizeHint().width()
        props_w = 0 if not self._props_visible else self._props_scroll.sizeHint().width()
        canvas_w = max(200, self._hsplitter.width() - palette_w - props_w)
        sizes = [palette_w, canvas_w, props_w]
        self._hsplitter.setSizes(sizes)

    def _redistribute_vsplitter(self) -> None:
        """重新分配垂直分割器空间：隐藏的日志区设为 0。"""
        if not hasattr(self, "_vsplitter"):
            return
        main_h = max(200, self._vsplitter.height())
        log_h = 0 if not self._log_visible else min(200, self._vsplitter.height() // 4)
        if not self._log_visible:
            self._vsplitter.setSizes([main_h, 0])
        else:
            self._vsplitter.setSizes([main_h - log_h, log_h])

    # ── 主区域 ──────────────────────────────────────────────

    def _build_main_area(self):
        th = current_theme()
        sm = qt_scale_manager()

        self._vsplitter = QSplitter(Qt.Orientation.Vertical)
        self._hsplitter = QSplitter(Qt.Orientation.Horizontal)

        from PySide6.QtWidgets import QScrollArea

        self._build_node_palette()
        self._canvas = QtGraphCanvas(self._on_canvas_event, self._hsplitter)
        self._props_scroll = QScrollArea()
        self._props_scroll.setFixedWidth(sm.s(th.panel_width_right))
        self._props_scroll.setWidgetResizable(True)
        self._props_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._props_scroll.setStyleSheet(f"background-color: {th.page_bg};")
        self._props_scroll.setVisible(self._props_visible)
        self._props_inner = QWidget()
        self._props_scroll.setWidget(self._props_inner)
        self._props_inner_layout = QVBoxLayout(self._props_inner)
        self._props_inner_layout.setContentsMargins(4, 4, 4, 4)
        self._props_inner_layout.addStretch()

        self._hsplitter.addWidget(self._palette_widget)
        self._hsplitter.addWidget(self._canvas)
        self._hsplitter.addWidget(self._props_scroll)
        self._hsplitter.setStretchFactor(0, 0)
        self._hsplitter.setStretchFactor(1, 1)
        self._hsplitter.setStretchFactor(2, 0)

        self._log_container = QWidget()
        self._log_container.setVisible(self._log_visible)
        log_layout = QVBoxLayout(self._log_container)
        log_layout.setContentsMargins(0, 0, 0, 0)
        self._log_notebook = QTabWidget()
        self._log_notebook.tabBar().hide()
        log_layout.addWidget(self._log_notebook)

        self._vsplitter.addWidget(self._hsplitter)
        self._vsplitter.addWidget(self._log_container)
        self._vsplitter.setStretchFactor(0, 1)
        self._vsplitter.setStretchFactor(1, 0)

        self.layout().addWidget(self._vsplitter)

    # ── 日志区 ──────────────────────────────────────────────

    def _build_log(self):
        console_tab = QWidget()
        self._log_notebook.addTab(console_tab, t("workflow.tab.console"))
        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumBlockCount(200)
        from PySide6.QtGui import QTextOption
        opt = QTextOption()
        opt.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self._log_text.document().setDefaultTextOption(opt)
        tab_layout = QVBoxLayout(console_tab)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.addWidget(self._log_text)

    # ── 事件订阅 ──────────────────────────────────────────

    def _subscribe_events(self):
        self.subscribe(EventName.CHAIN_LOADED, self._on_graph_loaded)
        self.subscribe(EventName.CHAIN_STEPS_CHANGED, self._on_graph_changed)
        self.subscribe(EventName.EXECUTOR_STATE_CHANGED, self._on_executor_state)
        self.subscribe(EventName.UI_NODE_HIGHLIGHT, self._on_node_highlight)
        self.subscribe(EventName.CHAIN_MONITORS_CHANGED, self._on_monitors_changed)

    # ── 边样式 ──────────────────────────────────────────────

    def _on_edge_style_changed(self):
        style = self._edge_style_combo.currentData()
        if style is not None:
            self._canvas.set_edge_style(style)

    # ── 配置文件操作 ──────────────────────────────────────

    profile_i18n_prefix = "workflow"

    def _refresh_profiles(self):
        self._profile_combo.clear()
        profiles = self._controller.list_profiles()
        for name in profiles:
            self._profile_combo.addItem(name)
        current = self._model.current_profile_name
        if current:
            idx = self._profile_combo.findText(current)
            if idx >= 0:
                self._profile_combo.setCurrentIndex(idx)

    def _get_selected_profile_name(self) -> str | None:
        return self._profile_combo.currentText() or None

    # ── 区域选择 ──────────────────────────────────────────

    def _on_pick_region(self):
        from src.panel.qt_backend.region_picker import show_region_picker

        def on_region(left, top, width, height):
            self._controller.set_region(left, top, width, height)
            self._append_log(t("workflow.msg.region_set", w=width, h=height, x=left, y=top))

        show_region_picker(self.window(), self.app.capture, on_region)

    def _on_fullscreen(self):
        self._controller.set_fullscreen()
        self._append_log(t("workflow.msg.fullscreen"))

    def _on_export_script(self):
        from pathlib import Path
        from PySide6.QtWidgets import QFileDialog
        from src.core.io.script_exporter import ScriptExporter

        graph = self._model.graph
        if not graph or not graph.nodes:
            self._show_warning(t("chain.export"), t("workflow.msg.start_failed"))
            return

        name = self._model.current_profile_name or "untitled"
        path, _ = QFileDialog.getSaveFileName(
            self,
            t("chain.msg.export_title"),
            f"{name}.py",
            "Python (*.py);;All (*)",
        )
        if not path:
            return

        try:
            exporter = ScriptExporter()
            result = exporter.export(graph, Path(path), profile_name=name)
            self._append_log(t("chain.msg.exported").format(path=str(result.output_path)))
        except Exception as e:
            logger.exception("Script export failed")
            self._show_error(t("chain.export"), t("chain.msg.export_failed"))

    # ── 缩放 ──────────────────────────────────────────────

    def _zoom_in(self):
        self._canvas.zoom_by(1.25)

    def _zoom_out(self):
        self._canvas.zoom_by(0.8)

    def _zoom_reset(self):
        self._canvas.zoom_reset()

    # ── 循环边管理 ──────────────────────────────────────────

    def _on_loop_toggled(self, state):
        checked = state == Qt.CheckState.Checked.value
        if not checked:
            remove_loop_edge(self._model.graph)
        else:
            ensure_loop_edge(self._model.graph)
        self._canvas.render_graph(self._model.graph)

    # ── 执行控制 ──────────────────────────────────────────

    def _on_start(self):
        try:
            self._model.graph.loop = self._loop_cb.isChecked()
            self._model.graph.loop_count = 0 if self._loop_cb.isChecked() else 1
            self._controller.start_chain()
        except Exception as e:
            self._show_error(t("workflow.msg.start_failed"), str(e))

    def _on_pause(self):
        self._controller.pause_chain()

    def _on_resume(self):
        self._controller.resume_chain()

    def _on_stop(self):
        self._controller.stop_chain()

    # ── 事件处理 ──────────────────────────────────────────

    def _on_graph_loaded(self, **_kwargs):
        has_loop = find_loop_edge(self._model.graph) is not None
        self._loop_cb.setChecked(has_loop)
        self._canvas.render_graph(self._model.graph)
        self._refresh_monitor_list()
        self._append_log(f"{t('workflow.msg.graph_loaded')}: {self._model.graph.describe()}")
        self._update_status_bar()

    def _on_graph_changed(self, **_kwargs):
        if self._selected_node_id:
            node = self._model.graph.get_node(self._selected_node_id)
            if node:
                self._show_node_properties(self._selected_node_id)
                self._canvas.update_node_visual(self._selected_node_id)
            else:
                self._selected_node_id = None
                self._clear_props()
        self._update_status_bar()

    def _on_executor_state(self, state=None, **_kwargs):
        running = state == ExecutorState.RUNNING
        paused = state == ExecutorState.PAUSED
        active = running or paused

        if not running:
            self._canvas.highlight_node(None)

        self._canvas.set_execution_state(state)

        if hasattr(self, "_status_center"):
            self._status_center.setText(t(STATE_I18N.get(state, "")))

        if hasattr(self, "_palette_btn_widgets"):
            enabled = not active
            for btn in self._palette_btn_widgets:
                btn.setEnabled(enabled)

        if hasattr(self, "_run_actions") and len(self._run_actions) == 4:
            start, pause, resume, stop = self._run_actions
            start.setEnabled(not active)
            pause.setEnabled(running)
            resume.setEnabled(paused)
            stop.setEnabled(active)

    def _on_node_highlight(self, node_id=None, **_kwargs):
        if self._model.executor_state != ExecutorState.RUNNING:
            return
        self._canvas.highlight_node(node_id)

    def _on_monitors_changed(self, **_kwargs):
        self._refresh_monitor_list()

    # ── 主题 ──────────────────────────────────────────────

    def apply_theme(self) -> None:
        super().apply_theme()
        th = current_theme()

        btn_style = (
            f"QPushButton {{ background: transparent; border: none; "
            f"padding: 4px 8px; color: {th.text_primary}; }}"
            f"QPushButton:hover {{ background: {th.bg_surface_hover}; border-radius: 3px; }}"
            f"QPushButton:checked {{ background: {th.bg_surface_hover}; border-radius: 3px; }}"
            f"QPushButton:disabled {{ color: {th.text_muted}; }}"
        )

        if hasattr(self, "_toolbar1"):
            self._toolbar1.setStyleSheet(f"QWidget#workflowToolbar1 {{ background-color: {th.panel_bg}; border: none; }}")
            for btn in self._toolbar1.findChildren(QPushButton):
                btn.setStyleSheet(btn_style)
        if hasattr(self, "_toolbar2"):
            self._toolbar2.setStyleSheet(f"QWidget#workflowToolbar2 {{ background-color: {th.panel_bg}; border: none; }}")
            for btn in self._toolbar2.findChildren(QPushButton):
                btn.setStyleSheet(btn_style)
        if hasattr(self, "_status_bar"):
            self._status_bar.setStyleSheet(
                f"background-color: {th.panel_bg}; border-top: 1px solid {th.border_default};"
            )

        if hasattr(self, "_canvas") and self._model.graph:
            self._canvas.viewport().update()

        if hasattr(self, "_selected_node_id") and self._selected_node_id:
            self._show_node_properties(self._selected_node_id)
        else:
            self._clear_props()

    # ── Toast ──────────────────────────────────────────────

    def _show_toast(self, message: str) -> None:
        if hasattr(self, "_status_center"):
            self._status_center.setText(message)
            self.schedule(2000, lambda: self._status_center.setText(""))

    # ── 导航 ──────────────────────────────────────────────

    # ── 生命周期 ──────────────────────────────────────────

    def on_enter(self, **kwargs) -> None:
        if not hasattr(self, "_canvas"):
            return

        import_steps = kwargs.get("import_steps")
        if import_steps:
            if not self._resolve_import_conflict(
                has_content=bool(self._model.get_steps()),
                is_dirty=self._model.is_dirty,
                save_callback=self._on_save_profile,
            ):
                return

            self._model.clear_steps()
            self._canvas.render_graph(self._model.graph)
            self._import_steps(import_steps)

        self._restore_executor_state()
        if not import_steps and hasattr(self, "_model") and self._model.graph:
            self._canvas.render_graph(self._model.graph)
        if hasattr(self, "_saved_viewport"):
            self._canvas.set_viewport(*self._saved_viewport)
        self._update_status_bar()

    def on_leave(self) -> None:
        if hasattr(self, "_canvas") and self._canvas:
            self._saved_viewport = self._canvas.get_viewport()

    def keyPressEvent(self, event) -> None:
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit
        focus = self.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit)):
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_B and not mods:
            self._toggle_palette()
        elif key == Qt.Key.Key_N and not mods:
            self._toggle_props()
        elif key == Qt.Key.Key_L and (mods & Qt.KeyboardModifier.ControlModifier):
            self._toggle_log()
        else:
            super().keyPressEvent(event)

    def _restore_executor_state(self) -> None:
        result = super()._restore_executor_state()
        if result.graph_copied:
            self._canvas.render_graph(self._model.graph)
            has_loop = find_loop_edge(self._model.graph) is not None
            self._loop_cb.setChecked(has_loop)
        if result.state != ExecutorState.IDLE:
            self._on_executor_state(state=result.state)
            self._refresh_monitor_list()
            self._update_status_bar()

    def destroy_page(self) -> None:
        if hasattr(self, "_canvas"):
            self._canvas.destroy_canvas()
        if hasattr(self, "_controller"):
            self._controller.destroy()
        self._clipboard.clear()
        super().destroy_page()
