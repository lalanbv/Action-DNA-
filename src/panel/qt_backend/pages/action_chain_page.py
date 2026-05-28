"""QtActionChainPage — PySide6 action chain page.

替代 tkinter ActionChainPage (~765 行)，三栏布局 + 步骤列表 + 监控 + 日志。
"""

from __future__ import annotations

import copy
import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QPlainTextEdit, QPushButton,
    QSizePolicy,
    QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from src.core.action import ActionType
from src.core.debug.ring_buffer_log import LogEventType, RingBufferLog
from src.core.events.event_names import EventName
from src.core.step_types import STEP_CLASSES
from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.components.palette_data import ACTION_PALETTE
from src.panel.controllers.action_chain_controller import ActionChainController
from src.panel.models.chain_model import ChainModel
from src.panel.profile_manager import ProfileManager
from src.panel.qt_backend.pages.action_chain_profile_mixin import QtActionChainProfileMixin
from src.panel.qt_backend.pages.action_chain_props_mixin import QtActionChainPropsMixin
from src.panel.qt_backend.pages.base_page import QtBasePage
from src.panel.pages.page_i18n import ACTION_CHAIN_DESC, ACTION_CHAIN_TITLE
from src.panel.qt_backend.pages.page_registry import register_page
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_label, themed_palette_button, themed_section_header
from src.utils.i18n import t

logger = logging.getLogger(__name__)


@register_page("action_chain", label_i18n=ACTION_CHAIN_TITLE, desc_i18n=ACTION_CHAIN_DESC, icon="🔗", category="main")
class QtActionChainPage(QtActionChainProfileMixin, QtActionChainPropsMixin, QtBasePage):
    """动作链配置与执行页面 — 纯 View，委托业务给 ActionChainController。"""

    def title(self) -> str:
        return t("chain.title")

    def build(self):
        QVBoxLayout(self)
        self._init_services()
        self._build_toolbar()
        self._build_status_bar()
        self._build_main_area()
        self._subscribe_events()
        self._sync_executor_state()
        self._refresh_profile_list()
        self._refresh_monitor_list()

    # ── 服务初始化 ──────────────────────────────────────────

    def _init_services(self):
        bus = self.app.event_bus
        self._model = ChainModel(bus)
        self._controller = ActionChainController(
            model=self._model,
            executor=self.app.executor,
            capture=self.app.capture,
            matcher=self.app.matcher,
            profile_mgr=ProfileManager(),
            event_bus=bus,
            main_thread_schedule=self.schedule,
        )
        self._ring_log = RingBufferLog(capacity=1000)
        self._selected_step_idx: int | None = None

    # ── 工具栏 ──────────────────────────────────────────────

    def _build_toolbar(self):
        th = current_theme()
        sm = qt_scale_manager()

        toolbar = QWidget()
        toolbar.setObjectName("actionChainToolbar")
        toolbar.setStyleSheet(
            f"QWidget#actionChainToolbar {{ background-color: {th.panel_bg}; border: none; }}"
        )
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        btn_style = (
            f"QPushButton {{ background: transparent; border: none; "
            f"padding: 4px 8px; color: {th.text_primary}; }}"
            f"QPushButton:hover {{ background: {th.bg_surface_hover}; "
            f"border-radius: 3px; }}"
        )

        def _tb(text: str, handler) -> QPushButton:
            b = QPushButton(text)
            b.setStyleSheet(btn_style)
            b.clicked.connect(handler)
            return b

        layout.addWidget(_tb(t("common.back"), self._go_home))
        layout.addWidget(self._make_label(t("chain.title"), bold=True))

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {th.border_default};")
        layout.addWidget(sep)

        # 配置文件
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(sm.s(120))
        self._profile_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        layout.addWidget(self._profile_combo)

        for label, handler in [
            (t("common.load"), self._on_load_profile),
            (t("common.save"), self._on_save_profile),
            (t("common.save_as"), self._on_save_as_profile),
            (t("common.delete"), self._on_delete_profile),
            (t("chain.export"), self._on_export_profile),
            (t("chain.import"), self._on_import_profile),
        ]:
            layout.addWidget(_tb(label, handler))

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet(f"color: {th.border_default};")
        layout.addWidget(sep2)

        # 区域
        layout.addWidget(_tb(t("chain.region.fullscreen"), self._on_fullscreen))
        layout.addWidget(_tb(t("chain.region.pick"), self._on_pick_region))

        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.VLine)
        sep3.setStyleSheet(f"color: {th.border_default};")
        layout.addWidget(sep3)

        # 循环
        self._loop_cb = QCheckBox(t("common.infinite_loop"))
        self._loop_cb.setChecked(True)
        layout.addWidget(self._loop_cb)
        self._loop_count_spin = QSpinBox()
        self._loop_count_spin.setRange(0, 9999)
        self._loop_count_spin.setValue(0)
        self._loop_count_spin.setVisible(not self._loop_cb.isChecked())
        layout.addWidget(self._loop_count_spin)
        self._loop_cb.stateChanged.connect(
            lambda: self._loop_count_spin.setVisible(not self._loop_cb.isChecked()),
        )

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(spacer)

        # 运行控制
        for label, handler in [
            (t("common.start"), self._on_start),
            (t("common.pause"), self._on_pause),
            (t("common.resume"), self._on_resume),
            (t("common.stop"), self._on_stop),
        ]:
            layout.addWidget(_tb(label, handler))

        sep4 = QFrame()
        sep4.setFrameShape(QFrame.Shape.VLine)
        sep4.setStyleSheet(f"color: {th.border_default};")
        layout.addWidget(sep4)

        layout.addWidget(_tb(t("chain.clear"), self._on_clear_steps))

        self._status_label = QLabel(t("chain.status.ready"))
        self._status_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        layout.addWidget(self._status_label)

        self._toolbar = toolbar
        self.layout().addWidget(toolbar)

    # ── 状态栏 ──────────────────────────────────────────────

    def _build_status_bar(self):
        self._build_qt_status_bar(center_label=False)

        from src.panel.qt_backend.components.monitor_status_widget import QtMonitorStatusWidget
        self._monitor_widget = QtMonitorStatusWidget()

        status_container = QWidget()
        container_layout = QVBoxLayout(status_container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(self._monitor_widget)
        container_layout.addWidget(self._status_bar)

        self.layout().addWidget(status_container)

    # ── 主区域 ──────────────────────────────────────────────

    def _build_main_area(self):
        th = current_theme()
        sm = qt_scale_manager()

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：步骤面板
        self._palette_widget = self._build_palette_panel()
        self._palette_widget.setFixedWidth(sm.s(160))

        # 中央：步骤列表 + 监控器 + 日志
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(4)
        self._build_step_list(center_layout)
        self._build_monitors_section(center_layout)
        self._build_log_viewer(center_layout)

        # 右侧：属性面板
        self._props_widget = QWidget()
        self._props_widget.setFixedWidth(sm.s(240))
        self._props_layout = QVBoxLayout(self._props_widget)
        self._props_layout.setContentsMargins(4, 4, 4, 4)
        self._show_empty_props()

        splitter.addWidget(self._palette_widget)
        splitter.addWidget(center)
        splitter.addWidget(self._props_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        self.layout().addWidget(splitter)
        self._splitter = splitter

    # ── 步骤面板 ──────────────────────────────────────────

    def _build_palette_panel(self) -> QWidget:
        th = current_theme()
        sm = qt_scale_manager()
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        header = themed_section_header(widget, t("workflow.palette.section_action"))
        layout.addWidget(header)

        self._palette_buttons: list[QPushButton] = []
        color = node_fill_color("ACTION")
        for action_type, i18n_key in ACTION_PALETTE:
            btn = themed_palette_button(
                widget, t(i18n_key), color,
                command=lambda at=action_type, ik=i18n_key: self._add_step_dialog(at, t(ik)),
            )
            layout.addWidget(btn)
            self._palette_buttons.append(btn)

        layout.addStretch()
        return widget

    # ── 步骤列表 ──────────────────────────────────────────

    def _build_step_list(self, parent_layout: QVBoxLayout):
        th = current_theme()
        sm = qt_scale_manager()

        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(sm.s(4), sm.s(4), sm.s(4), sm.s(4))

        title = QLabel(t("chain.steps"))
        title.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(10)}px;")
        frame_layout.addWidget(title)

        self._step_tree = QTreeWidget()
        self._step_tree.setHeaderLabels([
            "#", t("chain.col.type"), t("chain.col.detail"),
            t("chain.col.wait"), t("common.enabled"), t("chain.col.comment"),
        ])
        self._step_tree.setRootIsDecorated(False)
        self._step_tree.setColumnCount(6)
        header = self._step_tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        # No fixed max height — let layout allocate space dynamically
        self._step_tree.currentItemChanged.connect(lambda *_: self._on_step_selected())
        self._step_tree.itemDoubleClicked.connect(lambda: self._on_edit_step())
        frame_layout.addWidget(self._step_tree)

        parent_layout.addWidget(frame, 1)  # stretch=1: step list gets most vertical space ──────────────────────────────────────────

    def _build_monitors_section(self, parent_layout: QVBoxLayout):
        th = current_theme()
        sm = qt_scale_manager()

        frame = QFrame()
        frame.setStyleSheet(f"""
            QFrame {{
                background-color: {th.panel_bg};
                border: 1px solid {th.border_default};
                border-radius: 4px;
            }}
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(sm.s(4), sm.s(4), sm.s(4), sm.s(4))

        title = QLabel(t("chain.tab.monitors"))
        title.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(10)}px;")
        frame_layout.addWidget(title)

        self._mon_tree = QTreeWidget()
        self._mon_tree.setHeaderLabels([
            t("common.enabled"), t("common.name"), t("chain.mon.col.image"),
            t("chain.mon.col.action"), t("chain.mon.col.interval"), t("chain.mon.col.priority"),
        ])
        self._mon_tree.setRootIsDecorated(False)
        self._mon_tree.setColumnCount(6)
        # No fixed max height — let layout allocate space dynamically
        self._mon_tree.itemDoubleClicked.connect(lambda: self._on_edit_monitor())
        frame_layout.addWidget(self._mon_tree)

        btn_row = QHBoxLayout()
        self._mon_edit_btn: QPushButton | None = None
        self._mon_toggle_btn: QPushButton | None = None
        self._mon_delete_btn: QPushButton | None = None
        for icon, handler in [
            (t("chain.mon.add"), self._on_add_monitor),
            (t("common.edit"), self._on_edit_monitor),
            (t("chain.mon.toggle"), self._on_toggle_monitor),
            (t("common.delete"), self._on_delete_monitor),
        ]:
            btn = QPushButton(icon)
            btn.setFixedHeight(sm.s(24))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {th.btn_bg};
                    color: {th.text_primary};
                    border: 1px solid {th.border_default};
                    border-radius: 3px;
                    padding: 2px {sm.s(6)}px;
                    font-size: {sm.s(9)}px;
                }}
                QPushButton:hover {{
                    background-color: {th.btn_bg_hover};
                    border-color: {th.accent_blue};
                }}
            """)
            btn.clicked.connect(lambda _checked, h=handler: h())
            btn_row.addWidget(btn)
            # 保存编辑/切换/删除按钮引用，用于根据选择状态启用/禁用
            if icon == t("common.edit"):
                self._mon_edit_btn = btn
            elif icon == t("chain.mon.toggle"):
                self._mon_toggle_btn = btn
            elif icon == t("common.delete"):
                self._mon_delete_btn = btn

        # 初始状态：无选中时禁用编辑/切换/删除
        self._set_mon_buttons_enabled(False)
        self._mon_tree.currentItemChanged.connect(lambda *_: self._on_monitor_select())

        self._mon_count_label = QLabel("")
        self._mon_count_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
        btn_row.addStretch()
        btn_row.addWidget(self._mon_count_label)
        frame_layout.addLayout(btn_row)

        parent_layout.addWidget(frame)

    # ── 日志区 ──────────────────────────────────────────

    def _build_log_viewer(self, parent_layout: QVBoxLayout):
        th = current_theme()
        sm = qt_scale_manager()

        self._log_text = QPlainTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setMaximumBlockCount(200)
        self._log_text.setStyleSheet(f"""
            color: {th.text_primary};
            font-size: {sm.s(9)}px;
            font-family: monospace;
            background-color: {th.panel_bg};
            border: 1px solid {th.border_default};
            border-radius: 4px;
            padding: {sm.s(4)}px;
        """)
        parent_layout.addWidget(self._log_text, stretch=1)

    # ── 事件订阅 ──────────────────────────────────────────

    def _subscribe_events(self):
        self.subscribe(EventName.CHAIN_STEPS_CHANGED, self._on_steps_changed)
        self.subscribe(EventName.CHAIN_LOADED, self._on_chain_loaded)
        self.subscribe(EventName.CHAIN_MONITORS_CHANGED, self._on_monitors_changed)
        self.subscribe(EventName.EXECUTOR_STATE_CHANGED, self._on_executor_state)
        self.subscribe(EventName.UI_STEP_HIGHLIGHT, self._on_step_highlight)
        self.subscribe(EventName.UI_ROUND_STARTED, self._on_round_started)
        self.subscribe(EventName.REGION_CHANGED, self._on_region_changed)

    # ── 步骤操作 ──────────────────────────────────────────

    def _add_step_dialog(self, action_type: ActionType, title: str):
        try:
            step = STEP_CLASSES[action_type]()
        except (KeyError, TypeError) as e:
            logger.warning("Unsupported action type: %s", action_type, exc_info=True)
            self._show_warning(t("common.error"), str(e))
            return

        def on_done(updated_step):
            self._controller.add_step(updated_step)

        from src.panel.qt_backend.dialogs.step_dialogs import open_step_dialog
        open_step_dialog(self, step, title, on_done=on_done)

    def _on_step_selected(self) -> None:
        idx = self._get_selected_step_index()
        steps = self._model.get_steps()
        if idx is not None and idx < len(steps):
            self._selected_step_idx = idx
            self._show_step_props(steps[idx], idx, len(steps))
        else:
            self._selected_step_idx = None
            self._show_empty_props()

    def _get_selected_step_index(self) -> int | None:
        item = self._step_tree.currentItem()
        if item is None:
            return None
        idx = self._step_tree.indexOfTopLevelItem(item)
        return idx if idx >= 0 else None

    def _on_edit_step(self):
        idx = self._get_selected_step_index()
        if idx is None:
            self._show_info(t("common.hint"), t("chain.msg.select_step"))
            return
        steps = self._model.get_steps()
        if idx >= len(steps):
            return
        step = copy.copy(steps[idx])

        def on_done(updated_step):
            try:
                self._controller.update_step(idx, updated_step)
            except RuntimeError:
                self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))
                return
            self._on_step_selected()

        from src.panel.qt_backend.dialogs.step_dialogs import open_step_dialog
        open_step_dialog(self, step, t("chain.edit_step"), on_done=on_done)

    def _on_step_enabled_change(self):
        idx = self._selected_step_idx
        if idx is not None:
            steps = self._model.get_steps()
            if idx < len(steps):
                try:
                    self._controller.update_step(idx, steps[idx])
                except RuntimeError:
                    pass

    def _on_delete_step(self):
        idx = self._selected_step_idx
        if idx is not None:
            try:
                self._controller.remove_step(idx)
            except RuntimeError:
                self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))
                return
            self._selected_step_idx = None
            self._show_empty_props()

    def _on_clear_steps(self):
        steps = self._model.get_steps()
        if steps:
            if self._ask_yes_no(t("common.confirm"), t("chain.msg.confirm_clear")):
                try:
                    self._controller.clear_steps()
                except RuntimeError:
                    self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))
                    return
                self._selected_step_idx = None
                self._show_empty_props()

    def _move_step(self, delta: int) -> None:
        idx = self._selected_step_idx
        if idx is None:
            return
        target = idx + delta
        steps = self._model.get_steps()
        if target < 0 or target >= len(steps):
            return
        try:
            self._controller.move_step(idx, target)
        except RuntimeError:
            self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))
            return
        self._selected_step_idx = target
        item = self._step_tree.topLevelItem(target)
        if item:
            self._step_tree.setCurrentItem(item)
        self._on_step_selected()

    def _on_move_up(self):
        self._move_step(-1)

    def _on_move_down(self):
        self._move_step(1)

    # ── 监控器操作 ──────────────────────────────────────────

    def _on_add_monitor(self):
        from src.core.monitor import MonitorConfig
        from src.panel.qt_backend.dialogs.monitor_dialog import open_monitor_dialog

        mon = MonitorConfig()

        def on_done(result):
            self._controller.add_monitor(result)
            self._append_log(t("chain.msg.monitor_added", name=result.name))

        open_monitor_dialog(self, mon, t("chain.mon.add"), on_done=on_done)

    def _get_selected_monitor(self) -> tuple[int, list] | None:
        item = self._mon_tree.currentItem()
        if item is None:
            return None
        idx = self._mon_tree.indexOfTopLevelItem(item)
        monitors = self._controller.get_monitors()
        if idx < 0 or idx >= len(monitors):
            return None
        return idx, monitors

    def _on_edit_monitor(self):
        result = self._get_selected_monitor()
        if result is None:
            self._show_info(t("common.hint"), t("chain.msg.no_monitors"))
            return
        idx, monitors = result
        from src.panel.qt_backend.dialogs.monitor_dialog import open_monitor_dialog
        mon = copy.copy(monitors[idx])

        def on_done(updated):
            self._controller.update_monitor(idx, updated)
            self._append_log(t("chain.msg.monitor_updated", name=updated.name))

        open_monitor_dialog(self, mon, t("common.edit"), on_done=on_done)

    def _on_delete_monitor(self):
        result = self._get_selected_monitor()
        if result is None:
            return
        idx, monitors = result
        if self._ask_yes_no(
            t("common.confirm"),
            t("chain.msg.confirm_delete_monitor", name=monitors[idx].name),
        ):
            self._controller.remove_monitor(idx)

    def _on_toggle_monitor(self):
        result = self._get_selected_monitor()
        if result is None:
            return
        idx, monitors = result
        mon = copy.copy(monitors[idx])
        mon.enabled = not mon.enabled
        self._controller.update_monitor(idx, mon)

    def _set_mon_buttons_enabled(self, enabled: bool) -> None:
        for btn in (self._mon_edit_btn, self._mon_toggle_btn, self._mon_delete_btn):
            if btn is not None:
                btn.setEnabled(enabled)

    def _on_monitor_select(self) -> None:
        has_selection = self._get_selected_monitor() is not None
        self._set_mon_buttons_enabled(has_selection)

    def _refresh_monitor_list(self):
        if not hasattr(self, "_mon_tree") or self._mon_tree is None:
            return
        self._mon_tree.clear()
        monitors = self._controller.get_monitors()
        for m in monitors:
            action_text = m.handler_action.value
            item = QTreeWidgetItem([
                "✓" if m.enabled else "--",
                m.name,
                m.image_path or "",
                action_text,
                f"{m.check_interval}s",
                str(m.priority),
            ])
            self._mon_tree.addTopLevelItem(item)

        count = len(monitors)
        enabled = sum(1 for m in monitors if m.enabled)
        if hasattr(self, "_mon_count_label"):
            self._mon_count_label.setText(t("chain.mon.count_format", enabled=enabled, total=count))

    # ── 列表刷新 ──────────────────────────────────────────

    def _refresh_step_list(self):
        if not hasattr(self, "_step_tree") or self._step_tree is None:
            return
        self._step_tree.clear()
        steps = self._model.get_steps()
        for i, step in enumerate(steps):
            type_name = step.action_type.value
            wait_text = f"{step.wait_time}s" if hasattr(step, "wait_time") and step.wait_time else ""
            enabled_text = "✓" if step.enabled else "--"
            item = QTreeWidgetItem([
                str(i + 1),
                type_name,
                step.describe(),
                wait_text,
                enabled_text,
                step.comment or "",
            ])
            self._step_tree.addTopLevelItem(item)

        # 恢复选中
        if self._selected_step_idx is not None and self._selected_step_idx < len(steps):
            item = self._step_tree.topLevelItem(self._selected_step_idx)
            if item:
                self._step_tree.setCurrentItem(item)

    # ── 配置文件列表刷新 ──────────────────────────────────────────

    def _refresh_profile_list(self):
        if not hasattr(self, "_profile_combo"):
            return
        self._profile_combo.clear()
        names = self._controller.list_profiles()
        for name in names:
            self._profile_combo.addItem(name)
        current = self._model.current_profile_name
        if current:
            idx = self._profile_combo.findText(current)
            if idx >= 0:
                self._profile_combo.setCurrentIndex(idx)

    # ── 主题 ──────────────────────────────────────────────

    def apply_theme(self) -> None:
        super().apply_theme()
        th = current_theme()
        sm = qt_scale_manager()
        if hasattr(self, "_toolbar"):
            btn_style = (
                f"QPushButton {{ background: transparent; border: none; "
                f"padding: 4px 8px; color: {th.text_primary}; }}"
                f"QPushButton:hover {{ background: {th.bg_surface_hover}; "
                f"border-radius: 3px; }}"
            )
            self._toolbar.setStyleSheet(
                f"QWidget#actionChainToolbar {{ background-color: {th.panel_bg}; border: none; }}"
            )
            for btn in self._toolbar.findChildren(QPushButton):
                btn.setStyleSheet(btn_style)
        if hasattr(self, "_status_bar"):
            self._status_bar.setStyleSheet(
                f"background-color: {th.panel_bg}; border-top: 1px solid {th.border_default};"
            )
        if self._selected_step_idx is not None:
            steps = self._model.get_steps()
            if self._selected_step_idx < len(steps):
                self._show_step_props(steps[self._selected_step_idx],
                                      self._selected_step_idx, len(steps))

    # ── 辅助 ──────────────────────────────────────────────

    def _make_label(self, text: str, bold: bool = False) -> QLabel:
        return themed_label(self, text=text, style="section" if bold else "body")

    # ── 导航 ──────────────────────────────────────────────

    # ── 生命周期 ──────────────────────────────────────────

    def on_enter(self, **kwargs) -> None:
        if not hasattr(self, "_controller"):
            return

        import_steps = kwargs.get("import_steps")
        if import_steps:
            if not self._resolve_import_conflict(
                has_content=bool(self._model.get_steps()),
                is_dirty=self._model.is_dirty,
                save_callback=self._on_save_profile,
            ):
                return
            try:
                self._controller.clear_steps()
            except RuntimeError:
                self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))
                return
            self._selected_step_idx = None
            self._show_empty_props()

            for step in import_steps:
                self._controller.add_step(step)

        self._sync_executor_state()
        self._refresh_profile_list()
        self._refresh_monitor_list()

    def on_leave(self) -> None:
        pass

    def destroy_page(self) -> None:
        if hasattr(self, "_controller"):
            self._controller.destroy()
        super().destroy_page()
