"""通知系统集成测试 — 验证 execute→trigger→notify 完整管道。"""

from unittest.mock import MagicMock

import pytest

from src.notification.notifier import Notification, Notifier
from src.notification.rule_manager import NotificationRuleManager
from src.notification.triggers import NotificationRule, NotificationTrigger
from src.schedule.scheduler import ScheduleConfig, ScheduleType, Scheduler


# ---- 端到端: Notifier + RuleManager + 触发器 → 通知发送 ----


class TestNotificationPipeline:
    """模拟执行流程中的事件 → 规则匹配 → 通道发送。"""

    def setup_method(self):
        self.channel = MagicMock()
        self.channel.enabled = True
        self.channel.name = "mock_ch"
        self.channel.send.return_value = True

        self.notifier = Notifier()
        self.notifier.register_channel(self.channel)

        self.manager = NotificationRuleManager(self.notifier)

    def test_on_complete_sends_success_notification(self):
        self.manager.add_rule(
            NotificationRule(
                trigger=NotificationTrigger.ON_COMPLETE,
                channels=["mock_ch"],
                title_template="完成: {{profile}}",
                message_template="共 {{total_loops}} 次",
                cooldown=0,
            )
        )

        count = self.manager.check_and_notify(
            {
                "trigger_type": NotificationTrigger.ON_COMPLETE,
                "profile": "自动化A",
                "total_loops": 100,
            }
        )

        assert count == 1
        self.channel.send.assert_called_once()
        notification = self.channel.send.call_args[0][0]
        assert notification.title == "完成: 自动化A"
        assert notification.message == "共 100 次"
        assert notification.level == "success"

    def test_on_error_sends_error_notification(self):
        self.manager.add_rule(
            NotificationRule(
                trigger=NotificationTrigger.ON_ERROR,
                channels=["mock_ch"],
                title_template="出错",
                message_template="步骤 {{step_name}} 失败",
                cooldown=0,
            )
        )

        count = self.manager.check_and_notify(
            {
                "trigger_type": NotificationTrigger.ON_ERROR,
                "step_name": "点击怪物",
            }
        )

        assert count == 1
        notification = self.channel.send.call_args[0][0]
        assert notification.level == "error"

    def test_on_loop_count_periodic_notification(self):
        self.manager.add_rule(
            NotificationRule(
                trigger=NotificationTrigger.ON_LOOP_COUNT,
                channels=["mock_ch"],
                title_template="进度",
                message_template="第 {{loop_count}} 次",
                condition={"interval": 10},
                cooldown=0,
            )
        )

        triggered = 0
        for i in range(1, 31):
            count = self.manager.check_and_notify(
                {"trigger_type": NotificationTrigger.ON_LOOP_COUNT, "loop_count": i}
            )
            triggered += count

        assert triggered == 3  # at 10, 20, 30

    def test_multiple_rules_fire_simultaneously(self):
        self.manager.add_rule(
            NotificationRule(
                trigger=NotificationTrigger.ON_COMPLETE,
                channels=["mock_ch"],
                title_template="规则1",
                message_template="m1",
                cooldown=0,
            )
        )
        self.manager.add_rule(
            NotificationRule(
                trigger=NotificationTrigger.ON_COMPLETE,
                channels=["mock_ch"],
                title_template="规则2",
                message_template="m2",
                cooldown=0,
            )
        )

        count = self.manager.check_and_notify(
            {"trigger_type": NotificationTrigger.ON_COMPLETE}
        )
        assert count == 2
        assert self.channel.send.call_count == 2

    def test_cooldown_prevents_spam(self):
        self.manager.add_rule(
            NotificationRule(
                trigger=NotificationTrigger.ON_ERROR,
                channels=["mock_ch"],
                title_template="错误",
                message_template="m",
                cooldown=999,
            )
        )

        ctx = {"trigger_type": NotificationTrigger.ON_ERROR}
        assert self.manager.check_and_notify(ctx) == 1
        assert self.manager.check_and_notify(ctx) == 0


# ---- 端到端: Scheduler + Notifier ----


class TestSchedulerNotificationIntegration:
    def test_schedule_execution_sends_notification(self):
        executor = MagicMock()
        notifier = Notifier()
        channel = MagicMock()
        channel.enabled = True
        channel.name = "test_ch"
        channel.send.return_value = True
        notifier.register_channel(channel)

        scheduler = Scheduler(executor, notifier)
        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="自动化B",
            interval_seconds=0,
        )
        scheduler.add_schedule(cfg)
        scheduler._check_schedules()

        executor.execute_profile.assert_called_once_with("自动化B", loop_count=1)
        channel.send.assert_called()

    def test_schedule_failure_sends_error_notification(self):
        executor = MagicMock()
        executor.execute_profile.side_effect = RuntimeError("执行崩溃")
        notifier = Notifier()
        channel = MagicMock()
        channel.enabled = True
        channel.name = "test_ch"
        channel.send.return_value = True
        notifier.register_channel(channel)

        scheduler = Scheduler(executor, notifier)
        cfg = ScheduleConfig(
            schedule_type=ScheduleType.INTERVAL,
            profile_name="自动化C",
            interval_seconds=0,
        )
        scheduler.add_schedule(cfg)
        scheduler._check_schedules()

        notification = channel.send.call_args[0][0]
        assert notification.level == "error"
        assert "执行崩溃" in notification.message
