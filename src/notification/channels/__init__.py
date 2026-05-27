"""通知通道注册工厂。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.notification.notifier import NotificationChannel


def create_default_channels() -> list[NotificationChannel]:
    """创建默认启用的通知通道列表（系统通知 + 声音）。"""
    from src.notification.channels.system_notify import SystemNotifyChannel
    from src.notification.channels.sound_notify import SoundNotifyChannel

    return [
        SystemNotifyChannel(),
        SoundNotifyChannel(),
    ]


def create_channel_from_config(config: dict) -> NotificationChannel | None:
    """根据配置创建通知通道。

    Args:
        config: 通道配置字典，必须包含 "type" 键。
            type="system_notify" -> SystemNotifyChannel
            type="sound" -> SoundNotifyChannel
            type="webhook" -> WebhookNotifyChannel
    """
    channel_type = config.get("type", "")
    if channel_type == "system_notify":
        from src.notification.channels.system_notify import SystemNotifyChannel
        return SystemNotifyChannel()
    elif channel_type == "sound":
        from src.notification.channels.sound_notify import SoundNotifyChannel
        return SoundNotifyChannel()
    elif channel_type == "webhook":
        from src.notification.channels.webhook_notify import WebhookNotifyChannel
        return WebhookNotifyChannel(
            webhook_url=config.get("url", ""),
            channel_type=config.get("channel_type", "generic"),
            secret=config.get("secret", ""),
            timeout=config.get("timeout", 5),
        )
    return None
