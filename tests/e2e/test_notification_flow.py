"""E2E 测试 — 通知调度完整流程: Scheduler → Executor → RuleManager → Notifier"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.notification.notifier import Notification, Notifier
from src.notification.rule_manager import NotificationRuleManager
from src.notification.triggers import NotificationRule, NotificationTrigger
from src.schedule.scheduler import ScheduleConfig, ScheduleType, Scheduler


# ── 辅助 ──────────────────────────────────────────────────


def _make_notifier() -> tuple[Notifier, MagicMock]:
    notifier = Notifier()
    channel = MagicMock()
    channel.enabled = True
    channel.name = "e2e_ch"
    channel.send.return_value = True
    notifier.register_channel(channel)
    return notifier, channel


def _immediate_interval_config(profile: str = "自动化") -> ScheduleConfig:
    return ScheduleConfig(
        schedule_type=ScheduleType.INTERVAL,
        profile_name=profile,
        interval_seconds=0,
        loop_count=3,
    )


# ── E2E: 调度执行 + 通知分发 ──────────────────────────────


class TestSchedulerNotifierE2E:
    """调度器执行后自动通知（成功/失败）。"""

    def test_successful_execution_notifies(self) -> None:
        executor = MagicMock()
        notifier, channel = _make_notifier()
        scheduler = Scheduler(executor, notifier)

        scheduler.add_schedule(_immediate_interval_config("自动化A"))
        scheduler._check_schedules()

        executor.execute_profile.assert_called_once_with("自动化A", loop_count=3)
        assert channel.send.call_count == 1
        n = channel.send.call_args[0][0]
        assert isinstance(n, Notification)
        assert n.level == "success"
        assert "自动化A" in n.title
        assert n.data["run_count"] == 1

    def test_failed_execution_sends_error(self) -> None:
        executor = MagicMock()
        executor.execute_profile.side_effect = RuntimeError("崩溃了")
        notifier, channel = _make_notifier()
        scheduler = Scheduler(executor, notifier)

        scheduler.add_schedule(_immediate_interval_config("自动化B"))
        scheduler._check_schedules()

        n = channel.send.call_args[0][0]
        assert n.level == "error"
        assert "崩溃了" in n.message
        assert n.data["profile"] == "自动化B"

    def test_multiple_schedules_fire(self) -> None:
        executor = MagicMock()
        notifier, channel = _make_notifier()
        scheduler = Scheduler(executor, notifier)

        scheduler.add_schedule(_immediate_interval_config("任务1"))
        scheduler.add_schedule(_immediate_interval_config("任务2"))
        scheduler._check_schedules()

        assert executor.execute_profile.call_count == 2
        assert channel.send.call_count == 2

    def test_max_runs_respected(self) -> None:
        executor = MagicMock()
        notifier, channel = _make_notifier()
        scheduler = Scheduler(executor, notifier)

        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="限量",
            interval_seconds=0,
            max_runs=1,
        )
        sid = scheduler.add_schedule(cfg)
        scheduler._check_schedules()
        assert scheduler.get_run_count(sid) == 1

        scheduler._check_schedules()
        assert scheduler.get_run_count(sid) == 1
        assert executor.execute_profile.call_count == 1


# ── E2E: 规则管理器 + 多触发条件 ───────────────────────────


class TestRuleManagerE2E:
    """规则管理器 + 多触发条件 + 冷却。"""

    def test_complete_and_error_rules_both_registered(self) -> None:
        notifier, channel = _make_notifier()
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["e2e_ch"],
            title_template="完成: {{profile}}",
            message_template="ok",
            cooldown=0,
        ))
        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_ERROR,
            channels=["e2e_ch"],
            title_template="出错: {{profile}}",
            message_template="fail",
            cooldown=0,
        ))

        c1 = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_COMPLETE,
            "profile": "P1",
        })
        assert c1 == 1
        assert channel.send.call_args[0][0].level == "success"

        c2 = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_ERROR,
            "profile": "P1",
        })
        assert c2 == 1
        assert channel.send.call_args[0][0].level == "error"

    def test_loop_count_interval_triggers(self) -> None:
        notifier, channel = _make_notifier()
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_LOOP_COUNT,
            channels=["e2e_ch"],
            title_template="进度 {{loop_count}}",
            message_template="",
            condition={"interval": 5},
            cooldown=0,
        ))

        fired_at: list[int] = []
        for i in range(1, 21):
            count = manager.check_and_notify({
                "trigger_type": NotificationTrigger.ON_LOOP_COUNT,
                "loop_count": i,
            })
            if count > 0:
                fired_at.append(i)

        assert fired_at == [5, 10, 15, 20]

    def test_step_reached_triggers(self) -> None:
        notifier, channel = _make_notifier()
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_STEP_REACHED,
            channels=["e2e_ch"],
            title_template="到达步骤 {{step_id}}",
            message_template="",
            condition={"step_id": "boss_fight"},
            cooldown=0,
        ))

        c1 = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_STEP_REACHED,
            "step_id": "walk",
        })
        assert c1 == 0

        c2 = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_STEP_REACHED,
            "step_id": "boss_fight",
        })
        assert c2 == 1

    def test_disabled_rule_ignored(self) -> None:
        notifier, channel = _make_notifier()
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["e2e_ch"],
            title_template="t",
            message_template="m",
            enabled=False,
        ))

        count = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_COMPLETE,
        })
        assert count == 0


# ── E2E: 多通道分发 ──────────────────────────────────────


class TestMultiChannelE2E:
    """Notifier 向多个通道分发通知。"""

    def test_notify_all_channels(self) -> None:
        notifier = Notifier()
        ch1 = MagicMock()
        ch1.enabled = True
        ch1.name = "ch1"
        ch1.send.return_value = True

        ch2 = MagicMock()
        ch2.enabled = True
        ch2.name = "ch2"
        ch2.send.return_value = True

        notifier.register_channel(ch1)
        notifier.register_channel(ch2)

        results = notifier.notify(Notification(
            title="测试", message="hello", level="info",
        ))
        assert results == {"ch1": True, "ch2": True}

    def test_disabled_channel_skipped(self) -> None:
        notifier = Notifier()
        ch_active = MagicMock()
        ch_active.enabled = True
        ch_active.name = "active"
        ch_active.send.return_value = True

        ch_disabled = MagicMock()
        ch_disabled.enabled = False
        ch_disabled.name = "disabled"

        notifier.register_channel(ch_active)
        notifier.register_channel(ch_disabled)

        results = notifier.notify(Notification(
            title="测试", message="hello", level="info",
        ))
        assert results == {"active": True, "disabled": False}
        ch_disabled.send.assert_not_called()

    def test_channel_failure_doesnt_block_others(self) -> None:
        notifier = Notifier()
        ch_fail = MagicMock()
        ch_fail.enabled = True
        ch_fail.name = "fail"
        ch_fail.send.side_effect = ConnectionError("网络错误")

        ch_ok = MagicMock()
        ch_ok.enabled = True
        ch_ok.name = "ok"
        ch_ok.send.return_value = True

        notifier.register_channel(ch_fail)
        notifier.register_channel(ch_ok)

        results = notifier.notify(Notification(
            title="测试", message="hello", level="info",
        ))
        assert results["fail"] is False
        assert results["ok"] is True


# ── E2E: ScheduleConfig next_run_time 计算 ─────────────────


class TestScheduleConfigE2E:
    """ScheduleConfig 时间计算在真实调度流程中的表现。"""

    def test_once_schedule_past_time_returns_none(self) -> None:
        cfg = ScheduleConfig(
            schedule_type=ScheduleType.ONCE,
            profile_name="过期任务",
            run_at=datetime.now() - timedelta(hours=1),
        )
        assert cfg.next_run_time() is None

    def test_daily_schedule_next_day(self) -> None:
        now = datetime(2026, 5, 1, 15, 0, 0)
        cfg = ScheduleConfig(
            schedule_type=ScheduleType.DAILY,
            profile_name="每日",
            daily_time="09:00",
        )
        result = cfg.next_run_time(now)
        assert result is not None
        assert result.hour == 9
        assert result.day == 2

    def test_weekly_schedule(self) -> None:
        now = datetime(2026, 5, 1, 10, 0, 0)
        cfg = ScheduleConfig(
            schedule_type=ScheduleType.WEEKLY,
            profile_name="每周",
            weekly_day=0,
            weekly_time="08:00",
        )
        result = cfg.next_run_time(now)
        assert result is not None
        assert result.hour == 8
        assert result.weekday() == 0
