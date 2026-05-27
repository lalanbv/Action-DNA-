"""通知系统核心 — Notification 数据模型、NotificationChannel ABC、Notifier 多通道分发器。"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from src.utils.i18n import t

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """通知内容数据模型。"""

    title: str
    message: str
    level: str = "info"
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)

    @property
    def level_icon(self) -> str:
        icons = {
            "info": "ℹ️",
            "warning": "⚠️",
            "error": "❌",
            "success": "✅",
        }
        return icons.get(self.level, "ℹ️")

    @property
    def level_color(self) -> int:
        colors = {
            "info": 0x3498DB,
            "warning": 0xF39C12,
            "error": 0xE74C3C,
            "success": 0x2ECC71,
        }
        return colors.get(self.level, 0x3498DB)

    def format_message(self, template: str) -> str:
        result = template
        for key, value in self.data.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result


class NotificationChannel(ABC):
    """通知通道抽象基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """通道唯一标识名。"""

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """发送通知，返回是否成功。异常应被捕获，不应向外抛出。"""

    @property
    def enabled(self) -> bool:
        return True

    def test(self) -> bool:
        return self.send(Notification(
            title=t("notifier.test_title"),
            message=t("notifier.test_message"),
            level="info",
        ))


class Notifier:
    """多通道通知分发器。"""

    def __init__(self) -> None:
        self._channels: dict[str, NotificationChannel] = {}
        self._lock = threading.Lock()

    def register_channel(self, channel: NotificationChannel) -> None:
        with self._lock:
            self._channels[channel.name] = channel
        logger.info(t("notifier.log.channel_registered", name=channel.name))

    def unregister_channel(self, name: str) -> None:
        with self._lock:
            if name in self._channels:
                del self._channels[name]
        logger.info(t("notifier.log.channel_unregistered", name=name))

    def get_channel(self, name: str) -> NotificationChannel | None:
        with self._lock:
            return self._channels.get(name)

    @property
    def channels(self) -> dict[str, NotificationChannel]:
        with self._lock:
            return dict(self._channels)

    def notify(self, notification: Notification) -> dict[str, bool]:
        with self._lock:
            snapshot = list(self._channels.items())
        results: dict[str, bool] = {}
        for name, channel in snapshot:
            if not channel.enabled:
                results[name] = False
                continue
            try:
                results[name] = channel.send(notification)
                if results[name]:
                    logger.debug(t("notifier.log.send_success", name=name, title=notification.title))
            except Exception as e:
                logger.error(t("notifier.log.send_failed", name=name, error=e))
                results[name] = False
        return results

    def notify_async(self, notification: Notification) -> None:
        thread = threading.Thread(
            target=self.notify,
            args=(notification,),
            name=f"Notify-{notification.title[:20]}",
            daemon=True,
        )
        thread.start()

    def test_all(self) -> dict[str, bool]:
        with self._lock:
            snapshot = list(self._channels.items())
        results: dict[str, bool] = {}
        for name, channel in snapshot:
            try:
                results[name] = channel.test()
            except Exception as e:
                logger.error(t("notifier.log.test_failed", name=name, error=e))
                results[name] = False
        return results
