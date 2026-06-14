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

from src.core.action import FoundAction, MatchStrategy, ThresholdMode
from src.core.monitor import MonitorConfig
from src.panel.qt_backend.dialogs._mappings import _FOUND_ACTION_I18N
from src.panel.qt_backend.dialogs.multi_template_editor import MultiTemplateEditorQt
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

        # 触发图多模板管理器(完整:含阈值模式/策略/全局阈值)
        self._trigger_editor = MultiTemplateEditorQt(parent=self)
        self._trigger_editor.set_state(
            monitor.image_path, monitor.alt_image_paths, monitor.alt_thresholds,
            monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
        )
        form.addRow(t("dialog.label.detect_image"), self._trigger_editor)

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

        # 处理图多模板管理器(精简:不显示模式/策略/全局阈值,共用触发图的)
        self._handler_editor = MultiTemplateEditorQt(parent=self, show_match_settings=False)
        self._handler_editor.set_state(
            monitor.handler_image_path, monitor.alt_handler_image_paths,
            monitor.alt_handler_thresholds,
            monitor.threshold_mode, monitor.match_strategy, monitor.threshold,
        )
        form.addRow(t("dialog.label.handler_target_image"), self._handler_editor)
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
        # 触发图(完整编辑器:含 mode/strategy/threshold)+ 处理图(精简编辑器,mode/strategy 忽略)
        t_path, t_alts, t_thr, mode, strategy, threshold = self._trigger_editor.get_state()
        h_path, h_alts, h_thr, _hm, _hs, _hg = self._handler_editor.get_state()
        result = MonitorConfig(
            name=self._name_edit.text().strip() or t("common.unnamed_monitor"),
            enabled=self._enabled_cb.isChecked(),
            image_path=t_path.strip(),
            threshold=threshold,
            check_interval=self._interval_spin.value(),
            handler_action=handler_action,
            handler_image_path=h_path.strip(),
            max_consecutive=self._max_consecutive_spin.value(),
            cooldown=self._cooldown_spin.value(),
            alt_image_paths=t_alts,
            alt_thresholds=t_thr,
            alt_handler_image_paths=h_alts,
            alt_handler_thresholds=h_thr,
            match_strategy=strategy,
            threshold_mode=mode,
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
