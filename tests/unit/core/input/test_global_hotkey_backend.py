"""PynputBackend 异步 listener 启动的回归测试。

背景:Windows 打包 exe 下,pynput 的 ``GlobalHotKeys.start()`` 在主线程
同步等待 listener 线程安装 ``WH_KEYBOARD_LL`` 全局键盘钩子。一旦
``SetWindowsHookEx`` 挂起(打包 exe / 特定桌面会话 / 安全软件介入),
``start()`` 阻塞主线程 → Qt 事件循环冻结 → 「窗口出现但卡死,无日志」。
由于是阻塞而非异常,``sys.excepthook`` / ``try-except`` 全都抓不住。

契约:
1. ``_restart_listener`` 必须把 listener 启动移到后台线程,调用线程绝不等待
   ``start()`` 返回(主线程不阻塞)。
2. listener 仍须被真正创建启动(不能退化成「丢弃启动」,热键功能须保留)。
3. 并发 restart 必须串行化,不得同时存在两个活 listener(``_exec_lock`` 保证)
   —— 否则两个全局钩子共存,重叠热键会被双触发。
"""

from __future__ import annotations

import sys
import threading
import time
import types

import pytest


@pytest.fixture
def fake_pynput(monkeypatch):
    """注入 fake ``pynput.keyboard``,其 ``listener.start()`` 阻塞。

    模拟 Windows 下 ``SetWindowsHookEx`` 安装钩子挂起 —— ``start()`` 在
    ``block`` 被 set 前永不返回。同时追踪创建数与存活峰值,供不同测试断言。

    Yields:
        (block, created, state)
        - block: 控制 start 何时返回(teardown 时 set 以释放线程)
        - created: 所有创建的 listener 实例(验证后台创建)
        - state: ``{"active": 当前活数, "max_active": 峰值活数}``(验证不双开)
    """
    block = threading.Event()
    created: list = []
    state = {"active": 0, "max_active": 0}
    state_lock = threading.Lock()

    class _Listener:
        """fake pynput listener:start() 阻塞直到 block 被 set。"""

        def __init__(self, bindings):
            self.bindings = bindings
            created.append(self)

        def start(self):
            with state_lock:
                state["active"] += 1
                state["max_active"] = max(state["max_active"], state["active"])
            block.wait(timeout=30)  # 模拟 SetWindowsHookEx 挂起

        def stop(self):
            with state_lock:
                state["active"] = max(0, state["active"] - 1)
            block.set()

        def is_alive(self):
            return False

    # 同时注入 pynput 包与 pynput.keyboard 子模块,使
    # ``from pynput.keyboard import GlobalHotKeys`` 命中 fake
    fake_pkg = types.ModuleType("pynput")
    fake_kb = types.ModuleType("pynput.keyboard")
    fake_kb.GlobalHotKeys = _Listener
    fake_pkg.keyboard = fake_kb

    monkeypatch.setitem(sys.modules, "pynput", fake_pkg)
    monkeypatch.setitem(sys.modules, "pynput.keyboard", fake_kb)

    yield block, created, state

    # teardown:释放任何仍在 wait 的 start,避免 daemon 线程泄漏
    block.set()


@pytest.mark.unit
def test_restart_listener_does_not_block_when_start_hangs(fake_pynput):
    """``_restart_listener`` 绝不能阻塞调用线程 —— 即使 pynput ``start()`` 挂起。

    回归守护:同步实现下 ``register`` 会卡 30s(fake start hang);
    异步化后调用线程应即时返回。
    """
    from src.core.input.global_hotkey_backend import PynputBackend

    _block, _created, _state = fake_pynput
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
def test_listener_eventually_started_in_background(fake_pynput):
    """异步化后 listener 仍须在后台被真正创建并 start(非「丢弃启动」)。

    防止退化成「异步派发但什么都不做」—— 必须保证热键功能完整保留:
    后台线程在调用线程返回后,仍然实例化 GlobalHotKeys 并调用 start()。
    """
    from src.core.input.global_hotkey_backend import PynputBackend

    _block, created, _state = fake_pynput
    backend = PynputBackend()
    backend.register("ctrl", lambda: None)

    # 后台线程有调度延迟;2s 内应完成 GlobalHotKeys 实例化
    # (此时 start() 仍在 block 上阻塞,但 __init__ 已 append 到 created)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not created:
        time.sleep(0.01)

    assert len(created) == 1, f"应在后台创建 1 个 listener,实际 {len(created)}"
    assert "<ctrl>" in created[0].bindings, "listener 绑定应包含注册的 hotkey"


@pytest.mark.unit
def test_no_concurrent_active_listeners_on_rapid_restart(fake_pynput):
    """并发 restart 不得同时存在两个活 listener(restart 流程必须串行化)。

    回归守护:每请求一线程模型下,两次 register 会并发 start 两个 listener
    (max_active=2,双全局钩子 → 热键双触发);``_exec_lock`` 串行化后应同时
    只有一个(max_active=1)。
    """
    from src.core.input.global_hotkey_backend import PynputBackend

    _block, _created, state = fake_pynput
    backend = PynputBackend()
    # 快速连续 register 触发并发 restart 请求
    backend.register("ctrl", lambda: None)
    backend.register("shift", lambda: None)

    # 等待后台线程进入 start(最多 2s)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and state["max_active"] == 0:
        time.sleep(0.01)

    # 前置:确认至少一个 listener 启动 —— 否则测试无效(后台未触发会假阳性通过)
    assert state["max_active"] >= 1, (
        "后台 listener 未在 2s 内启动,测试未真正触发并发 restart —— 无法验证串行化"
    )
    # 断言:同时最多一个活 listener(_exec_lock 串行化保证)
    assert state["max_active"] <= 1, (
        f"检测到并发双 listener(max_active={state['max_active']})"
        "—— restart 流程必须串行化,同时只允许一个 listener 存活"
    )
