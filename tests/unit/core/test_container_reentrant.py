"""容器递归解析防回归测试.

根因(2026-06-18):``ServiceContainer._lock`` 曾为 ``threading.Lock``(非重入)。
当某服务的工厂回调在持锁期间再次解析同一容器的另一个服务时(典型路径:
``ActionExecutor`` 工厂访问 ``self.ring_log`` → ``ServiceProviderMixin.ring_log``
property → ``try_get(RingBufferLog)`` → ``_resolve`` 再次获取同一把锁),同线程
第二次获取非重入锁会**自死锁**,表现为 Windows exe「窗口出现即卡死、无任何日志」
——死锁发生在 ``__init__`` 之前,故 ``try/except`` 与 ``sys.excepthook`` 全部失效。

改用 ``threading.RLock``(可重入)修复之:同线程可多次获取,跨线程仍互斥,单例
双重检查锁语义不变。本测试用线程 + 超时断言「递归解析不再死锁」。
"""
from __future__ import annotations

import threading

import pytest

from src.core.container.container import ServiceContainer


# ── 测试夹具类型(置于顶部,便于注解直观) ─────────────────────────────


class _Dep:
    """依赖服务(类比 RingBufferLog)。"""

    def __init__(self, value: str) -> None:
        self.value = value


class _Main:
    """主服务(类比 ActionExecutor):构造期间递归解析 _Dep。"""

    def __init__(self, dep: _Dep) -> None:
        self.dep = dep


# ── 测试用例 ─────────────────────────────────────────────────────────


@pytest.mark.unit
def test_reentrant_resolution_does_not_deadlock() -> None:
    """工厂持锁期间递归解析另一单例,必须完成而非自死锁。

    ``Lock``(非重入)下本用例的 worker 线程会永久阻塞 → ``done.wait`` 超时 → 断言失败。
    """
    container = ServiceContainer()

    # 依赖服务(类比 RingBufferLog)
    container.register(_Dep, lambda: _Dep("dep-instance"))

    # 主服务工厂在构造期间递归解析 _Dep(类比 ActionExecutor 工厂访问 self.ring_log)
    def _make_main() -> _Main:
        dep = container.get(_Dep)  # ← 持锁期间再 resolve;Lock 下自死锁
        return _Main(dep)

    container.register(_Main, _make_main)

    result: dict[str, object] = {}
    errors: list[BaseException] = []
    done = threading.Event()

    def _worker() -> None:
        try:
            result["main"] = container.get(_Main)
        except BaseException as exc:  # noqa: BLE001 — 收集任意异常用于断言
            errors.append(exc)
        finally:
            done.set()

    thread = threading.Thread(target=_worker, daemon=True, name="reentrant-resolve")
    thread.start()

    # 2s 内必须完成;Lock(非重入)下永久阻塞,此断言失败即回归
    assert done.wait(timeout=2.0), "容器递归解析自死锁(锁非重入)— 回归!"

    assert errors == [], f"递归解析抛异常: {errors}"
    main = result["main"]
    assert isinstance(main, _Main)
    assert main.dep.value == "dep-instance"


@pytest.mark.unit
def test_singleton_still_dedup_across_resolves() -> None:
    """RLock 不破坏单例语义:多次解析同一服务只构造一次。"""
    container = ServiceContainer()
    counter = {"n": 0}

    def _factory() -> _Dep:
        counter["n"] += 1
        return _Dep("once")

    container.register(_Dep, _factory)

    first = container.get(_Dep)
    second = container.get(_Dep)
    assert first is second
    assert counter["n"] == 1


@pytest.mark.unit
def test_cross_thread_resolution_serializes() -> None:
    """RLock 跨线程仍互斥:并发解析同一未实例化单例,工厂只执行一次。"""
    container = ServiceContainer()
    counter = {"n": 0}

    def _factory() -> _Dep:
        # 小停顿放大并发竞争窗口
        threading.Event().wait(0.01)
        counter["n"] += 1
        return _Dep("shared")

    container.register(_Dep, _factory)

    results: list[object] = []
    errors: list[BaseException] = []

    def _worker() -> None:
        try:
            results.append(container.get(_Dep))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, daemon=True) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert errors == [], f"并发解析抛异常: {errors}"
    assert counter["n"] == 1, f"单例被构造多次: {counter['n']}"
    assert len(results) == 8
    assert all(r is results[0] for r in results)
