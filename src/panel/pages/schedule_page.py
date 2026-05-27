"""调度管理页面 — 调度列表 + 启停控制 UI"""

import tkinter as tk
from tkinter import ttk, messagebox

from src.core.config import (
    ScheduleEntryConfig,
    load_config,
    save_config,
)
from src.panel.canvas.theme import current_theme
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import SCHEDULE_DESC, SCHEDULE_TITLE
from src.panel.pages.page_registry import PAGE_HOME, register_page
from src.panel.widgets import (
    themed_button,
    themed_checkbutton,
    themed_entry,
    themed_frame,
    themed_label,
    themed_labelframe,
    themed_spinbox,
)
from src.utils.i18n import t

_SCHEDULE_TYPES = ["once", "interval", "daily", "weekly"]


@register_page("schedule", label_i18n=SCHEDULE_TITLE, desc_i18n=SCHEDULE_DESC, icon="⏰", category="settings")
class SchedulePage(BasePage):
    """调度管理页面 — 调度列表 CRUD + 启停"""

    def title(self) -> str:
        return t("schedule.title")

    def build(self):
        th = current_theme()

        # ── 统一工具栏 ──
        toolbar = self._build_toolbar_base("schedule.title")

        toolbar.add_spacer()

        toolbar.make_button(
            "actions", text=t("common.ok"), icon="save",
            command=self._save_and_back, style="primary",
            tooltip=t("common.ok"),
        )

        container = themed_frame(self.frame)
        container.pack(fill=tk.BOTH, expand=True, padx=th.pad_xl, pady=th.pad_sm)

        self._build_list_section(container)
        self._load_config()

    # ── 调度列表 ──────────────────────────────────────────

    def _build_list_section(self, parent: tk.Widget):
        section = themed_labelframe(parent, text=t("schedule.title"))
        section.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        th = current_theme()
        btn_frame = themed_frame(section)
        btn_frame.pack(fill=tk.X, padx=th.pad_md, pady=th.pad_xs)

        themed_button(
            btn_frame, text="+ " + t("schedule.add"), style="primary",
            command=self._add_schedule,
        ).pack(side=tk.LEFT)

        self._list_container = themed_frame(section)
        self._list_container.pack(
            fill=tk.BOTH, expand=True, padx=th.pad_md, pady=th.pad_xs,
        )

        self._schedule_rows: list[dict] = []
        self._rule_traces: list[tuple] = []

    def _render_list(self):
        for var, trace_name in self._rule_traces:
            try:
                var.trace_remove("write", trace_name)
            except Exception:
                pass
        self._rule_traces = []
        for w in self._list_container.winfo_children():
            w.destroy()

        for i, entry in enumerate(self._schedule_rows):
            row = themed_frame(self._list_container)
            row.pack(fill=tk.X, pady=2)

            type_label = t(f"schedule.type.{entry['schedule_type']}")
            profile = entry["profile_name"] or "—"
            enabled_text = t("common.enabled") if entry["enabled"] else ""
            info_text = f"{type_label} | {profile}"
            if enabled_text:
                info_text += f" | {enabled_text}"

            themed_label(
                row, text=info_text, anchor=tk.W,
            ).pack(side=tk.LEFT, fill=tk.X, expand=True)

            var_enabled = tk.BooleanVar(value=entry["enabled"])
            trace_name = var_enabled.trace_add(
                "write",
                lambda *_, idx=i, v=var_enabled: self._toggle_enabled(idx, v),
            )
            self._rule_traces.append((var_enabled, trace_name))
            themed_checkbutton(
                row, text=t("common.enabled"), variable=var_enabled,
            ).pack(side=tk.LEFT, padx=4)

            themed_button(
                row, text=t("common.edit"), style="secondary",
                command=lambda idx=i: self._edit_schedule(idx),
            ).pack(side=tk.LEFT, padx=2)

            themed_button(
                row, text=t("common.delete"), style="secondary",
                command=lambda idx=i: self._delete_schedule(idx),
            ).pack(side=tk.LEFT, padx=2)

    def _add_schedule(self):
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

    def _edit_schedule(self, idx: int):
        entry = self._schedule_rows[idx]
        dialog = tk.Toplevel(self.frame)
        dialog.title(t("common.edit"))
        dialog.geometry("450x420")
        dialog.transient(self.frame)
        dialog.grab_set()

        th = current_theme()
        dialog.configure(bg=th.page_bg)

        frame = themed_frame(dialog)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        type_internal = entry["schedule_type"]
        var_type = tk.StringVar(value=t(f"schedule.type.{type_internal}"))
        var_profile = tk.StringVar(value=entry["profile_name"])
        var_interval = tk.IntVar(value=entry["interval_seconds"])
        var_daily_time = tk.StringVar(value=entry["daily_time"])
        var_weekly_day = tk.IntVar(value=entry["weekly_day"])
        var_weekly_time = tk.StringVar(value=entry["weekly_time"])
        var_max_runs = tk.IntVar(value=entry["max_runs"] or 0)
        var_loop_count = tk.IntVar(value=entry["loop_count"])
        var_unlimited = tk.BooleanVar(value=entry["max_runs"] is None)

        r = 0

        def _add_field(label_text: str, widget_factory, **kw):
            nonlocal r
            themed_label(
                frame, text=label_text,
            ).grid(row=r, column=0, sticky=tk.W, pady=2)
            widget_factory(**kw).grid(row=r, column=1, sticky=tk.EW, padx=4, pady=2)
            r += 1

        def _build_type_combo():
            combo = ttk.Combobox(
                frame, textvariable=var_type, state="readonly",
                values=[t(f"schedule.type.{v}") for v in _SCHEDULE_TYPES], width=12,
            )

            def _on_type_selected(_event=None):
                nonlocal type_internal
                display = var_type.get()
                for val in _SCHEDULE_TYPES:
                    if t(f"schedule.type.{val}") == display:
                        type_internal = val
                        break

            combo.bind("<<ComboboxSelected>>", _on_type_selected)
            return combo

        _add_field(
            t("schedule.type"),
            lambda **_: _build_type_combo(),
        )
        _add_field(
            t("schedule.profile"),
            lambda **_: themed_entry(frame, textvariable=var_profile),
        )
        _add_field(
            t("schedule.interval_seconds"),
            lambda **_: themed_spinbox(
                frame, from_=60, to=86400, textvariable=var_interval, width=8,
            ),
        )
        _add_field(
            t("schedule.daily_time"),
            lambda **_: themed_entry(frame, textvariable=var_daily_time),
        )
        _add_field(
            t("schedule.weekly_day"),
            lambda **_: ttk.Combobox(
                frame, textvariable=var_weekly_day, state="readonly",
                values=list(range(7)), width=5,
            ),
        )
        _add_field(
            t("schedule.weekly_time"),
            lambda **_: themed_entry(frame, textvariable=var_weekly_time),
        )
        _add_field(
            t("schedule.loop_count"),
            lambda **_: themed_spinbox(
                frame, from_=1, to=9999, textvariable=var_loop_count, width=8,
            ),
        )

        themed_label(
            frame, text=t("schedule.max_runs"),
        ).grid(row=r, column=0, sticky=tk.W, pady=2)
        mr_frame = themed_frame(frame)
        mr_frame.grid(row=r, column=1, sticky=tk.W, padx=4, pady=2)

        def _on_unlimited_toggle():
            if var_unlimited.get():
                var_max_runs.set(0)

        themed_checkbutton(
            mr_frame, text=t("common.infinite_loop"), variable=var_unlimited,
            command=_on_unlimited_toggle,
        ).pack(side=tk.LEFT)
        themed_spinbox(
            mr_frame, from_=1, to=9999, textvariable=var_max_runs, width=6,
        ).pack(side=tk.LEFT, padx=4)
        r += 1

        frame.columnconfigure(1, weight=1)

        def _save():
            self._schedule_rows[idx] = {
                "schedule_type": type_internal,
                "profile_name": var_profile.get(),
                "interval_seconds": var_interval.get(),
                "daily_time": var_daily_time.get(),
                "daily_days": entry.get("daily_days"),
                "weekly_day": var_weekly_day.get(),
                "weekly_time": var_weekly_time.get(),
                "max_runs": None if var_unlimited.get() else var_max_runs.get(),
                "loop_count": var_loop_count.get(),
                "enabled": entry["enabled"],
            }
            self._render_list()
            dialog.destroy()

        btn_frame = themed_frame(frame)
        btn_frame.grid(row=r, column=0, columnspan=2, pady=10)
        themed_button(
            btn_frame, text=t("common.ok"), style="primary", command=_save,
        ).pack(side=tk.LEFT, padx=4)
        themed_button(
            btn_frame, text=t("common.cancel"), style="secondary",
            command=dialog.destroy,
        ).pack(side=tk.LEFT, padx=4)

    def _delete_schedule(self, idx: int):
        name = self._schedule_rows[idx].get("profile_name", "")
        if not messagebox.askyesno(
            t("workflow.msg.confirm_delete"),
            t("schedule.msg.confirm_delete").format(name=name or "—"),
        ):
            return
        self._schedule_rows.pop(idx)
        self._render_list()

    def _toggle_enabled(self, idx: int, var: tk.BooleanVar):
        if idx < len(self._schedule_rows):
            self._schedule_rows[idx]["enabled"] = var.get()

    # ── 配置加载/保存 ────────────────────────────────────

    def _load_config(self):
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

    def _save_current_config(self):
        cfg = load_config()
        cfg.schedule_list.schedules = [
            ScheduleEntryConfig(**r) for r in self._schedule_rows
        ]
        save_config(cfg)

    # ── 导航 ─────────────────────────────────────────────

    def _save_and_back(self):
        self._save_current_config()
        self.app.navigate_to(PAGE_HOME)

    def destroy(self):
        self._save_current_config()
        super().destroy()
