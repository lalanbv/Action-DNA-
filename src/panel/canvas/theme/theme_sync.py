"""系统主题同步编排 — 框架无关，两后端提供定时器/marshal 原语接入。

探测在 worker 线程执行（``detect_system_theme`` 的 subprocess 不阻塞 UI 主线程 → B1）。
检测到 OS resolved 主题变化时，通过 :meth:`ThemeSyncBackend.marshal_main`
将 :func:`theme_manager.refresh_theme` 调度回 UI 主线程执行（B5 修复）。
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Protocol, runtime_checkable

from src.panel.canvas.theme.platform_theme import detect_system_theme
from src.panel.canvas.theme.theme_manager import current_theme_mode, refresh_theme

logger = logging.getLogger(__name__)


@runtime_checkable
class ThemeSyncBackend(Protocol):
    """各后端实现并注入的主题同步原语。"""

    def marshal_main(self, fn: Callable[[], None]) -> None:
        """将回调调度到 UI 主线程执行（tkinter/Qt 均非线程安全）。"""

    def start_timer(self, interval_ms: int, fn: Callable[[], None]) -> object:
        """启动周期定时器，返回句柄（供 stop_timer 使用）。"""

    def stop_timer(self, handle: object) -> None:
        """停止定时器。"""


class SystemThemeSync:
    """系统主题同步编排器。

    只在主题模式为 ``"system"`` 时触发刷新；``dark``/``light`` 模式下探测到
    变化也不动作（用户已显式选择固定模式）。
    """

    POLL_INTERVAL_MS: int = 30000  # tk 降级轮询间隔；Qt 6.5+ 走实时信号，此值仅兜底

    def __init__(self) -> None:
        self._backend: ThemeSyncBackend | None = None
        self._executor: ThreadPoolExecutor = ThreadPoolExecutor(max_workers=1)
        self._timer_handle: object | None = None
        self._last_resolved: str = ""

    def start(self, backend: ThemeSyncBackend) -> None:
        """注入后端并启动周期探测。"""
        self._backend = backend
        self._last_resolved = _safe_detect()
        self._timer_handle = backend.start_timer(self.POLL_INTERVAL_MS, self._schedule_poll)

    def stop(self) -> None:
        """停止周期探测（不关闭 executor，留待进程退出）。"""
        if self._backend is not None and self._timer_handle is not None:
            self._backend.stop_timer(self._timer_handle)
            self._timer_handle = None

    def _schedule_poll(self) -> None:
        """由后端定时器在主线程触发；把探测丢到 worker 线程。"""
        self._executor.submit(self._poll)

    def _poll(self) -> None:
        """worker 线程：探测 OS 主题，变化时 marshal 回主线程刷新。

        仅当当前模式为 system 时生效。
        """
        if current_theme_mode() != "system":
            return
        resolved = _safe_detect()
        if resolved == self._last_resolved:
            return
        self._last_resolved = resolved
        if self._backend is not None:
            self._backend.marshal_main(refresh_theme)


def _safe_detect() -> str:
    """探测 OS 主题，异常时返回空串（视为未知，不触发刷新）。"""
    try:
        return detect_system_theme()
    except Exception:
        logger.debug("System theme detection failed", exc_info=True)
        return ""
