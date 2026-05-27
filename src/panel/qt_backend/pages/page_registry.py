"""Qt 页面注册 — re-export from shared PageRegistry."""

from src.panel.pages.page_registry import PageMeta, PageRegistry, STATE_I18N, register_page

__all__ = ["PageMeta", "PageRegistry", "STATE_I18N", "register_page"]
