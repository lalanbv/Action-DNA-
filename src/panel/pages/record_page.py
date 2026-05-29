"""RecordPage — 宏录制控制面板。

功能：
- 开始/停止录制（F9 快捷键）
- 实时彩色事件流（左栏 Treeview）
- 合并步骤编辑器（右栏 Treeview，支持双击编辑、删除、排序）
- 底部操作栏（添加到动作链 / 工作流 / 清空）
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

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
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import RECORD_DESC, RECORD_TITLE
from src.panel.pages.page_registry import PAGE_ACTION_CHAIN, PAGE_WORKFLOW_EDITOR, register_page
from src.panel.components.toolbar_icons import ICONS
from src.panel.widgets import (
    themed_button,
    themed_frame,
    themed_label,
    themed_paned_window,
)
from src.utils.i18n import t

if TYPE_CHECKING:
    from src.panel.app import PanelApp

__all__ = ["RecordPage"]

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

_EVENT_TAG_THEME_KEYS: dict[str, str] = {
    "mouse": "accent_blue",
    "scroll": "accent_orange",
    "key": "accent_green",
    "move": "accent_gray",
    "drag_path": "accent_mauve",
}

_STEP_TAG_THEME_KEYS: dict[ActionType, str] = {
    ActionType.CLICK_POS: "accent_blue",
    ActionType.PRESS_KEY: "accent_green",
    ActionType.HOLD_KEY: "accent_yellow",
    ActionType.KEY_COMBO: "accent_pink",
    ActionType.MOUSE_MOVE: "accent_teal",
    ActionType.MOUSE_SCROLL: "accent_orange",
    ActionType.WAIT: "accent_gray",
    ActionType.WAIT_RANDOM: "accent_gray",
}


@register_page("record", label_i18n=RECORD_TITLE, desc_i18n=RECORD_DESC, icon="⏺", category="main")
class RecordPage(BasePage):
    """录制控制面板页面。"""

    def __init__(self, parent: tk.Widget, app: PanelApp, **kwargs) -> None:
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

        # ── 统一工具栏 ──
        toolbar = self._build_toolbar_base("record.title")

        toolbar.add_spacer()

        toolbar.add_section("edit")
        self._btn_undo = themed_button(
            toolbar, text=f"{ICONS['undo']} {t('record.btn.undo')}",
            style="secondary", command=self._on_undo, state=tk.DISABLED,
        )
        toolbar.add_widget("edit", self._btn_undo)

        self._btn_redo = themed_button(
            toolbar, text=f"{ICONS['redo']} {t('record.btn.redo')}",
            style="secondary", command=self._on_redo, state=tk.DISABLED,
        )
        toolbar.add_widget("edit", self._btn_redo)

        toolbar.add_section("actions")
        self._btn_stop = themed_button(
            toolbar, text=f"{ICONS['stop']} {t('record.stop')}",
            style="danger", command=self._on_stop, state=tk.DISABLED,
        )
        toolbar.add_widget("actions", self._btn_stop)

        self._btn_start = themed_button(
            toolbar, text=f"{ICONS['record']} {t('record.start')} (F9)",
            style="primary", command=self._on_start,
        )
        toolbar.add_widget("actions", self._btn_start)

        # 状态行
        status_row = themed_frame(self.frame)
        status_row.pack(fill=tk.X, padx=th.pad_xl)

        self._lbl_status = themed_label(status_row, text=t("record.status.ready"))
        self._lbl_status.pack(side=tk.LEFT, pady=th.pad_xs)

        self._lbl_count = themed_label(status_row, text=t("record.event_count", count=0))
        self._lbl_count.pack(side=tk.LEFT, padx=th.pad_lg)

        self._lbl_duration = themed_label(status_row, text=t("record.duration", duration="0.0"))
        self._lbl_duration.pack(side=tk.LEFT, padx=th.pad_lg)

        # ── 底部操作栏 (pack before paned so it doesn't expand) ──
        footer = themed_frame(self.frame)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=th.pad_xl, pady=th.pad_md)

        self._btn_import = themed_button(
            footer, text=t("record.btn.add_to_chain"), style="success",
            command=self._on_import, state=tk.DISABLED,
        )
        self._btn_import.pack(side=tk.RIGHT, padx=th.pad_sm)

        self._btn_workflow = themed_button(
            footer, text=t("record.btn.add_to_workflow"), style="success",
            command=self._on_import_workflow, state=tk.DISABLED,
        )
        self._btn_workflow.pack(side=tk.RIGHT, padx=th.pad_sm)

        self._btn_clear = themed_button(
            footer, text=t("record.btn.clear"), style="secondary",
            command=self._on_clear, state=tk.DISABLED,
        )
        self._btn_clear.pack(side=tk.RIGHT, padx=th.pad_sm)

        self._btn_delete = themed_button(
            footer, text=t("record.btn.delete_selected"), style="danger",
            command=self._on_delete_step, state=tk.DISABLED,
        )
        self._btn_delete.pack(side=tk.RIGHT, padx=th.pad_sm)

        self._btn_up = themed_button(
            footer, text=t("record.btn.move_up"), style="secondary", width=3,
            command=self._on_move_step_up, state=tk.DISABLED,
        )
        self._btn_up.pack(side=tk.RIGHT, padx=2)

        self._btn_down = themed_button(
            footer, text=t("record.btn.move_down"), style="secondary", width=3,
            command=self._on_move_step_down, state=tk.DISABLED,
        )
        self._btn_down.pack(side=tk.RIGHT, padx=2)

        # ── 分栏主体 ──
        paned = themed_paned_window(self.frame, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=th.pad_xl, pady=th.pad_sm)

        # 左栏: 实时事件流
        left_frame = themed_frame(paned)
        themed_label(left_frame, text=t("record.event_stream"), style="subtitle").pack(
            anchor="w", pady=(0, 2),
        )

        _event_col_keys = ("col.index", "col.type", "col.position_key", "col.interval")
        _event_col_ids = tuple(t(f"record.{k}") for k in _event_col_keys)
        self._event_tree = ttk.Treeview(
            left_frame, columns=_event_col_ids, show="headings", height=15,
        )
        for col_id, col_key in zip(_event_col_ids, _event_col_keys):
            self._event_tree.heading(col_id, text=t(f"record.{col_key}"))
        self._event_tree.column(_event_col_ids[0], width=70, minwidth=40)
        self._event_tree.column(_event_col_ids[1], width=70, minwidth=40)
        self._event_tree.column(_event_col_ids[2], width=140, minwidth=80)
        self._event_tree.column(_event_col_ids[3], width=60, minwidth=40)
        self._event_col_ids = _event_col_ids

        ev_scroll = ttk.Scrollbar(
            left_frame, orient=tk.VERTICAL, command=self._event_tree.yview,
        )
        self._event_tree.configure(yscrollcommand=ev_scroll.set)
        self._event_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ev_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        for tag, theme_key in _EVENT_TAG_THEME_KEYS.items():
            self._event_tree.tag_configure(tag, foreground=getattr(th, theme_key))

        paned.add(left_frame, weight=1)

        # 右栏: 合并步骤编辑器
        right_frame = themed_frame(paned)
        themed_label(right_frame, text=t("record.merged_steps"), style="subtitle").pack(
            anchor="w", pady=(0, 2),
        )

        _step_col_keys = ("col.index", "col.type", "col.description", "col.duration")
        _step_col_ids = tuple(t(f"record.{k}") for k in _step_col_keys)
        self._step_tree = ttk.Treeview(
            right_frame, columns=_step_col_ids, show="headings", height=15,
        )
        for col_id, col_key in zip(_step_col_ids, _step_col_keys):
            self._step_tree.heading(col_id, text=t(f"record.{col_key}"))
        self._step_tree.column(_step_col_ids[0], width=80, minwidth=50)
        self._step_tree.column(_step_col_ids[1], width=80, minwidth=50)
        self._step_tree.column(_step_col_ids[2], width=180, minwidth=100)
        self._step_tree.column(_step_col_ids[3], width=60, minwidth=40)
        self._step_col_ids = _step_col_ids

        st_scroll = ttk.Scrollbar(
            right_frame, orient=tk.VERTICAL, command=self._step_tree.yview,
        )
        self._step_tree.configure(yscrollcommand=st_scroll.set)
        self._step_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        st_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._step_tree.bind("<Double-1>", self._on_step_double_click)
        self._step_tree.bind("<<TreeviewSelect>>", self._on_step_select)
        self._step_tree.bind("<Button-3>", self._on_step_context_menu)

        for tag, theme_key in _STEP_TAG_THEME_KEYS.items():
            self._step_tree.tag_configure(tag.name, foreground=getattr(th, theme_key))

        paned.add(right_frame, weight=1)

        # F9 快捷键
        self.frame.bind_all("<F9>", lambda e: self._toggle_recording())

        # 撤销/重做快捷键
        self.frame.bind_all("<Control-z>", lambda e: self._on_undo())
        self.frame.bind_all("<Control-y>", lambda e: self._on_redo())
        self.frame.bind_all("<Control-Z>", lambda e: self._on_redo())
        self.frame.bind_all("<Command-z>", lambda e: self._on_undo())
        self.frame.bind_all("<Command-y>", lambda e: self._on_redo())
        self.frame.bind_all("<Command-Z>", lambda e: self._on_redo())

        # 撤销管理器状态回调
        self._undo_manager.on_change(self._update_undo_redo_buttons)

    def destroy(self) -> None:
        if self._bridge.is_recording:
            self._bridge.stop_and_convert()
        self._undo_manager.remove_on_change(self._update_undo_redo_buttons)
        self.frame.unbind_all("<F9>")
        self.frame.unbind_all("<Control-z>")
        self.frame.unbind_all("<Control-y>")
        self.frame.unbind_all("<Control-Z>")
        self.frame.unbind_all("<Command-z>")
        self.frame.unbind_all("<Command-y>")
        self.frame.unbind_all("<Command-Z>")
        super().destroy()

    # ---- 录制控制 ----

    def _toggle_recording(self) -> None:
        if self._bridge.is_recording:
            self._on_stop()
        else:
            self._on_start()

    def _on_start(self) -> None:
        self._steps.clear()
        self._undo_manager.clear()
        self._last_event_count = 0
        for item in self._event_tree.get_children():
            self._event_tree.delete(item)
        for item in self._step_tree.get_children():
            self._step_tree.delete(item)

        self._bridge.start_recording()
        if self._merger is not None:
            self._merger.reset_cache()

        self._btn_start.configure(state=tk.DISABLED)
        self._btn_stop.configure(state=tk.NORMAL)
        self._btn_import.configure(state=tk.DISABLED)
        self._btn_workflow.configure(state=tk.DISABLED)
        self._btn_clear.configure(state=tk.DISABLED)
        self._lbl_status.configure(text=t("record.status.recording"))

        self._update_status()
        self._schedule_merge_preview()

    def _on_stop(self) -> None:
        steps = self._bridge.stop_and_convert()
        self._steps = steps

        # 最终刷新事件流：补充录制期间未显示的事件
        all_events = self._bridge.snapshot_events()
        if len(all_events) > self._last_event_count:
            skip_moves = len(all_events) > self._MOVE_DISPLAY_THRESHOLD
            for evt in all_events[self._last_event_count:]:
                if skip_moves and evt.event_type == "mouse_move":
                    continue
                self._add_event_row(evt)
            children = self._event_tree.get_children()
            excess = len(children) - self._MAX_EVENT_ROWS
            if excess > 0:
                for child in children[:excess]:
                    self._event_tree.delete(child)
            self._last_event_count = len(all_events)

        # 更新最终计数和时长
        self._lbl_count.configure(
            text=t("record.event_count", count=len(all_events)),
        )
        dur = sum(s.recorded_duration for s in steps)
        self._lbl_duration.configure(text=t("record.duration", duration=f"{dur:.1f}"))

        self._btn_start.configure(state=tk.NORMAL)
        self._btn_stop.configure(state=tk.DISABLED)
        self._btn_import.configure(state=tk.NORMAL if steps else tk.DISABLED)
        self._btn_workflow.configure(state=tk.NORMAL if steps else tk.DISABLED)
        self._btn_clear.configure(state=tk.NORMAL)
        self._lbl_status.configure(text=t("record.status.stopped"))

        self._show_steps(steps)

    def _on_import(self) -> None:
        if not self._steps:
            return
        self.app.navigate_to(PAGE_ACTION_CHAIN, import_steps=self._steps)

    def _on_import_workflow(self) -> None:
        if not self._steps:
            return
        self.app.navigate_to(PAGE_WORKFLOW_EDITOR, import_steps=self._steps)

    # ---- 实时更新 ----

    _MAX_EVENT_ROWS: int = 1000
    _MOVE_DISPLAY_THRESHOLD: int = 200

    def _update_status(self) -> None:
        if not self._bridge.is_recording:
            return

        events = self._bridge.snapshot_events()
        count = len(events)
        dur = self._bridge.duration

        self._lbl_count.configure(text=t("record.event_count", count=count))
        self._lbl_duration.configure(text=t("record.duration", duration=f"{dur:.1f}"))

        skip_moves = count > self._MOVE_DISPLAY_THRESHOLD
        for evt in events[self._last_event_count:]:
            if skip_moves and evt.event_type == "mouse_move":
                continue
            # mouse_drag 不跳过 — 是有意义的用户操作
            self._add_event_row(evt)

        # 超出上限时删除最旧行
        children = self._event_tree.get_children()
        excess = len(children) - self._MAX_EVENT_ROWS
        if excess > 0:
            for child in children[:excess]:
                self._event_tree.delete(child)

        self._last_event_count = count
        self.schedule(200, self._update_status)

    def _schedule_merge_preview(self) -> None:
        """录制中每 2 秒运行合并预览，更新右栏。"""
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
        row_num = len(self._event_tree.get_children()) + 1

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

        self._event_tree.insert("", tk.END, values=(
            row_num, etype_name, detail, f"{evt.delta_time:.3f}s",
        ), tags=(tag,))

        children = self._event_tree.get_children()
        if children:
            self._event_tree.see(children[-1])

    def _on_clear(self) -> None:
        if not self._steps:
            return
        cmd = ClearStepsCommand(
            _get_steps=lambda: self._steps,
            _set_steps=self._set_steps,
        )
        self._undo_manager.execute(cmd)
        self._last_event_count = 0
        for item in self._event_tree.get_children():
            self._event_tree.delete(item)
        self._lbl_status.configure(text=t("record.status.ready"))
        self._lbl_count.configure(text=t("record.event_count", count=0))
        self._lbl_duration.configure(text=t("record.duration", duration="0.0"))

    # ---- 步骤 getter/setter（命令模式回调） ----

    def _set_steps(self, steps: list[BaseStep]) -> None:
        """由命令对象调用，更新步骤数据并刷新 UI。"""
        self._steps = steps
        self._show_steps(self._steps)
        has_steps = bool(self._steps)
        self._btn_import.configure(state=tk.NORMAL if has_steps else tk.DISABLED)
        self._btn_workflow.configure(state=tk.NORMAL if has_steps else tk.DISABLED)
        self._btn_clear.configure(state=tk.NORMAL if has_steps else tk.DISABLED)
        self._btn_delete.configure(state=tk.NORMAL if has_steps else tk.DISABLED)
        self._btn_up.configure(state=tk.NORMAL if has_steps else tk.DISABLED)
        self._btn_down.configure(state=tk.NORMAL if has_steps else tk.DISABLED)

    # ---- 撤销/重做 ----

    def _on_undo(self) -> None:
        self._undo_manager.undo()

    def _on_redo(self) -> None:
        self._undo_manager.redo()

    def _update_undo_redo_buttons(self) -> None:
        if not hasattr(self, "_btn_undo") or not self._btn_undo.winfo_exists():
            return
        self._btn_undo.configure(state=tk.NORMAL if self._undo_manager.can_undo else tk.DISABLED)
        self._btn_redo.configure(state=tk.NORMAL if self._undo_manager.can_redo else tk.DISABLED)

    def _show_steps(self, steps: list[BaseStep]) -> None:
        for item in self._step_tree.get_children():
            self._step_tree.delete(item)

        for i, step in enumerate(steps, 1):
            name = _action_type_display(step)
            desc = step.describe()
            path_mark = " *" if getattr(step, "path_points", None) else ""
            dur_str = f"{step.recorded_duration:.2f}s" if step.recorded_duration > 0 else "-"
            tag = step.action_type.name
            self._step_tree.insert("", tk.END, values=(
                i, f"{name}{path_mark}", desc, dur_str,
            ), tags=(tag,))

    def _on_step_select(self, _event) -> None:
        has_sel = bool(self._step_tree.selection()) and bool(self._steps)
        self._btn_delete.configure(state=tk.NORMAL if has_sel else tk.DISABLED)
        self._btn_up.configure(state=tk.NORMAL if has_sel else tk.DISABLED)
        self._btn_down.configure(state=tk.NORMAL if has_sel else tk.DISABLED)

    def _on_step_context_menu(self, event) -> None:
        item = self._step_tree.identify_row(event.y)
        if not item:
            return
        self._step_tree.selection_set(item)

        menu = tk.Menu(self.frame, tearoff=0)
        menu.add_command(label=t("record.ctx.edit"), command=self._on_step_double_click)
        menu.add_command(label=t("record.ctx.delete"), command=self._on_delete_step)
        menu.add_separator()
        menu.add_command(label=t("record.ctx.move_up"), command=self._on_move_step_up)
        menu.add_command(label=t("record.ctx.move_down"), command=self._on_move_step_down)
        menu.add_separator()
        menu.add_command(label=t("record.ctx.duplicate"), command=self._on_duplicate_step)
        menu.tk_popup(event.x_root, event.y_root)

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
        """返回所有选中步骤的索引列表（已排序去重）。"""
        sel = self._step_tree.selection()
        if not sel or not self._steps:
            return []
        indices = []
        for item_id in sel:
            values = self._step_tree.item(item_id, "values")
            indices.append(int(values[0]) - 1)
        return sorted(set(indices))

    def _get_selected_step_index(self) -> int | None:
        """返回第一个选中步骤的索引（向后兼容单选操作）。"""
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
        children = self._step_tree.get_children()
        if target < len(children):
            self._step_tree.selection_set(children[target])

    def _on_move_step_up(self) -> None:
        self._move_step(-1)

    def _on_move_step_down(self) -> None:
        self._move_step(1)

    def _on_step_double_click(self, _event) -> None:
        idx = self._get_selected_step_index()
        if idx is None or idx >= len(self._steps):
            return
        step = self._steps[idx]
        from src.panel.dialogs import open_step_dialog
        open_step_dialog(
            self.frame, step,
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
