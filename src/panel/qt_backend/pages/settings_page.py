"""QtSettingsPage — PySide6 设置页面。

替代 tkinter SettingsPage，使用 QWidget + QTreeWidget + QRadioButton。
快捷键配置 + 外观设置。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QRadioButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from src.core.config import HotkeyBindingConfig, load_config, save_config
from src.core.input.global_hotkey_backend import BackendType
from src.panel.canvas.theme import (
    current_theme, current_theme_mode, resolved_theme_mode, set_theme_mode,
)
from src.panel.pages.page_i18n import SETTINGS_TITLE, SETTINGS_DESC
from src.panel.qt_backend.pages.base_page import QtBasePage
from src.panel.qt_backend.pages.page_registry import register_page
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import themed_button, themed_frame, themed_label
from src.utils.i18n import t

_ACTION_KEYS = [
    ("start_stop", "hotkey.start_stop"),
    ("pause", "hotkey.pause"),
    ("step", "hotkey.step"),
    ("emergency_stop", "hotkey.emergency_stop"),
]


@register_page("settings", label_i18n=SETTINGS_TITLE, desc_i18n=SETTINGS_DESC, icon="⚙", category="settings")
class QtSettingsPage(QtBasePage):
    """设置页面 — 主题切换 + 热键管理。"""

    def title(self) -> str:
        return t("settings.title")

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

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md), sm.s(th.pad_md))
        scroll_layout.setSpacing(sm.s(8))

        self._build_appearance_section(scroll_layout, th, sm)
        self._build_status_section(scroll_layout, th, sm)
        self._build_hotkey_section(scroll_layout, th, sm)
        scroll_layout.addStretch()

        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

    def _build_toolbar(self, layout: QVBoxLayout, th, sm) -> None:
        self._build_toolbar_base(layout, "settings.title")

    def _build_appearance_section(self, layout: QVBoxLayout, th, sm) -> None:
        section = themed_frame(self)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_sm), sm.s(th.pad_md), sm.s(th.pad_sm))

        section_lbl = themed_label(self, text=t("settings.appearance"), style="subtitle")
        section_layout.addWidget(section_lbl)

        radio_row = QHBoxLayout()
        self._theme_radios: dict[str, QRadioButton] = {}
        current_mode = current_theme_mode()
        for mode, label_key in [("light", "settings.theme_light"), ("dark", "settings.theme_dark"), ("system", "settings.theme_system")]:
            rb = QRadioButton(t(label_key))
            rb.setStyleSheet(f"color: {th.text_primary};")
            if mode == current_mode:
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, m=mode: self._on_theme_radio(m) if checked else None)
            self._theme_radios[mode] = rb
            radio_row.addWidget(rb)
        radio_row.addStretch()
        section_layout.addLayout(radio_row)

        self._theme_hint_label = QLabel()
        self._theme_hint_label.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(11)}px;")
        self._update_theme_hint()
        section_layout.addWidget(self._theme_hint_label)

        layout.addWidget(section)

    def _build_status_section(self, layout: QVBoxLayout, th, sm) -> None:
        hm = self.app.hotkey_manager
        if hm is None:
            return

        section = themed_frame(self)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_sm), sm.s(th.pad_md), sm.s(th.pad_sm))

        lbl = themed_label(self, text=t("settings.global_status"), style="subtitle")
        section_layout.addWidget(lbl)

        backend = hm.backend_name
        backend_map = {
            BackendType.PYNPUT.value: t("settings.backend_pynput"),
            BackendType.KEYBOARD.value: t("settings.backend_keyboard"),
        }
        status_text = backend_map.get(backend, t("settings.backend_none"))
        status_lbl = themed_label(self, text=status_text, style="body")
        section_layout.addWidget(status_lbl)

        layout.addWidget(section)

    def _build_hotkey_section(self, layout: QVBoxLayout, th, sm) -> None:
        section = themed_frame(self)
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(sm.s(th.pad_md), sm.s(th.pad_sm), sm.s(th.pad_md), sm.s(th.pad_sm))

        lbl = themed_label(self, text=t("settings.hotkey_section"), style="subtitle")
        section_layout.addWidget(lbl)

        self._tree = QTreeWidget()
        self._tree.setHeaderLabels([
            t("settings.action_name"),
            t("settings.key_combo"),
            t("common.enabled"),
            t("settings.mode"),
        ])
        self._tree.setRootIsDecorated(False)
        self._tree.setStyleSheet(f"""
            QTreeWidget {{
                background-color: {th.bg_surface};
                color: {th.text_primary};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(4)}px;
                font-size: {sm.s(13)}px;
                alternate-background-color: {th.input_bg};
            }}
            QTreeWidget::item {{
                padding: {sm.s(4)}px;
                border-bottom: 1px solid {th.border_default};
            }}
            QTreeWidget::item:selected {{
                background-color: {th.accent_blue};
                color: {th.text_on_accent};
            }}
            QHeaderView::section {{
                background-color: {th.bg_surface};
                color: {th.text_muted};
                border: none;
                border-bottom: 1px solid {th.border_default};
                padding: {sm.s(4)}px {sm.s(8)}px;
                font-weight: bold;
            }}
        """)
        self._tree.setAlternatingRowColors(True)
        header = self._tree.header()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Fixed)
        header.resizeSection(2, sm.s(70))
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        header.resizeSection(3, sm.s(100))

        self._tree.itemClicked.connect(self._on_tree_click)
        section_layout.addWidget(self._tree)

        btn_row = QHBoxLayout()
        edit_btn = themed_button(
            self, text=t("common.edit"), style="primary",
            command=self._on_edit,
        )
        btn_row.addWidget(edit_btn)
        reset_btn = themed_button(
            self, text=t("settings.reset_defaults"), style="secondary",
            command=self._on_reset,
        )
        btn_row.addWidget(reset_btn)
        btn_row.addStretch()
        self._status_label = QLabel()
        self._status_label.setStyleSheet(f"color: {th.text_muted};")
        btn_row.addWidget(self._status_label)
        section_layout.addLayout(btn_row)

        layout.addWidget(section, 1)
        self._populate_tree()

    def _on_theme_radio(self, mode: str) -> None:
        cfg = load_config()
        cfg.editor.theme_mode = mode
        save_config(cfg)
        set_theme_mode(mode)
        self._update_theme_hint()

    def _update_theme_hint(self) -> None:
        mode = current_theme_mode()
        if mode == "system":
            resolved = resolved_theme_mode()
            label = t("settings.theme_dark") if resolved == "dark" else t("settings.theme_light")
            self._theme_hint_label.setText(t("settings.theme_system_hint", mode=label))
        else:
            self._theme_hint_label.setText("")

    def _populate_tree(self) -> None:
        self._tree.clear()
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
                item = QTreeWidgetItem([
                    t(desc_key),
                    binding.key_combination,
                    t("common.enabled") if binding.enabled else "--",
                    mode_text,
                ])
                item.setData(0, Qt.UserRole, action_name)
                self._tree.addTopLevelItem(item)

    def _on_tree_click(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 3:
            return
        action_name = item.data(0, Qt.UserRole)
        if not action_name:
            return
        hm = self.app.hotkey_manager
        if hm is None:
            return
        binding = hm.get_binding(action_name)
        if binding is None:
            return
        hm.set_use_global(action_name, not binding.use_global)
        self._save_hotkey_config(action_name, binding.key_combination)
        self._populate_tree()

    def _on_edit(self) -> None:
        item = self._tree.currentItem()
        if item is None:
            return
        action_name = item.data(0, Qt.UserRole)
        if not action_name:
            return
        self._status_label.setText(t("settings.capture_hint"))
        self.setFocus()
        self._capture_keys(action_name)

    def _capture_keys(self, action_name: str) -> None:
        self._captured_parts: list[str] = []
        self._capture_action = action_name
        self.grabKeyboard()

    def keyPressEvent(self, event) -> None:
        if not hasattr(self, "_capture_action"):
            super().keyPressEvent(event)
            return

        key = event.key()
        text = event.text()
        key_name = None

        modifiers = event.modifiers()
        mod_names = []
        if modifiers & Qt.ControlModifier:
            mod_names.append("ctrl")
        if modifiers & Qt.ShiftModifier:
            mod_names.append("shift")
        if modifiers & Qt.AltModifier:
            mod_names.append("alt")
        if modifiers & Qt.MetaModifier:
            mod_names.append("cmd")

        if key in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            self._captured_parts = mod_names
            combo = "+".join(sorted(self._captured_parts))
            self._status_label.setText(combo)
            return

        if Qt.Key_A <= key <= Qt.Key_Z:
            key_name = chr(key).lower()
        elif Qt.Key_0 <= key <= Qt.Key_9:
            key_name = str(key - Qt.Key_0)
        elif key == Qt.Key_Space:
            key_name = "space"
        elif key == Qt.Key_Return:
            key_name = "enter"
        elif key == Qt.Key_Escape:
            self.releaseKeyboard()
            del self._capture_action
            self._status_label.setText(t("settings.hotkey.cancelled"))
            return
        elif key == Qt.Key_Tab:
            key_name = "tab"
        elif key == Qt.Key_Backspace:
            key_name = "backspace"
        elif Qt.Key_F1 <= key <= Qt.Key_F24:
            key_name = f"f{key - Qt.Key_F1 + 1}"
        else:
            key_name = text.lower() if text else str(key)

        parts = mod_names + [key_name]
        combo = "+".join(sorted(parts))

        self.releaseKeyboard()
        saved_action = action_name
        del self._capture_action
        self._apply_key(saved_action, combo)

    def keyReleaseEvent(self, event) -> None:
        if not hasattr(self, "_capture_action"):
            super().keyReleaseEvent(event)
            return

        if event.key() in (Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta):
            return

        if len(self._captured_parts) > 1:
            combo = "+".join(sorted(self._captured_parts))
            action_name = self._capture_action
            self.releaseKeyboard()
            del self._capture_action
            self._apply_key(action_name, combo)

    def _apply_key(self, action_name: str, combo: str) -> None:
        hm = self.app.hotkey_manager
        if hm and hm.reregister(action_name, combo):
            self._save_hotkey_config(action_name, combo)
            self._populate_tree()
            self._status_label.setText(t("settings.saved"))
        else:
            self._status_label.setText("")

    def _on_reset(self) -> None:
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
        self._status_label.setText(t("settings.saved"))

    def _save_hotkey_config(self, action_name: str, combo: str) -> None:
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
                cfg.hotkey, action_name,
                HotkeyBindingConfig(key_combination=combo, use_global=use_global),
            )
        save_config(cfg)

    def destroy_page(self) -> None:
        if hasattr(self, "_capture_action"):
            self.releaseKeyboard()
            del self._capture_action
        super().destroy_page()
