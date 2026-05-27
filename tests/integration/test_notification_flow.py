"""集成测试 — 通知+调度流程。

参考: 13_风险与验证策略.md §5.3
验证: Notifier 多通道分发 + NotificationRuleManager 规则触发 + Scheduler 调度执行。
覆盖: 通道隔离、规则冷却、调度类型、执行完成通知。
"""

import time
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.integration

from src.notification.notifier import Notification, NotificationChannel, Notifier
from src.notification.rule_manager import NotificationRuleManager
from src.notification.triggers import NotificationRule, NotificationTrigger
from src.schedule.scheduler import ScheduleConfig, ScheduleType, Scheduler


# ============================================================
# helpers
# ============================================================


class MockChannel(NotificationChannel):
    """内存 mock 通道，记录所有发送的通知。"""

    def __init__(self, name: str = "mock", *, should_fail: bool = False):
        self._name = name
        self._should_fail = should_fail
        self.sent: list[Notification] = []

    @property
    def name(self) -> str:
        return self._name

    def send(self, notification: Notification) -> bool:
        if self._should_fail:
            return False
        self.sent.append(notification)
        return True


def _make_notifier_with_channels(*names: str) -> tuple[Notifier, dict[str, MockChannel]]:
    notifier = Notifier()
    channels: dict[str, MockChannel] = {}
    for name in names:
        ch = MockChannel(name)
        notifier.register_channel(ch)
        channels[name] = ch
    return notifier, channels


# ============================================================
# Notifier 多通道集成
# ============================================================


class TestNotifierMultiChannel:
    """Notifier 多通道分发集成。"""

    def test_notify_dispatches_to_all_channels(self):
        """notify() 向所有已注册通道分发通知。"""
        notifier, channels = _make_notifier_with_channels("ch_a", "ch_b", "ch_c")
        notification = Notification(title="测试", message="多通道测试")

        results = notifier.notify(notification)

        assert len(results) == 3
        assert all(v is True for v in results.values())
        for ch in channels.values():
            assert len(ch.sent) == 1
            assert ch.sent[0].title == "测试"

    def test_channel_failure_isolation(self):
        """单个通道失败不影响其他通道。"""
        fail_channel = MockChannel("fail_ch", should_fail=True)
        ok_channel = MockChannel("ok_ch")
        notifier = Notifier()
        notifier.register_channel(fail_channel)
        notifier.register_channel(ok_channel)

        results = notifier.notify(Notification(title="隔离测试", message=""))

        assert results["fail_ch"] is False
        assert results["ok_ch"] is True
        assert len(ok_channel.sent) == 1

    def test_notify_async_completes(self):
        """notify_async() 在后台线程完成发送。"""
        notifier, channels = _make_notifier_with_channels("async_ch")

        notifier.notify_async(Notification(title="异步", message=""))
        time.sleep(0.2)

        assert len(channels["async_ch"].sent) == 1

    def test_register_unregister_channel(self):
        """注册和注销通道。"""
        notifier = Notifier()
        ch = MockChannel("temp")
        notifier.register_channel(ch)
        assert "temp" in notifier.channels

        notifier.unregister_channel("temp")
        assert "temp" not in notifier.channels


# ============================================================
# NotificationRuleManager 规则触发集成
# ============================================================


class TestRuleManagerIntegration:
    """规则管理器 + 通道分发集成。"""

    def test_on_complete_triggers_notification(self):
        """ON_COMPLETE 规则触发时通过通道发送成功通知。"""
        notifier, channels = _make_notifier_with_channels("log")
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["log"],
            title_template="执行完成: {{profile}}",
            message_template="耗时 {{elapsed}}s",
            cooldown=0,
        ))

        count = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_COMPLETE,
            "profile": "自动化任务A",
            "elapsed": "120",
        })

        assert count == 1
        assert len(channels["log"].sent) == 1
        n = channels["log"].sent[0]
        assert n.title == "执行完成: 自动化任务A"
        assert n.message == "耗时 120s"
        assert n.level == "success"

    def test_on_error_triggers_error_notification(self):
        """ON_ERROR 规则触发时发送 error 级别通知。"""
        notifier, channels = _make_notifier_with_channels("alert")
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_ERROR,
            channels=["alert"],
            title_template="执行错误",
            message_template="{{error}}",
            cooldown=0,
        ))

        manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_ERROR,
            "error": "模板未找到",
        })

        n = channels["alert"].sent[0]
        assert n.level == "error"
        assert "模板未找到" in n.message

    def test_cooldown_prevents_rapid_retrigger(self):
        """冷却期内相同规则不重复触发。"""
        notifier, channels = _make_notifier_with_channels("log")
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["log"],
            title_template="完成",
            message_template="",
            cooldown=10.0,
        ))

        context = {"trigger_type": NotificationTrigger.ON_COMPLETE}
        manager.check_and_notify(context)
        manager.check_and_notify(context)

        assert len(channels["log"].sent) == 1

    def test_disabled_rule_not_triggered(self):
        """禁用的规则不触发通知。"""
        notifier, channels = _make_notifier_with_channels("log")
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["log"],
            title_template="完成",
            message_template="",
            enabled=False,
            cooldown=0,
        ))

        count = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_COMPLETE,
        })

        assert count == 0
        assert len(channels["log"].sent) == 0

    def test_multiple_rules_different_triggers(self):
        """多个不同触发类型的规则同时存在。"""
        notifier, channels = _make_notifier_with_channels("log")
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["log"],
            title_template="完成: {{profile}}",
            message_template="",
            cooldown=0,
        ))
        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_ERROR,
            channels=["log"],
            title_template="错误: {{profile}}",
            message_template="",
            cooldown=0,
        ))

        c1 = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_COMPLETE,
            "profile": "任务1",
        })
        assert c1 == 1

        c2 = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_ERROR,
            "profile": "任务1",
        })
        assert c2 == 1

        assert len(channels["log"].sent) == 2

    def test_remove_rule(self):
        """移除规则后不再触发。"""
        notifier, channels = _make_notifier_with_channels("log")
        manager = NotificationRuleManager(notifier)

        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["log"],
            title_template="规则1",
            message_template="",
            cooldown=0,
        ))
        manager.add_rule(NotificationRule(
            trigger=NotificationTrigger.ON_COMPLETE,
            channels=["log"],
            title_template="规则2",
            message_template="",
            cooldown=0,
        ))

        manager.remove_rule(0)
        assert len(manager.rules) == 1

        count = manager.check_and_notify({
            "trigger_type": NotificationTrigger.ON_COMPLETE,
        })
        assert count == 1


# ============================================================
# Scheduler 调度集成
# ============================================================


class TestSchedulerIntegration:
    """调度器 + 执行器 + 通知集成。"""

    def test_interval_schedule_executes(self):
        """INTERVAL 调度到期后执行任务。"""
        executor = MagicMock()
        notifier, channels = _make_notifier_with_channels("notify")
        scheduler = Scheduler(executor, notifier)

        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="间隔任务",
            interval_seconds=0,
            loop_count=2,
        )
        scheduler.add_schedule(cfg)
        scheduler._check_schedules()

        executor.execute_profile.assert_called_once_with("间隔任务", loop_count=2)

    def test_execution_success_sends_notification(self):
        """执行成功后发送 success 通知。"""
        executor = MagicMock()
        notifier, channels = _make_notifier_with_channels("notify")
        scheduler = Scheduler(executor, notifier)

        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="成功任务",
            interval_seconds=0,
        )
        scheduler.add_schedule(cfg)
        scheduler._check_schedules()

        time.sleep(0.3)
        assert len(channels["notify"].sent) == 1
        n = channels["notify"].sent[0]
        assert n.level == "success"
        assert "成功任务" in n.title

    def test_execution_failure_sends_error_notification(self):
        """执行失败后发送 error 通知。"""
        executor = MagicMock()
        executor.execute_profile.side_effect = RuntimeError("执行出错")
        notifier, channels = _make_notifier_with_channels("notify")
        scheduler = Scheduler(executor, notifier)

        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="失败任务",
            interval_seconds=0,
        )
        scheduler.add_schedule(cfg)
        scheduler._check_schedules()

        time.sleep(0.3)
        assert len(channels["notify"].sent) == 1
        n = channels["notify"].sent[0]
        assert n.level == "error"
        assert "执行出错" in n.message

    def test_max_runs_limits_execution(self):
        """max_runs 限制最大执行次数。"""
        executor = MagicMock()
        notifier, channels = _make_notifier_with_channels("notify")
        scheduler = Scheduler(executor, notifier)

        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="限量任务",
            interval_seconds=0,
            max_runs=2,
        )
        sid = scheduler.add_schedule(cfg)

        scheduler._check_schedules()
        assert scheduler.get_run_count(sid) == 1

        scheduler._check_schedules()
        assert scheduler.get_run_count(sid) == 2

        # 第三次不应执行
        scheduler._check_schedules()
        assert scheduler.get_run_count(sid) == 2
        assert executor.execute_profile.call_count == 2

    def test_remove_schedule_stops_execution(self):
        """移除调度后不再执行。"""
        executor = MagicMock()
        notifier = Notifier()
        scheduler = Scheduler(executor, notifier)

        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="移除任务",
            interval_seconds=0,
        )
        sid = scheduler.add_schedule(cfg)

        scheduler._check_schedules()
        assert executor.execute_profile.call_count == 1

        scheduler.remove_schedule(sid)
        scheduler._check_schedules()
        assert executor.execute_profile.call_count == 1

    def test_list_schedules_returns_info(self):
        """list_schedules 返回调度信息。"""
        executor = MagicMock()
        notifier = Notifier()
        scheduler = Scheduler(executor, notifier)

        cfg = ScheduleConfig(
            schedule_type=ScheduleType.ONCE,
            profile_name="一次性",
            run_at=datetime.now() + timedelta(hours=1),
        )
        scheduler.add_schedule(cfg)

        schedules = scheduler.list_schedules()
        assert len(schedules) == 1
        _, config, next_time = schedules[0]
        assert config.profile_name == "一次性"
        assert next_time is not None
