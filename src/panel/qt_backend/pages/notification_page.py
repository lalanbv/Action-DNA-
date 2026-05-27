"""QtNotificationPage — PySide6 通知设置页面。

替代 tkinter NotificationPage，通道开关 + Webhook 配置 + 通知规则管理。
"""

from __future__ import annotations

import threading

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QFormLayout, QHBoxLayout,
    QLabel, QLineEdit, QScrollArea, QSpinBox,
    QVBoxLayout, QWidget,
)

from src.core.config import (
    ChannelConfig,
    NotificationRuleConfig,
    load_config,
    save_config,
)
from src.panel.canvas.theme import current_theme
from src.panel.pages.page_i18n import NOTIFICATION_TITLE, NOTIFICATION_DESC
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.qt_backend.dialogs.rule_edit_dialog import RuleEditDialog
from src.panel.qt_backend.pages.base_page import QtBasePage
from src.panel.qt_backend.pages.page_registry import register_page
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button, themed_frame, themed_label
from src.utils.i18n import t

_TRIGGER_OPTIONS: list[tuple[str, str]] = [
    ("on_complete", "notification.trigger.on_complete"),
    ("on_error", "notification.trigger.on_error"),
    ("on_loop_count", "notification.trigger.on_loop_count"),
]

_WEBHOOK_TYPE_VALUES = ["generic", "dingtalk", "wechat_work", "discord", "bark"]

_CHANNEL_I18N_KEYS: dict[str, str] = {
    "system_notify": "notification.channel.system",
    "sound": "notification.channel.sound",
    "webhook": "notification.channel.webhook",
}


@register_page("notification", label_i18n=NOTIFICATION_TITLE, desc_i18n=NOTIFICATION_DESC, icon="🔔", category="settings")
class QtNotificationPage(QtBasePage):
    _webhook_test_done = Signal(str)
    """通知设置页面。"""

    def title(self) -> str:
        return t("notification.title")

    def build(self) -> None:
        self._webhook_test_done.connect(self._handle_webhook_test_result)
        th = current_theme()
        sm = qt_scale_manager()

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md))
        main_layout.setSpacing(sm.s(8))

        self._build_toolbar(main_layout, th, sm)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setSpacing(sm.s(8))
        scroll.setWidget(self._content)
        main_layout.addWidget(scroll, 1)

        self._build_channel_section(th, sm)
        self._build_webhook_section(th, sm)
        self._build_rules_section(th, sm)
        self._content_layout.addStretch()

        self._load_config()

    def _build_toolbar(self, layout: QVBoxLayout, th, sm) -> None:
        toolbar = self._build_toolbar_base(layout, "notification.title")
        save_btn = themed_button(
            self, text=t("common.ok"), style="primary",
            command=self._save_and_back,
        )
        toolbar.addWidget(save_btn)

    def _build_channel_section(self, th, sm) -> None:
        section = themed_frame(self._content)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_sm), sm.s(th.pad_md), sm.s(th.pad_sm))

        lbl = themed_label(self._content, text=t("notification.channels"), style="subtitle")
        section_layout.addWidget(lbl)

        cb_style = f"color: {th.text_primary};"
        self._cb_system = QCheckBox(t("notification.channel.system"))
        self._cb_system.setStyleSheet(cb_style)
        section_layout.addWidget(self._cb_system)

        self._cb_sound = QCheckBox(t("notification.channel.sound"))
        self._cb_sound.setStyleSheet(cb_style)
        section_layout.addWidget(self._cb_sound)

        self._content_layout.addWidget(section)

    def _build_webhook_section(self, th, sm) -> None:
        section = themed_frame(self._content)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_sm), sm.s(th.pad_md), sm.s(th.pad_sm))

        self._cb_webhook = QCheckBox(t("notification.channel.webhook"))
        self._cb_webhook.setStyleSheet(f"color: {th.text_primary};")
        section_layout.addWidget(self._cb_webhook)

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

        form = QFormLayout()
        form.setSpacing(sm.s(6))

        url_field = QLabel(t("notification.webhook.url"))
        url_field.setStyleSheet(label_style)
        self._webhook_url_entry = QLineEdit()
        self._webhook_url_entry.setStyleSheet(entry_style)
        form.addRow(url_field, self._webhook_url_entry)

        type_field = QLabel(t("notification.webhook.type"))
        type_field.setStyleSheet(label_style)
        self._webhook_type_combo = QComboBox()
        for val in _WEBHOOK_TYPE_VALUES:
            self._webhook_type_combo.addItem(t(f"notification.webhook.type.{val}"), val)
        self._webhook_type_combo.setStyleSheet(combo_style)
        form.addRow(type_field, self._webhook_type_combo)

        secret_field = QLabel(t("notification.webhook.secret"))
        secret_field.setStyleSheet(label_style)
        self._webhook_secret_entry = QLineEdit()
        self._webhook_secret_entry.setStyleSheet(entry_style)
        form.addRow(secret_field, self._webhook_secret_entry)

        timeout_field = QLabel(t("notification.webhook.timeout"))
        timeout_field.setStyleSheet(label_style)
        self._webhook_timeout_spin = QSpinBox()
        self._webhook_timeout_spin.setRange(1, 30)
        self._webhook_timeout_spin.setValue(5)
        self._webhook_timeout_spin.setStyleSheet(entry_style)
        form.addRow(timeout_field, self._webhook_timeout_spin)

        section_layout.addLayout(form)

        test_btn = themed_button(
            section, text=t("notification.test"), style="secondary",
            command=self._test_webhook,
        )
        section_layout.addWidget(test_btn)

        self._content_layout.addWidget(section)

    def _build_rules_section(self, th, sm) -> None:
        section = themed_frame(self._content)
        self._rules_section_layout = QVBoxLayout(section)
        self._rules_section_layout.setContentsMargins(
            sm.s(th.pad_md), sm.s(th.pad_sm), sm.s(th.pad_md), sm.s(th.pad_sm),
        )

        lbl = themed_label(self._content, text=t("notification.rules"), style="subtitle")
        self._rules_section_layout.addWidget(lbl)

        add_btn = themed_button(
            section, text="+ " + t("notification.add_rule"), style="primary",
            command=self._add_rule,
        )
        self._rules_section_layout.addWidget(add_btn)

        self._rules_container = QWidget()
        self._rules_container_layout = QVBoxLayout(self._rules_container)
        self._rules_container_layout.setContentsMargins(0, 0, 0, 0)
        self._rules_section_layout.addWidget(self._rules_container)

        self._rule_rows: list[dict] = []
        self._rule_widgets: list[QWidget] = []

        self._content_layout.addWidget(section)

    def _render_rules(self) -> None:
        for w in self._rule_widgets:
            w.setParent(None)
            w.deleteLater()
        self._rule_widgets.clear()

        th = current_theme()
        sm = qt_scale_manager()

        for i, rule_data in enumerate(self._rule_rows):
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(sm.s(4), sm.s(2), sm.s(4), sm.s(2))
            row_layout.setSpacing(sm.s(4))

            trigger_label = rule_data["trigger"]
            for val, i18n_key in _TRIGGER_OPTIONS:
                if val == trigger_label:
                    trigger_label = t(i18n_key)
                    break

            info_lbl = QLabel(trigger_label)
            info_lbl.setStyleSheet(f"color: {th.text_primary};")
            row_layout.addWidget(info_lbl, 1)

            cb = QCheckBox(t("common.enabled"))
            cb.setChecked(rule_data["enabled"])
            cb.setStyleSheet(f"color: {th.text_primary};")
            cb.toggled.connect(lambda checked, idx=i: self._toggle_rule(idx, checked))
            row_layout.addWidget(cb)

            edit_btn = themed_button(
                row, text=t("notification.edit_rule"), style="secondary",
                command=lambda idx=i: self._edit_rule(idx),
            )
            row_layout.addWidget(edit_btn)

            del_btn = themed_button(
                row, text=t("common.delete"), style="secondary",
                command=lambda idx=i: self._delete_rule(idx),
            )
            row_layout.addWidget(del_btn)

            self._rules_container_layout.addWidget(row)
            self._rule_widgets.append(row)

    def _add_rule(self) -> None:
        self._rule_rows.append({
            "trigger": "on_complete",
            "channels": ["system_notify"],
            "title_template": "",
            "message_template": "",
            "condition": None,
            "cooldown": 60.0,
            "enabled": True,
        })
        self._render_rules()

    def _edit_rule(self, idx: int) -> None:
        rule = self._rule_rows[idx]
        dlg = RuleEditDialog(self, rule)
        if dlg.exec() == QDialog.Accepted:
            self._rule_rows[idx] = dlg.get_result()
            self._render_rules()

    def _delete_rule(self, idx: int) -> None:
        self._rule_rows.pop(idx)
        self._render_rules()

    def _toggle_rule(self, idx: int, checked: bool) -> None:
        if idx < len(self._rule_rows):
            self._rule_rows[idx]["enabled"] = checked

    def _load_config(self) -> None:
        cfg = load_config()
        nc = cfg.notification

        self._cb_system.setChecked(nc.channels.system_notify.enabled)
        self._cb_sound.setChecked(nc.channels.sound.enabled)
        self._cb_webhook.setChecked(nc.channels.webhook.enabled)
        self._webhook_url_entry.setText(nc.channels.webhook.url)
        self._webhook_secret_entry.setText(nc.channels.webhook.secret)
        self._webhook_timeout_spin.setValue(nc.channels.webhook.timeout)

        for i, val in enumerate(_WEBHOOK_TYPE_VALUES):
            if val == nc.channels.webhook.channel_type:
                self._webhook_type_combo.setCurrentIndex(i)
                break

        self._rule_rows = []
        for rule_cfg in nc.rules:
            self._rule_rows.append({
                "trigger": rule_cfg.trigger,
                "channels": list(rule_cfg.channels),
                "title_template": rule_cfg.title_template,
                "message_template": rule_cfg.message_template,
                "condition": rule_cfg.condition,
                "cooldown": rule_cfg.cooldown,
                "enabled": rule_cfg.enabled,
            })
        self._render_rules()

    def _save_current_config(self) -> None:
        if not hasattr(self, "_cb_system") or not hasattr(self, "_rule_rows"):
            return
        cfg = load_config()
        cfg.notification.channels.system_notify.enabled = self._cb_system.isChecked()
        cfg.notification.channels.sound.enabled = self._cb_sound.isChecked()
        cfg.notification.channels.webhook = ChannelConfig(
            enabled=self._cb_webhook.isChecked(),
            url=self._webhook_url_entry.text(),
            channel_type=self._webhook_type_combo.currentData() or "generic",
            secret=self._webhook_secret_entry.text(),
            timeout=self._webhook_timeout_spin.value(),
        )
        cfg.notification.rules = [
            NotificationRuleConfig(**r) for r in self._rule_rows
        ]
        save_config(cfg)

    def _test_webhook(self) -> None:
        url = self._webhook_url_entry.text().strip()
        if not url:
            self._show_warning(
                t("notification.test"),
                t("notification.webhook.url_required"),
            )
            return
        self._save_current_config()

        channel_type = self._webhook_type_combo.currentData() or "generic"
        secret = self._webhook_secret_entry.text()
        timeout = self._webhook_timeout_spin.value()

        def _do_test() -> None:
            try:
                from src.notification.channels.webhook_notify import WebhookNotifyChannel
                channel = WebhookNotifyChannel(
                    webhook_url=url,
                    channel_type=channel_type,
                    secret=secret,
                    timeout=timeout,
                )
                channel.test()
            except Exception as e:
                return e

            return None

        def _worker() -> None:
            error = _do_test()
            self._webhook_test_done.emit(str(error) if error else "")

        threading.Thread(target=_worker, daemon=True).start()

    def _handle_webhook_test_result(self, error_msg: str) -> None:
        if error_msg:
            self._show_error(t("notification.test"), error_msg)
        else:
            self._show_info(t("notification.test"), t("notification.test_success"))

    def _save_and_back(self) -> None:
        self._save_current_config()
        self.app.navigate_to(PAGE_HOME)

    def destroy_page(self) -> None:
        self._save_current_config()
        super().destroy_page()
