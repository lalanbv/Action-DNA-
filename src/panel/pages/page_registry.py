"""PageRegistry — 页面自注册系统。

受 Blender SpaceType 注册启发：每个页面通过装饰器声明自己的 ID 和元数据，
PanelApp 从 registry 动态发现可用页面，无需手动维护映射表。

用法::

    # 在页面模块中（如 home_page.py）:
    from src.panel.pages.page_i18n import HOME_TITLE

    @register_page("home", label_i18n=HOME_TITLE, icon="🏠")
    class HomePage(BasePage):
        ...

    # 在 PanelApp 中:
    from src.panel.pages.page_registry import PageRegistry
    for page_id, meta in PageRegistry.all().items():
        ...
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from src.utils.i18n import schedule_validation, t

if TYPE_CHECKING:
    from src.panel.pages.base_page import BasePage

from src.panel.models.chain_model import ExecutorState

logger = logging.getLogger(__name__)

# Page ID constants — use these instead of raw strings for navigate_to()
PAGE_HOME = "home"
PAGE_ACTION_CHAIN = "action_chain"
PAGE_WORKFLOW_EDITOR = "workflow_editor"
PAGE_RECORD = "record"
PAGE_NOTIFICATION = "notification"
PAGE_SCHEDULE = "schedule"
PAGE_SETTINGS = "settings"
PAGE_PLUGIN = "plugin"

# ExecutorState → i18n key mapping (shared by both backends)
STATE_I18N: dict[int, str] = {
    ExecutorState.IDLE: "workflow.status.ready",
    ExecutorState.RUNNING: "workflow.status.running",
    ExecutorState.PAUSED: "workflow.status.paused",
}


@dataclass(frozen=True)
class PageMeta:
    """页面注册元数据。"""

    page_id: str
    module_path: str
    class_name: str
    label_i18n: str = ""
    desc_i18n: str = ""
    icon: str = ""
    category: str = ""


_PAGES: dict[str, PageMeta] = {}


class PageRegistry:
    """页面注册表 — 单例，全局共享。"""

    @classmethod
    def register(
        cls,
        page_id: str,
        *,
        label_i18n: str = "",
        desc_i18n: str = "",
        icon: str = "",
        category: str = "",
    ) -> Callable[[type], type]:
        """装饰器：注册页面类。

        Args:
            page_id: 唯一页面标识符。
            label_i18n: i18n 键名（用于显示标题）。
            desc_i18n: i18n 键名（用于功能卡片描述）。
            icon: 图标字符。
            category: 分类（如 "main"、"settings"）。
        """
        def decorator(page_class: type) -> type:
            module = page_class.__module__
            qualified = f"{page_id} ({module}:{page_class.__qualname__})"
            if label_i18n:
                schedule_validation(label_i18n, qualified)
            if desc_i18n:
                schedule_validation(desc_i18n, qualified)
            _PAGES[page_id] = PageMeta(
                page_id=page_id,
                module_path=module,
                class_name=page_class.__qualname__,
                label_i18n=label_i18n,
                desc_i18n=desc_i18n,
                icon=icon,
                category=category,
            )
            logger.debug("注册页面: %s → %s:%s", page_id, module, page_class.__qualname__)
            return page_class
        return decorator

    @classmethod
    def get(cls, page_id: str) -> PageMeta | None:
        return _PAGES.get(page_id)

    @classmethod
    def all(cls) -> dict[str, PageMeta]:
        return dict(_PAGES)

    @classmethod
    def resolve(cls, page_id: str) -> type:
        """解析 page_id 为实际的页面类（lazy import）。"""
        meta = _PAGES.get(page_id)
        if meta is None:
            raise ValueError(t("app.error.unknown_page", page_id=page_id))
        module = importlib.import_module(meta.module_path)
        return getattr(module, meta.class_name)

    @classmethod
    def clear(cls) -> None:
        _PAGES.clear()


register_page = PageRegistry.register

# Deferred page modules for parallel preloading — shared by both tkinter and Qt backends
DEFERRED_PAGE_MODULES: tuple[str, ...] = (
    "src.panel.pages.action_chain_page",
    "src.panel.pages.workflow_page",
    "src.panel.pages.record_page",
    "src.panel.pages.notification_page",
    "src.panel.pages.schedule_page",
    "src.panel.pages.settings_page",
    "src.panel.pages.plugin_page",
)
