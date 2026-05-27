"""通知设置页面 — 通道配置 UI"""

import tkinter as tk
import threading
from tkinter import ttk, messagebox

from src.core.config import (
    ChannelConfig,
    NotificationRuleConfig,
    load_config,
    save_config,
)
from src.panel.canvas.theme import current_theme
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import NOTIFICATION_DESC, NOTIFICATION_TITLE
from src.panel.pages.page_registry import PAGE_HOME, register_page
from src.panel.widgets import (
    themed_button,
    themed_checkbutton,
    themed_entry,
    themed_frame,
    themed_label,
    themed_labelframe,
    themed_separator,
    themed_spinbox,
)
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
class NotificationPage(BasePage):
    """通知设置页面 — 通道开关 + Webhook 配置 + 通知规则管理"""

    def title(self) -> str:
        return t("notification.title")

    def build(self):
        th = current_theme()

        # ── 统一工具栏 ──
        toolbar = self._build_toolbar_base("notification.title")

        toolbar.add_spacer()

        toolbar.make_button(
            "actions", text=t("common.ok"), icon="save",
            command=self._save_and_back, style="primary",
            tooltip=t("common.ok"),
        )

        # 可滚动内容区
        container = themed_frame(self.frame)
        container.pack(fill=tk.BOTH, expand=True, padx=th.pad_xl, pady=th.pad_sm)

        canvas = tk.Canvas(container, bg=th.page_bg, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=canvas.yview)
        self._scroll_frame = themed_frame(canvas)

        self._scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self._scroll_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self._build_channel_section()
        self._build_webhook_section()
        themed_separator(self._scroll_frame).pack(fill=tk.X, pady=th.pad_md)
        self._build_rules_section()

        self._load_config()

    # ── 通道开关 ──────────────────────────────────────────

    def _build_channel_section(self):
        th = current_theme()
        section = themed_labelframe(
            self._scroll_frame, text=t("notification.channels"),
        )
        section.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

        self._var_system = tk.BooleanVar()
        self._var_sound = tk.BooleanVar()

        for var, label in [
            (self._var_system, t("notification.channel.system")),
            (self._var_sound, t("notification.channel.sound")),
        ]:
            themed_checkbutton(
                section, text=label, variable=var,
            ).pack(anchor=tk.W, padx=th.pad_md, pady=th.pad_xs)

    # ── Webhook 配置 ─────────────────────────────────────

    def _build_webhook_section(self):
        th = current_theme()
        section = themed_labelframe(
            self._scroll_frame, text=t("notification.webhook"),
        )
        section.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

        self._var_webhook_enabled = tk.BooleanVar()
        themed_checkbutton(
            section, text=t("notification.channel.webhook"),
            variable=self._var_webhook_enabled,
        ).pack(anchor=tk.W, padx=th.pad_md, pady=th.pad_xs)

        fields_frame = themed_frame(section)
        fields_frame.pack(fill=tk.X, padx=th.pad_md, pady=th.pad_xs)

        self._var_webhook_url = tk.StringVar()
        self._webhook_type_internal = "generic"
        self._var_webhook_type = tk.StringVar(value=t("notification.webhook.type.generic"))
        self._var_webhook_secret = tk.StringVar()
        self._var_webhook_timeout = tk.IntVar(value=5)

        for label_text, var, widget in [
            (t("notification.webhook.url"), self._var_webhook_url, "entry"),
            (t("notification.webhook.type"), self._var_webhook_type, "combo"),
            (t("notification.webhook.secret"), self._var_webhook_secret, "entry"),
            (t("notification.webhook.timeout"), self._var_webhook_timeout, "spinbox"),
        ]:
            row = themed_frame(fields_frame)
            row.pack(fill=tk.X, pady=1)
            themed_label(
                row, text=label_text, style="small", width=12, anchor=tk.W,
            ).pack(side=tk.LEFT)
            if widget == "entry":
                themed_entry(row, textvariable=var).pack(
                    side=tk.LEFT, fill=tk.X, expand=True,
                )
            elif widget == "combo":
                self._webhook_type_combo = ttk.Combobox(
                    row, textvariable=var, state="readonly", width=15,
                    values=[t(f"notification.webhook.type.{v}") for v in _WEBHOOK_TYPE_VALUES],
                )
                self._webhook_type_combo.pack(side=tk.LEFT)
                self._webhook_type_combo.bind("<<ComboboxSelected>>", self._on_webhook_type_selected)
            elif widget == "spinbox":
                themed_spinbox(
                    row, from_=1, to=30, textvariable=var, width=5,
                ).pack(side=tk.LEFT)

        themed_button(
            section, text=t("notification.test"), style="secondary",
            command=self._test_webhook,
        ).pack(anchor=tk.E, padx=th.pad_md, pady=th.pad_sm)

    # ── 通知规则 ─────────────────────────────────────────

    def _build_rules_section(self):
        self._rules_section = themed_labelframe(
            self._scroll_frame, text=t("notification.rules"),
        )
        th = current_theme()
        self._rules_section.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)

        btn_frame = themed_frame(self._rules_section)
        btn_frame.pack(fill=tk.X, padx=th.pad_md, pady=th.pad_xs)

        themed_button(
            btn_frame, text="+ " + t("notification.add_rule"), style="primary",
            command=self._add_rule,
        ).pack(side=tk.LEFT)

        self._rules_container = themed_frame(self._rules_section)
        self._rules_container.pack(fill=tk.X, padx=th.pad_md, pady=th.pad_xs)

        self._rule_rows: list[dict] = []

    def _render_rules(self):
        for var, trace_name in getattr(self, "_rule_traces", []):
            try:
                var.trace_remove("write", trace_name)
            except Exception:
                pass
        self._rule_traces = []
        for w in self._rules_container.winfo_children():
            w.destroy()

        th = current_theme()
        for i, rule_data in enumerate(self._rule_rows):
            row = themed_frame(self._rules_container)
            row.pack(fill=tk.X, pady=th.pad_xs)

            trigger_label = rule_data["trigger"]
            for val, i18n_key in _TRIGGER_OPTIONS:
                if val == trigger_label:
                    trigger_label = t(i18n_key)
                    break

            themed_label(
                row, text=trigger_label, anchor=tk.W,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

            var_enabled = tk.BooleanVar(value=rule_data["enabled"])
            trace_name = var_enabled.trace_add(
                "write",
                lambda *_, idx=i, v=var_enabled: self._toggle_rule(idx, v),
            )
            self._rule_traces.append((var_enabled, trace_name))
            themed_checkbutton(
                row, t("common.enabled"), variable=var_enabled,
            ).pack(side=tk.LEFT, padx=th.pad_xs)

            themed_button(
                row, text=t("notification.edit_rule"), style="secondary",
                command=lambda idx=i: self._edit_rule(idx),
            ).pack(side=tk.LEFT, padx=th.pad_xs)

            themed_button(
                row, text=t("common.delete"),
                style="secondary",
                command=lambda idx=i: self._delete_rule(idx),
            ).pack(side=tk.LEFT, padx=th.pad_xs)

    def _add_rule(self):
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

    def _edit_rule(self, idx: int):
        rule = self._rule_rows[idx]
        dialog = tk.Toplevel(self.frame)
        dialog.title(t("notification.edit_rule"))
        dialog.geometry("450x400")
        dialog.transient(self.frame)
        dialog.grab_set()

        th = current_theme()
        dialog.configure(bg=th.page_bg)

        frame = themed_frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=th.pad_md, pady=th.pad_md)

        trigger_internal = rule["trigger"]
        var_trigger = tk.StringVar(
            value=next((t(i18n) for v, i18n in _TRIGGER_OPTIONS if v == trigger_internal), trigger_internal),
        )
        var_title = tk.StringVar(value=rule["title_template"])
        var_message = tk.StringVar(value=rule["message_template"])
        var_cooldown = tk.DoubleVar(value=rule["cooldown"])

        channel_vars = {}
        for ch_name in ("system_notify", "sound", "webhook"):
            channel_vars[ch_name] = tk.BooleanVar(value=ch_name in rule["channels"])

        r = 0
        themed_label(
            frame, text=t("notification.rule.trigger"),
        ).grid(row=r, column=0, sticky=tk.W, pady=th.pad_xs)
        trigger_combo = ttk.Combobox(
            frame, textvariable=var_trigger, state="readonly",
            values=[t(i18n) for _, i18n in _TRIGGER_OPTIONS], width=15,
        )
        trigger_combo.grid(row=r, column=1, sticky=tk.W, padx=th.pad_xs, pady=th.pad_xs)

        def _on_trigger_selected(_event=None):
            nonlocal trigger_internal
            display = var_trigger.get()
            for val, i18n_key in _TRIGGER_OPTIONS:
                if t(i18n_key) == display:
                    trigger_internal = val
                    break

        trigger_combo.bind("<<ComboboxSelected>>", _on_trigger_selected)
        r += 1

        themed_label(
            frame, text=t("notification.rule.title_template"),
        ).grid(row=r, column=0, sticky=tk.W, pady=th.pad_xs)
        themed_entry(frame, textvariable=var_title).grid(
            row=r, column=1, sticky=tk.EW, padx=th.pad_xs, pady=th.pad_xs,
        )
        r += 1

        themed_label(
            frame, text=t("notification.rule.message_template"),
        ).grid(row=r, column=0, sticky=tk.W, pady=th.pad_xs)
        themed_entry(frame, textvariable=var_message).grid(
            row=r, column=1, sticky=tk.EW, padx=th.pad_xs, pady=th.pad_xs,
        )
        r += 1

        themed_label(
            frame, text=t("notification.rule.cooldown"),
        ).grid(row=r, column=0, sticky=tk.W, pady=th.pad_xs)
        themed_spinbox(
            frame, from_=0, to=3600, textvariable=var_cooldown, width=8,
        ).grid(row=r, column=1, sticky=tk.W, padx=th.pad_xs, pady=th.pad_xs)
        r += 1

        themed_label(
            frame, text=t("notification.channels"),
        ).grid(row=r, column=0, sticky=tk.W, pady=th.pad_xs)
        ch_frame = themed_frame(frame)
        ch_frame.grid(row=r, column=1, sticky=tk.W, padx=th.pad_xs, pady=th.pad_xs)
        for ch_name, ch_var in channel_vars.items():
            ch_label = t(_CHANNEL_I18N_KEYS.get(ch_name, ch_name))
            themed_checkbutton(ch_frame, text=ch_label, variable=ch_var).pack(
                side=tk.LEFT, padx=th.pad_xs,
            )
        r += 1

        frame.columnconfigure(1, weight=1)

        def _save():
            selected_channels = [n for n, v in channel_vars.items() if v.get()]
            self._rule_rows[idx] = {
                "trigger": trigger_internal,
                "channels": selected_channels,
                "title_template": var_title.get(),
                "message_template": var_message.get(),
                "condition": rule.get("condition"),
                "cooldown": var_cooldown.get(),
                "enabled": rule["enabled"],
            }
            self._render_rules()
            dialog.destroy()

        btn_frame = themed_frame(frame)
        btn_frame.grid(row=r, column=0, columnspan=2, pady=th.pad_md)
        themed_button(
            btn_frame, text=t("common.ok"), style="primary", command=_save,
        ).pack(side=tk.LEFT, padx=th.pad_xs)
        themed_button(
            btn_frame, text=t("common.cancel"), style="secondary",
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=th.pad_xs)

    def _delete_rule(self, idx: int):
        self._rule_rows.pop(idx)
        self._render_rules()

    def _toggle_rule(self, idx: int, var: tk.BooleanVar):
        if idx < len(self._rule_rows):
            self._rule_rows[idx]["enabled"] = var.get()

    # ── 配置加载/保存 ────────────────────────────────────

    def _load_config(self):
        cfg = load_config()
        nc = cfg.notification

        self._var_system.set(nc.channels.system_notify.enabled)
        self._var_sound.set(nc.channels.sound.enabled)
        self._var_webhook_enabled.set(nc.channels.webhook.enabled)
        self._var_webhook_url.set(nc.channels.webhook.url)
        self._var_webhook_type.set(t(f"notification.webhook.type.{nc.channels.webhook.channel_type}"))
        self._webhook_type_internal = nc.channels.webhook.channel_type
        self._var_webhook_secret.set(nc.channels.webhook.secret)
        self._var_webhook_timeout.set(nc.channels.webhook.timeout)

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

    def _save_current_config(self):
        if not hasattr(self, "_var_system") or not hasattr(self, "_rule_rows"):
            return
        cfg = load_config()
        cfg.notification.channels.system_notify.enabled = self._var_system.get()
        cfg.notification.channels.sound.enabled = self._var_sound.get()
        cfg.notification.channels.webhook = ChannelConfig(
            enabled=self._var_webhook_enabled.get(),
            url=self._var_webhook_url.get(),
            channel_type=self._webhook_type_internal,
            secret=self._var_webhook_secret.get(),
            timeout=self._var_webhook_timeout.get(),
        )
        cfg.notification.rules = [
            NotificationRuleConfig(**r) for r in self._rule_rows
        ]
        save_config(cfg)

    def _on_webhook_type_selected(self, _event=None) -> None:
        display = self._var_webhook_type.get()
        for val in _WEBHOOK_TYPE_VALUES:
            if t(f"notification.webhook.type.{val}") == display:
                self._webhook_type_internal = val
                break

    # ── Webhook 测试 ─────────────────────────────────────

    def _test_webhook(self):
        url = self._var_webhook_url.get().strip()
        if not url:
            messagebox.showwarning(
                t("notification.test"),
                t("notification.webhook.url_required"),
            )
            return
        self._save_current_config()

        def _do_test():
            try:
                from src.notification.channels.webhook_notify import WebhookNotifyChannel

                channel = WebhookNotifyChannel(
                    webhook_url=url,
                    channel_type=self._webhook_type_internal,
                    secret=self._var_webhook_secret.get(),
                    timeout=self._var_webhook_timeout.get(),
                )
                result = channel.test()
                if self.frame.winfo_exists():
                    self.frame.after_idle(
                        lambda: messagebox.showinfo(
                            t("notification.test"),
                            t("notification.test_success"),
                        ) if result else messagebox.showerror(
                            t("notification.test"),
                            t("notification.test_failed"),
                        ),
                    )
            except Exception as e:
                if self.frame.winfo_exists():
                    self.frame.after_idle(
                        lambda: messagebox.showerror(t("notification.test"), str(e)),
                    )

        threading.Thread(target=_do_test, daemon=True).start()

    # ── 导航 ─────────────────────────────────────────────

    def _save_and_back(self):
        self._save_current_config()
        self.app.navigate_to(PAGE_HOME)

    def destroy(self):
        self._save_current_config()
        super().destroy()
