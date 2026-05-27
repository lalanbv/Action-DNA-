"""RuleEditDialog — 通知规则编辑对话框。

从 notification_page.py 抽取的独立对话框模块。
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.panel.canvas.theme import current_theme
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button
from src.utils.i18n import t

_TRIGGER_OPTIONS: list[tuple[str, str]] = [
    ("on_complete", "notification.trigger.on_complete"),
    ("on_error", "notification.trigger.on_error"),
    ("on_loop_count", "notification.trigger.on_loop_count"),
]

_CHANNEL_I18N_KEYS: dict[str, str] = {
    "system_notify": "notification.channel.system",
    "sound": "notification.channel.sound",
    "webhook": "notification.channel.webhook",
}


class RuleEditDialog(QDialog):
    """通知规则编辑对话框。"""

    def __init__(self, parent: QWidget, rule: dict) -> None:
        super().__init__(parent)
        th = current_theme()
        sm = qt_scale_manager()

        self.setWindowTitle(t("notification.edit_rule"))
        self.setMinimumSize(sm.s(420), sm.s(350))
        self.setModal(True)

        self._rule = rule
        self._result: dict | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(sm.s(12), sm.s(12), sm.s(12), sm.s(12))
        layout.setSpacing(sm.s(6))

        entry_style = f"""
            QLineEdit {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px;
            }}
        """
        combo_style = f"""
            QComboBox {{
                background-color: {th.input_bg}; color: {th.text_primary};
                border: 1px solid {th.border_default}; border-radius: {sm.s(3)}px;
                padding: {sm.s(3)}px {sm.s(6)}px; min-width: {sm.s(120)}px;
            }}
        """
        label_style = f"color: {th.text_primary};"
        cb_style = f"color: {th.text_primary};"

        form = QFormLayout()
        form.setSpacing(sm.s(6))

        trigger_field = QLabel(t("notification.rule.trigger"))
        trigger_field.setStyleSheet(label_style)
        self._trigger_combo = QComboBox()
        for val, i18n_key in _TRIGGER_OPTIONS:
            self._trigger_combo.addItem(t(i18n_key), val)
        for i, (val, _) in enumerate(_TRIGGER_OPTIONS):
            if val == rule["trigger"]:
                self._trigger_combo.setCurrentIndex(i)
                break
        self._trigger_combo.setStyleSheet(combo_style)
        form.addRow(trigger_field, self._trigger_combo)

        title_field = QLabel(t("notification.rule.title_template"))
        title_field.setStyleSheet(label_style)
        self._title_entry = QLineEdit(rule["title_template"])
        self._title_entry.setStyleSheet(entry_style)
        form.addRow(title_field, self._title_entry)

        msg_field = QLabel(t("notification.rule.message_template"))
        msg_field.setStyleSheet(label_style)
        self._message_entry = QLineEdit(rule["message_template"])
        self._message_entry.setStyleSheet(entry_style)
        form.addRow(msg_field, self._message_entry)

        cooldown_field = QLabel(t("notification.rule.cooldown"))
        cooldown_field.setStyleSheet(label_style)
        self._cooldown_spin = QSpinBox()
        self._cooldown_spin.setRange(0, 3600)
        self._cooldown_spin.setValue(int(rule["cooldown"]))
        self._cooldown_spin.setStyleSheet(entry_style)
        form.addRow(cooldown_field, self._cooldown_spin)

        ch_field = QLabel(t("notification.channels"))
        ch_field.setStyleSheet(label_style)
        ch_widget = QWidget()
        ch_layout = QHBoxLayout(ch_widget)
        ch_layout.setContentsMargins(0, 0, 0, 0)
        self._channel_cbs: dict[str, QCheckBox] = {}
        for ch_name in ("system_notify", "sound", "webhook"):
            ch_label = t(_CHANNEL_I18N_KEYS.get(ch_name, ch_name))
            cb = QCheckBox(ch_label)
            cb.setChecked(ch_name in rule["channels"])
            cb.setStyleSheet(cb_style)
            ch_layout.addWidget(cb)
            self._channel_cbs[ch_name] = cb
        form.addRow(ch_field, ch_widget)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        ok_btn = themed_button(self, text=t("common.ok"), style="primary", command=self._on_save)
        btn_row.addWidget(ok_btn)
        cancel_btn = themed_button(self, text=t("common.cancel"), style="secondary", command=self.reject)
        btn_row.addWidget(cancel_btn)
        layout.addLayout(btn_row)

    def _on_save(self) -> None:
        selected_channels = [n for n, cb in self._channel_cbs.items() if cb.isChecked()]
        self._result = {
            "trigger": self._trigger_combo.currentData() or "on_complete",
            "channels": selected_channels,
            "title_template": self._title_entry.text(),
            "message_template": self._message_entry.text(),
            "condition": self._rule.get("condition"),
            "cooldown": float(self._cooldown_spin.value()),
            "enabled": self._rule["enabled"],
        }
        self.accept()

    def get_result(self) -> dict:
        return self._result or self._rule
