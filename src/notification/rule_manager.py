"""通知规则管理器 — 检查规则并分发通知。"""

from __future__ import annotations

import logging
import threading

from src.notification.notifier import Notification, Notifier
from src.notification.triggers import NotificationRule, NotificationTrigger
from src.utils.i18n import t

import re

logger = logging.getLogger(__name__)

_LEVEL_MAP = {
    NotificationTrigger.ON_COMPLETE: "success",
    NotificationTrigger.ON_ERROR: "error",
    NotificationTrigger.ON_LOOP_COUNT: "info",
    NotificationTrigger.ON_STEP_REACHED: "info",
    NotificationTrigger.ON_VARIABLE_MATCH: "info",
    NotificationTrigger.ON_CUSTOM: "info",
}


class NotificationRuleManager:
    """通知规则管理器 — 管理规则增删，执行时检查所有规则并分发通知。"""

    def __init__(self, notifier: Notifier) -> None:
        self._notifier = notifier
        self._rules: list[NotificationRule] = []
        self._lock = threading.Lock()

    def add_rule(self, rule: NotificationRule) -> None:
        with self._lock:
            self._rules.append(rule)

    def remove_rule(self, index: int) -> None:
        with self._lock:
            if 0 <= index < len(self._rules):
                self._rules.pop(index)

    @property
    def rules(self) -> list[NotificationRule]:
        with self._lock:
            return list(self._rules)

    def check_and_notify(self, context: dict) -> int:
        triggered = 0

        with self._lock:
            snapshot = list(self._rules)

        for rule in snapshot:
            if not rule.should_trigger(context):
                continue

            title = _render_template(rule.title_template, context)
            message = _render_template(rule.message_template, context)
            level = _LEVEL_MAP.get(rule.trigger, "info")

            notification = Notification(
                title=title,
                message=message,
                level=level,
                data=context,
            )

            for channel_name in rule.channels:
                channel = self._notifier.get_channel(channel_name)
                if channel and channel.enabled:
                    try:
                        channel.send(notification)
                    except Exception as e:
                        logger.error(t("rule_manager.log.send_failed", channel=channel_name, error=e))

            triggered += 1

        return triggered


def _render_template(template: str, context: dict) -> str:
    def _replacer(match: re.Match) -> str:
        key = match.group(1)
        val = context.get(key)
        if isinstance(val, (str, int, float)):
            return str(val)
        return match.group(0)
    return re.sub(r"\{\{(\w+)\}\}", _replacer, template)
