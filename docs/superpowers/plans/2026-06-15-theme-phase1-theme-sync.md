# Phase 1：主题同步基础设施 + B5 核心修复 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立框架无关的主题同步基础设施（`refresh_theme` + `SystemThemeSync`），消除两后端重复的系统主题轮询逻辑（D1），并修复"跟随系统"模式的根本性失效（B5）与主线程阻塞（B1），为 Qt 实时通知（B3）铺路。

**Architecture:** MVC + 单一真相源。`canvas/theme/theme_manager.py` 新增 `refresh_theme()`（强制重建+通知，绕过 skip 逻辑）与 `restore_from_config()`（D2 去重）。新增 `canvas/theme/theme_sync.py`：`SystemThemeSync` 在 worker 线程探测 OS 主题，变更时 marshal 回主线程调 `refresh_theme`；通过 `ThemeSyncBackend` Protocol 注入各后端的「定时器/marshal」原语。两 app 各自的 `TkThemeSyncBackend`/`QtThemeSyncBackend` 替换内联轮询。

**Tech Stack:** Python 3.11+、pytest、PySide6（可选，运行时探测）、threading（worker 线程）、tkinter QTimer/root.after（主线程 marshal）。

**关联规格：** [docs/superpowers/specs/2026-06-15-theme-dedup-unify-design.md](../specs/2026-06-15-theme-dedup-unify-design.md) §4、§6.1–6.2。

**范围说明：** 本计划仅覆盖 Phase 1 的核心（D1/D2/B1/B5 + Qt B3 实时）。D3/D4/D5 其余去重、Phase 2 UI 统一、B4 注册审计作为后续独立计划。

---

## File Structure

| 文件 | 职责 | 动作 |
|------|------|------|
| `src/panel/canvas/theme/theme_manager.py` | 主题模式/缓存/回调；新增 `refresh_theme()` + `restore_from_config()` | 修改 |
| `src/panel/canvas/theme/theme_sync.py` | `SystemThemeSync` + `ThemeSyncBackend` Protocol（worker 线程探测 + marshal） | 新建 |
| `src/panel/canvas/theme/__init__.py` | 导出 `refresh_theme`、`restore_from_config`、`SystemThemeSync`、`ThemeSyncBackend` | 修改 |
| `src/panel/qt_backend/theme_sync_backend.py` | Qt 后端原语：marshal（`QTimer.singleShot`）+ 实时 `colorSchemeChanged` | 新建 |
| `src/panel/app.py` | 删除内联 `_start/_stop_system_theme_poller`，改用 `SystemThemeSync` + tk 原语 | 修改 |
| `src/panel/qt_backend/app.py` | 删除内联 `_start_system_theme_poller`/`_poll_system_theme`，改用 `QtThemeSyncBackend` | 修改 |
| `tests/unit/panel/test_theme_manager_refresh.py` | `refresh_theme` / `restore_from_config` 单测 | 新建 |
| `tests/unit/panel/test_theme_sync.py` | `SystemThemeSync` 单测（worker/marshal/start/stop） | 新建 |
| `tests/regression/test_theme_system_follow.py` | B5 回归：system 模式 OS 切换 → 主题重建 | 新建 |

**测试可无头运行**：共享逻辑通过 Protocol 注入后端，不依赖 display（`src/panel/*` 虽被 coverage omit，但测试照常执行；后续计划可细化 omit 让共享逻辑纳入覆盖率）。

---

## Task 1: `refresh_theme()` — B5 核心修复

**Files:**
- Modify: `src/panel/canvas/theme/theme_manager.py`（在 `set_theme_mode` 之后新增函数）
- Test: `tests/unit/panel/test_theme_manager_refresh.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/panel/test_theme_manager_refresh.py`：

```python
"""theme_manager.refresh_theme / restore_from_config 单元测试。

验证 B5 修复：system 模式下强制重建主题并通知订阅，绕过 set_theme_mode 的 skip 逻辑。
"""

from __future__ import annotations

import pytest

from src.panel.canvas.theme import theme_manager
from src.panel.canvas.theme.theme_manager import refresh_theme


@pytest.fixture(autouse=True)
def _reset_theme_state():
    """每个测试前后清理 theme_manager 模块全局状态。"""
    saved_mode = theme_manager._theme_mode
    saved_theme = theme_manager._current_theme
    saved_cbs = dict(theme_manager._theme_callbacks)
    theme_manager._current_theme = None
    yield
    theme_manager._theme_mode = saved_mode
    theme_manager._current_theme = saved_theme
    theme_manager._theme_callbacks.clear()
    theme_manager._theme_callbacks.update(saved_cbs)


def test_refresh_theme_rebuilds_cache(monkeypatch):
    """refresh_theme 清除缓存并重建（即使 _theme_mode 未变）。"""
    rebuilt = {"sentinel": "dark_v2"}
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: rebuilt)

    theme_manager._theme_mode = "system"
    theme_manager._current_theme = {"sentinel": "old"}  # 旧缓存

    refresh_theme()

    assert theme_manager._current_theme is rebuilt


def test_refresh_theme_notifies_subscribers(monkeypatch):
    """refresh_theme 触发所有已注册回调。"""
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: object())
    theme_manager._theme_mode = "system"

    notified = []
    cb_id = theme_manager.on_theme_change(lambda: notified.append("called"))

    refresh_theme()

    assert notified == ["called"]
    theme_manager.remove_theme_change(cb_id)


def test_refresh_theme_skips_dead_callbacks(monkeypatch):
    """回调抛异常时被静默移除，不影响其他回调。"""
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: object())
    theme_manager._theme_mode = "system"

    good = []
    theme_manager.on_theme_change(lambda: (_ for _ in ()).throw(RuntimeError("dead")))
    theme_manager.on_theme_change(lambda: good.append("alive"))

    refresh_theme()

    assert good == ["alive"]
    # 抛异常的回调应被移除
    assert all(
        not (cb.__qualname__ == "<lambda>")
        for cb in theme_manager._theme_callbacks.values()
    ) or len(theme_manager._theme_callbacks) <= 1


def test_refresh_theme_does_not_change_mode(monkeypatch):
    """refresh_theme 不改变 _theme_mode（system 仍是 system）。"""
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: object())
    theme_manager._theme_mode = "system"

    refresh_theme()

    assert theme_manager._theme_mode == "system"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `pytest tests/unit/panel/test_theme_manager_refresh.py -v`
Expected: FAIL — `ImportError: cannot import name 'refresh_theme'`

- [ ] **Step 3: 实现 `refresh_theme()`**

在 `src/panel/canvas/theme/theme_manager.py` 的 `set_theme_mode` 函数之后新增：

```python
def refresh_theme() -> None:
    """强制重建当前主题并通知所有订阅。

    用于 system 模式下 OS 实际主题发生变化：不改变 ``_theme_mode``，
    仅清除缓存、重建主题、触发全部回调，从而绕过 :func:`set_theme_mode`
    在"模式未变"时的 skip 逻辑（B5 修复）。

    必须在 UI 主线程调用（由 :class:`theme_sync.SystemThemeSync` 通过
    ``ThemeSyncBackend.marshal_main`` 保证）。
    """
    global _current_theme
    _current_theme = None
    current_theme()  # 重建缓存

    dead_ids: list[int] = []
    # 快照遍历 —— 回调可能在迭代中调用 remove_theme_change。
    for cb_id, cb in list(_theme_callbacks.items()):
        try:
            cb()
        except Exception:
            dead_ids.append(cb_id)
    for cb_id in dead_ids:
        _theme_callbacks.pop(cb_id, None)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `pytest tests/unit/panel/test_theme_manager_refresh.py -v`
Expected: PASS（4 个测试）

- [ ] **Step 5: 提交**

```bash
git add src/panel/canvas/theme/theme_manager.py tests/unit/panel/test_theme_manager_refresh.py
git commit -m "fix(theme): add refresh_theme to fix follow-system OS switch (B5)"
```

---

## Task 2: `restore_from_config()` — D2 去重

**Files:**
- Modify: `src/panel/canvas/theme/theme_manager.py`（新增 `restore_from_config`）
- Modify: `tests/unit/panel/test_theme_manager_refresh.py`（追加测试）

- [ ] **Step 1: 追加失败测试**

在 `tests/unit/panel/test_theme_manager_refresh.py` 末尾追加：

```python
from src.panel.canvas.theme.theme_manager import restore_from_config


class _FakeEditor:
    def __init__(self, mode: str) -> None:
        self.theme_mode = mode


class _FakeConfig:
    def __init__(self, mode: str) -> None:
        self.editor = _FakeEditor(mode)


def test_restore_from_config_valid_mode(monkeypatch):
    """合法 theme_mode 被恢复。"""
    called = {}
    monkeypatch.setattr(theme_manager, "set_theme_mode", lambda m: called.__setitem__("mode", m))

    restore_from_config(_FakeConfig("dark"))

    assert called == {"mode": "dark"}


def test_restore_from_config_invalid_mode_falls_back(monkeypatch):
    """非法 theme_mode 回退到 system。"""
    called = {}
    monkeypatch.setattr(theme_manager, "set_theme_mode", lambda m: called.__setitem__("mode", m))

    restore_from_config(_FakeConfig("hot-pink"))

    assert called == {"mode": "system"}


def test_restore_from_config_accepts_system(monkeypatch):
    called = {}
    monkeypatch.setattr(theme_manager, "set_theme_mode", lambda m: called.__setitem__("mode", m))

    restore_from_config(_FakeConfig("system"))

    assert called == {"mode": "system"}
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/unit/panel/test_theme_manager_refresh.py -v -k restore`
Expected: FAIL — `ImportError: cannot import name 'restore_from_config'`

- [ ] **Step 3: 实现 `restore_from_config()`**

在 `theme_manager.py` 的 `refresh_theme` 之后新增：

```python
def restore_from_config(cfg) -> None:
    """从持久化配置恢复主题模式（D2 去重，供两后端共用）。

    读取 ``cfg.editor.theme_mode``，合法值（dark/light/system）恢复，
    非法或缺省回退到 ``system``。

    Args:
        cfg: 配置对象，需有 ``editor.theme_mode`` 属性。
    """
    mode = getattr(getattr(cfg, "editor", None), "theme_mode", None)
    if mode in _VALID_THEME_MODES:
        set_theme_mode(mode)
    else:
        set_theme_mode("system")
```

- [ ] **Step 4: 运行确认通过**

Run: `pytest tests/unit/panel/test_theme_manager_refresh.py -v`
Expected: PASS（全部）

- [ ] **Step 5: 提交**

```bash
git add src/panel/canvas/theme/theme_manager.py tests/unit/panel/test_theme_manager_refresh.py
git commit -m "refactor(theme): extract restore_from_config for D2 dedup"
```

---

## Task 3: `SystemThemeSync` + `ThemeSyncBackend` Protocol — D1 + B1

**Files:**
- Create: `src/panel/canvas/theme/theme_sync.py`
- Modify: `src/panel/canvas/theme/__init__.py`（导出新符号）
- Test: `tests/unit/panel/test_theme_sync.py`

- [ ] **Step 1: 写失败测试**

创建 `tests/unit/panel/test_theme_sync.py`：

```python
"""SystemThemeSync 单元测试 — worker 线程探测 + 主线程 marshal 编排。

验证 D1（去重）+ B1（探测不阻塞主线程，结果 marshal 回主线程）+ B5（变更调 refresh_theme）。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.panel.canvas.theme import theme_sync
from src.panel.canvas.theme.theme_sync import SystemThemeSync


class FakeBackend:
    """记录 marshal / timer 调用的假后端。"""

    def __init__(self) -> None:
        self.marshaled: list = []
        self.timers: list = []
        self.stopped: list = []

    def marshal_main(self, fn):
        self.marshaled.append(fn)

    def start_timer(self, interval_ms, fn):
        handle = ("timer", len(self.timers))
        self.timers.append((interval_ms, fn))
        return handle

    def stop_timer(self, handle):
        self.stopped.append(handle)


@pytest.fixture
def sync():
    return SystemThemeSync()


def test_start_schedules_poll_timer(sync):
    backend = FakeBackend()
    sync.start(backend)
    assert len(backend.timers) == 1
    assert backend.timers[0][0] == SystemThemeSync.POLL_INTERVAL_MS


def test_stop_cancels_timer(sync):
    backend = FakeBackend()
    sync.start(backend)
    sync.stop()
    assert backend.stopped  # 至少停止了一个 timer handle


def test_poll_detects_change_and_marshals_refresh(sync, monkeypatch):
    """OS resolved 变化时，探测结果 marshal 回主线程调 refresh_theme。"""
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    backend = FakeBackend()
    sync.start(backend)
    sync._last_resolved = "dark"  # 模拟先前 OS 是 dark

    sync._poll()

    assert len(backend.marshaled) == 1
    assert backend.marshaled[0].__name__ == "refresh_theme"


def test_poll_no_change_does_not_marshal(sync, monkeypatch):
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "dark")
    backend = FakeBackend()
    sync.start(backend)
    sync._last_resolved = "dark"

    sync._poll()

    assert backend.marshaled == []


def test_poll_records_new_resolved(sync, monkeypatch):
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    backend = FakeBackend()
    sync.start(backend)
    sync._last_resolved = "dark"

    sync._poll()

    assert sync._last_resolved == "light"


def test_poll_swallows_detection_errors(sync, monkeypatch):
    """detect_system_theme 抛异常时不崩溃、不 marshal。"""
    def boom():
        raise OSError("subprocess failed")
    monkeypatch.setattr(theme_sync, "detect_system_theme", boom)
    backend = FakeBackend()
    sync.start(backend)

    sync._poll()  # 不应抛异常

    assert backend.marshaled == []
```

- [ ] **Step 2: 运行确认失败**

Run: `pytest tests/unit/panel/test_theme_sync.py -v`
Expected: FAIL — `ImportError: cannot import name 'theme_sync'`（或 `SystemThemeSync`）

- [ ] **Step 3: 实现 `theme_sync.py`**

创建 `src/panel/canvas/theme/theme_sync.py`：

```python
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
```

- [ ] **Step 4: 导出新符号**

修改 `src/panel/canvas/theme/__init__.py`，在现有导出之后追加（保留原有导出不变）：

```python
from src.panel.canvas.theme.theme_manager import (
    current_theme,
    current_theme_mode,
    resolved_theme_mode,
    set_theme_mode,
    refresh_theme,
    restore_from_config,
    on_theme_change,
    remove_theme_change,
    ThemeCallbackMixin,
    theme_registry,
)
from src.panel.canvas.theme.theme_sync import SystemThemeSync, ThemeSyncBackend
```

> 注：先读取该 `__init__.py` 的实际现有内容，**只追加缺失的导出**（`refresh_theme`、`restore_from_config`、`SystemThemeSync`、`ThemeSyncBackend`），勿删除已有导出。若已用 `from … import *` 形式，则改写为显式列表。

- [ ] **Step 5: 运行确认通过**

Run: `pytest tests/unit/panel/test_theme_sync.py -v`
Expected: PASS（6 个测试）

- [ ] **Step 6: 提交**

```bash
git add src/panel/canvas/theme/theme_sync.py src/panel/canvas/theme/__init__.py tests/unit/panel/test_theme_sync.py
git commit -m "feat(theme): add SystemThemeSync orchestrator (D1 dedup + B1 off-thread)"
```

---

## Task 4: 接入 tkinter 后端 — 替换内联轮询（D1）

**Files:**
- Modify: `src/panel/app.py`（删除 `_start/_stop_system_theme_poller`，改用 `SystemThemeSync` + tk 原语）
- Test: 手动验证（tk 后端依赖 display，集成测试在 Task 6 覆盖）

- [ ] **Step 1: 读取现有 app.py 主题相关代码**

Run: `grep -n "_sys_poll_id\|_last_resolved\|_start_system_theme_poller\|_stop_system_theme_poller\|set_theme_mode(\"system\")\|resolved_theme_mode" src/panel/app.py`
确认所有待替换位置（预期：初始化 ~100-101、`_on_theme_changed` ~343、轮询器 345-357、清理 565-566/597-598）。

- [ ] **Step 2: 替换主题初始化段（~50-57 行）**

将：
```python
        mode = self._cfg.editor.theme_mode
        if mode in ("dark", "light", "system"):
            set_theme_mode(mode)
        else:
            set_theme_mode("system")
```
改为：
```python
        # 主题 — 从持久化配置恢复模式（D2：委托共享 helper）
        from src.panel.canvas.theme import restore_from_config
        restore_from_config(self._cfg)
```

- [ ] **Step 3: 替换轮询器启动（~100-101 行 + 345-357 行）**

将初始化段：
```python
        self._sys_poll_id: str | None = None
        self._last_resolved: str = resolved_theme_mode()
        self._start_system_theme_poller()
```
改为：
```python
        # 系统主题同步（D1：委托共享 SystemThemeSync，注入 tk 原语）
        from src.panel.canvas.theme import SystemThemeSync
        self._theme_sync = SystemThemeSync()
        self._theme_sync.start(_TkThemeSyncBackend(self))
```

删除整个 `_start_system_theme_poller` 与 `_stop_system_theme_poller` 方法（345-357 行），并在其原位置新增 tk 原语后端类（模块级，类外）：

```python
class _TkThemeSyncBackend:
    """tkinter 主题同步原语 — marshal 用 root.after(0)，定时器用 TkTimerScheduler。

    实现 theme_sync.ThemeSyncBackend Protocol。
    """

    def __init__(self, app: "PanelApp") -> None:
        self._app = app

    def marshal_main(self, fn: Callable[[], None]) -> None:
        """回 UI 主线程：root.after(0) 在 widget 仍存活时调度。"""
        try:
            if self._app.root.winfo_exists():
                self._app.root.after(0, fn)
        except tk.TclError:
            pass

    def start_timer(self, interval_ms: int, fn: Callable[[], None]) -> str:
        return self._app._timer.schedule(interval_ms, fn)

    def stop_timer(self, handle: object) -> None:
        self._app._timer.cancel(handle)
```

> 注：`Callable` 需在 app.py 顶部 `from typing import Callable`（若未导入则补）。`_TkThemeSyncBackend` 引用 `PanelApp`，用字符串前向引用或置于类定义之后。

- [ ] **Step 4: 从 `_on_theme_changed` 删除 `_last_resolved` 赋值（~343 行）**

`_last_resolved` 现由 `SystemThemeSync` 内部维护，删除该行：
```python
        self._last_resolved = resolved_theme_mode()
```
（`resolved_theme_mode` 若此后无其他引用，可从 import 移除；先 grep 确认。）

- [ ] **Step 5: 替换清理调用（~565-566、597-598 行）**

将：
```python
        self._unregister_theme_callback()
        self._stop_system_theme_poller()
```
改为：
```python
        self._unregister_theme_callback()
        self._theme_sync.stop()
```
（两处 cleanup 均改。）

- [ ] **Step 6: 冒烟测试 — 导入与实例化（不依赖 display 则跳过）**

Run: `python -c "import src.panel.app; print('import OK')"`
Expected: 输出 `import OK`（无语法/import 错误）。

- [ ] **Step 7: 提交**

```bash
git add src/panel/app.py
git commit -m "refactor(tk): replace inline system-theme poller with SystemThemeSync (D1)"
```

---

## Task 5: 接入 Qt 后端 + 实时 `colorSchemeChanged`（D1 + B3）

**Files:**
- Create: `src/panel/qt_backend/theme_sync_backend.py`
- Modify: `src/panel/qt_backend/app.py`（删除内联轮询，改用 `QtThemeSyncBackend`）
- Test: `tests/unit/panel/qt/test_theme_sync_backend.py`

- [ ] **Step 1: 写失败测试（offscreen 模式）**

创建 `tests/unit/panel/qt/test_theme_sync_backend.py`：

```python
"""QtThemeSyncBackend 单元测试（offscreen）。

验证 D1（去重）+ B3（Qt 6.5+ 实时 colorSchemeChanged → refresh_theme）。
需环境变量 QT_QPA_PLATFORM=offscreen。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication  # noqa: E402

from src.panel.qt_backend.theme_sync_backend import QtThemeSyncBackend  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication([])


def test_marshal_main_schedules_on_main_thread(qt_app):
    """marshal_main 用 QTimer.singleShot(0) 调度到主线程。"""
    backend = QtThemeSyncBackend(qt_app)
    called = []
    backend.marshal_main(lambda: called.append(True))
    # 处理一次事件循环以执行 singleShot 回调
    qt_app.processEvents()
    assert called == [True]


def test_has_color_scheme_signal_detection(qt_app):
    """探测 Qt 版本是否支持 colorSchemeChanged（6.5+）。"""
    backend = QtThemeSyncBackend(qt_app)
    # 不断言具体 True/False（取决于运行时 Qt 版本），只断言属性存在且为 bool
    assert isinstance(backend.has_color_scheme_signal, bool)


def test_refresh_on_color_scheme_changed_calls_refresh(qt_app, monkeypatch):
    """colorSchemeChanged 信号触发时调用 refresh_theme（B3）。"""
    backend = QtThemeSyncBackend(qt_app)
    if not backend.has_color_scheme_signal:
        pytest.skip("Qt < 6.5 无 colorSchemeChanged 信号")

    from src.panel.canvas.theme import theme_manager
    called = {}
    monkeypatch.setattr(theme_manager, "refresh_theme", lambda: called.__setitem__("x", True))

    backend._on_color_scheme_changed()

    assert called == {"x": True}
```

- [ ] **Step 2: 运行确认失败**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/panel/qt/test_theme_sync_backend.py -v`
Expected: FAIL — `ImportError: cannot import name 'QtThemeSyncBackend'`

- [ ] **Step 3: 实现 `QtThemeSyncBackend`**

创建 `src/panel/qt_backend/theme_sync_backend.py`：

```python
"""Qt 主题同步后端 — 提供 marshal 原语 + 实时 colorSchemeChanged（B3）。

实现 theme_sync.ThemeSyncBackend Protocol，并额外在 Qt 6.5+ 连接
``QGuiApplication.styleHints().colorSchemeChanged`` 实现 OS 主题实时响应；
低版本降级为 SystemThemeSync 的 worker 线程轮询。
"""

from __future__ import annotations

import logging
from typing import Callable

from src.panel.canvas.theme.theme_manager import refresh_theme

logger = logging.getLogger(__name__)


class QtThemeSyncBackend:
    """Qt 后端主题同步原语 + 实时信号。

    实现 :class:`theme_sync.ThemeSyncBackend` Protocol。
    """

    def __init__(self, app) -> None:
        self._app = app
        self._has_signal = _detect_color_scheme_signal(app)
        self._signal_connected = False

    @property
    def has_color_scheme_signal(self) -> bool:
        """是否支持 Qt 6.5+ colorSchemeChanged（运行时探测）。"""
        return self._has_signal

    def marshal_main(self, fn: Callable[[], None]) -> None:
        """回 UI 主线程：QTimer.singleShot(0)。"""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, fn)

    def start_timer(self, interval_ms: int, fn: Callable[[], None]) -> object:
        from PySide6.QtCore import QTimer
        timer = QTimer(self._app)
        timer.setInterval(interval_ms)
        timer.timeout.connect(fn)
        timer.start()
        return timer

    def stop_timer(self, handle: object) -> None:
        try:
            handle.stop()
        except Exception:
            logger.debug("Failed to stop Qt theme timer", exc_info=True)

    def connect_real_time(self) -> None:
        """连接 colorSchemeChanged 实时信号（B3）。仅在 has_color_scheme_signal 时有效。"""
        if not self._has_signal or self._signal_connected:
            return
        try:
            from PySide6.QtGui import QGuiApplication
            QGuiApplication.styleHints().colorSchemeChanged.connect(
                self._on_color_scheme_changed
            )
            self._signal_connected = True
        except Exception:
            logger.debug("colorSchemeChanged connect failed", exc_info=True)

    def _on_color_scheme_changed(self) -> None:
        """OS 主题变化实时回调（已在主线程，直接刷新）。"""
        refresh_theme()


def _detect_color_scheme_signal(app) -> bool:
    """探测 Qt 是否支持 styleHints().colorSchemeChanged（Qt 6.5+）。"""
    try:
        from PySide6.QtGui import QGuiApplication
        sh = QGuiApplication.styleHints()
        return hasattr(sh, "colorScheme") and hasattr(sh, "colorSchemeChanged")
    except Exception:
        return False
```

- [ ] **Step 4: 运行确认通过**

Run: `QT_QPA_PLATFORM=offscreen pytest tests/unit/panel/qt/test_theme_sync_backend.py -v`
Expected: PASS（3 个测试，colorSchemeChanged 测试在 Qt<6.5 时 skip）

- [ ] **Step 5: 接入 Qt app — 替换初始化（~115-119 行）**

将：
```python
        mode = self._cfg.editor.theme_mode
        if mode in ("dark", "light", "system"):
            set_theme_mode(mode)
        else:
            set_theme_mode("system")
```
改为：
```python
        # 主题 — 从持久化配置恢复（D2：委托共享 helper）
        from src.panel.canvas.theme import restore_from_config
        restore_from_config(self._cfg)
```

- [ ] **Step 6: 接入 Qt app — 替换轮询器（~137、155-156、300-311 行）**

将初始化段：
```python
        self._sys_theme_timer: QTimer | None = None
```
改为：
```python
        self._theme_sync_backend: "QtThemeSyncBackend" | None = None
        self._theme_sync: "SystemThemeSync" | None = None
```

将：
```python
        self._last_resolved: str = resolved_theme_mode()
        self._start_system_theme_poller()
```
改为：
```python
        # 系统主题同步（D1 + B3：委托共享 SystemThemeSync + Qt 实时信号）
        from src.panel.canvas.theme import SystemThemeSync
        from src.panel.qt_backend.theme_sync_backend import QtThemeSyncBackend
        self._theme_sync_backend = QtThemeSyncBackend(self)
        self._theme_sync = SystemThemeSync()
        self._theme_sync.start(self._theme_sync_backend)
        self._theme_sync_backend.connect_real_time()
```

删除整个 `_start_system_theme_poller` 与 `_poll_system_theme` 方法（300-311 行）。

从 `_on_theme_changed`（~281 行）删除：
```python
        self._last_resolved = resolved_theme_mode()
```
（grep 确认 `resolved_theme_mode` 是否还有其他引用；若无则从 import 移除。）

- [ ] **Step 7: 冒烟测试**

Run: `QT_QPA_PLATFORM=offscreen python -c "import src.panel.qt_backend.app; print('import OK')"`
Expected: `import OK`

- [ ] **Step 8: 提交**

```bash
git add src/panel/qt_backend/theme_sync_backend.py src/panel/qt_backend/app.py tests/unit/panel/qt/test_theme_sync_backend.py
git commit -m "refactor(qt): replace inline poller with QtThemeSyncBackend + realtime colorSchemeChanged (D1/B3)"
```

---

## Task 6: B5 回归测试 + 全量验证

**Files:**
- Test: `tests/regression/test_theme_system_follow.py`

- [ ] **Step 1: 写 B5 回归测试**

创建 `tests/regression/test_theme_system_follow.py`：

```python
"""B5 回归测试 — system 模式下 OS 深浅色切换后主题必须重建。

复现链（修复前）：OS dark→light → 轮询检测到 → set_theme_mode("system")
命中 skip 逻辑 → 不重建 → 界面卡旧主题。

修复后：SystemThemeSync._poll 检测到变化 → marshal refresh_theme → 重建 + 通知。
"""

from __future__ import annotations

import pytest

from src.panel.canvas.theme import theme_manager, theme_sync
from src.panel.canvas.theme.theme_manager import current_theme, set_theme_mode
from src.panel.canvas.theme.theme_sync import SystemThemeSync


class _RecordingBackend:
    def __init__(self) -> None:
        self.marshaled = []
        self._timer_fn = None

    def marshal_main(self, fn):
        # 模拟主线程立即执行（测试中同步）
        self.marshaled.append(fn)
        fn()

    def start_timer(self, interval_ms, fn):
        self._timer_fn = fn
        return "handle"

    def stop_timer(self, handle):
        pass


@pytest.fixture(autouse=True)
def _reset():
    saved_mode = theme_manager._theme_mode
    saved_theme = theme_manager._current_theme
    saved_cbs = dict(theme_manager._theme_callbacks)
    theme_manager._theme_mode = "system"
    theme_manager._current_theme = None
    yield
    theme_manager._theme_mode = saved_mode
    theme_manager._current_theme = saved_theme
    theme_manager._theme_callbacks.clear()
    theme_manager._theme_callbacks.update(saved_cbs)


def test_system_mode_os_switch_rebuilds_theme(monkeypatch):
    """OS dark→light：refresh_theme 被调用，current_theme() 反映新主题。"""
    # 用可辨识的假主题区分 dark/light
    dark_theme = object()
    light_theme = object()

    def fake_build():
        return light_theme if theme_sync.detect_system_theme() == "light" else dark_theme
    monkeypatch.setattr(theme_manager, "_build_theme", fake_build)

    # 初始 OS = dark
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "dark")
    set_theme_mode("system")
    assert current_theme() is dark_theme

    # 注册一个订阅，验证它会收到通知
    notified = []
    theme_manager.on_theme_change(lambda: notified.append(True))

    # 启动同步，初始 resolved = dark
    sync = SystemThemeSync()
    backend = _RecordingBackend()
    sync.start(backend)
    assert sync._last_resolved == "dark"

    # OS 切到 light，worker 线程探测
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    sync._poll()

    # B5 修复断言：主题已重建为新主题，订阅已通知
    assert current_theme() is light_theme
    assert notified == [True]
    assert sync._last_resolved == "light"

    sync.stop()


def test_explicit_dark_mode_ignores_os_change(monkeypatch):
    """显式 dark 模式：OS 变化不触发刷新（用户已固定模式）。"""
    fixed = object()
    monkeypatch.setattr(theme_manager, "_build_theme", lambda: fixed)
    theme_manager._theme_mode = "dark"
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "dark")
    set_theme_mode("dark")
    assert current_theme() is fixed

    sync = SystemThemeSync()
    backend = _RecordingBackend()
    sync.start(backend)

    # OS 切 light，但因模式非 system，_poll 不应 marshal
    monkeypatch.setattr(theme_sync, "detect_system_theme", lambda: "light")
    sync._poll()

    assert backend.marshaled == []
    assert current_theme() is fixed  # 仍是原主题
    sync.stop()
```

- [ ] **Step 2: 运行回归测试**

Run: `pytest tests/regression/test_theme_system_follow.py -v`
Expected: PASS（2 个测试）

- [ ] **Step 3: 运行全量主题相关测试**

Run: `pytest tests/unit/panel/test_theme_manager_refresh.py tests/unit/panel/test_theme_sync.py tests/unit/panel/qt/test_theme_sync_backend.py tests/regression/test_theme_system_follow.py -v`
Expected: 全部 PASS

- [ ] **Step 4: 运行全量测试套件（确认无回归）**

Run: `pytest tests/ -q --timeout=60 -x`
Expected: 全绿（无新增失败）

- [ ] **Step 5: 提交**

```bash
git add tests/regression/test_theme_system_follow.py
git commit -m "test(theme): add B5 regression for follow-system OS switch"
```

---

## Phase 1 完成验收（对照规格 §4.4 + §6.5）

- [ ] `refresh_theme()` 实现 + 单测（B5）
- [ ] `restore_from_config()` 实现 + 单测（D2）
- [ ] `SystemThemeSync` + `ThemeSyncBackend` 实现 + 单测（D1 + B1）
- [ ] tkinter app 接入，内联轮询删除（D1）
- [ ] Qt app 接入 + 实时 colorSchemeChanged（D1 + B3）
- [ ] B5 回归测试通过
- [ ] 全量测试套件无回归
- [ ] 两后端可启动（`import` 冒烟通过）

**未覆盖（后续独立计划）：** D3 page_i18n 迁移、D4 registries 下沉、D5 controllers 下沉、Phase 2 组件契约、B4 注册审计。

---

## Self-Review（计划 vs 规格）

**1. 规格覆盖**：
- §4.2 `theme_sync.py` → Task 3 ✅
- §4.3 D1 → Task 4/5 ✅；D2 → Task 2 ✅；D3/D4/D5 → 明确标注为后续计划 ✅（范围声明）
- §6.1 B5 `refresh_theme` → Task 1 ✅
- §6.2 B1（worker 线程）→ Task 3 `_safe_detect` + executor ✅；B3（colorSchemeChanged）→ Task 5 ✅；B2（粒度）→ Qt 实时解决，tk 维持 30s 但不卡顿 ✅
- §6.4 持久化 → Task 2 `restore_from_config` 覆盖恢复路径 ✅

**2. 占位符扫描**：无 TBD/TODO；所有代码步骤含完整代码；测试步骤含可运行测试。✅

**3. 类型/命名一致性**：`refresh_theme`、`restore_from_config`、`SystemThemeSync`、`ThemeSyncBackend`、`_last_resolved`、`POLL_INTERVAL_MS`、`marshal_main`、`start_timer`/`stop_timer`、`has_color_scheme_signal`、`connect_real_time`、`_on_color_scheme_changed` 跨任务命名一致。✅
