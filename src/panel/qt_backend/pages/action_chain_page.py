"""QtActionChainPage — PySide6 action chain page.

替代 tkinter ActionChainPage (~765 行)，三栏布局 + 步骤列表 + 监控 + 日志。
"""

from __future__ import annotations

import copy
import logging
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QPlainTextEdit, QPushButton,
    QScrollArea, QSizePolicy,
    QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from src.core.action import ActionType
from src.core.debug.ring_buffer_log import LogEventType, RingBufferLog
from src.core.events.event_names import EventName
from src.core.step_types import STEP_CLASSES
from src.panel.canvas.theme import current_theme, node_fill_color
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.components.palette_data import ACTION_PALETTE, action_accent
from src.panel.components.step_param_view import (
    build_batch_move_order,
    build_block_insert_order,
    build_bottom_order,
    build_top_order,
    drop_insert_target,
    wait_text,
)
from src.panel.controllers.action_chain_controller import ActionChainController
from src.panel.models.chain_model import ChainModel, ExecutorState
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


class _ReorderableTreeWidget(QTreeWidget):
    """支持拖拽重排 + 多选的步骤树。

    拖拽释放时计算「源选中行 → 目标行」的 insert 语义 new_order，
    通过 ``reordered`` 信号通知宿主调 ``controller.reorder_steps``；
    不让默认 dropEvent 移动 widget item，由 model 事件触发 refresh 重建。
    """

    reordered = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.setRootIsDecorated(False)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._drag_rows: list[int] = []

    def startDrag(self, actions):
        self._drag_rows = sorted({self.indexOfTopLevelItem(i) for i in self.selectedItems()})
        super().startDrag(actions)

    def dropEvent(self, event):
        if event.source() is not self or not self._drag_rows:
            super().dropEvent(event)
            return
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        target_item = self.itemAt(pos)
        n = self.topLevelItemCount()
        if target_item is None:
            target = n  # 落到所有行下方空区 → 追加末尾
        else:
            idx = self.indexOfTopLevelItem(target_item)
            below = pos.y() > self.visualItemRect(target_item).center().y()
            target = drop_insert_target(idx, below, n)  # 半行定位:下半→后,上半→前
        # 选中块整体 insert(支持多选拖拽)
        new_order = build_block_insert_order(n, self._drag_rows, target)
        self._drag_rows = []
        event.accept()
        # 不调 super().dropEvent：默认会移动 widget item 而 model 未同步；
        # 由 reordered → controller.reorder → CHAIN_STEPS_CHANGED → _refresh 重建。
        self.reordered.emit(new_order)


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
        # 共享执行日志缓冲(与工作流页/桥接器/LoggingLayer 同一实例)。防御性回退防 None。
        self._ring_log = self.app.ring_log or RingBufferLog(capacity=1000)
        self._selected_step_idx: int | None = None
        # 执行进度轮询器: 每秒刷新 3 段(仅 RUNNING 时持续)。状态栏标签在基类 base_page 构建。
        # 直达底层 _timer.schedule(绕过 self.schedule)——后者会把每个 token 追加进
        # _timer_ids 且永不修剪,每秒 re-arm 会让该列表无限增长。ticker 自管单个 token,
        # destroy_page 时显式 stop() 清理,无需 page 跟踪。
        from src.panel.execution_status import ExecutionStatusTicker
        self._exec_ticker = ExecutionStatusTicker(
            schedule=self._timer.schedule,
            cancel=self._timer.cancel,
            refresh=self._refresh_execution_status,
            is_running=lambda: self._model.executor_state == ExecutorState.RUNNING,
        )

    # ── 样式辅助 ──────────────────────────────────────────────

    @staticmethod
    def _toolbar_btn_style() -> str:
        th = current_theme()
        return (
            f"QPushButton {{ background: transparent; border: none; "
            f"padding: 4px 8px; color: {th.text_primary}; }}"
            f"QPushButton:hover {{ background: {th.bg_surface_hover}; "
            f"border-radius: 3px; }}"
        )

    @staticmethod
    def _make_vsep() -> QFrame:
        th = current_theme()
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet(f"color: {th.border_default};")
        return sep

    @staticmethod
    def _styled_panel() -> tuple[QFrame, QVBoxLayout]:
        sm = qt_scale_manager()
        frame = QFrame()
        # 用 objectName 引用全局 QSS 的 QFrame#dnaStyledPanel 规则，而非局部
        # setStyleSheet —— 后者会形成样式上下文隔离，导致主题切换时子树内的
        # QTreeWidget 内容区(viewport)不重新解析样式(内容区停留旧主题色)。
        frame.setObjectName("dnaStyledPanel")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(sm.s(4), sm.s(4), sm.s(4), sm.s(4))
        return frame, layout

    # ── 工具栏 ──────────────────────────────────────────────

    def _build_toolbar(self):
        th = current_theme()
        sm = qt_scale_manager()
        btn_style = self._toolbar_btn_style()

        toolbar = QWidget()
        toolbar.setObjectName("actionChainToolbar")
        toolbar.setStyleSheet(
            f"QWidget#actionChainToolbar {{ background-color: {th.panel_bg}; border: none; }}"
        )
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        def _tb(text: str, handler) -> QPushButton:
            b = QPushButton(text)
            b.setObjectName("dnaToolBtn")  # 工具栏按钮样式来自全局 QSS，随主题刷新
            b.clicked.connect(handler)
            return b

        layout.addWidget(_tb(t("common.back"), self._go_home))
        layout.addWidget(self._make_label(t("chain.title"), bold=True))
        layout.addWidget(self._make_vsep())

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

        layout.addWidget(self._make_vsep())

        # 区域
        layout.addWidget(_tb(t("chain.region.fullscreen"), self._on_fullscreen))
        layout.addWidget(_tb(t("chain.region.pick"), self._on_pick_region))

        layout.addWidget(self._make_vsep())

        # 循环 — 三模式下拉 + 可选次数输入，与 tkinter LoopControls 对齐
        self._build_loop_controls(toolbar, th, sm)
        layout.addWidget(self._loop_container)

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

        layout.addWidget(self._make_vsep())

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

        # 左侧：步骤面板（可拖拽调整宽度）
        self._palette_widget = self._build_palette_panel()
        self._palette_widget.setMinimumWidth(sm.s(100))

        # 中央：步骤列表 + 监控器 + 日志
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(4, 4, 4, 4)
        center_layout.setSpacing(4)
        self._build_step_list(center_layout)
        self._build_monitors_section(center_layout)
        self._build_log_viewer(center_layout)

        # 右侧：属性面板（可拖拽调整宽度）
        self._props_widget = QWidget()
        self._props_widget.setMinimumWidth(sm.s(150))
        self._props_layout = QVBoxLayout(self._props_widget)
        self._props_layout.setContentsMargins(4, 4, 4, 4)
        self._show_empty_props()

        splitter.addWidget(self._palette_widget)
        splitter.addWidget(center)
        splitter.addWidget(self._props_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)

        # 设置初始面板宽度分配
        palette_w = sm.s(th.panel_width_left if hasattr(th, 'panel_width_left') else 200)
        props_w = sm.s(th.panel_width_right if hasattr(th, 'panel_width_right') else 260)
        splitter.setSizes([palette_w, max(400, splitter.width() - palette_w - props_w), props_w])

        self.layout().addWidget(splitter)
        self._splitter = splitter

    # ── 步骤面板 ──────────────────────────────────────────

    def _build_palette_panel(self) -> QWidget:
        th = current_theme()
        sm = qt_scale_manager()
        widget = QWidget()
        outer_layout = QVBoxLayout(widget)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        header = themed_section_header(widget, t("workflow.palette.section_action"))
        outer_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {th.panel_bg};")

        scroll_content = QWidget()
        layout = QVBoxLayout(scroll_content)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)

        self._palette_buttons: list[QPushButton] = []
        self._palette_action_types: list[ActionType] = []

        def _add_step_cmd(at: ActionType, ik: str) -> Callable[[], None]:
            # 工厂捕获循环变量（每次调用绑定独立的 at/ik），返回无参 Callable
            return lambda: self._add_step_dialog(at, t(ik))

        for action_type, i18n_key in ACTION_PALETTE:
            accent_token = action_accent(action_type)
            color = getattr(th, accent_token, th.accent_blue)
            btn = themed_palette_button(
                scroll_content, t(i18n_key), color,
                command=_add_step_cmd(action_type, i18n_key),
            )
            layout.addWidget(btn)
            self._palette_buttons.append(btn)
            self._palette_action_types.append(action_type)

        layout.addStretch()
        scroll.setWidget(scroll_content)
        outer_layout.addWidget(scroll)
        return widget

    # ── 步骤列表 ──────────────────────────────────────────

    def _build_step_list(self, parent_layout: QVBoxLayout):
        sm = qt_scale_manager()
        th = current_theme()

        frame, frame_layout = self._styled_panel()

        # 标题行 + 批量重排按钮（支持多选）
        title_row = QHBoxLayout()
        title = QLabel(t("chain.steps"))
        title.setObjectName("dnaTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        for text, handler in [
            (t("common.move_top"), self._on_move_top),
            ("↑", lambda: self._on_move_batch(-1)),
            ("↓", lambda: self._on_move_batch(1)),
            (t("common.move_bottom"), self._on_move_bottom),
        ]:
            b = QPushButton(text)
            b.setObjectName("dnaToolBtn")
            b.setFixedHeight(sm.s(22))
            b.clicked.connect(handler)
            title_row.addWidget(b)
        frame_layout.addLayout(title_row)

        self._step_tree = _ReorderableTreeWidget()
        self._step_tree.setHeaderLabels([
            "#", t("chain.col.type"), t("chain.col.detail"),
            t("chain.col.wait"), t("common.enabled"), t("chain.col.comment"),
        ])
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
        self._step_tree.reordered.connect(self._on_tree_reorder)
        frame_layout.addWidget(self._step_tree)

        parent_layout.addWidget(frame, 1)  # stretch=1: step list gets most vertical space ──────────────────────────────────────────

    def _build_monitors_section(self, parent_layout: QVBoxLayout):
        th = current_theme()
        sm = qt_scale_manager()

        frame, frame_layout = self._styled_panel()

        title = QLabel(t("chain.tab.monitors"))
        title.setObjectName("dnaTitle")
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
            btn.setObjectName("dnaMonBtn")  # 紧凑按钮样式来自全局 QSS，随主题刷新
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

    # ── 循环控件 ──────────────────────────────────────────

    _LOOP_SINGLE = "single"
    _LOOP_INFINITE = "infinite"
    _LOOP_FINITE = "finite"

    def _build_loop_controls(self, parent: QWidget, th, sm) -> None:
        """构建三模式循环控件：单次执行 / 无限循环 / 指定次数。"""
        container = QFrame(parent)
        container.setObjectName("loopControlFrame")
        lay = QHBoxLayout(container)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(sm.s(4))

        combo_style = f"""
            QComboBox {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: 3px;
                padding: 1px {sm.s(4)}px;
                font-size: {sm.s(10)}px;
                min-width: {sm.s(80)}px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: {sm.s(16)}px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                selection-background-color: {th.accent_blue};
                selection-color: {th.text_on_accent};
            }}
        """

        self._loop_combo = QComboBox()
        self._loop_combo.setObjectName("loopCombo")
        self._loop_combo.setStyleSheet(combo_style)
        self._loop_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        for mode, i18n_key in [
            (self._LOOP_SINGLE, "common.loop.single"),
            (self._LOOP_INFINITE, "common.loop.infinite"),
            (self._LOOP_FINITE, "common.loop.finite"),
        ]:
            self._loop_combo.addItem(t(i18n_key), mode)
        self._loop_combo.setCurrentIndex(1)  # 默认：无限循环
        self._loop_combo.currentIndexChanged.connect(self._on_loop_mode_changed)
        lay.addWidget(self._loop_combo)

        spin_style = f"""
            QSpinBox {{
                background-color: {th.input_bg};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: 3px;
                padding: 1px {sm.s(4)}px;
                font-size: {sm.s(10)}px;
            }}
        """

        self._loop_count_spin = QSpinBox()
        self._loop_count_spin.setObjectName("loopCountSpin")
        self._loop_count_spin.setRange(1, 9999)
        self._loop_count_spin.setValue(1)
        self._loop_count_spin.setFixedWidth(sm.s(56))
        self._loop_count_spin.setStyleSheet(spin_style)
        self._loop_count_spin.setVisible(False)
        lay.addWidget(self._loop_count_spin)

        self._loop_times_label = QLabel(t("common.loop.times"))
        self._loop_times_label.setStyleSheet(
            f"color: {th.text_secondary}; font-size: {sm.s(10)}px;"
        )
        self._loop_times_label.setVisible(False)
        lay.addWidget(self._loop_times_label)

        self._loop_container = container

    def _on_loop_mode_changed(self) -> None:
        mode = self._loop_combo.currentData()
        finite = mode == self._LOOP_FINITE
        self._loop_count_spin.setVisible(finite)
        self._loop_times_label.setVisible(finite)

    def _loop_mode(self) -> str:
        return self._loop_combo.currentData() or self._LOOP_INFINITE

    def _set_loop_mode(self, mode: str, count: int = 1) -> None:
        for i in range(self._loop_combo.count()):
            if self._loop_combo.itemData(i) == mode:
                self._loop_combo.setCurrentIndex(i)
                break
        if mode == self._LOOP_FINITE:
            self._loop_count_spin.setValue(max(1, count))
        self._on_loop_mode_changed()

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

    def _on_duplicate(self):
        """复制当前步骤：副本插入到其后，并选中新副本。"""
        idx = self._selected_step_idx
        if idx is None:
            return
        try:
            new_idx = self._controller.duplicate_step(idx)
        except RuntimeError:
            self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))
            return
        if new_idx >= 0:
            self._selected_step_idx = new_idx
            self._on_step_selected()

    def _on_move_to_index(self, source: int, target: int) -> None:
        """把 source 步骤 insert 移动到 target（0-based），其余顺延。

        source 由详情面板渲染时捕获，避免依赖可能已变化的 _selected_step_idx。
        """
        steps = self._model.get_steps()
        if not (0 <= source < len(steps)) or not (0 <= target < len(steps)) or source == target:
            return
        try:
            self._controller.move_to_index(source, target)
        except RuntimeError:
            self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))
            return
        self._selected_step_idx = target
        self._on_step_selected()

    def _selected_rows(self) -> list[int]:
        """步骤树当前选中的行索引（升序、去重）。"""
        if not hasattr(self, "_step_tree") or self._step_tree is None:
            return []
        return sorted({self._step_tree.indexOfTopLevelItem(i) for i in self._step_tree.selectedItems()})

    def _apply_reorder(self, new_order: list[int], focus_idx: int | None = None) -> None:
        """应用重排（执行中被拒时提示）。

        先设 ``_selected_step_idx=focus_idx``，使 reorder 的同步 emit 触发
        ``_refresh_step_list`` 时即用新索引高亮/渲染，避免选中竞态；
        RuntimeError（执行中）时恢复旧值。
        """
        prev = self._selected_step_idx
        if focus_idx is not None:
            self._selected_step_idx = focus_idx
        try:
            self._controller.reorder_steps(new_order)
        except RuntimeError:
            self._selected_step_idx = prev
            self._show_warning(t("common.hint"), t("chain.msg.executor_busy"))

    def _on_move_top(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        order = build_top_order(len(self._model.get_steps()), rows)
        self._apply_reorder(order, focus_idx=0)

    def _on_move_bottom(self) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        n = len(self._model.get_steps())
        order = build_bottom_order(n, rows)
        self._apply_reorder(order, focus_idx=n - 1)

    def _on_move_batch(self, delta: int) -> None:
        rows = self._selected_rows()
        if not rows:
            return
        n = len(self._model.get_steps())
        new_order = build_batch_move_order(n, rows, delta)
        new_positions = sorted(new_order.index(r) for r in rows)
        self._apply_reorder(new_order, focus_idx=new_positions[0] if new_positions else None)

    def _on_tree_reorder(self, new_order: list[int]) -> None:
        """拖拽释放：应用 insert 语义重排。"""
        if not new_order:
            return
        self._apply_reorder(new_order)

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
            wait_col = wait_text(step)
            enabled_text = "✓" if step.enabled else "--"
            item = QTreeWidgetItem([
                str(i + 1),
                type_name,
                step.describe(),
                wait_col,
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
            btn_style = self._toolbar_btn_style()
            self._toolbar.setStyleSheet(
                f"QWidget#actionChainToolbar {{ background-color: {th.panel_bg}; border: none; }}"
            )
            for btn in self._toolbar.findChildren(QPushButton):
                btn.setStyleSheet(btn_style)
        if hasattr(self, "_loop_container"):
            self._loop_container.setStyleSheet(
                f"QFrame#loopControlFrame {{ background: transparent; }}"
            )
        if hasattr(self, "_loop_combo"):
            self._loop_combo.setStyleSheet(f"""
                QComboBox {{
                    background-color: {th.input_bg};
                    color: {th.text_primary};
                    border: 1px solid {th.border_default};
                    border-radius: 3px;
                    padding: 1px {sm.s(4)}px;
                    font-size: {sm.s(10)}px;
                    min-width: {sm.s(80)}px;
                }}
                QComboBox::drop-down {{
                    border: none;
                    width: {sm.s(16)}px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {th.input_bg};
                    color: {th.text_primary};
                    border: 1px solid {th.border_default};
                    selection-background-color: {th.accent_blue};
                    selection-color: {th.text_on_accent};
                }}
            """)
            for i, (_, i18n_key) in enumerate([
                ("single", "common.loop.single"),
                ("infinite", "common.loop.infinite"),
                ("finite", "common.loop.finite"),
            ]):
                self._loop_combo.setItemText(i, t(i18n_key))
        if hasattr(self, "_loop_count_spin"):
            self._loop_count_spin.setStyleSheet(f"""
                QSpinBox {{
                    background-color: {th.input_bg};
                    color: {th.text_primary};
                    border: 1px solid {th.border_default};
                    border-radius: 3px;
                    padding: 1px {sm.s(4)}px;
                    font-size: {sm.s(10)}px;
                }}
            """)
        if hasattr(self, "_loop_times_label"):
            self._loop_times_label.setStyleSheet(
                f"color: {th.text_secondary}; font-size: {sm.s(10)}px;"
            )
        if hasattr(self, "_status_bar"):
            self._status_bar.setStyleSheet(
                f"background-color: {th.panel_bg}; border-top: 1px solid {th.border_default};"
            )
        # Update palette scroll area
        if hasattr(self, "_palette_widget"):
            scroll = self._palette_widget.findChild(QScrollArea)
            if scroll:
                scroll.setStyleSheet(f"background-color: {th.panel_bg};")
            # Re-apply palette button styles with new theme
            palette_types = getattr(self, "_palette_action_types", [])
            for i, btn in enumerate(getattr(self, "_palette_buttons", [])):
                if i >= len(palette_types):
                    continue
                action_type = palette_types[i]
                accent_token = action_accent(action_type)
                accent = getattr(th, accent_token, th.accent_blue)
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background-color: {th.btn_bg};
                        color: {th.text_primary};
                        border: 1px solid {th.border_default};
                        border-left: 3px solid {accent};
                        border-radius: 2px;
                        padding: 2px {sm.s(6)}px;
                        text-align: left;
                        font-size: {sm.s(10)}px;
                    }}
                    QPushButton:hover {{
                        background-color: {th.btn_bg_hover};
                        border-color: {th.accent_blue};
                    }}
                """)
        # Update log viewer
        if hasattr(self, "_log_text"):
            self._log_text.setStyleSheet(f"""
                QPlainTextEdit {{
                    background-color: {th.bg_surface};
                    color: {th.text_primary};
                    border: 1px solid {th.border_default};
                    border-radius: {sm.s(3)}px;
                    font-family: {th.font_mono[0]};
                    font-size: {th.font_mono[1]}px;
                }}
            """)
        # Update status label
        if hasattr(self, "_status_label"):
            self._status_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(9)}px;")
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
        # 先停 ticker:它直达底层调度器,token 不在 _timer_ids 里,需显式取消。
        if hasattr(self, "_exec_ticker"):
            self._exec_ticker.stop()
        if hasattr(self, "_controller"):
            self._controller.destroy()
        super().destroy_page()
