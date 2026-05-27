"""PauseLayer 单元测试。

验证暂停/恢复/停止行为：
- 非暂停状态直接通过
- 暂停状态阻塞直到恢复
- 暂停状态阻塞直到停止
- 优先响应停止信号
"""

from __future__ import annotations

import threading
from unittest.mock import MagicMock

from src.core.layers.pause_layer import PauseLayer


def _make_ctx(
    *,
    paused: bool = False,
    stopped: bool = False,
) -> MagicMock:
    ctx = MagicMock()
    stop_event = threading.Event()
    pause_event = threading.Event()

    if stopped:
        stop_event.set()
    if paused:
        pause_event.set()

    ctx.stop_event = stop_event
    ctx.pause_event = pause_event
    ctx.is_paused = paused
    ctx.is_stopping = stopped
    return ctx


class TestPauseLayer:
    def test_name(self) -> None:
        assert PauseLayer().name == "pause"

    def test_priority(self) -> None:
        assert PauseLayer().priority == -200

    def test_non_paused_passes_through(self) -> None:
        ctx = _make_ctx(paused=False, stopped=False)
        result = PauseLayer().on_node_enter(ctx)
        assert result is ctx

    def test_stopped_passes_through(self) -> None:
        ctx = _make_ctx(paused=False, stopped=True)
        result = PauseLayer().on_node_enter(ctx)
        assert result is ctx

    def test_paused_resumes_after_clear(self) -> None:
        ctx = _make_ctx(paused=True, stopped=False)

        def _resume():
            ctx.pause_event.clear()
            ctx.is_paused = False

        timer = threading.Timer(0.15, _resume)
        timer.start()

        result = PauseLayer().on_node_enter(ctx)
        assert result is ctx
        assert not ctx.is_paused
        timer.join()

    def test_paused_stops_during_pause(self) -> None:
        ctx = _make_ctx(paused=True, stopped=False)

        def _stop():
            ctx.stop_event.set()
            ctx.is_stopping = True

        timer = threading.Timer(0.15, _stop)
        timer.start()

        result = PauseLayer().on_node_enter(ctx)
        assert result is ctx
        assert ctx.is_stopping
        timer.join()

    def test_both_paused_and_stopped_exits(self) -> None:
        ctx = _make_ctx(paused=True, stopped=True)
        result = PauseLayer().on_node_enter(ctx)
        assert result is ctx
