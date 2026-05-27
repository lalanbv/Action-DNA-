"""系统通知通道 — 利用操作系统原生通知机制。"""

import logging
import subprocess
import threading

from src.notification.notifier import Notification, NotificationChannel
from src.utils.i18n import t
from src.utils.platform import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)


class SystemNotifyChannel(NotificationChannel):
    """系统桌面通知通道。

    - macOS: osascript display notification
    - Windows: 非阻塞线程 + MessageBoxW
    """

    APP_NAME = "Action<DNA>"

    @property
    def name(self) -> str:
        return "system_notify"

    def send(self, notification: Notification) -> bool:
        if IS_MACOS:
            return self._send_macos(notification)
        elif IS_WINDOWS:
            return self._send_windows(notification)
        else:
            logger.warning(t("notification.log.platform_unsupported", system="Linux"))
            return False

    def _send_macos(self, notification: Notification) -> bool:
        try:
            title = notification.title.replace('"', '\\"')
            message = notification.message.replace('"', '\\"')
            subtitle = f"[{notification.level.upper()}]"

            script = (
                f'display notification "{message}" '
                f'with title "{self.APP_NAME}" '
                f'subtitle "{subtitle}"'
            )
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(t("notification.log.send_failed_macos", error=e))
            return False

    def _send_windows(self, notification: Notification) -> bool:
        try:
            title = f"[{notification.level.upper()}] {notification.title}"
            message = notification.message

            def _show_box() -> None:
                import ctypes

                user32 = ctypes.windll.user32  # type: ignore[attr-defined]
                user32.MessageBoxW(0, message, title, 0x40 | 0x1000)

            threading.Thread(target=_show_box, daemon=True).start()
            return True
        except Exception as e:
            logger.error(t("notification.log.send_failed_windows", error=e))
            return False
