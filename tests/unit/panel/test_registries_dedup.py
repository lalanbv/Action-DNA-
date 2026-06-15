"""D3/D4 去重验证测试 — 锁定框架无关 i18n 键 / 注册元数据的单源不变量。

对照规格 docs/superpowers/specs/2026-06-15-theme-dedup-unify-design.md §4.3 / §4.4：
- D3: page_i18n 仅一份定义，Qt 侧不重复（已满足，本测试锁定防回归）。
- D4 page_registry: Qt 侧为薄 re-export shim，与 tk 共享同一 PageRegistry。
- D4 dialog_registry: Qt 双后端分发器正确委托 tk 单后端注册表（去重机制）。
"""

from __future__ import annotations

import importlib.util

from src.core.action import ActionType

# ---------------------------------------------------------------------------
# D3 — page_i18n 单一真相源
# ---------------------------------------------------------------------------

# 期望存在的全部 i18n 键（与 src/panel/pages/page_i18n.py 一一对应）
EXPECTED_PAGE_I18N: dict[str, str] = {
    "HOME_TITLE": "app.title",
    "ACTION_CHAIN_TITLE": "chain.title",
    "ACTION_CHAIN_DESC": "feature.action_chain.desc",
    "WORKFLOW_EDITOR_TITLE": "workflow.title",
    "WORKFLOW_EDITOR_DESC": "feature.workflow_editor.desc",
    "PLUGIN_TITLE": "plugin.title",
    "PLUGIN_DESC": "feature.plugin_management.desc",
    "RECORD_TITLE": "record.title",
    "RECORD_DESC": "feature.macro_record.desc",
    "NOTIFICATION_TITLE": "notification.title",
    "NOTIFICATION_DESC": "feature.notification.desc",
    "SCHEDULE_TITLE": "schedule.title",
    "SCHEDULE_DESC": "feature.schedule.desc",
    "SETTINGS_TITLE": "settings.title",
    "SETTINGS_DESC": "feature.settings.desc",
}


def test_page_i18n_defines_all_expected_keys():
    """page_i18n 定义了全部预期键（拼写 / 遗漏在测试期即被捕获）。"""
    from src.panel.pages import page_i18n

    for attr, expected in EXPECTED_PAGE_I18N.items():
        assert getattr(page_i18n, attr) == expected, f"page_i18n.{attr} 不符"


def test_page_i18n_no_qt_duplicate_module():
    """Qt 侧不存在独立的 page_i18n 模块（D3 单一真相源）。"""
    spec = importlib.util.find_spec("src.panel.qt_backend.pages.page_i18n")
    assert spec is None, "Qt 侧不应有独立 page_i18n（违反 D3 单一真相源）"


# ---------------------------------------------------------------------------
# D4 page_registry — Qt 薄 re-export shim 共享同一类
# ---------------------------------------------------------------------------


def test_qt_page_registry_is_reexport_of_tk():
    """Qt page_registry 与 tk 是同一类 / 函数 / 常量对象（re-export，非重定义）。"""
    from src.panel.pages.page_registry import (
        PageMeta as TkPageMeta,
        PageRegistry as TkPageRegistry,
        STATE_I18N as TkStateI18n,
        register_page as TkRegisterPage,
    )
    from src.panel.qt_backend.pages.page_registry import (
        PageMeta as QtPageMeta,
        PageRegistry as QtPageRegistry,
        STATE_I18N as QtStateI18n,
        register_page as QtRegisterPage,
    )

    assert QtPageRegistry is TkPageRegistry
    assert QtRegisterPage is TkRegisterPage
    assert QtPageMeta is TkPageMeta
    assert QtStateI18n is TkStateI18n


def test_page_registry_register_get_all_clear():
    """PageRegistry CRUD 正确（此前无专门测试覆盖）。"""
    from src.panel.pages.page_registry import PageMeta, PageRegistry

    PageRegistry.clear()
    try:

        @PageRegistry.register(
            "dedup_probe",
            label_i18n="probe.title",
            desc_i18n="probe.desc",
            icon="🔍",
            category="test",
        )
        class _ProbePage:
            pass

        meta = PageRegistry.get("dedup_probe")
        assert isinstance(meta, PageMeta)
        assert meta.page_id == "dedup_probe"
        assert meta.label_i18n == "probe.title"
        assert meta.desc_i18n == "probe.desc"
        assert meta.icon == "🔍"
        assert meta.category == "test"
        assert meta.class_name.endswith("_ProbePage")

        assert "dedup_probe" in PageRegistry.all()
        assert PageRegistry.get("nonexistent") is None
    finally:
        PageRegistry.clear()


def test_page_registry_all_returns_defensive_copy():
    """all() 返回副本，外部篡改不影响内部注册表。"""
    from src.panel.pages.page_registry import PageRegistry

    PageRegistry.clear()
    try:
        snapshot = PageRegistry.all()
        snapshot["injected"] = "tampered"
        assert "injected" not in PageRegistry.all()
    finally:
        PageRegistry.clear()


# ---------------------------------------------------------------------------
# D4 dialog_registry — Qt 分发器委托 tk 注册表（去重机制）
# ---------------------------------------------------------------------------


def test_qt_dialog_registry_plugin_override_wins():
    """插件注册的对话框优先级最高，覆盖内置映射。"""
    from src.panel.qt_backend.dialogs import dialog_registry as qt_dr

    qt_dr.QtDialogRegistry._plugin_overrides.clear()
    try:

        class _PluginDialog:
            pass

        qt_dr.QtDialogRegistry.register_plugin(ActionType.WAIT, _PluginDialog)
        assert qt_dr.QtDialogRegistry.get(ActionType.WAIT) is _PluginDialog
        assert qt_dr.QtDialogRegistry.has(ActionType.WAIT)
    finally:
        qt_dr.QtDialogRegistry._plugin_overrides.clear()


def test_qt_dialog_registry_delegates_to_tk_when_not_qt(monkeypatch):
    """非 Qt 后端时，QtDialogRegistry 委托 tk DialogRegistry（D4 去重机制）。"""
    from src.panel.qt_backend.dialogs import dialog_registry as qt_dr

    class _FakeTkRegistry:
        def __init__(self) -> None:
            self.store: dict[ActionType, object] = {}

        def get(self, action_type: ActionType) -> object | None:
            return self.store.get(action_type)

        def all_registered(self) -> dict[ActionType, object]:
            return dict(self.store)

    fake_tk = _FakeTkRegistry()
    sentinel = object()
    fake_tk.store[ActionType.WAIT] = sentinel

    monkeypatch.setattr(qt_dr, "use_qt_backend", lambda: False)
    monkeypatch.setattr(qt_dr, "_get_tk_registry", lambda: fake_tk)
    qt_dr.QtDialogRegistry._plugin_overrides.clear()
    try:
        assert qt_dr.QtDialogRegistry.get(ActionType.WAIT) is sentinel
    finally:
        qt_dr.QtDialogRegistry._plugin_overrides.clear()


def test_tk_dialog_registry_basic_crud():
    """tk DialogRegistry CRUD 正确（单后端存储基线）。"""
    from src.panel.dialogs.dialog_registry import DialogRegistry

    class _FakeDialog:
        pass

    DialogRegistry._registry.clear()
    try:
        DialogRegistry.register(ActionType.WAIT, _FakeDialog)
        assert DialogRegistry.has(ActionType.WAIT)
        assert DialogRegistry.get(ActionType.WAIT) is _FakeDialog
        assert ActionType.WAIT in DialogRegistry.all_registered()
        DialogRegistry.unregister(ActionType.WAIT)
        assert not DialogRegistry.has(ActionType.WAIT)
    finally:
        DialogRegistry._registry.clear()
