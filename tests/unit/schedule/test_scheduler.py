"""Scheduler 单元测试 — ScheduleConfig.next_run_time + Scheduler 核心逻辑。"""

import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.notification.notifier import Notifier
from src.schedule.scheduler import ScheduleConfig, ScheduleType, Scheduler


def _config(**overrides) -> ScheduleConfig:
    defaults = {
        "schedule_type": ScheduleType.ONCE,
        "profile_name": "test_profile",
    }
    defaults.update(overrides)
    return ScheduleConfig(**defaults)


# ---- ScheduleConfig.next_run_time ----


class TestNextRunTimeOnce:
    def test_future_time(self):
        future = datetime(2030, 1, 1, 10, 0, 0)
        cfg = _config(run_at=future)
        now = datetime(2030, 1, 1, 9, 0, 0)
        assert cfg.next_run_time(now) == future

    def test_past_time_returns_none(self):
        past = datetime(2020, 1, 1, 10, 0, 0)
        cfg = _config(run_at=past)
        now = datetime(2030, 1, 1, 9, 0, 0)
        assert cfg.next_run_time(now) is None

    def test_no_run_at_returns_none(self):
        cfg = _config()
        assert cfg.next_run_time() is None


class TestNextRunTimeInterval:
    def test_returns_now_plus_interval(self):
        now = datetime(2030, 1, 1, 12, 0, 0)
        cfg = _config(schedule_type=ScheduleType.INTERVAL, interval_seconds=3600)
        result = cfg.next_run_time(now)
        assert result == now + timedelta(hours=1)


class TestNextRunTimeDaily:
    def test_same_day_future_time(self):
        now = datetime(2030, 1, 1, 8, 0, 0)
        cfg = _config(schedule_type=ScheduleType.DAILY, daily_time="10:00")
        result = cfg.next_run_time(now)
        assert result == datetime(2030, 1, 1, 10, 0, 0)

    def test_same_day_past_time_moves_to_tomorrow(self):
        now = datetime(2030, 1, 1, 11, 0, 0)
        cfg = _config(schedule_type=ScheduleType.DAILY, daily_time="10:00")
        result = cfg.next_run_time(now)
        assert result == datetime(2030, 1, 2, 10, 0, 0)

    def test_with_daily_days_skips_non_matching(self):
        # 2030-01-01 is Tuesday (weekday=1), skip to Thursday (weekday=3)
        now = datetime(2030, 1, 1, 11, 0, 0)
        cfg = _config(
            schedule_type=ScheduleType.DAILY,
            daily_time="09:00",
            daily_days=[3],
        )
        result = cfg.next_run_time(now)
        assert result.weekday() == 3
        assert result > now

    def test_with_daily_days_includes_today(self):
        # 2030-01-01 is Tuesday (weekday=1), time not yet passed
        now = datetime(2030, 1, 1, 8, 0, 0)
        cfg = _config(
            schedule_type=ScheduleType.DAILY,
            daily_time="10:00",
            daily_days=[1, 3],
        )
        result = cfg.next_run_time(now)
        assert result == datetime(2030, 1, 1, 10, 0, 0)


class TestNextRunTimeWeekly:
    def test_finds_next_target_day(self):
        # 2030-01-01 is Tuesday (weekday=1), target Friday (weekday=4)
        now = datetime(2030, 1, 1, 12, 0, 0)
        cfg = _config(
            schedule_type=ScheduleType.WEEKLY,
            weekly_day=4,
            weekly_time="09:00",
        )
        result = cfg.next_run_time(now)
        assert result.weekday() == 4
        assert result.hour == 9
        assert result > now

    def test_same_day_past_time_advances_week(self):
        # 2030-01-04 is Friday, target Friday at 09:00 but now is 10:00
        now = datetime(2030, 1, 4, 10, 0, 0)
        cfg = _config(
            schedule_type=ScheduleType.WEEKLY,
            weekly_day=4,
            weekly_time="09:00",
        )
        result = cfg.next_run_time(now)
        assert result == datetime(2030, 1, 11, 9, 0, 0)

    def test_same_day_future_time_runs_today(self):
        # 2030-01-04 is Friday, target Friday at 15:00 and now is 10:00
        now = datetime(2030, 1, 4, 10, 0, 0)
        cfg = _config(
            schedule_type=ScheduleType.WEEKLY,
            weekly_day=4,
            weekly_time="15:00",
        )
        result = cfg.next_run_time(now)
        assert result == datetime(2030, 1, 4, 15, 0, 0)


# ---- Scheduler core ----


def _make_scheduler() -> tuple[Scheduler, MagicMock, MagicMock]:
    executor = MagicMock()
    notifier = MagicMock(spec=Notifier)
    notifier.notify_async = MagicMock()
    return Scheduler(executor, notifier), executor, notifier


class TestSchedulerAddRemove:
    def test_add_returns_id(self):
        sched, _, _ = _make_scheduler()
        cfg = _config(schedule_type=ScheduleType.INTERVAL, interval_seconds=60)
        sid = sched.add_schedule(cfg)
        assert isinstance(sid, str)
        assert len(sid) == 8

    def test_list_schedules(self):
        sched, _, _ = _make_scheduler()
        cfg = _config(schedule_type=ScheduleType.INTERVAL, interval_seconds=60)
        sid = sched.add_schedule(cfg)
        items = sched.list_schedules()
        assert len(items) == 1
        assert items[0][0] == sid

    def test_remove_schedule(self):
        sched, _, _ = _make_scheduler()
        sid = sched.add_schedule(_config())
        sched.remove_schedule(sid)
        assert len(sched.list_schedules()) == 0

    def test_remove_nonexistent_no_error(self):
        sched, _, _ = _make_scheduler()
        sched.remove_schedule("nonexistent")


class TestSchedulerStartStop:
    def test_start_and_stop(self):
        sched, _, _ = _make_scheduler()
        sched.start()
        assert sched.running is True
        sched.stop()
        assert sched.running is False

    def test_double_start_no_error(self):
        sched, _, _ = _make_scheduler()
        sched.start()
        sched.start()
        sched.stop()

    def test_stop_cleans_thread(self):
        sched, _, _ = _make_scheduler()
        sched.start()
        sched.stop()
        assert sched._thread is None


class TestSchedulerExecution:
    def test_check_schedules_executes_due(self):
        sched, executor, _ = _make_scheduler()
        cfg = _config(schedule_type=ScheduleType.INTERVAL, interval_seconds=0)
        sched.add_schedule(cfg)
        sched._check_schedules()
        executor.execute_profile.assert_called_once_with(
            "test_profile", loop_count=1
        )

    def test_max_runs_limits_execution(self):
        sched, executor, _ = _make_scheduler()
        cfg = _config(
            schedule_type=ScheduleType.INTERVAL,
            interval_seconds=0,
            max_runs=1,
        )
        sid = sched.add_schedule(cfg)

        sched._check_schedules()
        assert sched.get_run_count(sid) == 1

        executor.reset_mock()
        sched._check_schedules()
        executor.execute_profile.assert_not_called()

    def test_execute_sends_success_notification(self):
        sched, _, notifier = _make_scheduler()
        cfg = _config(schedule_type=ScheduleType.INTERVAL, interval_seconds=0)
        sched.add_schedule(cfg)
        sched._check_schedules()
        notifier.notify_async.assert_called_once()
        notification = notifier.notify_async.call_args[0][0]
        assert notification.level == "success"

    def test_execute_failure_sends_error_notification(self):
        sched, executor, notifier = _make_scheduler()
        executor.execute_profile.side_effect = RuntimeError("boom")
        cfg = _config(schedule_type=ScheduleType.INTERVAL, interval_seconds=0)
        sched.add_schedule(cfg)
        sched._check_schedules()
        notifier.notify_async.assert_called_once()
        notification = notifier.notify_async.call_args[0][0]
        assert notification.level == "error"

    def test_once_type_past_time_not_executed(self):
        sched, executor, _ = _make_scheduler()
        cfg = _config(
            schedule_type=ScheduleType.ONCE,
            run_at=datetime(2020, 1, 1, 10, 0, 0),
        )
        sched.add_schedule(cfg)
        sched._check_schedules()
        executor.execute_profile.assert_not_called()
