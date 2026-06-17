"""PynputBackend 异步 listener 启动的回归测试。

背景:Windows 打包 exe 下,pynput 的 ``GlobalHotKeys.start()`` 在主线程
同步等待 listener 线程安装 ``WH_KEYBOARD_LL`` 全局键盘钩子。一旦
``SetWindowsHookEx`` 挂起(打包 exe / 特定桌面会话 / 安全软件介入),
``start()`` 阻塞主线程 → Qt 事件循环冻结 → 「窗口出现但卡死,无日志」。
由于是阻塞而非异常,``sys.excepthook`` / ``try-except`` 全都抓不住。

契约:``_restart_listener`` 必须把 listener 启动移到后台线程,
调用线程绝不等待 ``start()`` 返回;同时 listener 仍须被真正创建启动
(热键功能完整保留,不能退化成「丢弃启动」)。
"""

from __future__ import annotations

import sys
import threading
import time
import types

import pytest


@pytest.fixture
def fake_pynput_blocking(monkeypatch):
    """注入 fake ``pynput.keyboard``,其 ``GlobalHotKeys.start()`` 阻塞。

    模拟 Windows 下 ``SetWindowsHookEx`` 安装钩子挂起 —— ``start()`` 在
    ``block`` 被 set 前永不返回。

    Yields:
        (listener_class, block_event, created_list)
        - listener_class: fake GlobalHotKeys 类
        - block_event: 控制 start 何时返回(teardown 时 set 以释放线程)
        - created_list: 记录所有创建的 listener 实例(验证后台副作用)
    """
    block = threading.Event()
    created: list = []

    class _BlockingListener:
        """fake pynput listener:start() 阻塞直到 block 被 set。"""

        def __init__(self, bindings):
            self.bindings = bindings
            created.append(self)

        def start(self):
            block.wait(timeout=30)  # 模拟 SetWindowsHookEx 挂起

        def stop(self):
            block.set()

        def is_alive(self):
            return False

    # 同时注入 pynput 包与 pynput.keyboard 子模块,使
    # ``from pynput.keyboard import GlobalHotKeys`` 命中 fake
    fake_pkg = types.ModuleType("pynput")
    fake_kb = types.ModuleType("pynput.keyboard")
    fake_kb.GlobalHotKeys = _BlockingListener
    fake_pkg.keyboard = fake_kb

    monkeypatch.setitem(sys.modules, "pynput", fake_pkg)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_kb)

    yield _BlockingListener, block, created

    # teardown:释放任何仍在 wait 的 start,避免 daemon 线程泄漏
    block.set()


@pytest.mark.unit
def test_restart_listener_does_not_block_when_start_hangs(fake_pynput_blocking):
    """``_restart_listener`` 绝不能阻塞调用线程 —— 即使 pynput ``start()`` 挂起。

    回归守护:同步实现下 ``register`` 会卡 30s(fake start hang);
    异步化后调用线程应即时返回。
    """
    from src.core.input.global_hotkey_backend import PynputBackend

    _listener_cls, _block, _created = fake_pynput_blocking
    backend = PynputBackend()
    assert backend.is_available(), "fake pynput 应使 backend 可用"

    done = threading.Event()

    def _register() -> None:
        backend.register("ctrl", lambda: None)
        done.set()

    worker = threading.Thread(target=_register, daemon=True)
    worker.start()

    # 调用线程必须在 2s 内返回;fake start 会 hang 30s,
    # 同步实现下 done 永不在此窗口内 set → 断言失败(RED)。
    assert done.wait(timeout=2.0), (
        "_restart_listener 阻塞了调用线程(等待 pynput start 返回)"
        "—— listener 启动必须异步化"
    )


@pytest.mark.unit
def test_listener_eventually_started_in_background(fake_pynput_blocking):
    """异步化后 listener 仍须在后台被真正创建并 start(非「丢弃启动」)。

    防止退化成「异步派发但什么都不做」—— 必须保证热键功能完整保留:
    后台线程在调用线程返回后,仍然实例化 GlobalHotKeys 并调用 start()。
    """
    from src.core.input.global_hotkey_backend import PynputBackend

    _listener_cls, _block, created = fake_pynput_blocking
    backend = PynputBackend()
    backend.register("ctrl", lambda: None)

    # 后台线程有调度延迟;2s 内应完成 GlobalHotKeys 实例化
    # (此时 start() 仍在 block 上阻塞,但 __init__ 已 append 到 created)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not created:
        time.sleep(0.01)

    assert len(created) == 1, f"应在后台创建 1 个 listener,实际 {len(created)}"
    assert "<ctrl>" in created[0].bindings, "listener 绑定应包含注册的 hotkey"
