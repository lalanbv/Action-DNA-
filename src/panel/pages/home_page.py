"""主页 — 功能选择"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.panel.profile_manager import ProfileManager

from src.panel.canvas.scale import Breakpoint, scale_manager
from src.panel.home_shared import (
    CHECK_EXECUTOR_MS,
    SECTION_I18N,
    SECTION_TYPES,
    PageType,
    SectionState,
    discover_features,
    HomeStateMixin,
)
from src.panel.pages.base_page import BasePage
from src.panel.pages.page_i18n import HOME_TITLE
from src.panel.pages.page_registry import PAGE_HOME, register_page
from src.panel.canvas.theme import current_theme, current_theme_mode
from src.panel.components.toolbar import ToolbarFrame
from src.panel.components.toolbar_icons import ICONS
from src.panel.widgets import (
    themed_button,
    themed_frame,
    themed_label,
    themed_labelframe,
    themed_radiobutton,
)
from src.utils.i18n import t, get_language

@register_page("home", label_i18n=HOME_TITLE, icon="🏠", category="main")
class HomePage(HomeStateMixin, BasePage):
    """功能选择主页"""

    def __init__(self, parent: tk.Widget, app, **kwargs) -> None:
        super().__init__(parent, app, **kwargs)
        self._toolbar: ToolbarFrame
        self._lang_var: tk.StringVar
        self._btn_theme: object
        self._scroll_canvas: tk.Canvas
        self._scroll_vbar: ttk.Scrollbar
        self._scroll_inner: tk.Frame
        self._scroll_win_id: int = 0
        self._banner_frame: tk.Frame
        self._section_frames: dict[PageType, tk.Frame | None] = {}
        self._last_states: dict[PageType, SectionState | None] = {}
        self._section_vars: dict[PageType, tk.StringVar] = {}
        self._section_dots: dict[PageType, tuple[tk.Canvas | None, int]] = {}
        self._dot_on: bool = True
        self._pulse_timer_id: str | None = None
        self._cards_frame: tk.Frame
        self._pm: ProfileManager | None = None
        self._launchable_cache: dict[str, tuple[str, ...]] = {pt: () for pt in SECTION_TYPES}
        self._poll_tick: int = 0
        self._profiles_dir_mtime: float = 0.0
        self._profiles_sub_mtime: float = 0.0
        self._profiles_scan_time: float = 0.0
        self._scrollbar_check_pending: bool = False
        self._section_refs: dict[PageType, dict] = {}

    def title(self) -> str:
        return t("app.title")

    def build(self):
        th = current_theme()

        # ── 统一工具栏（与 WorkflowPage/ActionChainPage 一致）──
        toolbar = ToolbarFrame(self.frame)
        toolbar.pack(fill=tk.X, padx=th.pad_xs, pady=th.pad_xs)
        self._toolbar = toolbar

        toolbar.add_section("nav")
        title_label = themed_label(toolbar, text=t("app.title"), style="section")
        toolbar.add_widget("nav", title_label)

        toolbar.add_spacer()

        # 主题/语言切换
        toolbar.add_section("settings")
        self._lang_var = tk.StringVar(value=get_language())
        for code, label in [("zh", "中文"), ("en", "EN")]:
            rb = themed_radiobutton(
                toolbar, text=label, value=code,
                variable=self._lang_var,
                command=self._switch_language,
            )
            toolbar.add_widget("settings", rb)

        _THEME_ICONS = {"dark": ICONS["theme_dark"], "light": ICONS["theme_light"], "system": ICONS["settings"]}
        theme_icon = _THEME_ICONS.get(current_theme_mode(), ICONS["settings"])
        self._btn_theme = themed_button(
            toolbar, text=theme_icon, style="secondary",
            command=self._toggle_theme,
        )
        toolbar.add_widget("settings", self._btn_theme)

        # ── 可滚动内容区域 ──
        scroll_container = themed_frame(self.frame)
        scroll_container.pack(fill=tk.BOTH, expand=True)
        scroll_container.rowconfigure(0, weight=1)
        scroll_container.columnconfigure(0, weight=1)

        self._scroll_canvas = tk.Canvas(
            scroll_container, bg=th.page_bg, highlightthickness=0,
        )
        self._scroll_canvas.grid(row=0, column=0, sticky=tk.NSEW)

        self._scroll_vbar = ttk.Scrollbar(
            scroll_container, orient=tk.VERTICAL,
            command=self._scroll_canvas.yview,
        )
        self._scroll_vbar.grid(row=0, column=1, sticky=tk.NS)

        self._scroll_canvas.configure(
            yscrollcommand=self._update_scrollbar_visibility,
        )

        self._scroll_inner = themed_frame(self._scroll_canvas)
        self._scroll_win_id = self._scroll_canvas.create_window(
            (0, 0), window=self._scroll_inner, anchor="nw",
        )

        self._scroll_inner.bind(
            "<Configure>", self._on_scroll_inner_configure,
        )
        self._scroll_canvas.bind(
            "<Configure>", self._on_scroll_canvas_configure,
        )

        # 鼠标滚轮绑定 — 绑定到整个 frame 而非仅 canvas
        self.frame.bind("<Enter>", self._bind_mousewheel)
        self.frame.bind("<Leave>", self._unbind_mousewheel)

        themed_label(
            self._scroll_inner, text=t("home.select_feature"), style="section",
            fg=th.text_muted,
        ).pack(anchor=tk.W, padx=th.pad_xl, pady=(th.pad_xs, th.pad_xs))

        # 快捷启动横幅区域（双 section）
        self._banner_frame = themed_frame(self._scroll_inner)
        self._banner_frame.pack(fill=tk.X, padx=th.pad_xl, pady=0)

        for pt in SECTION_TYPES:
            self._section_frames[pt] = None
            self._last_states[pt] = None
            self._section_vars[pt] = tk.StringVar()
            self._section_dots[pt] = (None, -1)

        # 功能卡片区域（先创建容器，内容延迟填充）
        self._cards_frame = themed_frame(self._scroll_inner)
        self._cards_frame.pack(fill=tk.BOTH, expand=True, padx=th.pad_xl, pady=th.pad_sm)

        # 延迟加载重内容（文件扫描 + widget 构建），让窗口先渲染
        self._timer.schedule_idle(self._deferred_build)

    def _deferred_build(self) -> None:
        """延迟构建：文件扫描 + 横幅 + 卡片，避免阻塞首帧渲染。"""
        if not self.frame.winfo_exists():
            return
        self.app._register_deferred_pages()  # 确保 discover_features 前页面已注册
        self._rescan_launchable_profiles()
        self._rebuild_all_sections()
        self._rebuild_cards(self._breakpoint_cols())
        self.schedule(CHECK_EXECUTOR_MS, self._check_executor_state)

    # ── 滚动区域 ──────────────────────────────────────────

    def _on_scroll_inner_configure(self, _event: tk.Event) -> None:
        self._scroll_canvas.configure(
            scrollregion=self._scroll_canvas.bbox("all"),
        )
        self._check_scrollbar_needed()

    def _update_scrollbar_visibility(self, first: str, last: str) -> None:
        self._scroll_vbar.set(first, last)
        if float(first) <= 0.0 and float(last) >= 1.0:
            self._scroll_vbar.grid_remove()
        else:
            self._scroll_vbar.grid()

    def _check_scrollbar_needed(self) -> None:
        if self._scrollbar_check_pending:
            return
        self._scrollbar_check_pending = True
        self.frame.after_idle(self._do_check_scrollbar)

    def _do_check_scrollbar(self) -> None:
        self._scrollbar_check_pending = False
        if not self._scroll_canvas.winfo_exists():
            return
        bbox = self._scroll_canvas.bbox("all")
        if bbox is None:
            return
        canvas_h = self._scroll_canvas.winfo_height()
        content_h = bbox[3] - bbox[1]
        if content_h <= canvas_h:
            self._scroll_vbar.grid_remove()
        else:
            self._scroll_vbar.grid()

    def _on_scroll_canvas_configure(self, event: tk.Event) -> None:
        self._scroll_canvas.itemconfig(self._scroll_win_id, width=event.width)

    def _bind_mousewheel(self, _event: tk.Event) -> None:
        self._scroll_canvas.bind_all("<MouseWheel>", self._on_mousewheel)
        self._scroll_canvas.bind_all("<Button-4>", self._on_mousewheel)
        self._scroll_canvas.bind_all("<Button-5>", self._on_mousewheel)

    def _unbind_mousewheel(self, _event: tk.Event) -> None:
        self._scroll_canvas.unbind_all("<MouseWheel>")
        self._scroll_canvas.unbind_all("<Button-4>")
        self._scroll_canvas.unbind_all("<Button-5>")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4:
            self._scroll_canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._scroll_canvas.yview_scroll(1, "units")
        else:
            self._scroll_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    # ── 功能卡片 ──────────────────────────────────────────

    def _create_card(self, parent: tk.Frame, feat: dict, row: int, col: int):
        th = current_theme()
        card = themed_labelframe(parent, text=t(feat["title_key"]))
        card.grid(row=row, column=col, padx=th.pad_sm, pady=th.pad_sm, sticky=tk.NSEW)

        themed_label(card, text=t(feat["desc_key"]), justify=tk.LEFT).pack(
            anchor=tk.W, padx=th.pad_md, pady=(th.pad_sm, th.pad_xs)
        )
        themed_button(
            card, text=t("home.enter"), style="primary",
            command=lambda: self.app.navigate_to(feat["page"]),
        ).pack(anchor=tk.E, padx=th.pad_md, pady=(th.pad_xs, th.pad_md))

    def _create_placeholder(self, parent: tk.Frame, row: int, col: int):
        th = current_theme()
        card = themed_labelframe(parent, text=t("home.coming_soon"))
        card.grid(row=row, column=col, padx=th.pad_sm, pady=th.pad_sm, sticky=tk.NSEW)
        themed_label(
            card, text=t("home.more_features"), style="small",
        ).pack(padx=th.pad_md, pady=th.pad_xl)

    def _rebuild_cards(self, cols: int) -> None:
        for child in self._cards_frame.winfo_children():
            child.destroy()
        features = discover_features()
        total = max(len(features), 4)
        for i, feat in enumerate(features):
            row, col = divmod(i, cols)
            self._create_card(self._cards_frame, feat, row, col)
        for i in range(len(features), total):
            row, col = divmod(i, cols)
            self._create_placeholder(self._cards_frame, row, col)
        for c in range(cols):
            self._cards_frame.columnconfigure(c, weight=1)

    def on_breakpoint_changed(self, old: Breakpoint, new: Breakpoint) -> None:
        self._rebuild_cards(self._breakpoint_cols())

    def apply_theme(self):
        super().apply_theme()
        if self._toolbar.winfo_exists():
            self._toolbar.apply_theme()
        th = current_theme()
        if self._scroll_canvas.winfo_exists():
            self._scroll_canvas.configure(bg=th.page_bg)
        if self._scroll_inner.winfo_exists():
            self._scroll_inner.configure(bg=th.page_bg)
        if self._scroll_vbar.winfo_exists():
            self._check_scrollbar_needed()
        if self._banner_frame.winfo_exists():
            self._rebuild_all_sections()

    def _switch_language(self):
        lang = self._lang_var.get()
        if self._do_switch_language(lang):
            self.app.clear_page_cache()
            self.app.navigate_to(PAGE_HOME)

    def _toggle_theme(self):
        self._do_toggle_theme()

    # ── 横幅构建 ──────────────────────────────────────────

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

        # Same mode and section exists → in-place update to avoid flicker
        if old_mode == new_mode and visible:
            frame = self._section_frames.get(page_type)
            if frame is not None and frame.winfo_exists():
                self._update_section_in_place(page_type, state, new_mode)
                return

        # Mode changed or first build → full rebuild
        self._section_refs.pop(page_type, None)

        old = self._section_frames.get(page_type)
        if old is not None and old.winfo_exists():
            old.destroy()
        self._section_frames[page_type] = None

        if not visible:
            self._update_banner_visibility()
            return

        th = current_theme()
        sm = scale_manager()

        frame = themed_frame(self._banner_frame)
        frame.pack(fill=tk.X, pady=sm.s(2))
        self._section_frames[page_type] = frame

        if state.is_running:
            self._build_section_running(frame, page_type, state, th, sm)
        else:
            self._build_section_idle(frame, page_type, state, th, sm)

        self._update_banner_visibility()

    def _update_banner_visibility(self) -> None:
        """当没有任何 section 可见时隐藏 banner 容器，避免留白。"""
        if not self._banner_frame.winfo_exists():
            return
        has_visible = any(
            f is not None and f.winfo_exists()
            for f in self._section_frames.values()
        )
        if has_visible:
            if not self._banner_frame.winfo_ismapped():
                self._banner_frame.pack(
                    fill=tk.X, padx=current_theme().pad_xl, pady=0,
                )
        elif self._banner_frame.winfo_ismapped():
            self._banner_frame.pack_forget()

    # ── Widget adapter overrides ──

    def _widget_exists(self, widget) -> bool:
        return widget is not None and widget.winfo_exists()

    def _widget_set_label_text(self, widget, text: str) -> None:
        if widget and widget.winfo_exists():
            widget.configure(text=text)

    def _widget_set_visible(self, widget, visible: bool) -> None:
        if widget is None or not widget.winfo_exists():
            return
        if visible:
            widget.pack(side=tk.LEFT, padx=(0, scale_manager().s(8)))
        else:
            widget.pack_forget()

    def _widget_set_button(
        self, btn, text: str, style: str, callback, refs: dict, conn_key: str,
    ) -> None:
        if btn and btn.winfo_exists():
            btn.configure(text=text, command=callback)
            btn.set_style(style)

    def _widget_combo_needs_update(self, combo, profiles: tuple) -> bool:
        if combo and combo.winfo_exists():
            return profiles != combo["values"]
        return False

    def _widget_set_combo_items(
        self, combo, profiles: tuple, current: str | None, page_type: PageType,
    ) -> None:
        if combo and combo.winfo_exists():
            combo["values"] = profiles
            var = self._section_vars[page_type]
            if profiles:
                if current and current in profiles:
                    var.set(current)
                else:
                    var.set(profiles[0])

    def _build_section_running(
        self, parent: tk.Frame, page_type: PageType, state: SectionState, th, sm,
    ) -> None:
        i18n = SECTION_I18N[page_type]
        bg_color = th.accent_green_dim
        inner = tk.Frame(
            parent,
            bg=bg_color,
            highlightbackground=th.status_running,
            highlightthickness=2,
            padx=sm.s(12), pady=sm.s(8),
        )
        inner.pack(fill=tk.X, ipady=sm.s(4))

        dot_canvas = tk.Canvas(
            inner, width=14, height=14,
            bg=bg_color, highlightthickness=0,
        )
        dot_canvas.pack(side=tk.LEFT, padx=(0, sm.s(8)))
        dot_oval = dot_canvas.create_oval(2, 2, 12, 12, fill=th.status_running, outline="")
        self._section_dots[page_type] = (dot_canvas, dot_oval)

        themed_label(
            inner, text=t(i18n["title"]), style="section", fg=th.status_running,
        ).pack(side=tk.LEFT, padx=(0, sm.s(4)))

        name_text = state.profile_name or t(i18n["unsaved"])
        themed_label(
            inner, text=name_text, fg=th.text_muted,
        ).pack(side=tk.LEFT, padx=(0, sm.s(8)))

        status_text = (
            t("workflow.status.paused") if state.is_paused
            else t("workflow.status.running")
        )
        status_label = themed_label(
            inner, text=status_text, style="section", fg=th.status_running,
        )
        status_label.pack(side=tk.LEFT, padx=(0, sm.s(8)))

        themed_button(
            inner, text=t("common.stop"), style="danger",
            command=self._on_section_stop,
        ).pack(side=tk.RIGHT, padx=(sm.s(4), 0))

        if state.is_paused:
            pause_btn = themed_button(
                inner, text=t("common.resume"), style="primary",
                command=self._on_section_resume,
            )
        else:
            pause_btn = themed_button(
                inner, text=t("common.pause"), style="secondary",
                command=self._on_section_pause,
            )
        pause_btn.pack(side=tk.RIGHT, padx=(sm.s(4), 0))

        themed_button(
            inner, text=t("home.banner.go_to"), style="secondary",
            command=lambda: self._on_section_go_to(page_type),
        ).pack(side=tk.RIGHT, padx=(sm.s(4), 0))

        self._dot_on = True
        if self._pulse_timer_id is not None:
            try:
                self.frame.after_cancel(self._pulse_timer_id)
            except tk.TclError:
                pass
        self._pulse_timer_id = self.schedule(600, self._pulse_dots)

        self._section_refs[page_type] = {
            "status_label": status_label,
            "pause_btn": pause_btn,
            "is_resume": state.is_paused,
            "status_text": status_text,
        }

    def _build_section_idle(
        self, parent: tk.Frame, page_type: PageType, state: SectionState, th, sm,
    ) -> None:
        i18n = SECTION_I18N[page_type]
        border_color = getattr(th, "border_color", th.text_muted)
        inner = tk.Frame(
            parent,
            bg=th.bg_surface,
            highlightbackground=border_color,
            highlightthickness=1,
            padx=sm.s(12), pady=sm.s(8),
        )
        inner.pack(fill=tk.X, ipady=sm.s(2))

        themed_label(
            inner, text=t(i18n["title"]), style="section", fg=th.text_muted,
        ).pack(side=tk.LEFT, padx=(0, sm.s(8)))

        name_label = themed_label(inner, text="")
        if state.has_content:
            name_text = state.profile_name or t(i18n["unsaved"])
            if state.is_dirty:
                name_text += " *"
            name_label.configure(text=name_text)
            name_label.pack(side=tk.LEFT, padx=(0, sm.s(8)))

        profiles = state.launchable_profiles
        var = self._section_vars[page_type]
        combo: ttk.Combobox | None = None
        if profiles:
            if state.profile_name and state.profile_name in profiles:
                var.set(state.profile_name)
            else:
                var.set(profiles[0])
            combo = ttk.Combobox(
                inner, textvariable=var,
                values=profiles, state="readonly", width=18,
            )
            combo.pack(side=tk.LEFT, padx=(0, sm.s(8)))
            combo.bind(
                "<<ComboboxSelected>>",
                lambda _e: self._on_section_profile_selected(page_type),
            )
        else:
            var.set("")
            themed_label(
                inner, text=t("home.banner.no_profile"), fg=th.text_muted,
            ).pack(side=tk.LEFT, padx=(0, sm.s(8)))

        if state.has_content or profiles:
            themed_button(
                inner, text=t("common.start"), style="primary",
                command=lambda: self._on_section_start(page_type),
            ).pack(side=tk.LEFT, padx=(0, sm.s(4)))

        if state.has_content:
            themed_button(
                inner, text=t("home.banner.clear"), style="secondary",
                command=lambda: self._on_section_clear(page_type),
            ).pack(side=tk.LEFT, padx=(0, sm.s(4)))

        self._section_refs[page_type] = {
            "name_label": name_label,
            "combo": combo,
        }

    # ── 脉冲动画 ──────────────────────────────────────────

    def _pulse_dots(self) -> None:
        executor = self.app.executor
        if not executor or not executor.is_running:
            self._pulse_timer_id = None
            return

        th = current_theme()
        self._dot_on = not self._dot_on
        color = th.status_running if self._dot_on else th.accent_green_dim

        for pt in SECTION_TYPES:
            canvas, oval = self._section_dots.get(pt, (None, -1))
            if canvas is not None and canvas.winfo_exists() and oval >= 0:
                try:
                    canvas.itemconfig(oval, fill=color)
                except tk.TclError:
                    pass

        self._pulse_timer_id = self.schedule(600, self._pulse_dots)

    # ── 操作回调 ──────────────────────────────────────────

    def _on_section_start(self, page_type: PageType) -> None:
        profile_name = self._section_vars[page_type].get()
        result = self._do_section_start(page_type, profile_name)
        if result == "not_found":
            messagebox.showerror(t("app.title"), t("profile.error.file_not_found", path=profile_name))

    def _on_section_clear(self, page_type: PageType) -> None:
        result = self._do_section_clear(page_type)
        if result == "navigate":
            self.app.navigate_to(page_type)
        elif result == "confirm_needed":
            if messagebox.askyesno(t("common.confirm"), t("chain.msg.confirm_clear")):
                self._section_vars[page_type].set("")
                self._do_clear_confirmed(page_type)

    def _on_section_go_to(self, page_type: str) -> None:
        self.app.navigate_to(page_type)

    def _on_section_profile_selected(self, page_type: PageType) -> None:
        new_name = self._section_vars[page_type].get()
        if not new_name:
            return

        model = self._get_cached_model(page_type)
        controller = self._get_cached_controller(page_type)

        if model is None or controller is None:
            return

        if model.current_profile_name == new_name:
            return

        if model.is_dirty:
            answer = messagebox.askyesnocancel(
                t("record.export.unsaved_title"),
                t("record.export.unsaved_message"),
            )
            if answer is None:
                if model.current_profile_name:
                    self._section_vars[page_type].set(model.current_profile_name)
                return
            if answer:
                controller.save_profile()

        try:
            controller.load_profile(new_name)
        except Exception:  # pylint: disable=broad-exception-caught
            messagebox.showerror(t("app.title"), t("common.load_failed"))
            self._section_vars[page_type].set(
                model.current_profile_name or ""
            )
