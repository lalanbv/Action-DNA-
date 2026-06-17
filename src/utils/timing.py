"""真人节奏噪声工具 — Gamma 噪声扰动。

使用 Gamma(k=2, θ=0.5) 分布生成均值≈1.0、右偏的随机乘数，
使回放时序更接近真人的速度变化特征。
"""

from __future__ import annotations

import random

from src.utils.i18n import t

GAMMA_SHAPE = 2.0
GAMMA_SCALE = 0.5


def human_like_duration(base: float) -> float:
    """对基准时长施加 Gamma 噪声，生成更接近真人的持续时长。"""
    return base * random.gammavariate(GAMMA_SHAPE, GAMMA_SCALE)


def format_duration_human(seconds: float) -> str:
    """把秒数格式化为人类可读时长,智能省略前导零,固定最多 2 个有效单位。

    < 60s  → "45秒"
    < 1h   → "2分14秒"
    < 1d   → "1小时5分"
    >= 1d  → "1天3小时"

    负数按 0 处理。占位符单位走 i18n(duration.*)。
    """
    total = int(max(0.0, seconds))
    if total < 60:
        return t("duration.seconds", s=total)
    minutes, secs = divmod(total, 60)
    if total < 3600:
        return t("duration.minutes_seconds", m=minutes, s=secs)
    hours, minutes = divmod(minutes, 60)
    if total < 86400:
        return t("duration.hours_minutes", h=hours, m=minutes)
    days, hours = divmod(hours, 24)
    return t("duration.days_hours", d=days, h=hours)
