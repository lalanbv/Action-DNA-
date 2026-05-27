"""通知触发器 — NotificationTrigger 枚举 + NotificationRule 规则数据类。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum

from src.core.safe_eval import safe_eval
from src.utils.i18n import t

logger = logging.getLogger(__name__)


class NotificationTrigger(Enum):
    """通知触发条件类型。"""

    ON_COMPLETE = "on_complete"
    ON_ERROR = "on_error"
    ON_LOOP_COUNT = "on_loop_count"
    ON_STEP_REACHED = "on_step_reached"
    ON_VARIABLE_MATCH = "on_var_match"
    ON_CUSTOM = "on_custom"


@dataclass
class NotificationRule:
    """通知规则 — 定义何时触发、发送到哪些通道、通知内容格式。"""

    trigger: NotificationTrigger
    channels: list[str]
    title_template: str
    message_template: str
    condition: dict | None = None
    cooldown: float = 60.0
    enabled: bool = True

    _last_triggered: float = field(default=0.0, repr=False)

    def __post_init__(self) -> None:
        self._lock = threading.Lock()

    def should_trigger(self, context: dict) -> bool:
        if not self.enabled:
            return False

        if context.get("trigger_type") != self.trigger:
            return False

        now = time.time()
        with self._lock:
            if now - self._last_triggered < self.cooldown:
                return False

        if self.condition is None:
            with self._lock:
                self._last_triggered = now
            return True

        if self._check_condition(context):
            with self._lock:
                self._last_triggered = now
            return True

        return False

    def _check_condition(self, context: dict) -> bool:
        """检查条件是否满足。"""
        if self.trigger == NotificationTrigger.ON_LOOP_COUNT:
            interval = self.condition.get("interval", 1)
            loop_count = context.get("loop_count", 0)
            if loop_count > 0 and loop_count % interval == 0:
                return True

        elif self.trigger == NotificationTrigger.ON_STEP_REACHED:
            target_step = self.condition.get("step_id", "")
            current_step = context.get("step_id", "")
            if current_step == target_step:
                return True

        elif self.trigger == NotificationTrigger.ON_VARIABLE_MATCH:
            var_name = self.condition.get("var_name", "")
            operator = self.condition.get("operator", "==")
            target_value = self.condition.get("value")
            variables = context.get("variables")
            if variables and var_name in variables:
                expr = f"{var_name} {operator} {target_value!r}"
                if safe_eval(expr, variables):
                    return True

        elif self.trigger == NotificationTrigger.ON_CUSTOM:
            expression = self.condition.get("expression", "False")
            if safe_eval(expression, context):
                return True

        return False
