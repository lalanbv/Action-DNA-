"""Qt 监控器配置对话框 — 配置后台弹窗检测与处理。"""

from __future__ import annotations

import os
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core.action import FoundAction
from src.core.monitor import MonitorConfig
from src.panel.qt_backend.dialogs._mappings import _FOUND_ACTION_I18N
from src.utils.i18n import t
from src.utils.paths import get_assets_dir


class QtMonitorDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None,
        monitor: MonitorConfig,
        title: str,
        on_done: Callable[[MonitorConfig], None],
    ) -> None:
        super().__init__(parent)
        self._monitor = monitor
        self._on_done = on_done
        self.setWindowTitle(title)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)

        self._name_edit = QLineEdit(monitor.name)
        form.addRow(t("dialog.label.monitor_name"), self._name_edit)

        self._enabled_cb = QCheckBox(t("common.enabled"))
        self._enabled_cb.setChecked(monitor.enabled)
        form.addRow(self._enabled_cb)

        form.addRow(QLabel(t("dialog.label.detection_config")))

        img_row, self._image_edit = self._make_browse_row(monitor.image_path)
        form.addRow(t("dialog.label.detect_image"), img_row)

        threshold_row = QWidget()
        th_lay = QHBoxLayout(threshold_row)
        th_lay.setContentsMargins(0, 0, 0, 0)
        self._threshold_slider = QSlider()
        self._threshold_slider.setRange(50, 100)
        self._threshold_slider.setValue(int(monitor.threshold * 100))
        self._threshold_slider.setOrientation(Qt.Orientation.Horizontal)
        th_lay.addWidget(self._threshold_slider)
        self._threshold_label = QLabel(f"{monitor.threshold:.2f}")
        self._threshold_slider.valueChanged.connect(
            lambda v: self._threshold_label.setText(f"{v / 100:.2f}")
        )
        th_lay.addWidget(self._threshold_label)
        form.addRow(t("dialog.label.match_threshold"), threshold_row)

        self._interval_spin = QDoubleSpinBox()
        self._interval_spin.setRange(0.5, 30.0)
        self._interval_spin.setSingleStep(0.5)
        self._interval_spin.setValue(monitor.check_interval)
        self._interval_spin.setSuffix(" s")
        form.addRow(t("dialog.label.detect_interval"), self._interval_spin)

        form.addRow(QLabel(t("dialog.label.handler_config")))

        self._action_combo = QComboBox()
        self._action_data: list[FoundAction] = []
        fa_labels = {fa: t(key) for fa, key in _FOUND_ACTION_I18N.items() if fa != FoundAction.OUTPUT_COORD}
        current_label = fa_labels.get(monitor.handler_action, monitor.handler_action.value)
        for fa, lbl in fa_labels.items():
            self._action_combo.addItem(lbl)
            self._action_data.append(fa)
        idx = list(fa_labels.values()).index(current_label) if current_label in fa_labels.values() else 0
        self._action_combo.setCurrentIndex(idx)
        form.addRow(t("dialog.label.handler_action"), self._action_combo)

        himg_row, self._handler_image_edit = self._make_browse_row(monitor.handler_image_path)
        form.addRow(t("dialog.label.handler_target_image"), himg_row)
        form.addRow(QLabel(t("dialog.hint.optional_handler_image")))

        self._max_consecutive_spin = QSpinBox()
        self._max_consecutive_spin.setRange(1, 20)
        self._max_consecutive_spin.setValue(monitor.max_consecutive)
        form.addRow(t("dialog.label.max_consecutive"), self._max_consecutive_spin)

        self._cooldown_spin = QDoubleSpinBox()
        self._cooldown_spin.setRange(0.5, 60.0)
        self._cooldown_spin.setSingleStep(0.5)
        self._cooldown_spin.setValue(monitor.cooldown)
        self._cooldown_spin.setSuffix(" s")
        form.addRow(t("dialog.label.trigger_cooldown"), self._cooldown_spin)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton(t("common.ok"))
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton(t("common.cancel"))
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _make_browse_row(self, initial_text: str) -> tuple[QWidget, QLineEdit]:
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        edit = QLineEdit(initial_text)
        lay.addWidget(edit)
        btn = QPushButton(t("dialog.btn.browse"))
        btn.clicked.connect(lambda: self._browse_image(edit))
        lay.addWidget(btn)
        return row, edit

    def _browse_image(self, target: QLineEdit) -> None:
        initial_dir = get_assets_dir() if os.path.isdir(get_assets_dir()) else os.path.expanduser("~")
        path, _ = QFileDialog.getOpenFileName(
            self,
            t("dialog.title.select_image"),
            initial_dir,
            f"{t('dialog.filetype.image_files')} (*.png *.jpg *.jpeg *.bmp);;{t('dialog.filetype.all')} (*.*)",
        )
        if path:
            target.setText(path)

    def _on_ok(self) -> None:
        idx = self._action_combo.currentIndex()
        handler_action = self._action_data[idx] if 0 <= idx < len(self._action_data) else self._monitor.handler_action
        result = MonitorConfig(
            name=self._name_edit.text().strip() or t("common.unnamed_monitor"),
            enabled=self._enabled_cb.isChecked(),
            image_path=self._image_edit.text().strip(),
            threshold=self._threshold_slider.value() / 100.0,
            check_interval=self._interval_spin.value(),
            handler_action=handler_action,
            handler_image_path=self._handler_image_edit.text().strip(),
            max_consecutive=self._max_consecutive_spin.value(),
            cooldown=self._cooldown_spin.value(),
        )
        self.accept()
        self._on_done(result)


def open_monitor_dialog(
    parent: QWidget | None,
    monitor: MonitorConfig,
    title: str,
    on_done: Callable[[MonitorConfig], None],
) -> None:
    dlg = QtMonitorDialog(parent, monitor, title, on_done)
    dlg.open()
