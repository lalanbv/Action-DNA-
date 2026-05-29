"""动作链自动化页面 — 纯 View，委托所有业务逻辑给 Controller

三栏布局：左侧动作面板 + 中央步骤列表/监控器/日志 + 右侧属性面板。

业务逻辑拆分到 Mixin:
  - TkActionChainProfileMixin: 配置文件 CRUD + 区域选择 + 执行控制 + 事件回调 + 监控器操作
"""

import copy
import logging
import tkinter as tk
from tkinter import ttk, messagebox

from src.core.action import ActionType
from src.core.step_types import STEP_CLASSES
from src.core.debug.ring_buffer_log import RingBufferLog
from src.core.events.event_names import EventName
from src.panel.canvas.scale import scale_manager
from src.panel.canvas.theme import current_theme
from src.panel.components import (
    LogViewer,
    LoopControls,
    ProfileBar,
    ProportionalTreeMixin,
    RegionBar,
    RunControls,
    StatusBar,
    StepPalette,
    StepPropertyPanel,
    ThreeColumnLayout,
    ToolbarFrame,
)
from src.panel.components.editor_toolbar import add_editor_toolbar_sections
from src.panel.components.toolbar_icons import ICONS
from src.panel.controllers.action_chain_controller import ActionChainController
from src.panel.models.chain_model import ChainModel
from src.panel.pages.action_chain_profile_mixin import TkActionChainProfileMixin
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import ACTION_CHAIN_DESC, ACTION_CHAIN_TITLE
from src.panel.pages.page_registry import register_page
from src.panel.profile_manager import ProfileManager
from src.panel.widgets import (
    themed_button,
    themed_frame,
    themed_label,
    themed_labelframe,
)
from src.utils.i18n import t
from src.utils.step_ring import StepRing

logger = logging.getLogger(__name__)


@register_page("action_chain", label_i18n=ACTION_CHAIN_TITLE, desc_i18n=ACTION_CHAIN_DESC, icon="🔗", category="main")
class ActionChainPage(TkActionChainProfileMixin, BasePage, ProportionalTreeMixin):
    """动作链配置与执行页面（纯 View）"""

    def __init__(self, parent: tk.Widget, app, **kwargs) -> None:
        super().__init__(parent, app, **kwargs)
        self.model: ChainModel | None = None
        self.controller: ActionChainController | None = None
        self.step_ring: StepRing | None = None
        self._ring_log: RingBufferLog | None = None
        self._paned: tk.PanedWindow | None = None
        self._monitor_widget = None
        self.status_bar: StatusBar | None = None
        self._toolbar: ToolbarFrame | None = None
        self.profile_bar: ProfileBar | None = None
        self.region_bar: RegionBar | None = None
        self.run_controls: RunControls | None = None
        self.var_status: tk.StringVar | None = None
        self._lbl_status = None
        self.step_palette: StepPalette | None = None
        self.log_viewer: LogViewer | None = None
        self.step_props: StepPropertyPanel | None = None
        self.tree: ttk.Treeview | None = None
        self._tree_cols: list = []
        self._mon_frame = None
        self.mon_tree: ttk.Treeview | None = None
        self._mon_tree_cols: list = []
        self._btn_mon_add = None
        self._btn_mon_edit = None
        self._btn_mon_toggle = None
        self._btn_mon_delete = None
        self._mon_count_var: tk.StringVar | None = None

    def title(self) -> str:
        return t("chain.title")

    def build(self):
        bus = self.app.event_bus
        self.model = ChainModel(bus)
        self.controller = ActionChainController(
            model=self.model,
            executor=self.app.executor,
            capture=self.app.capture,
            matcher=self.app.matcher,
            profile_mgr=ProfileManager(),
            event_bus=bus,
            main_thread_schedule=self.frame.after,
        )
        self._ring_log = RingBufferLog(capacity=1000)

        self._build_toolbar()

        sm = scale_manager()

        self._layout = ThreeColumnLayout(
            self.frame,
            left_builder=self._build_left_panel,
            center_builder=self._build_center_panel,
            right_builder=self._build_right_panel,
        )
        self._paned = self._layout.paned

        from src.panel.components.monitor_status_widget import MonitorStatusWidget
        self._monitor_widget = MonitorStatusWidget(self.frame)
        self._monitor_widget.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_bar = StatusBar(self.frame)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        self.step_ring = StepRing(self.tree)

        self.subscribe(EventName.CHAIN_STEPS_CHANGED, self._on_steps_changed)
        self.subscribe(EventName.CHAIN_LOADED, self._on_chain_loaded)
        self.subscribe(EventName.CHAIN_MONITORS_CHANGED, self._on_monitors_changed)
        self.subscribe(EventName.EXECUTOR_STATE_CHANGED, self._on_executor_state)
        self.subscribe(EventName.UI_STEP_HIGHLIGHT, self._on_step_highlight)
        self.subscribe(EventName.UI_ROUND_STARTED, self._on_round_started)
        self.subscribe(EventName.REGION_CHANGED, self._on_region_changed)

        self._sync_executor_state()
        self._refresh_profile_list()
        self._refresh_monitor_list()

    def on_enter(self, **kwargs) -> None:
        if self.controller is None:
            return

        import_steps = kwargs.get("import_steps")
        if import_steps:
            if not self._resolve_import_conflict(
                has_content=bool(self.model.get_steps()),
                is_dirty=self.model.is_dirty,
                save_callback=self._on_save_profile,
            ):
                return
            try:
                self.controller.clear_steps()
            except RuntimeError:
                messagebox.showwarning(t("common.hint"), t("chain.msg.executor_busy"))
                return
            self.step_props.show_empty()

            for step in import_steps:
                self.controller.add_step(step)

        self._sync_executor_state()
        self._refresh_profile_list()
        self._refresh_monitor_list()

    def on_leave(self) -> None:
        pass

    def destroy(self):
        if self.controller:
            self.controller.destroy()
        super().destroy()

    def apply_theme(self):
        super().apply_theme()
        if hasattr(self, '_layout'):
            self._layout.apply_theme()
        for widget in (self.profile_bar, self.region_bar, self.run_controls, self.loop_controls):
            if widget and widget.winfo_exists():
                widget.apply_theme()

    # ── UI 构建 ──

    def _build_toolbar(self):
        th = current_theme()
        toolbar = ToolbarFrame(self.frame)
        toolbar.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)
        self._toolbar = toolbar

        # ── 创建各通用组件 ──
        self.profile_bar = ProfileBar(
            toolbar,
            on_load=self._on_load_profile,
            on_save=self._on_save_profile,
            on_save_as=self._on_save_as_profile,
            on_delete=self._on_delete_profile,
            on_export=self._on_export_profile,
            on_import=self._on_import_profile,
            compact=True,
        )

        self.loop_controls = LoopControls(
            toolbar, on_change=self._on_loop_changed,
        )

        self.region_bar = RegionBar(
            toolbar,
            on_fullscreen=self.controller.set_fullscreen,
            on_pick_region=self._on_pick_region,
            on_reset=self.controller.set_fullscreen,
            compact=True,
        )

        self.run_controls = RunControls(
            toolbar,
            on_start=self._on_start,
            on_pause=self._on_pause,
            on_resume=self._on_resume,
            on_stop=self._on_stop,
        )

        # ── 通用工具栏布局 ──
        add_editor_toolbar_sections(
            toolbar,
            title_text=t("chain.title"),
            on_back=self._go_home,
            profile_bar=self.profile_bar,
            loop_controls=self.loop_controls,
            region_bar=self.region_bar,
            run_controls=self.run_controls,
        )

        # ── 动作链特有：清空 + 状态 ──
        from src.panel.components.toolbar_tooltip import ToolbarTooltip

        btn_clear = themed_button(
            toolbar, text=f"{ICONS['delete']} {t('chain.clear')}",
            command=self._on_clear_steps,
        )
        toolbar.add_widget("run", btn_clear)
        ToolbarTooltip(btn_clear, t("chain.clear"))

        self.var_status = tk.StringVar(value=t("chain.status.ready"))
        self._lbl_status = themed_label(
            toolbar, textvariable=self.var_status, fg=th.text_muted,
        )
        toolbar.add_widget("run", self._lbl_status)
        ToolbarTooltip(self._lbl_status, t("chain.status.ready"))

    def _build_left_panel(self, parent):
        self.step_palette = StepPalette(
            parent, on_add_step=self._add_step_dialog,
        )

    def _build_center_panel(self, parent):
        self._build_step_list(parent)
        self._build_monitors_section(parent)

        self.log_viewer = LogViewer(parent, log=self._ring_log, max_visible=100)
        self.log_viewer.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))

    def _build_right_panel(self, parent):
        self.step_props = StepPropertyPanel(
            parent,
            on_move_up=self._on_move_up,
            on_move_down=self._on_move_down,
            on_edit=self._on_edit_step,
            on_delete=self._on_delete_step,
            on_enabled_change=self._on_step_enabled_change,
        )

    def _build_step_list(self, parent):
        lf = themed_labelframe(parent, text=t("chain.steps"))
        lf.pack(fill=tk.X, padx=4, pady=4)

        columns = ("index", "type", "detail", "wait", "enabled", "comment")
        self.tree = ttk.Treeview(lf, columns=columns, show="headings", height=8)
        self._tree_cols = [
            ("index", "#", 0.05, tk.CENTER),
            ("type", t("chain.col.type"), 0.12, tk.CENTER),
            ("detail", t("chain.col.detail"), 0.35, None),
            ("wait", t("chain.col.wait"), 0.14, None),
            ("enabled", t("common.enabled"), 0.06, tk.CENTER),
            ("comment", t("chain.col.comment"), 0.18, None),
        ]
        self.setup_proportional_columns(self.tree, self._tree_cols, key="steps")
        self.tree.bind("<<TreeviewSelect>>", lambda _: self._on_step_selected())
        sb = ttk.Scrollbar(lf, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<Double-1>", lambda _: self._on_edit_step())

    def _build_monitors_section(self, parent):
        th = current_theme()
        self._mon_frame = themed_labelframe(parent, text=t("chain.tab.monitors"))
        self._mon_frame.pack(fill=tk.X, padx=4, pady=(0, 4))

        tree_frame = themed_frame(self._mon_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True)

        columns = ("enabled", "name", "image", "action", "interval", "priority")
        self.mon_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=3)
        self._mon_tree_cols = [
            ("enabled", t("common.enabled"), 0.08, tk.CENTER),
            ("name", t("common.name"), 0.22, tk.W),
            ("image", t("chain.mon.col.image"), 0.25, tk.W),
            ("action", t("chain.mon.col.action"), 0.18, tk.CENTER),
            ("interval", t("chain.mon.col.interval"), 0.10, tk.CENTER),
            ("priority", t("chain.mon.col.priority"), 0.07, tk.CENTER),
        ]
        for col, text, _, anchor in self._mon_tree_cols:
            self.mon_tree.heading(col, text=text)
            self.mon_tree.column(col, width=50, anchor=anchor, stretch=True)

        self.setup_proportional_columns(self.mon_tree, self._mon_tree_cols, key="monitors")
        self.mon_tree.bind("<<TreeviewSelect>>", lambda _: self._on_monitor_select())
        self.mon_tree.bind("<Double-1>", lambda _: self._on_edit_monitor())
        self.mon_tree.bind("<Delete>", lambda _: self._on_delete_monitor())

        sb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.mon_tree.yview)
        self.mon_tree.configure(yscrollcommand=sb.set)
        self.mon_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        toolbar = themed_frame(self._mon_frame)
        toolbar.pack(fill=tk.X, pady=(th.pad_xs, 0))
        self._btn_mon_add = themed_button(toolbar, text=t("chain.mon.add"), command=self._on_add_monitor)
        self._btn_mon_add.pack(side=tk.LEFT, padx=th.pad_xs)
        self._btn_mon_edit = themed_button(toolbar, text=t("common.edit"), command=self._on_edit_monitor, state=tk.DISABLED)
        self._btn_mon_edit.pack(side=tk.LEFT, padx=th.pad_xs)
        self._btn_mon_toggle = themed_button(toolbar, text=t("chain.mon.toggle"), command=self._on_toggle_monitor, state=tk.DISABLED)
        self._btn_mon_toggle.pack(side=tk.LEFT, padx=th.pad_xs)
        self._btn_mon_delete = themed_button(toolbar, text=t("common.delete"), command=self._on_delete_monitor, state=tk.DISABLED)
        self._btn_mon_delete.pack(side=tk.LEFT, padx=th.pad_xs)

        self._mon_count_var = tk.StringVar()
        themed_label(toolbar, textvariable=self._mon_count_var, style="small").pack(side=tk.RIGHT, padx=th.pad_xs)

    # ── 步骤操作 ──

    def _on_step_selected(self) -> None:
        idx = self.step_ring.selected_index() if self.step_ring else None
        steps = self.model.get_steps()
        if idx is not None and idx < len(steps):
            self.step_props.show_step(steps[idx], idx, len(steps))
        else:
            self.step_props.show_empty()

    def _add_step_dialog(self, action_type: ActionType, title: str):
        if not self.controller:
            messagebox.showwarning(t("common.hint"), t("chain.msg.executor_busy"))
            return

        try:
            step = STEP_CLASSES[action_type]()
        except Exception:
            logger.exception("创建步骤失败: %s", action_type)
            messagebox.showerror(t("common.hint"), f"创建步骤失败: {action_type}")
            return

        def on_done(updated_step):
            try:
                self.controller.add_step(updated_step)
            except RuntimeError:
                messagebox.showwarning(t("common.hint"), t("chain.msg.executor_busy"))

        try:
            from src.panel.dialogs import open_step_dialog
            open_step_dialog(self.app.root, step, title, on_done)
        except Exception:
            logger.exception("打开步骤对话框失败: %s", action_type)
            messagebox.showerror(t("common.hint"), f"打开对话框失败: {action_type}")

    def _on_edit_step(self):
        idx = self.step_ring.selected_index() if self.step_ring else None
        if idx is None:
            messagebox.showinfo(t("common.hint"), t("chain.msg.select_step"))
            return
        steps = self.model.get_steps()
        if idx >= len(steps):
            return
        from src.panel.dialogs import open_step_dialog
        step = copy.copy(steps[idx])

        def on_done(updated_step):
            try:
                self.controller.update_step(idx, updated_step)
            except RuntimeError:
                messagebox.showwarning(t("common.hint"), t("chain.msg.executor_busy"))
                return
            self._on_step_selected()

        open_step_dialog(self.app.root, step, t("chain.edit_step"), on_done)

    def _on_step_enabled_change(self):
        idx = self.step_ring.selected_index() if self.step_ring else None
        if idx is not None:
            steps = self.model.get_steps()
            if idx < len(steps):
                try:
                    self.controller.update_step(idx, steps[idx])
                except RuntimeError:
                    pass

    def _on_delete_step(self):
        idx = self.step_ring.selected_index() if self.step_ring else None
        if idx is not None:
            try:
                self.controller.remove_step(idx)
            except RuntimeError:
                messagebox.showwarning(t("common.hint"), t("chain.msg.executor_busy"))
                return
            self.step_props.show_empty()

    def _on_clear_steps(self):
        steps = self.model.get_steps()
        if steps and messagebox.askyesno(t("common.confirm"), t("chain.msg.confirm_clear")):
            try:
                self.controller.clear_steps()
            except RuntimeError:
                messagebox.showwarning(t("common.hint"), t("chain.msg.executor_busy"))
                return
            self.step_props.show_empty()

    def _move_step(self, delta: int) -> None:
        if not self.step_ring:
            return
        idx = self.step_ring.selected_index()
        if idx is None:
            return
        target = idx + delta
        steps = self.model.get_steps()
        if target < 0 or target >= len(steps):
            return
        try:
            self.controller.move_step(idx, target)
        except RuntimeError:
            messagebox.showwarning(t("common.hint"), t("chain.msg.executor_busy"))
            return
        self.step_ring.select(target)
        self._on_step_selected()

    def _on_move_up(self):
        self._move_step(-1)

    def _on_move_down(self):
        self._move_step(1)

    # ── 辅助 ──

    def _append_log(self, msg: str) -> None:
        if self._ring_log:
            self._ring_log.append(msg)

    def _refresh_profile_list(self):
        names = self.controller.list_profiles()
        self.profile_bar.refresh_list(names, self.model.current_profile_name)

    def _on_loop_changed(self) -> None:
        """LoopControls 模式变化回调 — 由子类 Mixin 使用。"""
