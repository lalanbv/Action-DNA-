"""条件系统 — 条件类型定义与求值器"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.vision import ScreenCapture, TemplateMatcher


class ConditionType(Enum):
    """条件类型"""
    IMAGE_FOUND = auto()
    IMAGE_NOT_FOUND = auto()
    VARIABLE_EXISTS = auto()
    VARIABLE_COMPARE = auto()
    ELAPSED_TIME = auto()
    COMPOUND_AND = auto()
    COMPOUND_OR = auto()
    COMPOUND_NOT = auto()


# 类型 → i18n key 映射（UI 显示用）
_CONDITION_TYPE_I18N_KEYS: dict[ConditionType, str] = {
    ConditionType.IMAGE_FOUND: "dialog.condition_type.image_found",
    ConditionType.IMAGE_NOT_FOUND: "dialog.condition_type.image_not_found",
    ConditionType.VARIABLE_EXISTS: "dialog.condition_type.variable_exists",
    ConditionType.VARIABLE_COMPARE: "dialog.condition_type.variable_compare",
    ConditionType.ELAPSED_TIME: "dialog.condition_type.elapsed_time",
    ConditionType.COMPOUND_AND: "dialog.condition_type.compound_and",
    ConditionType.COMPOUND_OR: "dialog.condition_type.compound_or",
    ConditionType.COMPOUND_NOT: "dialog.condition_type.compound_not",
}

# 比较运算符
_COMPARE_OPS = {"==", "!=", ">", "<", ">=", "<="}


@dataclass
class Condition:
    """可求值的条件"""
    condition_type: ConditionType
    # IMAGE_FOUND / IMAGE_NOT_FOUND
    image_path: str = ""
    threshold: float = 0.8
    # VARIABLE_EXISTS / VARIABLE_COMPARE
    variable_name: str = ""
    compare_op: str = ""         # "==", "!=", ">", "<", ">=", "<="
    compare_value_x: int = 0
    compare_value_y: int = 0
    # ELAPSED_TIME
    timeout_seconds: float = 0.0
    timer_name: str = ""
    # COMPOUND (AND / OR / NOT)
    children: list[Condition] = field(default_factory=list)

    def describe(self) -> str:
        """返回人类可读的条件描述"""
        from src.utils.i18n import t
        match self.condition_type:
            case ConditionType.IMAGE_FOUND:
                name = os.path.basename(self.image_path) if self.image_path else t("common.not_set")
                return t("condition.describe.image_found", name=name)
            case ConditionType.IMAGE_NOT_FOUND:
                name = os.path.basename(self.image_path) if self.image_path else t("common.not_set")
                return t("condition.describe.image_not_found", name=name)
            case ConditionType.VARIABLE_EXISTS:
                return t("condition.describe.variable_exists", name=self.variable_name)
            case ConditionType.VARIABLE_COMPARE:
                return t("condition.describe.variable_compare", name=self.variable_name, op=self.compare_op, x=self.compare_value_x, y=self.compare_value_y)
            case ConditionType.ELAPSED_TIME:
                return t("condition.describe.elapsed_time", name=self.timer_name, seconds=self.timeout_seconds)
            case ConditionType.COMPOUND_AND:
                inner = ", ".join(c.describe() for c in self.children)
                return t("condition.describe.compound_and", inner=inner)
            case ConditionType.COMPOUND_OR:
                inner = ", ".join(c.describe() for c in self.children)
                return t("condition.describe.compound_or", inner=inner)
            case ConditionType.COMPOUND_NOT:
                if self.children:
                    return t("condition.describe.compound_not", inner=self.children[0].describe())
                return t("condition.describe.compound_not_empty")

    @staticmethod
    def type_label(ct: ConditionType) -> str:
        from src.utils.i18n import t
        key = _CONDITION_TYPE_I18N_KEYS.get(ct)
        return t(key) if key else ct.name


class ConditionEvaluator:
    """条件求值器 — 在运行时评估条件

    持有运行时变量和计时器状态，使用 ScreenCapture + TemplateMatcher
    执行图片检测条件。
    """

    _log = logging.getLogger(__name__)

    def __init__(self, capture: ScreenCapture, matcher: TemplateMatcher):
        self._capture = capture
        self._matcher = matcher
        self._variables: dict[str, tuple[int, int]] = {}
        self._timers: dict[str, float] = {}  # name -> monotonic start time
        self._lock = threading.Lock()

    # ── 变量操作 ──────────────────────────────────────────────

    def set_variable(self, name: str, value: tuple[int, int]) -> None:
        with self._lock:
            self._variables[name] = value

    def get_variable(self, name: str) -> tuple[int, int] | None:
        with self._lock:
            return self._variables.get(name)

    def has_variable(self, name: str) -> bool:
        with self._lock:
            return name in self._variables

    def clear_variables(self) -> None:
        with self._lock:
            self._variables.clear()

    # ── 计时器操作 ──────────────────────────────────────────────

    def start_timer(self, name: str) -> None:
        with self._lock:
            self._timers[name] = time.monotonic()

    def reset_timer(self, name: str) -> None:
        with self._lock:
            self._timers[name] = time.monotonic()

    def clear_timers(self) -> None:
        with self._lock:
            self._timers.clear()

    # ── 求值 ──────────────────────────────────────────────

    def evaluate(self, condition: Condition) -> bool:
        """评估条件，返回 True/False"""
        match condition.condition_type:
            case ConditionType.IMAGE_FOUND:
                return self._check_image_found(condition)
            case ConditionType.IMAGE_NOT_FOUND:
                return not self._check_image_found(condition)
            case ConditionType.VARIABLE_EXISTS:
                return self.has_variable(condition.variable_name)
            case ConditionType.VARIABLE_COMPARE:
                return self._compare_variable(condition)
            case ConditionType.ELAPSED_TIME:
                return self._check_elapsed(condition)
            case ConditionType.COMPOUND_AND:
                return all(self.evaluate(c) for c in condition.children)
            case ConditionType.COMPOUND_OR:
                return any(self.evaluate(c) for c in condition.children)
            case ConditionType.COMPOUND_NOT:
                if condition.children:
                    return not self.evaluate(condition.children[0])
                return False
            case _:
                self._log.warning("未知条件类型: %s, 默认返回 False", condition.condition_type)
                return False

    def _check_image_found(self, cond: Condition) -> bool:
        """检查模板图片是否出现在屏幕上"""
        if not cond.image_path:
            return False
        try:
            screen = self._capture.grab_reuse()
            rect = self._matcher.find(screen, cond.image_path, cond.threshold)
            return rect is not None
        except (FileNotFoundError, ValueError):
            return False

    def _compare_variable(self, cond: Condition) -> bool:
        """比较运行时变量的值"""
        with self._lock:
            val = self._variables.get(cond.variable_name)
        if val is None:
            return False
        target = (cond.compare_value_x, cond.compare_value_y)
        op = cond.compare_op
        if op == "==":
            return val == target
        if op == "!=":
            return val != target
        if op == ">":
            return val > target
        if op == "<":
            return val < target
        if op == ">=":
            return val >= target
        if op == "<=":
            return val <= target
        return False

    def _check_elapsed(self, cond: Condition) -> bool:
        """检查计时器是否已超过指定时间"""
        with self._lock:
            start = self._timers.get(cond.timer_name)
        if start is None:
            return False
        return (time.monotonic() - start) >= cond.timeout_seconds
