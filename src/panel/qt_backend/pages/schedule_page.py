"""QtSchedulePage — PySide6 调度管理页面。

替代 tkinter SchedulePage，调度列表 CRUD + 启停控制。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox, QDialog, QHBoxLayout,
    QLabel,
    QVBoxLayout, QWidget,
)

from src.core.config import ScheduleEntryConfig, load_config, save_config
from src.panel.pages.page_i18n import SCHEDULE_TITLE, SCHEDULE_DESC
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.dialogs.schedule_edit_dialog import ScheduleEditDialog
from src.panel.qt_backend.pages.base_page import QtBasePage
from src.panel.qt_backend.pages.page_registry import register_page
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button, themed_label
from src.utils.i18n import t

@register_page("schedule", label_i18n=SCHEDULE_TITLE, desc_i18n=SCHEDULE_DESC, icon="⏰", category="settings")
class QtSchedulePage(QtBasePage):
    """调度管理页面。"""

    def title(self) -> str:
        return t("schedule.title")

    def build(self) -> None:
        th = current_theme()
        sm = qt_scale_manager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._build_toolbar(main_layout, th, sm)

        from PySide6.QtWidgets import QScrollArea
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setStyleSheet(f"background-color: {th.page_bg};")

        self._list_container = QWidget()
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md))
        self._list_layout.setSpacing(sm.s(2))

        scroll.setWidget(self._list_container)
        main_layout.addWidget(scroll, 1)

        self._schedule_rows: list[dict] = []
        self._row_widgets: list[QWidget] = []
        self._dirty: bool = False
        self._load_config()

    def _build_toolbar(self, layout: QVBoxLayout, th, sm) -> None:
        toolbar = self._build_toolbar_base(layout, "schedule.title")
        save_btn = themed_button(
            self, text=t("common.ok"), style="primary",
            command=self._save_and_back,
        )
        toolbar.addWidget(save_btn)

    def _render_list(self) -> None:
        for w in self._row_widgets:
            w.setParent(None)
            w.deleteLater()
        self._row_widgets.clear()

        th = current_theme()
        sm = qt_scale_manager()

        add_btn = themed_button(
            self._list_container, text="+ " + t("schedule.add"), style="primary",
            command=self._add_schedule,
        )
        self._list_layout.addWidget(add_btn)
        self._row_widgets.append(add_btn)

        for i, entry in enumerate(self._schedule_rows):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(sm.s(4), sm.s(2), sm.s(4), sm.s(2))
            row_layout.setSpacing(sm.s(4))

            type_label = t(f"schedule.type.{entry['schedule_type']}")
            profile = entry["profile_name"] or "—"
            enabled_text = t("common.enabled") if entry["enabled"] else ""
            info_text = f"{type_label} | {profile}"
            if enabled_text:
                info_text += f" | {enabled_text}"

            info_lbl = QLabel(info_text)
            info_lbl.setStyleSheet(f"color: {th.text_primary};")
            row_layout.addWidget(info_lbl, 1)

            cb = QCheckBox(t("common.enabled"))
            cb.setChecked(entry["enabled"])
            cb.setStyleSheet(f"color: {th.text_primary};")
            cb.toggled.connect(lambda checked, idx=i: self._toggle_enabled(idx, checked))
            row_layout.addWidget(cb)

            edit_btn = themed_button(
                row, text=t("common.edit"), style="secondary",
                command=lambda idx=i: self._edit_schedule(idx),
            )
            row_layout.addWidget(edit_btn)

            del_btn = themed_button(
                row, text=t("common.delete"), style="secondary",
                command=lambda idx=i: self._delete_schedule(idx),
            )
            row_layout.addWidget(del_btn)

            self._list_layout.addWidget(row)
            self._row_widgets.append(row)

    def _add_schedule(self) -> None:
        self._dirty = True
        self._schedule_rows.append({
            "schedule_type": "once",
            "profile_name": "",
            "interval_seconds": 3600,
            "daily_time": "09:00",
            "daily_days": None,
            "weekly_day": 0,
            "weekly_time": "09:00",
            "max_runs": None,
            "loop_count": 1,
            "enabled": True,
        })
        self._render_list()

    def _edit_schedule(self, idx: int) -> None:
        self._dirty = True
        entry = self._schedule_rows[idx]
        dlg = ScheduleEditDialog(self, entry)
        if dlg.exec() == QDialog.Accepted:
            self._schedule_rows[idx] = dlg.get_result()
            self._render_list()

    def _delete_schedule(self, idx: int) -> None:
        name = self._schedule_rows[idx].get("profile_name", "")
        if self._ask_yes_no(
            t("workflow.msg.confirm_delete"),
            t("schedule.msg.confirm_delete").format(name=name or "—"),
        ):
            self._dirty = True
            self._schedule_rows.pop(idx)
            self._render_list()

    def _toggle_enabled(self, idx: int, checked: bool) -> None:
        self._dirty = True
        if idx < len(self._schedule_rows):
            self._schedule_rows[idx]["enabled"] = checked

    def _load_config(self) -> None:
        cfg = load_config()
        self._schedule_rows = []
        for s in cfg.schedule_list.schedules:
            self._schedule_rows.append({
                "schedule_type": s.schedule_type,
                "profile_name": s.profile_name,
                "interval_seconds": s.interval_seconds,
                "daily_time": s.daily_time,
                "daily_days": s.daily_days,
                "weekly_day": s.weekly_day,
                "weekly_time": s.weekly_time,
                "max_runs": s.max_runs,
                "loop_count": s.loop_count,
                "enabled": s.enabled,
            })
        self._render_list()

    def _save_current_config(self) -> None:
        cfg = load_config()
        cfg.schedule_list.schedules = [
            ScheduleEntryConfig(**r) for r in self._schedule_rows
        ]
        save_config(cfg)

    def _save_and_back(self) -> None:
        self._save_current_config()
        self.app.navigate_to(PAGE_HOME)

    def destroy_page(self) -> None:
        if getattr(self, "_dirty", False):
            try:
                self._save_current_config()
            except Exception:
                pass
        super().destroy_page()
