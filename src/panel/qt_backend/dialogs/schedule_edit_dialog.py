"""ScheduleEditDialog — 调度条目编辑对话框。

从 schedule_page.py 抽取的独立对话框模块。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button
from src.utils.i18n import t

_SCHEDULE_TYPES = ["once", "interval", "daily", "weekly"]


class ScheduleEditDialog(QDialog):
    """调度条目编辑对话框。"""

    def __init__(self, parent: QWidget, entry: dict) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self.setWindowTitle(t("common.edit"))
        self.setMinimumSize(sm.s(450), sm.s(420))
        self.setModal(True)

        self._entry = entry
        self._result: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sm.s(12), sm.s(12), sm.s(12), sm.s(12))
        layout.setSpacing(sm.s(6))

        type_internal = entry["schedule_type"]

        fields = [
            (t("schedule.type"), "combo_type"),
            (t("schedule.profile"), "profile"),
            (t("schedule.interval_seconds"), "interval"),
            (t("schedule.daily_time"), "daily_time"),
            (t("schedule.weekly_day"), "weekly_day"),
            (t("schedule.weekly_time"), "weekly_time"),
            (t("schedule.loop_count"), "loop_count"),
        ]

        self._type_combo = QComboBox()
        for st in _SCHEDULE_TYPES:
            self._type_combo.addItem(t(f"schedule.type.{st}"), st)
        for i, st in enumerate(_SCHEDULE_TYPES):
            if st == type_internal:
                self._type_combo.setCurrentIndex(i)
                break
        self._type_combo.setStyleSheet(f"""
            QComboBox {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px; min-width: {sm.s(120)}px;
            }}
        """)

        self._profile_entry = QLineEdit(entry["profile_name"])
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(60, 86400)
        self._interval_spin.setValue(entry["interval_seconds"])

        self._daily_time_entry = QLineEdit(entry["daily_time"])

        self._weekly_day_combo = QComboBox()
        self._weekly_day_combo.addItems([str(d) for d in range(7)])
        self._weekly_day_combo.setCurrentIndex(entry["weekly_day"])

        self._weekly_time_entry = QLineEdit(entry["weekly_time"])

        self._loop_spin = QSpinBox()
        self._loop_spin.setRange(1, 9999)
        self._loop_spin.setValue(entry["loop_count"])

        entry_style = f"""
            QLineEdit, QSpinBox {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px;
            }}
        """

        for w in [self._profile_entry, self._interval_spin,
                   self._daily_time_entry, self._weekly_time_entry, self._loop_spin]:
            w.setStyleSheet(entry_style)
        self._weekly_day_combo.setStyleSheet(entry_style)

        form_layout = QVBoxLayout()
        for label_text, widget_key in fields:
            h = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setFixedWidth(sm.s(120))
            lbl.setStyleSheet(f"color: {th.text_primary};")
            h.addWidget(lbl)

            if widget_key == "combo_type":
                h.addWidget(self._type_combo)
            elif widget_key == "profile":
                h.addWidget(self._profile_entry, 1)
            elif widget_key == "interval":
                h.addWidget(self._interval_spin)
            elif widget_key == "daily_time":
                h.addWidget(self._daily_time_entry, 1)
            elif widget_key == "weekly_day":
                h.addWidget(self._weekly_day_combo)
            elif widget_key == "weekly_time":
                h.addWidget(self._weekly_time_entry, 1)
            elif widget_key == "loop_count":
                h.addWidget(self._loop_spin)
            form_layout.addLayout(h)

        max_runs_row = QHBoxLayout()
        self._unlimited_cb = QCheckBox(t("common.infinite_loop"))
        self._unlimited_cb.setChecked(entry["max_runs"] is None)
        self._unlimited_cb.setStyleSheet(f"color: {th.text_primary};")
        max_runs_row.addWidget(self._unlimited_cb)
        self._max_runs_spin = QSpinBox()
        self._max_runs_spin.setRange(1, 9999)
        self._max_runs_spin.setValue(entry["max_runs"] or 0)
        self._max_runs_spin.setStyleSheet(entry_style)
        max_runs_row.addWidget(self._max_runs_spin)
        max_runs_row.addStretch()
        form_layout.addLayout(max_runs_row)

        layout.addLayout(form_layout)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = themed_button(self, text=t("common.ok"), style="primary", command=self.accept)
        btn_row.addWidget(ok_btn)
        cancel_btn = themed_button(self, text=t("common.cancel"), style="secondary", command=self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def get_result(self) -> dict:
        type_data = self._type_combo.currentData()
        return {
            "schedule_type": type_data or "once",
            "profile_name": self._profile_entry.text(),
            "interval_seconds": self._interval_spin.value(),
            "daily_time": self._daily_time_entry.text(),
            "daily_days": self._entry.get("daily_days"),
            "weekly_day": self._weekly_day_combo.currentIndex(),
            "weekly_time": self._weekly_time_entry.text(),
            "max_runs": None if self._unlimited_cb.isChecked() else self._max_runs_spin.value(),
            "loop_count": self._loop_spin.value(),
            "enabled": self._entry["enabled"],
        }
