"""设置页面 — 快捷键配置 + 外观设置"""

import tkinter as tk
from tkinter import ttk

from src.panel.canvas.theme import current_theme, current_theme_mode, resolved_theme_mode, set_theme_mode
from src.core.input.global_hotkey_backend import BackendType
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import SETTINGS_DESC, SETTINGS_TITLE
from src.panel.pages.page_registry import register_page
from src.panel.widgets import (
    themed_button,
    themed_frame,
    themed_label,
    themed_labelframe,
    themed_radiobutton,
)
from src.utils.i18n import t

_ACTION_KEYS = [
    ("start_stop", "hotkey.start_stop"),
    ("pause", "hotkey.pause"),
    ("step", "hotkey.step"),
    ("emergency_stop", "hotkey.emergency_stop"),
]


@register_page("settings", label_i18n=SETTINGS_TITLE, desc_i18n=SETTINGS_DESC, icon="⚙", category="settings")
class SettingsPage(BasePage):

    def title(self) -> str:
        return t("settings.title")

    def build(self):
        th = current_theme()

        # ── 统一工具栏 ──
        self._build_toolbar_base("settings.title")

        # 外观设置区域
        self._build_appearance_section(th)

        # 全局热键状态提示区
        self._build_status_section(th)

        # Hotkey section
        section = themed_labelframe(self.frame, text=t("settings.hotkey_section"))
        section.pack(fill=tk.BOTH, expand=True, padx=th.pad_xl, pady=th.pad_md)

        # Treeview
        tree_frame = themed_frame(section)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=th.pad_md, pady=th.pad_md)

        cols = ("action", "key_combo", "enabled", "mode")
        self._tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings", height=6,
        )
        self._tree.heading("action", text=t("settings.action_name"))
        self._tree.heading("key_combo", text=t("settings.key_combo"))
        self._tree.heading("enabled", text=t("common.enabled"))
        self._tree.heading("mode", text=t("settings.mode"))
        self._tree.column("action", width=180, stretch=True)
        self._tree.column("key_combo", width=160, stretch=True)
        self._tree.column("enabled", width=70, stretch=False)
        self._tree.column("mode", width=100, stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)
        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind("<ButtonRelease-1>", self._on_tree_click)

        # Buttons
        btn_frame = themed_frame(section)
        btn_frame.pack(fill=tk.X, padx=th.pad_md, pady=(0, th.pad_md))

        themed_button(
            btn_frame, text=t("common.edit"), style="primary",
            command=self._on_edit,
        ).pack(side=tk.LEFT, padx=(0, th.pad_sm))

        themed_button(
            btn_frame, text=t("settings.reset_defaults"), style="secondary",
            command=self._on_reset,
        ).pack(side=tk.LEFT, padx=(0, th.pad_sm))

        # Status
        self._status_var = tk.StringVar()
        self._status_label = themed_label(
            btn_frame, textvariable=self._status_var, style="small",
        )
        self._status_label.pack(side=tk.RIGHT)

        self._populate_tree()

    def _build_status_section(self, th):
        """构建全局热键状态提示区。"""
        status_frame = themed_labelframe(self.frame, text=t("settings.global_status"))
        status_frame.pack(fill=tk.X, padx=th.pad_xl, pady=(th.pad_md, 0))

        hm = self.app.hotkey_manager
        if hm is None:
            return

        backend = hm.backend_name
        backend_map = {
            BackendType.PYNPUT.value: t("settings.backend_pynput"),
            BackendType.KEYBOARD.value: t("settings.backend_keyboard"),
        }
        status_text = backend_map.get(backend, t("settings.backend_none"))

        status_label = themed_label(status_frame, text=status_text, style="body")
        status_label.pack(padx=th.pad_md, pady=th.pad_sm, anchor=tk.W)

    def _build_appearance_section(self, th):
        """构建外观设置区域。"""
        section = themed_labelframe(self.frame, text=t("settings.appearance"))
        section.pack(fill=tk.X, padx=th.pad_xl, pady=(th.pad_md, 0))

        radio_frame = themed_frame(section)
        radio_frame.pack(fill=tk.X, padx=th.pad_md, pady=th.pad_sm)

        self._theme_var = tk.StringVar(value=current_theme_mode())
        for mode, label_key in [
            ("light", "settings.theme_light"),
            ("dark", "settings.theme_dark"),
            ("system", "settings.theme_system"),
        ]:
            themed_radiobutton(
                radio_frame, text=t(label_key), value=mode,
                variable=self._theme_var,
                command=lambda m=mode: self._on_theme_radio(m),
            ).pack(side=tk.LEFT, padx=(0, th.pad_lg))

        self._theme_hint_var = tk.StringVar()
        self._update_theme_hint()
        themed_label(
            section, textvariable=self._theme_hint_var, style="small",
        ).pack(padx=th.pad_md, pady=(0, th.pad_sm), anchor=tk.W)

    def _on_theme_radio(self, mode: str) -> None:
        from src.core.config import load_config, save_config
        cfg = load_config()
        cfg.editor.theme_mode = mode
        save_config(cfg)
        set_theme_mode(mode)
        self._update_theme_hint()

    def _update_theme_hint(self) -> None:
        mode = current_theme_mode()
        if mode == "system":
            resolved = resolved_theme_mode()
            resolved_label = (
                t("settings.theme_dark") if resolved == "dark"
                else t("settings.theme_light")
            )
            self._theme_hint_var.set(
                t("settings.theme_system_hint", mode=resolved_label)
            )
        else:
            self._theme_hint_var.set("")

    def _populate_tree(self):
        for item in self._tree.get_children():
            self._tree.delete(item)

        hm = self.app.hotkey_manager
        if hm is None:
            return

        for action_name, desc_key in _ACTION_KEYS:
            binding = hm.get_binding(action_name)
            if binding:
                mode_text = (
                    t("settings.use_global") if binding.use_global
                    else t("settings.app_only")
                )
                self._tree.insert("", tk.END, iid=action_name, values=(
                    t(desc_key),
                    binding.key_combination,
                    t("common.enabled") if binding.enabled else "--",
                    mode_text,
                ))

    def _on_edit(self):
        sel = self._tree.selection()
        if not sel:
            return
        action_name = sel[0]
        self._status_var.set(t("settings.capture_hint"))
        self.frame.focus_set()
        self._capture_keys(action_name)

    def _on_tree_click(self, event):
        """点击 Treeview 行处理：点击 mode 列切换全局/应用内模式。"""
        region = self._tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        column = self._tree.identify_column(event.x)
        item = self._tree.identify_row(event.y)
        if not item or column != "#4":
            return

        hm = self.app.hotkey_manager
        if hm is None:
            return

        binding = hm.get_binding(item)
        if binding is None:
            return

        hm.set_use_global(item, not binding.use_global)
        self._save_hotkey_config(item, binding.key_combination)
        self._populate_tree()

    def _capture_keys(self, action_name: str):
        from src.panel.dialogs.key_picker import _TK_TO_KEY

        self._captured_parts: list[str] = []

        def on_press(event):
            key = _TK_TO_KEY.get(event.keysym, event.keysym.lower())
            # Normalize modifier variants to canonical form
            modifier_canonical = {
                "ctrlleft": "ctrl", "ctrlright": "ctrl",
                "shiftleft": "shift", "shiftright": "shift",
                "altleft": "alt", "altright": "alt",
                "winleft": "cmd", "winright": "cmd",
                "command": "cmd", "option": "alt",
            }
            key = modifier_canonical.get(key, key)

            if key not in self._captured_parts:
                self._captured_parts.append(key)

            combo = "+".join(sorted(self._captured_parts))
            self._status_var.set(combo)

        def on_release(event):
            if len(self._captured_parts) > 1:
                combo = "+".join(sorted(self._captured_parts))
                self.frame.unbind("<KeyPress>")
                self.frame.unbind("<KeyRelease>")
                self._apply_key(action_name, combo)

        self.frame.bind("<KeyPress>", on_press)
        self.frame.bind("<KeyRelease>", on_release)

    def _apply_key(self, action_name: str, combo: str):
        hm = self.app.hotkey_manager
        if hm and hm.reregister(action_name, combo):
            self._save_hotkey_config(action_name, combo)
            self._populate_tree()
            self._status_var.set(t("settings.saved"))
        else:
            self._status_var.set("")

    def _on_reset(self):
        from src.core.config import HotkeyConfig

        defaults = HotkeyConfig()
        hm = self.app.hotkey_manager

        for action_name, _ in _ACTION_KEYS:
            default_binding = defaults.get_binding(action_name)
            if hm and default_binding.key_combination:
                hm.reregister(action_name, default_binding.key_combination)
                hm.set_enabled(action_name, True)
                hm.set_use_global(action_name, True)
                self._save_hotkey_config(action_name, default_binding.key_combination)

        self._populate_tree()
        self._status_var.set(t("settings.saved"))

    def _save_hotkey_config(self, action_name: str, combo: str):
        from src.core.config import HotkeyBindingConfig, load_config, save_config

        cfg = load_config()
        hm = self.app.hotkey_manager
        binding = hm.get_binding(action_name) if hm else None
        use_global = binding.use_global if binding else True

        binding_cfg = getattr(cfg.hotkey, action_name, None)
        if binding_cfg:
            binding_cfg.key_combination = combo
            binding_cfg.enabled = True
            binding_cfg.use_global = use_global
        else:
            setattr(
                cfg.hotkey,
                action_name,
                HotkeyBindingConfig(key_combination=combo, use_global=use_global),
            )
        save_config(cfg)
