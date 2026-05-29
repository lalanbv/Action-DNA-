"""WorkflowPage — 可视化工作流编辑页面"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Literal

from src.core.debug.debugger import Debugger
from src.core.debug.ring_buffer_log import RingBufferLog
from src.core.events.event_names import EventName
from src.core.flow import FlowNode, find_loop_edge
from src.panel.canvas.floating_controls import FloatingZoomControls
from src.panel.canvas.graph_canvas import GraphCanvas
from src.panel.canvas.search_dialog import SearchBar
from src.panel.canvas.theme import current_theme
from src.panel.components.log_viewer import LogViewer
from src.panel.components.profile_bar import ProfileBar
from src.panel.components.property_panel import PropertyPanel
from src.panel.pages.profile_ops_mixin import ProfileOpsMixin
from src.panel.components.region_bar import RegionBar
from src.panel.components.status_bar import StatusBar
from src.panel.components.loop_controls import LoopControls
from src.panel.components.toolbar import RunControls, ToolbarFrame
from src.panel.components.editor_toolbar import add_editor_toolbar_sections
from src.panel.controllers.workflow_controller import WorkflowController
from src.panel.models.chain_model import ChainModel, ExecutorState
from src.panel.models.enums import EdgeStyle
from src.panel.canvas.scale import scale_manager, Breakpoint
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import WORKFLOW_EDITOR_DESC, WORKFLOW_EDITOR_TITLE
from src.panel.pages.page_registry import STATE_I18N, register_page
from src.panel.pages.workflow_palette_mixin import WorkflowPaletteMixin
from src.panel.pages.workflow_properties_mixin import WorkflowPropertiesMixin
from src.panel.pages.workflow_actions_mixin import WorkflowActionsMixin
from src.panel.pages.workflow_undo_debug_mixin import WorkflowUndoDebugMixin
from src.panel.profile_manager import ProfileManager
from src.panel.widgets import LabelButton, apply_theme_recursive, themed_dropdown, themed_label, themed_separator
from src.utils.i18n import t



@register_page("workflow_editor", label_i18n=WORKFLOW_EDITOR_TITLE, desc_i18n=WORKFLOW_EDITOR_DESC, icon="🔧", category="main")
class WorkflowPage(ProfileOpsMixin, WorkflowPaletteMixin, WorkflowPropertiesMixin, WorkflowActionsMixin, WorkflowUndoDebugMixin, BasePage):
    """可视化工作流编辑页面 — MVC View"""  # pylint: disable=attribute-defined-outside-init,protected-access

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

        # 从执行器恢复正在执行的图数据，避免页面重建后画布为空
        self._restore_executor_state()

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
            main_thread_schedule=self.app.root.after,
        )
        self._selected_node_id: str | None = None
        self._current_zoom: float = 1.0
        self._ring_log = RingBufferLog(capacity=1000)
        self._debugger = Debugger()
        self._debugger.on_state_change(self._on_debugger_state_changed)
        self._debugger.on_breakpoint_hit(self._on_debugger_breakpoint_hit)

        # P6 状态
        self._clipboard: list[FlowNode] = []
        self._paste_offset: int = 0
        self._search_bar: SearchBar | None = None

        # 面板切换状态
        self._palette_mode: Literal["hidden", "full"] = "full"
        self._props_visible: bool = False
        self._log_visible: bool = True

    # ── 工具栏 ──────────────────────────────────────────────

    def _build_toolbar(self):
        th = current_theme()

        # ── 第一行：通用编辑器工具栏 ──
        self._toolbar = ToolbarFrame(self.frame)
        self._toolbar.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

        self.profile_bar = ProfileBar(
            self._toolbar,
            on_load=self._on_load_profile,
            on_save=self._on_save_profile,
            on_save_as=self._on_save_as_profile,
            on_delete=self._on_delete_profile,
            on_export=self._on_export_script,
            compact=True,
        )

        self.loop_controls = LoopControls(
            self._toolbar, on_change=self._on_loop_changed,
        )

        self.region_bar = RegionBar(
            self._toolbar,
            on_fullscreen=self._on_fullscreen,
            on_pick_region=self._on_pick_region,
            compact=True,
        )

        self.run_controls = RunControls(
            self._toolbar,
            on_start=self._on_start,
            on_pause=self._on_pause,
            on_resume=self._on_resume,
            on_stop=self._on_stop,
        )

        add_editor_toolbar_sections(
            self._toolbar,
            title_text=t("workflow.title"),
            on_back=self._go_home,
            profile_bar=self.profile_bar,
            loop_controls=self.loop_controls,
            region_bar=self.region_bar,
            run_controls=self.run_controls,
        )

        self._refresh_profiles()

        # ── 分隔线 ──
        themed_separator(self.frame, orient=tk.HORIZONTAL).pack(fill=tk.X)

        # ── 第二行：编辑 + 边样式 + 视图切换 + 调试 ──
        self._toolbar2 = ToolbarFrame(self.frame)
        self._toolbar2.pack(fill=tk.X, padx=th.pad_xs, pady=(0, th.pad_xs))

        self._btn_undo = self._toolbar2.make_button(
            "edit", text=t("workflow.undo"), icon="undo",
            command=self._on_undo,
            tooltip=t("workflow.undo"), shortcut_hint="Ctrl+Z",
        )
        self._btn_undo.configure(state=tk.DISABLED)
        self._btn_redo = self._toolbar2.make_button(
            "edit", text=t("workflow.redo"), icon="redo",
            command=self._on_redo,
            tooltip=t("workflow.redo"), shortcut_hint="Ctrl+Y",
        )
        self._btn_redo.configure(state=tk.DISABLED)

        self._edge_style_options = [
            (EdgeStyle.BEZIER.name, "workflow.edge_style.bezier"),
            (EdgeStyle.ORTHOGONAL.name, "workflow.edge_style.orthogonal"),
            (EdgeStyle.STRAIGHT.name, "workflow.edge_style.straight"),
        ]
        self._edge_style_var = tk.StringVar(value=EdgeStyle.BEZIER.name)
        self._toolbar2.add_section("edge_style")
        self._edge_style_dropdown = themed_dropdown(
            self._toolbar2, options=self._edge_style_options,
            value=EdgeStyle.BEZIER.name, state="readonly", width=12,
            command=lambda _: self._on_edge_style_changed(),
        )
        self._toolbar2.add_widget("edge_style", self._edge_style_dropdown)

        self._btn_palette = self._toolbar2.make_toggle_button(
            "view_toggle", text=t("workflow.toolbar.palette"), icon="palette",
            command=self._toggle_palette, active=True,
            tooltip=t("workflow.toolbar.palette"),
        )
        self._btn_props = self._toolbar2.make_toggle_button(
            "view_toggle", text=t("workflow.toolbar.properties"), icon="properties",
            command=self._toggle_props, active=False,
            tooltip=t("workflow.toolbar.properties"),
        )
        self._btn_log = self._toolbar2.make_toggle_button(
            "view_toggle", text=t("common.log"), icon="log",
            command=self._toggle_log, active=True,
            tooltip=t("common.log"),
        )

        self._btn_debug_toggle = self._toolbar2.make_button(
            "debug", text=t("workflow.debug.toggle"), icon="debug",
            command=self._on_debug_toggle,
            tooltip=t("workflow.debug.toggle"),
        )
        self._btn_breakpoint = self._toolbar2.make_button(
            "debug", text=t("workflow.debug.breakpoint"), icon="breakpoint",
            command=self._on_toggle_breakpoint,
            tooltip=t("workflow.debug.breakpoint"), shortcut_hint="F5",
        )
        self._btn_step = self._toolbar2.make_button(
            "debug", text=t("workflow.debug.step_over"), icon="step_over",
            command=self._on_debug_step,
            tooltip=t("workflow.debug.step_over"), shortcut_hint="F10",
        )
        self._btn_step.configure(state=tk.DISABLED)
        self._btn_debug_resume = self._toolbar2.make_button(
            "debug", text=t("workflow.debug.resume"), icon="start",
            command=self._on_debug_resume,
            tooltip=t("workflow.debug.resume"), shortcut_hint="F5",
        )
        self._btn_debug_resume.configure(state=tk.DISABLED)
        self._btn_debug_stop = self._toolbar2.make_button(
            "debug", text=t("workflow.debug.stop"), icon="stop",
            command=self._on_debug_stop,
            tooltip=t("workflow.debug.stop"), shortcut_hint="Shift+F5",
        )
        self._btn_debug_stop.configure(state=tk.DISABLED)

        self._controller.undo_manager.on_change(self._on_undo_state_changed)
        self._on_undo_state_changed()

    # ── 状态栏 ──────────────────────────────────────────────

    def _build_status_bar(self):
        from src.panel.components.monitor_status_widget import MonitorStatusWidget
        th = current_theme()
        sm = scale_manager()

        # 底部区域：从下往上 pack（StatusBar 最底，MonitorWidget 在上，分隔线最上）
        self._status_bar = StatusBar(self.frame)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._monitor_widget = MonitorStatusWidget(self.frame)
        self._monitor_widget.pack(fill=tk.X, side=tk.BOTTOM)
        # 状态栏区域顶部分隔线
        self._status_separator = themed_separator(
            self.frame, orient=tk.HORIZONTAL,
            bg=th.zone_border, height=sm.s(1),
        )
        self._status_separator.pack(fill=tk.X, side=tk.BOTTOM)

    # ── 面板切换（Phase 3/4/5 实现具体逻辑）──────────────────

    def _toggle_palette(self) -> None:
        self._set_palette_mode("full" if self._palette_mode == "hidden" else "hidden")

    def _set_palette_mode(self, mode: Literal["hidden", "full"]) -> None:
        if mode == self._palette_mode:
            return
        if self._is_in_paned(self._paned, self._palette_outer):
            self._paned.forget(self._palette_outer)
        if mode == "full":
            self._palette_outer.configure(width=current_theme().panel_width_left)
            self._paned.add(self._palette_outer, before=self._canvas, stretch="never")
            self._palette_labels_visible(True)
        self._palette_mode = mode
        ToolbarFrame.update_toggle(self._btn_palette, mode != "hidden")

    def _palette_labels_visible(self, visible: bool) -> None:
        """控制面板按钮文字标签的可见性。"""
        if not hasattr(self, "_palette_labels"):
            return
        for label in self._palette_labels:
            if visible:
                label.pack(side=tk.LEFT, fill=tk.X, expand=True)
            else:
                label.pack_forget()

    def _is_in_paned(self, paned: tk.PanedWindow, widget: tk.Widget) -> bool:
        try:
            return widget in paned.panes()
        except tk.TclError:
            return False

    def _toggle_panel(
        self,
        paned: tk.PanedWindow,
        widget: tk.Widget,
        btn: LabelButton,
        visible: bool,
        size_kw: dict,
        minsize: int = 0,
    ) -> bool:
        actually_in = self._is_in_paned(paned, widget)
        if visible and actually_in:
            paned.forget(widget)
            result = False
        elif not visible and not actually_in:
            widget.configure(**size_kw)
            paned.add(widget, stretch="never", minsize=minsize)
            result = True
        else:
            result = not visible
        ToolbarFrame.update_toggle(btn, result)
        return result

    def _toggle_props(self) -> None:
        """切换右侧属性面板。"""
        self._props_visible = self._toggle_panel(
            self._paned, self._prop_panel, self._btn_props,
            self._props_visible, {"width": current_theme().panel_width_right},
            minsize=150,
        )
        self.frame.after(150, self._reposition_minimap)

    def _reposition_minimap(self) -> None:
        if hasattr(self, "_canvas"):
            self._canvas.reposition_minimap()

    def _toggle_log(self) -> None:
        """切换底部日志面板。"""
        self._log_visible = self._toggle_panel(
            self._vpaned, self._log_container, self._btn_log,
            self._log_visible, {"height": 180}, minsize=60,
        )
        self.frame.after(100, self._reposition_minimap)

    def _bind_panel_shortcuts(self) -> None:
        root = self.app.root

        def _safe_key(handler):
            def wrapper(event):
                focus = event.widget
                if isinstance(focus, (tk.Entry, tk.Text)):
                    return
                handler()
                return "break"
            return wrapper

        self._root_bindings = [
            (root.bind("<b>", _safe_key(self._toggle_palette)), "<b>"),
            (root.bind("<B>", _safe_key(self._toggle_palette)), "<B>"),
            (root.bind("<n>", _safe_key(self._toggle_props)), "<n>"),
            (root.bind("<N>", _safe_key(self._toggle_props)), "<N>"),
            (root.bind("<Control-l>", _safe_key(self._toggle_log)), "<Control-l>"),
            (root.bind("<Control-L>", _safe_key(self._toggle_log)), "<Control-L>"),
        ]

    def _update_status_bar(self):
        if not hasattr(self, "_status_bar"):
            return
        graph = self._model.graph
        nodes = len(graph.nodes) if graph else 0
        edges = len(graph.edges) if graph else 0
        self._status_bar.set_left(t("workflow.status.nodes_edges", nodes=nodes, edges=edges))
        # 缩放信息始终在右侧，不覆盖中间状态文字
        zoom_text = f"{self._current_zoom:.0%}"
        if self.app.hotkey_manager:
            self._status_bar.set_hotkey_info(self.app.hotkey_manager)
        else:
            self._status_bar.set_right(zoom_text)

    # ── 主区域 ──────────────────────────────────────────────

    def _build_main_area(self):
        theme = current_theme()
        sm = scale_manager()

        self._vpaned = tk.PanedWindow(
            self.frame, orient=tk.VERTICAL, opaqueresize=True,
            sashwidth=max(sm.s(6), 4), sashrelief=tk.FLAT, bd=0,
            bg=theme.separator_color,
            sashcursor="sb_v_double_arrow",
        )
        self._vpaned.pack(fill=tk.BOTH, expand=True, side=tk.TOP)

        upper = tk.Frame(self._vpaned, bg=theme.bg_primary)
        self._paned = tk.PanedWindow(
            upper, orient=tk.HORIZONTAL, opaqueresize=True,
            sashwidth=max(sm.s(6), 4), sashrelief=tk.FLAT, bd=0,
            bg=theme.separator_color,
            sashcursor="sb_h_double_arrow",
        )
        self._paned.pack(fill=tk.BOTH, expand=True)

        self._build_node_palette()
        self._canvas = GraphCanvas(self._paned, self._on_canvas_event)

        self._prop_panel = PropertyPanel(
            self._paned, width=theme.panel_width_right,
            title=t("workflow.properties.title"),
        )

        self._paned.add(self._canvas, stretch="always", minsize=200)

        if self._palette_mode == "full":
            self._palette_outer.configure(width=current_theme().panel_width_left)
            self._paned.add(self._palette_outer, before=self._canvas, stretch="never", minsize=80)

        self._floating_zoom = FloatingZoomControls(
            parent=self._canvas,
            on_zoom_in=self._zoom_in,
            on_zoom_out=self._zoom_out,
            on_zoom_reset=self._zoom_reset,
            on_zoom_to_fit=self._canvas.zoom_to_fit,
            on_zoom_to=self._zoom_to_level,
            get_zoom=lambda: self._current_zoom if hasattr(self, "_current_zoom") else 1.0,
        )

        self._log_container = tk.Frame(self._vpaned, bg=theme.panel_bg, height=180)
        self._log_container.pack_propagate(False)

        self._vpaned.add(upper, stretch="always", minsize=200)

        if self._log_visible:
            self._vpaned.add(self._log_container, stretch="never", minsize=60)

        self._bind_panel_shortcuts()

    # ── 左侧节点面板（由 WorkflowPaletteMixin 提供）──

    # ── 右侧属性面板（由 WorkflowPropertiesMixin 提供）──

    # ── 日志区 ──────────────────────────────────────────────

    def _build_log(self):
        self._log_notebook = ttk.Notebook(self._log_container)
        self._log_notebook.pack(fill=tk.BOTH, expand=True)

        console_tab = tk.Frame(self._log_notebook)
        self._log_notebook.add(console_tab, text=t("workflow.tab.console"))
        self._log_viewer = LogViewer(console_tab, self._ring_log, max_visible=200)
        self._log_viewer.pack(fill=tk.BOTH, expand=True)

    # ── 事件订阅 ──────────────────────────────────────────

    def _subscribe_events(self):
        self.subscribe(EventName.CHAIN_LOADED, self._on_graph_loaded)
        self.subscribe(EventName.CHAIN_STEPS_CHANGED, self._on_graph_changed)
        self.subscribe(EventName.EXECUTOR_STATE_CHANGED, self._on_executor_state)
        self.subscribe(EventName.UI_NODE_HIGHLIGHT, self._on_node_highlight)
        self.subscribe(EventName.CHAIN_MONITORS_CHANGED, self._on_monitors_changed)


    def _on_edge_style_changed(self):
        val = self._edge_style_dropdown.get_value()
        try:
            internal = EdgeStyle[val]
        except KeyError:
            internal = EdgeStyle.BEZIER
        self._canvas.set_edge_style(internal)

    # ── 配置文件操作 ──────────────────────────────────────

    # ── 配置文件操作（ProfileOpsMixin 适配）──────────────

    profile_i18n_prefix = "workflow"

    def _refresh_profiles(self):
        profiles = self._controller.list_profiles()
        self.profile_bar.refresh_list(profiles, self._model.current_profile_name)

    def _get_selected_profile_name(self):
        return self.profile_bar.get_selected()

    def _ask_string(self, title, prompt):
        result = simpledialog.askstring(title, prompt, parent=self.frame)
        return (result, result is not None)

    def _show_info(self, title, message):
        messagebox.showinfo(title, message)

    def _show_error(self, title, message):
        messagebox.showerror(title, message)

    def _ask_yes_no(self, title, message):
        return messagebox.askyesno(title, message)

    # ── 区域选择 ──────────────────────────────────────────

    def _on_pick_region(self):
        def on_region(left, top, width, height):
            self._controller.set_region(left, top, width, height)
            self._append_log(
                t("workflow.msg.region_set", w=width, h=height, x=left, y=top)
            )

        self._pick_region(on_region, capture=self.app.capture)

    def _on_fullscreen(self):
        self._controller.set_fullscreen()
        self._append_log(t("workflow.msg.fullscreen"))

    # ── 缩放 ──────────────────────────────────────────────

    def _zoom_in(self):
        self._canvas.zoom_by(1.25)

    def _zoom_out(self):
        self._canvas.zoom_by(0.8)

    def _zoom_reset(self):
        self._canvas.zoom_reset()

    def _zoom_to_level(self, level: float):
        factor = level / (self._current_zoom if hasattr(self, "_current_zoom") and self._current_zoom > 0 else 1.0)
        self._canvas.zoom_by(factor)

    def _on_graph_loaded(self, **_kwargs):
        has_loop = find_loop_edge(self._model.graph) is not None
        loop_count = self._model.graph.loop_count
        self.loop_controls.set_from_model(has_loop, loop_count if has_loop else 0)
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
                self._prop_panel.show_empty()
        self._update_status_bar()

    def _on_executor_state(self, state=None, **_kwargs):
        running = state == ExecutorState.RUNNING
        paused = state == ExecutorState.PAUSED
        active = running or paused

        if not running:
            self._canvas.highlight_node(None)

        self.run_controls.set_state(state or ExecutorState.IDLE)
        self._status_bar.set_status_dot(state or ExecutorState.IDLE)

        self._status_bar.set_center(t(STATE_I18N.get(state, "")))

        btn_state = tk.DISABLED if active else tk.NORMAL
        for btn in self._palette_btn_widgets:
            btn.configure(state=btn_state)

    def _on_node_highlight(self, node_id=None, **_kwargs):
        if self._model.executor_state != ExecutorState.RUNNING:
            return
        self._canvas.highlight_node(node_id)

    def _on_monitors_changed(self, **_kwargs):
        self._refresh_monitor_list()


    def apply_theme(self) -> None:
        super().apply_theme()
        theme = current_theme()

        # 1. 全量重绘画布
        if hasattr(self, "_canvas") and self._canvas.winfo_exists() and self._model.graph:
            self._canvas.configure(bg=theme.bg_primary)
            self._canvas.render_graph(self._model.graph)

        # 2. 共享组件主题（_toolbar 由 BasePage.apply_theme 处理）
        for comp in (
            self._toolbar2, self.profile_bar,
            self.region_bar, self.run_controls, self.loop_controls,
            self._status_bar, self._monitor_widget, self._prop_panel,
        ):
            if hasattr(comp, "apply_theme"):
                comp.apply_theme()
        if hasattr(self, "_status_separator") and self._status_separator.winfo_exists():
            self._status_separator.configure(bg=theme.zone_border)

        # 3. 布局分区主题
        for widget_name in ("_vpaned", "_paned"):
            widget = getattr(self, widget_name, None)
            if widget:
                widget.configure(bg=theme.separator_color)

        # 4. 面板递归主题
        for widget_name in ("_palette_outer", "_log_container"):
            widget = getattr(self, widget_name, None)
            if widget:
                apply_theme_recursive(widget, theme)

        # 5. 浮动缩放控件 + 小地图
        if hasattr(self, "_floating_zoom"):
            self._floating_zoom.apply_theme()
        if hasattr(self, "_canvas"):
            self._canvas.apply_theme()

        # 6. 日志 tag 重建
        if hasattr(self, "_log_viewer") and self._log_viewer:
            self._log_viewer.rebuild_tags()

        # 7. 重新显示属性面板
        if hasattr(self, "_selected_node_id") and self._selected_node_id:
            self._show_node_properties(self._selected_node_id)
        else:
            self._prop_panel.show_empty()

    # ── Toast (P6) ──────────────────────────────────────────

    def _show_toast(self, message: str) -> None:
        if hasattr(self, "_status_bar"):
            self._status_bar.set_center(message)
            self._status_bar.after(2000, lambda: self._status_bar.set_center(""))

    # ── 导航 ──────────────────────────────────────────────

    # ── 断点响应 ──────────────────────────────────────────

    def on_breakpoint_changed(self, old: Breakpoint, new: Breakpoint) -> None:
        if not hasattr(self, "_paned"):
            return
        if new == Breakpoint.COMPACT:
            self._set_palette_mode("hidden")
            if self._props_visible:
                self._toggle_props()
            if self._log_visible:
                self._toggle_log()
        # NORMAL/WIDE: 用户手动控制面板，不自动恢复

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
        if hasattr(self, "_saved_viewport") and self._canvas.winfo_exists():
            self._canvas.set_viewport(*self._saved_viewport)
        self._update_status_bar()

    def on_leave(self) -> None:
        if hasattr(self, "_canvas") and self._canvas.winfo_exists():
            self._saved_viewport = self._canvas.get_viewport()

    def _restore_executor_state(self) -> None:
        """页面重建时从执行器恢复图数据和执行状态"""
        result = super()._restore_executor_state()
        if result.graph_copied:
            self._canvas.render_graph(self._model.graph)
            has_loop = find_loop_edge(self._model.graph) is not None
            loop_count = self._model.graph.loop_count
            self.loop_controls.set_from_model(has_loop, loop_count if has_loop else 0)
        if result.state != ExecutorState.IDLE:
            self._on_executor_state(state=result.state)
            self._refresh_monitor_list()
            self._update_status_bar()

    def _cleanup_bindings(self) -> None:
        for bind_id, sequence in getattr(self, "_root_bindings", []):
            try:
                root = self.frame.winfo_toplevel()
                root.unbind(sequence, bind_id)
            except Exception:
                pass
        self._root_bindings = []

    def destroy(self):
        self._cleanup_prop_vars()
        if hasattr(self, "_canvas"):
            self._canvas.destroy_canvas()
        if hasattr(self, "_controller"):
            self._controller.destroy()
        if hasattr(self, "_log_viewer"):
            self._log_viewer.destroy()
        self._cleanup_bindings()
        self._clipboard.clear()
        super().destroy()
