"""QtHomePage — PySide6 主页。

替代 tkinter HomePage，功能卡片网格 + 执行器状态横幅 + 主题/语言切换。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.panel.profile_manager import ProfileManager

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from src.panel.canvas.scale import Breakpoint, scale_manager
from src.panel.canvas.theme import current_theme, current_theme_mode, set_theme_mode
from src.panel.home_shared import (
    CHECK_EXECUTOR_MS,
    SECTION_I18N,
    SECTION_TYPES,
    THEME_CYCLE,
    PageType,
    SectionState,
    discover_features,
    HomeStateMixin,
)
from src.panel.pages.page_i18n import HOME_TITLE
from src.panel.pages.page_registry import PAGE_HOME
from src.panel.qt_backend.pages.base_page import QtBasePage, SaveDiscardCancel
from src.panel.qt_backend.pages.page_registry import register_page
from src.panel.qt_backend.scale import qt_scale_manager
from src.panel.qt_backend.widgets import style_button, themed_button, themed_frame, themed_label
from src.utils.i18n import t, get_language, set_language

@register_page("home", label_i18n=HOME_TITLE, icon="🏠", category="main")
class QtHomePage(HomeStateMixin, QtBasePage):
    """功能选择主页。"""

    def title(self) -> str:
        return t("app.title")

    def build(self) -> None:
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

        hint_lbl = themed_label(self._content, text=t("home.select_feature"), style="section")
        hint_lbl.setStyleSheet(f"color: {th.text_muted};")
        self._content_layout.addWidget(hint_lbl)

        self._banner_frame = QWidget()
        self._banner_layout = QVBoxLayout(self._banner_frame)
        self._banner_layout.setContentsMargins(0, 0, 0, 0)
        self._banner_layout.setSpacing(sm.s(2))
        self._content_layout.addWidget(self._banner_frame)

        self._section_widgets: dict[PageType, QWidget | None] = {}
        self._section_combos: dict[PageType, QComboBox] = {}
        self._last_states: dict[PageType, SectionState | None] = {}
        self._dot_labels: dict[PageType, QLabel] = {}
        self._section_refs: dict[PageType, dict] = {}
        self._dot_on: bool = True
        self._pulse_timer_id: str | None = None
        self._pm: ProfileManager | None = None
        self._launchable_cache: dict[str, tuple[str, ...]] = {pt: () for pt in SECTION_TYPES}
        self._poll_tick: int = 0
        self._profiles_dir_mtime: float = 0.0
        self._profiles_sub_mtime: float = 0.0
        self._profiles_scan_time: float = 0.0

        for pt in SECTION_TYPES:
            self._section_widgets[pt] = None
            self._last_states[pt] = None
            self._section_combos[pt] = QComboBox()
            self._dot_labels[pt] = QLabel()

        self._rescan_launchable_profiles()
        self._rebuild_all_sections()
        self.schedule(CHECK_EXECUTOR_MS, self._check_executor_state)

        self._cards_frame = QWidget()
        self._cards_layout = QGridLayout(self._cards_frame)
        self._cards_layout.setSpacing(sm.s(8))
        self._content_layout.addWidget(self._cards_frame, 1)
        self._rebuild_cards(self._breakpoint_cols())

        self._content_layout.addStretch()

    def _build_toolbar(self, layout: QVBoxLayout, th, sm) -> None:
        toolbar = self._build_toolbar_base(layout, "app.title", show_back=False)

        self._lang_radios: dict[str, QRadioButton] = {}
        for code, label in [("zh", "中文"), ("en", "EN")]:
            rb = QRadioButton(label)
            rb.setStyleSheet(f"color: {th.text_primary};")
            if code == get_language():
                rb.setChecked(True)
            rb.toggled.connect(lambda checked, c=code: self._switch_language(c) if checked else None)
            toolbar.addWidget(rb)
            self._lang_radios[code] = rb

        theme_btn = themed_button(
            self, text=current_theme_mode(), style="secondary",
            command=self._toggle_theme,
        )
        self._theme_btn = theme_btn
        toolbar.addWidget(theme_btn)

    def _rebuild_cards(self, cols: int) -> None:
        while self._cards_layout.count():
            item = self._cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        th = current_theme()
        sm = qt_scale_manager()
        card_style = f"""
            QFrame {{
                background-color: {th.bg_surface};
                border: 1px solid {th.border_default};
                border-radius: {sm.s(6)}px;
                padding: {sm.s(8)}px;
            }}
            QFrame:hover {{
                border-color: {th.accent_blue};
            }}
        """

        for i, feat in enumerate(discover_features()):
            row, col = divmod(i, cols)
            card = self._create_card(feat, card_style, th, sm)
            self._cards_layout.addWidget(card, row, col)

        for c in range(cols):
            self._cards_layout.setColumnStretch(c, 1)

    def _create_card(self, feat: dict, card_style: str, th, sm) -> QFrame:
        card = QFrame()
        card.setStyleSheet(card_style)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(sm.s(12), sm.s(8), sm.s(12), sm.s(8))
        card_layout.setSpacing(sm.s(4))

        title_lbl = QLabel(t(feat["title_key"]))
        title_lbl.setStyleSheet(f"color: {th.text_primary}; font-weight: bold; font-size: {sm.s(14)}px;")
        card_layout.addWidget(title_lbl)

        desc_lbl = QLabel(t(feat["desc_key"]))
        desc_lbl.setStyleSheet(f"color: {th.text_muted}; font-size: {sm.s(12)}px;")
        desc_lbl.setWordWrap(True)
        card_layout.addWidget(desc_lbl, 1)

        enter_btn = themed_button(
            card, text=t("home.enter"), style="primary",
            command=lambda page=feat["page"]: self.app.navigate_to(page),
        )
        card_layout.addWidget(enter_btn, 0, Qt.AlignRight)

        return card

    def _rebuild_section(self, page_type: PageType, state: SectionState) -> None:
        new_mode = "running" if state.is_running else "idle"
        prev_state = self._last_states.get(page_type)
        old_mode = (
            "running" if prev_state and prev_state.is_running else "idle"
        ) if prev_state else None

        visible = (
            state.is_running
            or state.has_content
            or len(state.launchable_profiles) > 0
        )

        if old_mode == new_mode and visible:
            old = self._section_widgets.get(page_type)
            if old is not None:
                try:
                    self._update_section_in_place(page_type, state, new_mode)
                    return
                except RuntimeError:
                    pass

        self._section_refs.pop(page_type, None)

        old = self._section_widgets.get(page_type)
        if old is not None:
            old.setParent(None)
            old.deleteLater()
        self._section_widgets[page_type] = None

        if not visible:
            self._update_banner_visibility()
            return

        th = current_theme()
        sm = qt_scale_manager()

        frame = QWidget()
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(0, 0, 0, 0)
        frame_layout.setSpacing(0)

        if state.is_running:
            self._build_section_running(frame_layout, page_type, state, th, sm)
        else:
            self._build_section_idle(frame_layout, page_type, state, th, sm)

        self._banner_layout.addWidget(frame)
        self._section_widgets[page_type] = frame
        self._update_banner_visibility()

    def _update_banner_visibility(self) -> None:
        has_visible = any(
            w is not None and self._widget_exists(w)
            for w in self._section_widgets.values()
        )
        self._banner_frame.setVisible(has_visible)

    # ── Widget adapter overrides ──

    def _widget_exists(self, widget) -> bool:
        try:
            _ = widget.objectName()
            return True
        except RuntimeError:
            return False

    def _widget_set_label_text(self, widget, text: str) -> None:
        try:
            widget.setText(text)
        except RuntimeError:
            pass

    def _widget_set_visible(self, widget, visible: bool) -> None:
        try:
            widget.setVisible(visible)
        except RuntimeError:
            pass

    def _widget_set_button(
        self, btn, text: str, style: str, callback, refs: dict, conn_key: str,
    ) -> None:
        try:
            btn.setText(text)
            style_button(btn, style)
            try:
                btn.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
            btn.clicked.connect(callback)
        except RuntimeError:
            pass

    def _widget_combo_needs_update(self, combo, profiles: tuple) -> bool:
        try:
            if combo.count() != len(profiles):
                return True
            return profiles != tuple(
                combo.itemText(i) for i in range(combo.count())
            )
        except RuntimeError:
            return False

    def _widget_set_combo_items(
        self, combo, profiles: tuple, current: str | None, page_type: PageType,
    ) -> None:
        try:
            combo.blockSignals(True)
            combo.clear()
            combo.addItems(profiles)
            if profiles:
                if current and current in profiles:
                    combo.setCurrentText(current)
                else:
                    combo.setCurrentIndex(0)
            combo.blockSignals(False)
        except RuntimeError:
            pass

    def _build_section_running(
        self, layout: QVBoxLayout, page_type: PageType, state: SectionState, th, sm,
    ) -> None:
        i18n = SECTION_I18N[page_type]
        inner = QFrame()
        inner.setStyleSheet(f"""
            QFrame {{
                background-color: {th.accent_green_dim};
                border: 2px solid {th.status_running};
                border-radius: {sm.s(4)}px;
                padding: {sm.s(8)}px;
            }}
        """)
        row = QHBoxLayout(inner)
        row.setContentsMargins(sm.s(12), sm.s(8), sm.s(12), sm.s(8))

        dot = QLabel("*")
        dot.setStyleSheet(f"color: {th.status_running}; font-size: {sm.s(16)}px; font-weight: bold;")
        dot.setFixedWidth(sm.s(16))
        row.addWidget(dot)
        self._dot_labels[page_type] = dot

        title_lbl = QLabel(t(i18n["title"]))
        title_lbl.setStyleSheet(f"color: {th.status_running}; font-weight: bold; font-size: {sm.s(14)}px;")
        row.addWidget(title_lbl)

        name_text = state.profile_name or t(i18n["unsaved"])
        name_lbl = QLabel(name_text)
        name_lbl.setStyleSheet(f"color: {th.text_muted};")
        row.addWidget(name_lbl)

        status_text = (
            t("workflow.status.paused") if state.is_paused
            else t("workflow.status.running")
        )
        status_lbl = QLabel(status_text)
        status_lbl.setStyleSheet(f"color: {th.status_running}; font-weight: bold;")
        row.addWidget(status_lbl)
        row.addStretch()

        go_btn = themed_button(inner, text=t("home.banner.go_to"), style="secondary",
                               command=lambda: self.app.navigate_to(page_type))
        row.addWidget(go_btn)

        if state.is_paused:
            pause_btn = themed_button(inner, text=t("common.resume"), style="primary")
            pause_conn = pause_btn.clicked.connect(self._on_section_resume)
        else:
            pause_btn = themed_button(inner, text=t("common.pause"), style="secondary")
            pause_conn = pause_btn.clicked.connect(self._on_section_pause)
        row.addWidget(pause_btn)

        stop_btn = themed_button(inner, text=t("common.stop"), style="danger",
                                 command=self._on_section_stop)
        row.addWidget(stop_btn)

        layout.addWidget(inner)

        self._section_refs[page_type] = {
            "status_label": status_lbl,
            "pause_btn": pause_btn,
            "pause_conn": pause_conn,
            "is_resume": state.is_paused,
            "status_text": status_text,
        }

        self._dot_on = True
        if self._pulse_timer_id is not None:
            self._timer.cancel(self._pulse_timer_id)
        self._pulse_timer_id = self.schedule(600, self._pulse_dots)

    def _build_section_idle(
        self, layout: QVBoxLayout, page_type: PageType, state: SectionState, th, sm,
    ) -> None:
        i18n = SECTION_I18N[page_type]
        border_color = getattr(th, "border_color", th.text_muted)
        inner = QFrame()
        inner.setStyleSheet(f"""
            QFrame {{
                background-color: {th.bg_surface};
                border: 1px solid {border_color};
                border-radius: {sm.s(4)}px;
                padding: {sm.s(4)}px;
            }}
        """)
        row = QHBoxLayout(inner)
        row.setContentsMargins(sm.s(12), sm.s(8), sm.s(12), sm.s(8))

        name_lbl: QLabel | None = None

        title_lbl = QLabel(t(i18n["title"]))
        title_lbl.setStyleSheet(f"color: {th.text_muted}; font-weight: bold;")
        row.addWidget(title_lbl)

        if state.has_content:
            name_text = state.profile_name or t(i18n["unsaved"])
            if state.is_dirty:
                name_text += " *"
            name_lbl = QLabel(name_text)
            name_lbl.setStyleSheet(f"color: {th.text_primary};")
            row.addWidget(name_lbl)

        profiles = state.launchable_profiles
        combo = self._section_combos[page_type]
        combo.clear()
        combo.addItems(profiles)
        if profiles:
            if state.profile_name and state.profile_name in profiles:
                combo.setCurrentText(state.profile_name)
            else:
                combo.setCurrentIndex(0)
            combo.currentTextChanged.disconnect()
            combo.currentTextChanged.connect(
                lambda _text, pt=page_type: self._on_section_profile_selected(pt),
            )
            row.addWidget(combo)
        else:
            no_profile_lbl = QLabel(t("home.banner.no_profile"))
            no_profile_lbl.setStyleSheet(f"color: {th.text_muted};")
            row.addWidget(no_profile_lbl)

        combo_ref: QComboBox | None = combo if profiles else None

        if state.has_content or profiles:
            start_btn = themed_button(
                inner, text=t("common.start"), style="primary",
                command=lambda pt=page_type: self._on_section_start(pt),
            )
            row.addWidget(start_btn)

        if state.has_content:
            clear_btn = themed_button(
                inner, text=t("home.banner.clear"), style="secondary",
                command=lambda pt=page_type: self._on_section_clear(pt),
            )
            row.addWidget(clear_btn)

        row.addStretch()
        layout.addWidget(inner)

        self._section_refs[page_type] = {
            "name_label": name_lbl,
            "combo": combo_ref,
        }

    def _pulse_dots(self) -> None:
        executor = self.app.executor
        if not executor or not executor.is_running:
            return

        th = current_theme()
        self._dot_on = not self._dot_on
        color = th.status_running if self._dot_on else th.accent_green_dim

        for pt in SECTION_TYPES:
            dot = self._dot_labels.get(pt)
            if dot is not None:
                try:
                    dot.setStyleSheet(f"color: {color}; font-size: {qt_scale_manager().s(16)}px; font-weight: bold;")
                except RuntimeError:
                    pass

        self._pulse_timer_id = self.schedule(600, self._pulse_dots)

    def _on_section_start(self, page_type: PageType) -> None:
        combo = self._section_combos.get(page_type)
        profile_name = combo.currentText() if combo else ""
        result = self._do_section_start(page_type, profile_name)
        if result == "not_found":
            self._show_error(t("app.title"), t("profile.error.file_not_found", path=profile_name))

    def _on_section_clear(self, page_type: PageType) -> None:
        result = self._do_section_clear(page_type)
        if result == "navigate":
            self.app.navigate_to(page_type)
        elif result == "confirm_needed":
            if self._ask_yes_no(t("common.confirm"), t("chain.msg.confirm_clear")):
                combo = self._section_combos.get(page_type)
                if combo is not None:
                    combo.setCurrentIndex(0)
                self._do_clear_confirmed(page_type)

    def _on_section_profile_selected(self, page_type: PageType) -> None:
        combo = self._section_combos.get(page_type)
        if combo is None:
            return
        new_name = combo.currentText()
        if not new_name:
            return

        model = self._get_cached_model(page_type)
        controller = self._get_cached_controller(page_type)

        if model is None or controller is None:
            return

        if model.current_profile_name == new_name:
            return

        if model.is_dirty:
            result = self._ask_save_discard_cancel(
                t("record.export.unsaved_title"),
                t("record.export.unsaved_message"),
            )
            if result == SaveDiscardCancel.CANCEL:
                if model.current_profile_name:
                    combo.setCurrentText(model.current_profile_name)
                return
            if result == SaveDiscardCancel.SAVE:
                controller.save_profile()

        try:
            controller.load_profile(new_name)
        except Exception:
            self._show_error(t("app.title"), t("common.load_failed"))
            combo.setCurrentText(model.current_profile_name or "")

    def _switch_language(self, lang: str) -> None:
        if self._do_switch_language(lang):
            self.app.clear_page_cache()
            self.app.navigate_to(PAGE_HOME)

    def _toggle_theme(self) -> None:
        new_mode = self._do_toggle_theme()
        self._theme_btn.setText(new_mode)

    def on_breakpoint_changed(self, old: Breakpoint, new: Breakpoint) -> None:
        self._rebuild_cards(self._breakpoint_cols())

    def apply_theme(self) -> None:
        super().apply_theme()
        th = current_theme()
        self._rebuild_all_sections()
        self._rebuild_cards(self._breakpoint_cols())
