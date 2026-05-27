"""主页共享逻辑 — 供 tkinter / Qt 后端复用。

包含横幅 section 状态模型、配置文件扫描、状态收集 mixin、功能卡片发现。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from src.panel.profile_manager import ProfileManager

from src.panel.canvas.theme import current_theme_mode, set_theme_mode
from src.utils.i18n import get_language, set_language, t

CHECK_EXECUTOR_MS = 500

PageType = Literal["action_chain", "workflow_editor"]

SectionMode = Literal["running", "idle"]

THEME_CYCLE = {"dark": "light", "light": "system", "system": "dark"}

SECTION_TYPES = ("action_chain", "workflow_editor")

SECTION_I18N = {
    "action_chain": {
        "title": "home.banner.action_chain",
        "unsaved": "home.banner.unsaved_chain",
        "model_attr": "model",
        "controller_attr": "controller",
    },
    "workflow_editor": {
        "title": "home.banner.workflow",
        "unsaved": "home.banner.unsaved_workflow",
        "model_attr": "_model",
        "controller_attr": "_controller",
    },
}


@dataclass(frozen=True)
class SectionState:
    has_content: bool
    profile_name: str | None
    is_dirty: bool
    is_running: bool
    is_paused: bool
    launchable_profiles: tuple[str, ...]


def read_profile_meta(pm: ProfileManager, name: str) -> dict | None:
    config_path = os.path.join(pm.root, name, "profile.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    version = data.get("version", 1)
    if version == 1:
        has_nodes = bool(data.get("chain", {}).get("steps"))
    else:
        has_nodes = bool(data.get("flow", {}).get("nodes"))
    page_type = "action_chain" if version == 1 else "workflow_editor"
    return {"version": version, "has_nodes": has_nodes, "page_type": page_type}


_cached_features: list[dict] | None = None


def discover_features() -> list[dict]:
    """从 PageRegistry 动态发现功能卡片（排除 home 页自身）。结果缓存。"""
    global _cached_features
    if _cached_features is not None:
        return _cached_features
    from src.panel.pages.page_registry import PAGE_HOME, PageRegistry

    features = []
    for page_id, meta in PageRegistry.all().items():
        if page_id == PAGE_HOME:
            continue
        if not meta.label_i18n:
            continue
        features.append({
            "id": page_id,
            "title_key": meta.label_i18n,
            "desc_key": meta.desc_i18n or f"feature.{page_id}.desc",
            "page": page_id,
        })
    _cached_features = features
    return features


class HomeStateMixin:
    """横幅 section 状态收集 mixin — 供 HomePage / QtHomePage 复用。

    子类需设置:
        self.app          — PanelApp 实例
        self._pm          — ProfileManager | None
        self._launchable_cache — dict[str, tuple[str, ...]]
        self._last_states — dict[str, SectionState | None]
        self._poll_tick   — int
        self._profiles_dir_mtime — float
        self._profiles_sub_mtime — float
        self._profiles_scan_time — float
    """

    def _ensure_pm(self):
        from src.panel.profile_manager import ProfileManager

        if self._pm is None:
            self._pm = ProfileManager()
        return self._pm

    def _rescan_launchable_profiles(self) -> None:
        pm = self._ensure_pm()
        profiles_dir = pm.root

        now = time.monotonic()
        if now - self._profiles_scan_time < 2.0:
            return

        try:
            root_mtime = os.path.getmtime(profiles_dir)
        except OSError:
            root_mtime = 0.0

        max_sub_mtime = 0.0
        try:
            for entry in os.scandir(profiles_dir):
                if entry.is_dir(follow_symlinks=False):
                    try:
                        max_sub_mtime = max(
                            max_sub_mtime,
                            entry.stat(follow_symlinks=False).st_mtime,
                        )
                    except OSError:
                        pass
                    try:
                        pj = os.path.join(entry.path, "profile.json")
                        max_sub_mtime = max(
                            max_sub_mtime,
                            os.path.getmtime(pj),
                        )
                    except OSError:
                        pass
        except OSError:
            pass

        if (root_mtime == self._profiles_dir_mtime
                and max_sub_mtime == self._profiles_sub_mtime
                and now - self._profiles_scan_time < 30.0):
            return

        self._profiles_dir_mtime = root_mtime
        self._profiles_sub_mtime = max_sub_mtime
        self._profiles_scan_time = now

        all_profiles = pm.list_profiles()

        profile_by_type: dict[str, list[str]] = {pt: [] for pt in SECTION_TYPES}
        for name in all_profiles:
            meta = read_profile_meta(pm, name)
            if meta is not None and meta["has_nodes"]:
                profile_by_type[meta["page_type"]].append(name)

        self._launchable_cache = {
            pt: tuple(v) for pt, v in profile_by_type.items()
        }

    def _get_cached_attr(self, page_type: PageType, attr_key: str):
        page = self.app.get_cached_page(page_type)
        if page is None:
            return None
        attr_name = SECTION_I18N[page_type][attr_key]
        return getattr(page, attr_name, None)

    def _get_cached_model(self, page_type: PageType):
        return self._get_cached_attr(page_type, "model_attr")

    def _get_cached_controller(self, page_type: PageType):
        return self._get_cached_attr(page_type, "controller_attr")

    def _build_section_state(
        self, page_type: PageType, launchable_profiles: tuple[str, ...],
    ) -> SectionState:
        model = self._get_cached_model(page_type)
        has_content = model is not None and bool(model.graph.action_nodes())
        profile_name = model.current_profile_name if model else None
        is_dirty = model.is_dirty if model else False

        executor = self.app.executor
        source_page = self.app.get_executor_source()
        is_running = (
            executor is not None
            and executor.is_running
            and source_page == page_type
        )
        is_paused = is_running and executor is not None and executor.is_paused

        return SectionState(
            has_content=has_content,
            profile_name=profile_name,
            is_dirty=is_dirty,
            is_running=is_running,
            is_paused=is_paused,
            launchable_profiles=launchable_profiles,
        )

    def _gather_all_states(self, only: PageType | None = None) -> dict[str, SectionState]:
        if only is not None:
            return {
                only: self._build_section_state(
                    only, self._launchable_cache.get(only, ()),
                )
            }
        return {
            pt: self._build_section_state(pt, self._launchable_cache.get(pt, ()))
            for pt in SECTION_TYPES
        }

    def _rebuild_all_sections(self, only: PageType | None = None) -> None:
        for pt, state in self._gather_all_states(only).items():
            self._rebuild_section(pt, state)
            self._last_states[pt] = state

    def _check_executor_state(self) -> None:
        self._poll_tick += 1
        if self._poll_tick >= 10:
            self._poll_tick = 0
            self._rescan_launchable_profiles()

        for pt, new_state in self._gather_all_states().items():
            old_state = self._last_states.get(pt)
            if old_state != new_state:
                self._rebuild_section(pt, new_state)
                self._last_states[pt] = new_state
        self.schedule(CHECK_EXECUTOR_MS, self._check_executor_state)

    # ── 原地更新（共享决策逻辑，后端实现 widget adapter）──

    def _update_section_in_place(
        self, page_type: PageType, state: SectionState, mode: SectionMode,
    ) -> None:
        if mode == "running":
            self._update_running_section(page_type, state)
        else:
            self._update_idle_section(page_type, state)

    def _update_running_section(
        self, page_type: PageType, state: SectionState,
    ) -> None:
        refs = self._section_refs.get(page_type)
        if not refs:
            return

        status_text = (
            t("workflow.status.paused") if state.is_paused
            else t("workflow.status.running")
        )
        if refs.get("status_text") != status_text:
            status_label = refs.get("status_label")
            if status_label is not None:
                self._widget_set_label_text(status_label, status_text)
            refs["status_text"] = status_text

        pause_btn = refs.get("pause_btn")
        if pause_btn is not None:
            is_resume = refs.get("is_resume", False)
            if is_resume != state.is_paused:
                is_paused = state.is_paused
                self._widget_set_button(
                    pause_btn,
                    t("common.resume") if is_paused else t("common.pause"),
                    "primary" if is_paused else "secondary",
                    self._on_section_resume if is_paused else self._on_section_pause,
                    refs, "pause_conn",
                )
                refs["is_resume"] = is_paused

    def _update_idle_section(
        self, page_type: PageType, state: SectionState,
    ) -> None:
        refs = self._section_refs.get(page_type)
        if not refs:
            return

        i18n = SECTION_I18N[page_type]

        name_label = refs.get("name_label")
        if name_label is not None:
            if state.has_content:
                name_text = state.profile_name or t(i18n["unsaved"])
                if state.is_dirty:
                    name_text += " *"
                self._widget_set_label_text(name_label, name_text)
                self._widget_set_visible(name_label, True)
            else:
                self._widget_set_visible(name_label, False)

        combo = refs.get("combo")
        if combo is not None:
            if self._widget_combo_needs_update(combo, state.launchable_profiles):
                self._widget_set_combo_items(
                    combo, state.launchable_profiles,
                    state.profile_name, page_type,
                )

    # ── Widget adapter methods（后端覆写）──

    def _widget_exists(self, widget) -> bool:
        raise NotImplementedError

    def _widget_set_label_text(self, widget, text: str) -> None:
        raise NotImplementedError

    def _widget_set_visible(self, widget, visible: bool) -> None:
        raise NotImplementedError

    def _widget_set_button(
        self, btn, text: str, style: str, callback, refs: dict, conn_key: str,
    ) -> None:
        raise NotImplementedError

    def _widget_combo_needs_update(self, combo, profiles: tuple) -> bool:
        raise NotImplementedError

    def _widget_set_combo_items(
        self, combo, profiles: tuple, current: str | None, page_type: PageType,
    ) -> None:
        raise NotImplementedError

    # ── 共享回调逻辑（后端调用 _do_*，自行处理 UI 差异）──

    def _on_section_pause(self) -> None:
        executor = self.app.executor
        if executor and executor.is_running:
            executor.pause()

    def _on_section_resume(self) -> None:
        executor = self.app.executor
        if executor and executor.is_paused:
            executor.resume()

    def _on_section_stop(self) -> None:
        executor = self.app.executor
        if executor and executor.is_running:
            executor.stop()

    # ── _do_* 辅助（返回状态码，后端据此决定 UI 行为）──

    def _do_section_start(self, page_type: PageType, profile_name: str) -> str | None:
        """启动 section 执行器。返回 None 或 'not_found'（后端显示错误）。"""
        if not profile_name:
            model = self._get_cached_model(page_type)
            if model and model.graph.action_nodes():
                self.app.set_executor_source(page_type)
                self.app.executor.start(model.graph)
            return None

        pm = self._ensure_pm()
        if not pm.exists(profile_name):
            return "not_found"

        graph = pm.load(profile_name)
        if not graph.nodes:
            return None

        self.app.set_executor_source(page_type)
        self.app.executor.start(graph)
        return None

    def _do_section_clear(self, page_type: PageType) -> str | None:
        """返回 'navigate' / 'confirm_needed' / None。"""
        executor = self.app.executor
        if executor and executor.is_running:
            return None

        model = self._get_cached_model(page_type)
        if model is None:
            return "navigate"

        return "confirm_needed"

    def _do_clear_confirmed(self, page_type: PageType) -> None:
        model = self._get_cached_model(page_type)
        if model:
            model.reset()
        self._rebuild_all_sections(only=page_type)

    def _do_toggle_theme(self) -> str:
        from src.core.config import load_config, save_config

        new_mode = THEME_CYCLE.get(current_theme_mode(), "system")
        cfg = load_config()
        cfg.editor.theme_mode = new_mode
        save_config(cfg)
        set_theme_mode(new_mode)
        return new_mode

    def _do_switch_language(self, lang: str) -> bool:
        if lang == get_language():
            return False
        from src.core.config import load_config, save_config

        set_language(lang)
        cfg = load_config()
        cfg.language.language = lang
        save_config(cfg)
        return True

    def _breakpoint_cols(self) -> int:
        from src.panel.canvas.scale import Breakpoint, scale_manager

        bp = scale_manager().breakpoint()
        if bp == Breakpoint.COMPACT:
            return 1
        elif bp == Breakpoint.WIDE:
            return 3
        return 2
