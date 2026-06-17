"""PanelApp 关闭路径健壮性回归测试。

针对 Windows PyInstaller windowed 打包（console=False）下的级联崩溃：

    _on_close → root.destroy() 抛 TclError "can't delete Tcl command"
      → Tk 默认 report_callback_exception 向无效 sys.stderr 写 → OSError [Errno 22]
      → mainloop 抛 OSError → main() 的 input() → EOFError（无控制台）

本测试验证三道防线中的两道（关闭路径 + 回调异常报告），第三道（input()）
在 main.py，属集成层，由人工/打包验证。
"""

import tkinter as tk

from src.panel.app import PanelApp, _log_tk_callback_exception


class _FakeRoot:
    """最小 tk root 桩：记录 quit/destroy 调用次数，destroy 可配置抛 TclError。

    用于在「不创建真实 tk.Tk()」的前提下驱动 _on_close —— 避开 macOS
    cocoa/Tcl-Tk9 多 Tk root 硬崩溃，保证测试跨平台稳定。
    """

    def __init__(self, *, destroy_raises: bool = False) -> None:
        self.quit_calls = 0
        self.destroy_calls = 0
        self._destroy_raises = destroy_raises

    def quit(self) -> None:
        self.quit_calls += 1

    def destroy(self) -> None:
        self.destroy_calls += 1
        if self._destroy_raises:
            raise tk.TclError("can't delete Tcl command")


class _Noop:
    """服务桩：提供 _on_close 调用的 stop/shutdown/close/cancel 等 no-op 方法。"""

    def stop(self) -> None: ...  # noqa: D401
    def shutdown(self) -> None: ...  # noqa: D401
    def cancel(self, _token) -> None: ...  # noqa: D401


class _EmptyContainer:
    """空服务容器桩：try_get 恒返回 None。

    PanelApp 的 executor/hotkey_manager/plugin_loader/capture/matcher 均为
    只读 property（经 self._container.try_get(...) 取值），无法直接赋值；
    注入空容器即可令它们全部返回 None，跳过 _on_close 的服务清理分支。
    """

    def try_get(self, _svc_type):  # noqa: D401
        return None

    def get(self, _svc_type):  # noqa: D401
        return None


def _make_app(*, destroy_raises: bool = False) -> PanelApp:
    """绕过重型 __init__，仅装配 _on_close 依赖的属性。

    PanelApp.__init__ 会创建真实 tk.Tk() + 导航首页 + 初始化服务，对单元测试
    过重且受平台 Tcl/Tk 限制；_on_close 只依赖一组属性/方法，用桩注入即可隔离。
    """
    app = PanelApp.__new__(PanelApp)
    app._closing = False
    app.root = _FakeRoot(destroy_raises=destroy_raises)
    # 空容器：executor/hotkey_manager/plugin_loader/capture/matcher 均返回 None
    app._container = _EmptyContainer()
    app._current_page = None
    app._theme_sync = _Noop()
    app._timer = _Noop()  # 供真实的 _stop_gc_collect 调用 cancel
    app._gc_collect_id = None
    # 其余 mixin 方法隔离为 no-op，避免触碰未装配的定时器/主题状态
    app._unregister_theme_callback = lambda: None  # type: ignore[assignment]
    app._stop_monitor_poll = lambda: None  # type: ignore[assignment]
    app.clear_page_cache = lambda: None  # type: ignore[assignment]
    return app


def test_on_close_swallows_destroy_tclerror():
    """root.destroy() 抛 TclError 时，_on_close 不得向 mainloop 传播异常。"""
    app = _make_app(destroy_raises=True)
    # 不应抛出 —— 否则会触发 report_callback_exception → OSError 级联
    app._on_close()
    assert app.root.destroy_calls == 1


def test_on_close_quits_then_destroys():
    """正常关闭：先 quit() 退出 mainloop，再 destroy()，且各调用一次。"""
    app = _make_app(destroy_raises=False)
    app._on_close()
    assert app.root.quit_calls == 1
    assert app.root.destroy_calls == 1


def test_on_close_idempotent():
    """重入保护：重复触发 _on_close（如 WM_DELETE_WINDOW 多次）只销毁一次。"""
    app = _make_app(destroy_raises=False)
    app._on_close()
    app._on_close()  # 第二次应被 _closing 标志短路
    app._on_close()  # 第三次同理
    assert app.root.destroy_calls == 1


def test_log_tk_callback_exception_does_not_raise(caplog):
    """安全回调报告：记录异常不抛出，且写入日志（而非触碰可能无效的 sys.stderr）。"""
    exc_val = ValueError("boom")
    # 直接构造 (type, value, tb) 三元组，不依赖 try/except 绑定（避免静态分析告警）
    _log_tk_callback_exception(ValueError, exc_val, None)

    records = [r for r in caplog.records if "Tk 回调" in r.getMessage()]
    assert records, "回调异常应通过 logger 记录（落盘到 assets/logs）"


def test_log_tk_callback_exception_survives_broken_logger(monkeypatch):
    """即便 logger.error 自身失败，安全回调也绝不抛出（回调报告路径不能再成为崩溃源）。"""
    import src.panel.app as app_module

    def _boom(*_a, **_k):
        raise OSError("simulated broken stream")

    monkeypatch.setattr(app_module.logger, "error", _boom)
    # 不应抛出
    _log_tk_callback_exception(ValueError, ValueError("x"), None)
