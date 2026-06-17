"""ExecutionTimer 单元测试 — 活跃计时,排除暂停,停止冻结。"""

from __future__ import annotations

import time

from src.core.execution_timer import ExecutionTimer


class TestBasics:
    def test_elapsed_none_before_start(self) -> None:
        timer = ExecutionTimer()
        assert timer.elapsed() is None

    def test_start_makes_elapsed_nonnone(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        elapsed = timer.elapsed()
        assert elapsed is not None
        assert elapsed < 0.01  # 刚启动应接近 0

    def test_elapsed_grows_while_running(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        elapsed = timer.elapsed()
        assert elapsed is not None
        assert elapsed >= 0.04


class TestPauseFreeze:
    def test_pause_excludes_paused_duration(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        timer.pause()
        frozen = timer.elapsed()
        assert frozen is not None
        time.sleep(0.10)  # 暂停期间不应增长
        after = timer.elapsed()
        assert after is not None
        assert abs(after - frozen) < 0.02

    def test_resume_continues_accumulating(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        timer.pause()
        time.sleep(0.10)
        timer.resume()
        before = timer.elapsed()
        assert before is not None
        time.sleep(0.05)
        after = timer.elapsed()
        assert after is not None
        assert after >= before + 0.04  # 恢复后继续增长

    def test_pause_when_not_started_is_noop(self) -> None:
        timer = ExecutionTimer()
        timer.pause()  # 不应抛异常
        assert timer.elapsed() is None

    def test_resume_when_not_paused_is_noop(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.resume()  # 未暂停,空操作
        assert timer.elapsed() is not None


class TestStopFreeze:
    def test_stop_freezes_final_value(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        time.sleep(0.05)
        timer.stop()
        final = timer.elapsed()
        assert final is not None
        time.sleep(0.10)
        after = timer.elapsed()
        assert after == final  # 冻结

    def test_stop_is_idempotent(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.stop()
        first = timer.elapsed()
        timer.stop()
        assert first == timer.elapsed()


class TestReset:
    def test_reset_clears_state(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.stop()
        timer.reset()
        assert timer.elapsed() is None

    def test_start_after_reset_works(self) -> None:
        timer = ExecutionTimer()
        timer.start()
        timer.stop()
        timer.reset()
        timer.start()
        assert timer.elapsed() is not None
