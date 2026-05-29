"""QtRecordPage — PySide6 宏录制页面。

替代 tkinter RecordPage，实时事件流 + 合并步骤编辑 + 撤销/重做。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QKeySequence
from PySide6.QtWidgets import (
    QHeaderView, QMenu, QSplitter, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QHBoxLayout, QWidget,
)

from src.core.action import ActionType
from src.core.editor.undo_manager import UndoManager
from src.core.editor.commands.step_commands import (
    DeleteStepsCommand,
    MoveStepCommand,
    DuplicateStepCommand,
    EditStepCommand,
    ClearStepsCommand,
)
from src.core.step_types import BaseStep
from src.core.engine.descriptors.record_descriptor import RecordBridge
from src.panel.canvas.theme import current_theme
from src.panel.pages.page_i18n import RECORD_TITLE, RECORD_DESC
from src.panel.pages.page_registry import PAGE_ACTION_CHAIN, PAGE_WORKFLOW_EDITOR
from src.panel.qt_backend.pages.base_page import QtBasePage
from src.panel.qt_backend.pages.page_registry import register_page
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button, themed_label
from src.utils.i18n import t

_ACTION_TYPE_KEYS: dict[ActionType, str] = {
    ActionType.CLICK_POS: "record.action_type.click_pos",
    ActionType.PRESS_KEY: "record.action_type.press_key",
    ActionType.HOLD_KEY: "record.action_type.hold_key",
    ActionType.KEY_COMBO: "record.action_type.key_combo",
    ActionType.MOUSE_MOVE: "record.action_type.mouse_move",
    ActionType.MOUSE_SCROLL: "record.action_type.mouse_scroll",
    ActionType.WAIT: "record.action_type.wait",
    ActionType.WAIT_RANDOM: "record.action_type.wait_random",
}


def _action_type_display(step: BaseStep) -> str:
    if step.action_type == ActionType.CLICK_POS:
        click_keys = {1: "record.click.single", 2: "record.click.double", 3: "record.click.triple"}
        name = t(click_keys.get(step.clicks, "record.click.multi"), count=step.clicks)
        if step.button == "right":
            name = t("record.click.right_prefix", name=name)
        elif step.button == "middle":
            name = t("record.click.middle_prefix", name=name)
        if step.hold_duration > 0.3:
            name = t("record.click.hold_replace") if step.clicks == 1 else t("record.click.hold_suffix", name=name)
        return name
    if step.action_type == ActionType.MOUSE_MOVE:
        base = t(_ACTION_TYPE_KEYS[step.action_type])
        if hasattr(step, "button") and step.button in ("right", "middle"):
            prefix_key = f"record.click.{step.button}_prefix"
            base = t(prefix_key, name=base)
        return base
    return t(_ACTION_TYPE_KEYS.get(step.action_type, step.action_type.name))


_EVENT_TAG_COLORS: dict[str, str] = {}
_STEP_TAG_COLORS: dict[str, str] = {}

_MAX_EVENT_ROWS = 1000
_MOVE_DISPLAY_THRESHOLD = 200


@register_page("record", label_i18n=RECORD_TITLE, desc_i18n=RECORD_DESC, icon="⏺", category="main")
class QtRecordPage(QtBasePage):
    """录制控制面板页面。"""

    def __init__(self, parent: QWidget, app, **kwargs) -> None:
        self._bridge = RecordBridge()
        self._steps: list[BaseStep] = []
        self._undo_manager = UndoManager()
        self._last_event_count: int = 0
        self._last_preview_count: int = 0
        self._merger = None
        super().__init__(parent, app, **kwargs)

    def title(self) -> str:
        return t("record.title")

    def build(self) -> None:
        th = current_theme()
        sm = qt_scale_manager()

        _EVENT_TAG_COLORS.update({
            "mouse": th.accent_blue,
            "scroll": th.accent_orange,
            "key": th.accent_green,
            "move": th.accent_gray,
            "drag_path": th.accent_mauve,
        })
        _STEP_TAG_COLORS.update({
            ActionType.CLICK_POS.name: th.accent_blue,
            ActionType.PRESS_KEY.name: th.accent_green,
            ActionType.HOLD_KEY.name: th.accent_yellow,
            ActionType.KEY_COMBO.name: th.accent_pink,
            ActionType.MOUSE_MOVE.name: th.accent_teal,
            ActionType.MOUSE_SCROLL.name: th.accent_orange,
            ActionType.WAIT.name: th.accent_gray,
            ActionType.WAIT_RANDOM.name: th.accent_gray,
        })

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md))
        main_layout.setSpacing(sm.s(8))

        self._build_toolbar(main_layout, th, sm)
        self._build_status(main_layout, th, sm)
        self._build_footer(main_layout, th, sm)
        self._build_splitter(main_layout, th, sm)

        self._undo_manager.on_change(self._update_undo_redo_buttons)

    def _build_toolbar(self, layout: QVBoxLayout, th, sm) -> None:
        toolbar = self._build_toolbar_base(layout, "record.title")

        self._btn_undo = themed_button(
            self, text=t("record.btn.undo"), style="secondary",
            command=self._on_undo,
        )
        self._btn_undo.setEnabled(False)
        toolbar.addWidget(self._btn_undo)

        self._btn_redo = themed_button(
            self, text=t("record.btn.redo"), style="secondary",
            command=self._on_redo,
        )
        self._btn_redo.setEnabled(False)
        toolbar.addWidget(self._btn_redo)

        self._btn_stop = themed_button(
            self, text=t("record.stop"), style="danger",
            command=self._on_stop,
        )
        self._btn_stop.setEnabled(False)
        toolbar.addWidget(self._btn_stop)

        self._btn_start = themed_button(
            self, text=t("record.start") + " (F9)", style="primary",
            command=self._on_start,
        )
        toolbar.addWidget(self._btn_start)

    def _build_status(self, layout: QVBoxLayout, th, sm) -> None:
        status_row = QHBoxLayout()
        self._lbl_status = themed_label(self, text=t("record.status.ready"), style="body")
        status_row.addWidget(self._lbl_status)
        self._lbl_count = themed_label(self, text=t("record.event_count", count=0), style="body")
        status_row.addWidget(self._lbl_count)
        self._lbl_duration = themed_label(self, text=t("record.duration", duration="0.0"), style="body")
        status_row.addWidget(self._lbl_duration)
        status_row.addStretch()
        layout.addLayout(status_row)

    def _build_footer(self, layout: QVBoxLayout, th, sm) -> None:
        footer = QHBoxLayout()

        self._btn_down = themed_button(
            self, text=t("record.btn.move_down"), style="secondary",
            command=self._on_move_step_down,
        )
        self._btn_down.setEnabled(False)
        footer.addWidget(self._btn_down)

        self._btn_up = themed_button(
            self, text=t("record.btn.move_up"), style="secondary",
            command=self._on_move_step_up,
        )
        self._btn_up.setEnabled(False)
        footer.addWidget(self._btn_up)

        self._btn_delete = themed_button(
            self, text=t("record.btn.delete_selected"), style="danger",
            command=self._on_delete_step,
        )
        self._btn_delete.setEnabled(False)
        footer.addWidget(self._btn_delete)

        self._btn_clear = themed_button(
            self, text=t("record.btn.clear"), style="secondary",
            command=self._on_clear,
        )
        self._btn_clear.setEnabled(False)
        footer.addWidget(self._btn_clear)

        self._btn_workflow = themed_button(
            self, text=t("record.btn.add_to_workflow"), style="primary",
            command=self._on_import_workflow,
        )
        self._btn_workflow.setEnabled(False)
        footer.addWidget(self._btn_workflow)

        self._btn_import = themed_button(
            self, text=t("record.btn.add_to_chain"), style="primary",
            command=self._on_import,
        )
        self._btn_import.setEnabled(False)
        footer.addWidget(self._btn_import)

        layout.addLayout(footer)

    def _build_splitter(self, layout: QVBoxLayout, th, sm) -> None:
        splitter = QSplitter(Qt.Horizontal)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(sm.s(2))

        left_title = themed_label(left_widget, text=t("record.event_stream"), style="subtitle")
        left_layout.addWidget(left_title)

        event_col_keys = ("col.index", "col.type", "col.position_key", "col.interval")
        self._event_tree = QTreeWidget()
        self._event_tree.setHeaderLabels([t(f"record.{k}") for k in event_col_keys])
        self._event_tree.setRootIsDecorated(False)
        self._event_tree.setAlternatingRowColors(True)
        self._apply_tree_style(self._event_tree, th, sm)
        ev_header = self._event_tree.header()
        ev_header.setSectionResizeMode(0, QHeaderView.Fixed)
        ev_header.resizeSection(0, sm.s(60))
        ev_header.setSectionResizeMode(1, QHeaderView.Fixed)
        ev_header.resizeSection(1, sm.s(70))
        ev_header.setSectionResizeMode(2, QHeaderView.Stretch)
        ev_header.setSectionResizeMode(3, QHeaderView.Fixed)
        ev_header.resizeSection(3, sm.s(60))
        left_layout.addWidget(self._event_tree, 1)
        splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(sm.s(2))

        right_title = themed_label(right_widget, text=t("record.merged_steps"), style="subtitle")
        right_layout.addWidget(right_title)

        step_col_keys = ("col.index", "col.type", "col.description", "col.duration")
        self._step_tree = QTreeWidget()
        self._step_tree.setHeaderLabels([t(f"record.{k}") for k in step_col_keys])
        self._step_tree.setRootIsDecorated(False)
        self._step_tree.setAlternatingRowColors(True)
        self._apply_tree_style(self._step_tree, th, sm)
        self._step_tree.setSelectionMode(QTreeWidget.ExtendedSelection)
        st_header = self._step_tree.header()
        st_header.setSectionResizeMode(0, QHeaderView.Fixed)
        st_header.resizeSection(0, sm.s(60))
        st_header.setSectionResizeMode(1, QHeaderView.Fixed)
        st_header.resizeSection(1, sm.s(100))
        st_header.setSectionResizeMode(2, QHeaderView.Stretch)
        st_header.setSectionResizeMode(3, QHeaderView.Fixed)
        st_header.resizeSection(3, sm.s(60))
        self._step_tree.itemSelectionChanged.connect(self._on_step_select)
        self._step_tree.itemDoubleClicked.connect(lambda _: self._on_step_double_click())
        self._step_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self._step_tree.customContextMenuRequested.connect(self._on_step_context_menu)
        right_layout.addWidget(self._step_tree, 1)
        splitter.addWidget(right_widget)

        splitter.setSizes([sm.s(300), sm.s(400)])
        layout.addWidget(splitter, 1)

    def _apply_tree_style(self, tree: QTreeWidget, th, sm) -> None:
        tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {th.bg_surface};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(4)}px;
                font-size: {sm.s(13)}px;
                alternate-background-color: {th.input_bg};
            }}
            QTreeWidget::item {{
                padding: {sm.s(2)}px;
                border-bottom: 1px solid {th.border_default};
            }}
            QTreeWidget::item:selected {{
                background-color: {th.accent_blue};
                color: {th.text_on_accent};
            }}
            QHeaderView::section {{
                background-color: {th.bg_surface};
                color: {th.text_muted};
                border: none;
                border-bottom: 1px solid {th.border_default};
                padding: {sm.s(4)}px {sm.s(8)}px;
                font-weight: bold;
            }}
        """)

    def keyPressEvent(self, event) -> None:
        from PySide6.QtWidgets import QLineEdit, QPlainTextEdit, QTextEdit
        focus = self.focusWidget()
        if isinstance(focus, (QLineEdit, QPlainTextEdit, QTextEdit)):
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_F9:
            self._toggle_recording()
        elif key == Qt.Key.Key_Z and (mods & Qt.KeyboardModifier.ControlModifier):
            if mods & Qt.KeyboardModifier.ShiftModifier:
                self._on_redo()
            else:
                self._on_undo()
        elif key == Qt.Key.Key_Y and (mods & Qt.KeyboardModifier.ControlModifier):
            self._on_redo()
        else:
            super().keyPressEvent(event)

    def apply_theme(self) -> None:
        super().apply_theme()
        th = current_theme()
        sm = qt_scale_manager()
        if hasattr(self, "_event_tree"):
            self._apply_tree_style(self._event_tree, th, sm)
        if hasattr(self, "_step_tree"):
            self._apply_tree_style(self._step_tree, th, sm)

    def destroy_page(self) -> None:
        if self._bridge.is_recording:
            self._bridge.stop_and_convert()
        self._undo_manager.remove_on_change(self._update_undo_redo_buttons)
        super().destroy_page()

    def _toggle_recording(self) -> None:
        if self._bridge.is_recording:
            self._on_stop()
        else:
            self._on_start()

    def _on_start(self) -> None:
        self._steps.clear()
        self._undo_manager.clear()
        self._last_event_count = 0
        self._last_preview_count = 0
        self._event_tree.clear()
        self._step_tree.clear()

        self._bridge.start_recording()
        if self._merger is not None:
            self._merger.reset_cache()

        self._btn_start.setEnabled(False)
        self._btn_stop.setEnabled(True)
        self._btn_import.setEnabled(False)
        self._btn_workflow.setEnabled(False)
        self._btn_clear.setEnabled(False)
        self._lbl_status.setText(t("record.status.recording"))

        self._update_status()
        self._schedule_merge_preview()

    def _on_stop(self) -> None:
        steps = self._bridge.stop_and_convert()
        self._steps = steps

        all_events = self._bridge.snapshot_events()
        if len(all_events) > self._last_event_count:
            skip_moves = len(all_events) > _MOVE_DISPLAY_THRESHOLD
            for evt in all_events[self._last_event_count:]:
                if skip_moves and evt.event_type == "mouse_move":
                    continue
                self._add_event_row(evt)
            self._trim_event_rows()
            self._last_event_count = len(all_events)

        self._lbl_count.setText(t("record.event_count", count=len(all_events)))
        dur = sum(s.recorded_duration for s in steps)
        self._lbl_duration.setText(t("record.duration", duration=f"{dur:.1f}"))

        self._btn_start.setEnabled(True)
        self._btn_stop.setEnabled(False)
        self._btn_import.setEnabled(bool(steps))
        self._btn_workflow.setEnabled(bool(steps))
        self._btn_clear.setEnabled(True)
        self._lbl_status.setText(t("record.status.stopped"))

        self._show_steps(steps)

    def _on_import(self) -> None:
        if not self._steps:
            return
        self.app.navigate_to(PAGE_ACTION_CHAIN, import_steps=self._steps)

    def _on_import_workflow(self) -> None:
        if not self._steps:
            return
        self.app.navigate_to(PAGE_WORKFLOW_EDITOR, import_steps=self._steps)

    def _update_status(self) -> None:
        if not self._bridge.is_recording:
            return

        events = self._bridge.snapshot_events()
        count = len(events)
        dur = self._bridge.duration

        self._lbl_count.setText(t("record.event_count", count=count))
        self._lbl_duration.setText(t("record.duration", duration=f"{dur:.1f}"))

        skip_moves = count > _MOVE_DISPLAY_THRESHOLD
        for evt in events[self._last_event_count:]:
            if skip_moves and evt.event_type == "mouse_move":
                continue
            self._add_event_row(evt)

        self._trim_event_rows()
        self._last_event_count = count
        self.schedule(200, self._update_status)

    def _schedule_merge_preview(self) -> None:
        if not self._bridge.is_recording:
            return
        self._update_merge_preview()
        self.schedule(2000, self._schedule_merge_preview)

    def _update_merge_preview(self) -> None:
        if self._merger is None:
            from src.recorder.event_merger import EventMerger
            self._merger = EventMerger()
        events = self._bridge.snapshot_events()
        if len(events) == self._last_preview_count:
            return
        self._last_preview_count = len(events)
        preview_steps = self._merger.merge_incremental(events)
        self._show_steps(preview_steps)

    _MOUSE_EVENT_TAGS: dict[str, str] = {
        "mouse_down": "drag_path",
        "mouse_up": "mouse",
        "mouse_scroll": "scroll",
        "mouse_move": "move",
        "mouse_drag": "drag_path",
    }

    def _add_event_row(self, evt) -> None:
        row_num = self._event_tree.topLevelItemCount() + 1

        if evt.is_mouse_event:
            tag = self._MOUSE_EVENT_TAGS.get(evt.event_type, "mouse")
            detail = f"({evt.x}, {evt.y})"
            if evt.event_type == "mouse_scroll":
                arrows = ""
                if evt.scroll_delta > 0:
                    arrows += f"↑{evt.scroll_delta}"
                elif evt.scroll_delta < 0:
                    arrows += f"↓{abs(evt.scroll_delta)}"
                if getattr(evt, "scroll_delta_x", 0) != 0:
                    dx = evt.scroll_delta_x
                    arrows += f"→{dx}" if dx > 0 else f"←{abs(dx)}"
                detail = f"({evt.x}, {evt.y}) {arrows}"
            elif evt.button:
                detail = f"({evt.x}, {evt.y}) {evt.button}"
            etype_name = evt.event_type.replace("mouse_", "M-")
        else:
            tag = "key"
            detail = evt.key
            etype_name = evt.event_type.replace("key_", "K-")

        color = _EVENT_TAG_COLORS.get(tag, "")
        item = QTreeWidgetItem([
            str(row_num), etype_name, detail, f"{evt.delta_time:.3f}s",
        ])
        if color:
            qcolor = QColor(color)
            for col in range(4):
                item.setForeground(col, qcolor)
        self._event_tree.addTopLevelItem(item)
        self._event_tree.scrollToItem(item)

    def _trim_event_rows(self) -> None:
        count = self._event_tree.topLevelItemCount()
        excess = count - _MAX_EVENT_ROWS
        if excess > 0:
            for _ in range(excess):
                self._event_tree.takeTopLevelItem(0)

    def _on_clear(self) -> None:
        if not self._steps:
            return
        cmd = ClearStepsCommand(
            _get_steps=lambda: self._steps,
            _set_steps=self._set_steps,
        )
        self._undo_manager.execute(cmd)
        self._last_event_count = 0
        self._event_tree.clear()
        self._lbl_status.setText(t("record.status.ready"))
        self._lbl_count.setText(t("record.event_count", count=0))
        self._lbl_duration.setText(t("record.duration", duration="0.0"))

    def _set_steps(self, steps: list[BaseStep]) -> None:
        self._steps = steps
        self._show_steps(self._steps)
        has_steps = bool(self._steps)
        self._btn_import.setEnabled(has_steps)
        self._btn_workflow.setEnabled(has_steps)
        self._btn_clear.setEnabled(has_steps)
        self._btn_delete.setEnabled(has_steps)
        self._btn_up.setEnabled(has_steps)
        self._btn_down.setEnabled(has_steps)

    def _on_undo(self) -> None:
        self._undo_manager.undo()

    def _on_redo(self) -> None:
        self._undo_manager.redo()

    def _update_undo_redo_buttons(self) -> None:
        if not hasattr(self, "_btn_undo"):
            return
        try:
            self._btn_undo.setEnabled(self._undo_manager.can_undo)
            self._btn_redo.setEnabled(self._undo_manager.can_redo)
        except RuntimeError:
            pass

    def _show_steps(self, steps: list[BaseStep]) -> None:
        self._step_tree.clear()

        for i, step in enumerate(steps, 1):
            name = _action_type_display(step)
            desc = step.describe()
            path_mark = " *" if getattr(step, "path_points", None) else ""
            dur_str = f"{step.recorded_duration:.2f}s" if step.recorded_duration > 0 else "-"

            item = QTreeWidgetItem([
                str(i), f"{name}{path_mark}", desc, dur_str,
            ])
            item.setData(0, Qt.UserRole, i - 1)
            step_color = _STEP_TAG_COLORS.get(step.action_type.name)
            if step_color:
                qcolor = QColor(step_color)
                if qcolor.isValid():
                    for col in range(item.columnCount()):
                        item.setForeground(col, qcolor)
            self._step_tree.addTopLevelItem(item)

    def _on_step_select(self) -> None:
        has_sel = bool(self._step_tree.selectedItems()) and bool(self._steps)
        self._btn_delete.setEnabled(has_sel)
        self._btn_up.setEnabled(has_sel)
        self._btn_down.setEnabled(has_sel)

    def _on_step_context_menu(self, pos) -> None:
        item = self._step_tree.itemAt(pos)
        if not item:
            return
        self._step_tree.setCurrentItem(item)

        menu = QMenu(self)
        menu.addAction(t("record.ctx.edit"), self._on_step_double_click)
        menu.addAction(t("record.ctx.delete"), self._on_delete_step)
        menu.addSeparator()
        menu.addAction(t("record.ctx.move_up"), self._on_move_step_up)
        menu.addAction(t("record.ctx.move_down"), self._on_move_step_down)
        menu.addSeparator()
        menu.addAction(t("record.ctx.duplicate"), self._on_duplicate_step)
        menu.exec(self._step_tree.viewport().mapToGlobal(pos))

    def _on_duplicate_step(self) -> None:
        idx = self._get_selected_step_index()
        if idx is None:
            return
        cmd = DuplicateStepCommand(
            _get_steps=lambda: self._steps,
            _set_steps=self._set_steps,
            _index=idx,
        )
        self._undo_manager.execute(cmd)

    def _get_selected_step_indices(self) -> list[int]:
        sel = self._step_tree.selectedItems()
        if not sel or not self._steps:
            return []
        indices = []
        for item in sel:
            idx = item.data(0, Qt.UserRole)
            if idx is not None:
                indices.append(idx)
        return sorted(set(indices))

    def _get_selected_step_index(self) -> int | None:
        indices = self._get_selected_step_indices()
        return indices[0] if indices else None

    def _on_delete_step(self) -> None:
        indices = self._get_selected_step_indices()
        if not indices:
            return
        cmd = DeleteStepsCommand(
            _get_steps=lambda: self._steps,
            _set_steps=self._set_steps,
            _indices=indices,
        )
        self._undo_manager.execute(cmd)

    def _move_step(self, delta: int) -> None:
        idx = self._get_selected_step_index()
        target = (idx or 0) + delta
        if idx is None or target < 0 or target >= len(self._steps):
            return
        cmd = MoveStepCommand(
            _get_steps=lambda: self._steps,
            _set_steps=self._set_steps,
            _from_index=idx,
            _to_index=target,
        )
        self._undo_manager.execute(cmd)
        if target < self._step_tree.topLevelItemCount():
            self._step_tree.setCurrentItem(self._step_tree.topLevelItem(target))

    def _on_move_step_up(self) -> None:
        self._move_step(-1)

    def _on_move_step_down(self) -> None:
        self._move_step(1)

    def _on_step_double_click(self) -> None:
        idx = self._get_selected_step_index()
        if idx is None or idx >= len(self._steps):
            return
        step = self._steps[idx]
        from src.panel.qt_backend.dialogs.step_dialogs import open_step_dialog
        open_step_dialog(
            self, step,
            t("record.edit_step_title", type=step.action_type.name),
            on_done=lambda s: self._update_step(idx, s),
        )

    def _update_step(self, idx: int, step: BaseStep) -> None:
        cmd = EditStepCommand(
            _get_steps=lambda: self._steps,
            _set_steps=self._set_steps,
            _index=idx,
            _new_step=step,
        )
        self._undo_manager.execute(cmd)
