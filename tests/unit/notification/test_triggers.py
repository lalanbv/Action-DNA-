"""通知触发器 + 规则管理器 单元测试。"""

from unittest.mock import MagicMock

import pytest

from src.notification.channels.system_notify import SystemNotifyChannel
from src.notification.notifier import Notification, Notifier
from src.notification.rule_manager import NotificationRuleManager
from src.notification.triggers import NotificationRule, NotificationTrigger


def _rule(**overrides) -> NotificationRule:
    defaults = {
        "trigger": NotificationTrigger.ON_COMPLETE,
        "channels": ["system_notify"],
        "title_template": "完成",
        "message_template": "循环 {{loop_count}} 次",
    }
    defaults.update(overrides)
    return NotificationRule(**defaults)


# ---- NotificationRule ----


class TestNotificationRule:
    def test_disabled_never_triggers(self):
        rule = _rule(enabled=False)
        assert rule.should_trigger({"trigger_type": NotificationTrigger.ON_COMPLETE}) is False

    def test_type_mismatch(self):
        rule = _rule(trigger=NotificationTrigger.ON_COMPLETE)
        assert rule.should_trigger({"trigger_type": NotificationTrigger.ON_ERROR}) is False

    def test_on_complete_triggers(self):
        rule = _rule(trigger=NotificationTrigger.ON_COMPLETE)
        ctx = {"trigger_type": NotificationTrigger.ON_COMPLETE}
        assert rule.should_trigger(ctx) is True

    def test_cooldown_blocks_second_call(self):
        rule = _rule(cooldown=999.0)
        ctx = {"trigger_type": NotificationTrigger.ON_COMPLETE}
        assert rule.should_trigger(ctx) is True
        assert rule.should_trigger(ctx) is False

    def test_on_loop_count_with_interval(self):
        rule = _rule(
            trigger=NotificationTrigger.ON_LOOP_COUNT,
            condition={"interval": 5},
        )
        ctx = {"trigger_type": NotificationTrigger.ON_LOOP_COUNT}
        assert rule.should_trigger({**ctx, "loop_count": 5}) is True
        assert rule.should_trigger({**ctx, "loop_count": 3}) is False

    def test_on_step_reached(self):
        rule = _rule(
            trigger=NotificationTrigger.ON_STEP_REACHED,
            condition={"step_id": "step_3"},
        )
        ctx = {"trigger_type": NotificationTrigger.ON_STEP_REACHED}
        assert rule.should_trigger({**ctx, "step_id": "step_3"}) is True
        assert rule.should_trigger({**ctx, "step_id": "step_1"}) is False

    def test_on_variable_match(self):
        rule = _rule(
            trigger=NotificationTrigger.ON_VARIABLE_MATCH,
            condition={"var_name": "hp", "operator": "<", "value": 30},
        )
        ctx = {"trigger_type": NotificationTrigger.ON_VARIABLE_MATCH}
        assert rule.should_trigger({**ctx, "variables": {"hp": 20}}) is True
        assert rule.should_trigger({**ctx, "variables": {"hp": 50}}) is False

    def test_on_custom_expression(self):
        rule = _rule(
            trigger=NotificationTrigger.ON_CUSTOM,
            condition={"expression": "loop_count >= 100"},
        )
        ctx = {"trigger_type": NotificationTrigger.ON_CUSTOM}
        assert rule.should_trigger({**ctx, "loop_count": 100}) is True
        assert rule.should_trigger({**ctx, "loop_count": 50}) is False

    def test_on_custom_bad_expression(self):
        rule = _rule(
            trigger=NotificationTrigger.ON_CUSTOM,
            condition={"expression": "invalid $$$ syntax"},
        )
        ctx = {"trigger_type": NotificationTrigger.ON_CUSTOM}
        assert rule.should_trigger(ctx) is False

    def test_compare_operators(self):
        base = {
            "trigger_type": NotificationTrigger.ON_VARIABLE_MATCH,
            "variables": {"val": 10},
        }
        cases = [
            ({"var_name": "val", "operator": "==", "value": 10}, True),
            ({"var_name": "val", "operator": "!=", "value": 5}, True),
            ({"var_name": "val", "operator": ">", "value": 5}, True),
            ({"var_name": "val", "operator": ">=", "value": 10}, True),
            ({"var_name": "val", "operator": "<", "value": 20}, True),
            ({"var_name": "val", "operator": "<=", "value": 10}, True),
        ]
        for cond, expected in cases:
            rule = _rule(
                trigger=NotificationTrigger.ON_VARIABLE_MATCH,
                condition=cond,
                cooldown=0,
            )
            assert rule.should_trigger(base) is expected, f"Failed: {cond}"

        # invalid operator → safe_eval rejects, returns False
        rule = _rule(
            trigger=NotificationTrigger.ON_VARIABLE_MATCH,
            condition={"var_name": "val", "operator": "???", "value": 5},
            cooldown=0,
        )
        assert rule.should_trigger(base) is False

    def test_on_error_triggers(self):
        rule = _rule(trigger=NotificationTrigger.ON_ERROR)
        ctx = {"trigger_type": NotificationTrigger.ON_ERROR}
        assert rule.should_trigger(ctx) is True

    def test_on_loop_count_zero_does_not_trigger(self):
        rule = _rule(
            trigger=NotificationTrigger.ON_LOOP_COUNT,
            condition={"interval": 5},
        )
        ctx = {"trigger_type": NotificationTrigger.ON_LOOP_COUNT, "loop_count": 0}
        assert rule.should_trigger(ctx) is False

    def test_on_variable_match_no_variables(self):
        rule = _rule(
            trigger=NotificationTrigger.ON_VARIABLE_MATCH,
            condition={"var_name": "hp", "operator": "<", "value": 30},
        )
        ctx = {"trigger_type": NotificationTrigger.ON_VARIABLE_MATCH}
        assert rule.should_trigger(ctx) is False

    def test_on_variable_match_all_operators(self):
        base = {
            "trigger_type": NotificationTrigger.ON_VARIABLE_MATCH,
            "variables": {"count": 10},
        }
        cases = [
            ({"var_name": "count", "operator": "==", "value": 10}, True),
            ({"var_name": "count", "operator": "!=", "value": 5}, True),
            ({"var_name": "count", "operator": ">", "value": 5}, True),
            ({"var_name": "count", "operator": ">=", "value": 10}, True),
            ({"var_name": "count", "operator": "<", "value": 20}, True),
            ({"var_name": "count", "operator": "<=", "value": 10}, True),
            ({"var_name": "count", "operator": ">", "value": 20}, False),
        ]
        for cond, expected in cases:
            rule = _rule(
                trigger=NotificationTrigger.ON_VARIABLE_MATCH,
                condition=cond,
                cooldown=0,
            )
            assert rule.should_trigger(base) is expected, f"Failed: {cond}"

    def test_cooldown_expires_allows_retrigger(self):
        rule = _rule(cooldown=0.0)
        ctx = {"trigger_type": NotificationTrigger.ON_COMPLETE}
        assert rule.should_trigger(ctx) is True
        assert rule.should_trigger(ctx) is True



# ---- NotificationRuleManager ----


class TestNotificationRuleManager:
    def test_add_and_list_rules(self):
        notifier = Notifier()
        mgr = NotificationRuleManager(notifier)
        rule = _rule()
        mgr.add_rule(rule)
        assert len(mgr.rules) == 1
        assert mgr.rules[0] is rule

    def test_remove_rule(self):
        mgr = NotificationRuleManager(Notifier())
        mgr.add_rule(_rule())
        mgr.remove_rule(0)
        assert len(mgr.rules) == 0

    def test_check_and_notify_triggers_rule(self):
        ch = MagicMock()
        ch.enabled = True
        ch.send.return_value = True

        notifier = Notifier()
        notifier.register_channel(ch)

        mgr = NotificationRuleManager(notifier)
        mgr.add_rule(_rule(channels=["stub"]))
        mgr.add_rule(_rule(channels=["stub"]))

        # Override the second rule channel name to "stub" for notifier lookup
        notifier.unregister_channel("stub")
        ch.name = "stub"
        notifier.register_channel(ch)

        count = mgr.check_and_notify({"trigger_type": NotificationTrigger.ON_COMPLETE})
        assert count == 2
        assert ch.send.call_count == 2

    def test_check_and_notify_error_level(self):
        ch = MagicMock()
        ch.enabled = True
        ch.name = "stub"
        ch.send.return_value = True

        notifier = Notifier()
        notifier.register_channel(ch)

        mgr = NotificationRuleManager(notifier)
        mgr.add_rule(
            _rule(
                trigger=NotificationTrigger.ON_ERROR,
                channels=["stub"],
            )
        )

        count = mgr.check_and_notify({"trigger_type": NotificationTrigger.ON_ERROR})
        assert count == 1
        sent_notification = ch.send.call_args[0][0]
        assert sent_notification.level == "error"

    def test_check_and_notify_no_match(self):
        mgr = NotificationRuleManager(Notifier())
        mgr.add_rule(_rule(trigger=NotificationTrigger.ON_ERROR))
        count = mgr.check_and_notify({"trigger_type": NotificationTrigger.ON_COMPLETE})
        assert count == 0

    def test_check_and_notify_skips_disabled_channel(self):
        ch = MagicMock()
        ch.enabled = False
        ch.name = "disabled"
        ch.send.return_value = True

        notifier = Notifier()
        notifier.register_channel(ch)

        mgr = NotificationRuleManager(notifier)
        mgr.add_rule(_rule(channels=["disabled"]))

        count = mgr.check_and_notify({"trigger_type": NotificationTrigger.ON_COMPLETE})
        assert count == 1
        ch.send.assert_not_called()
