"""声音通知通道 — 播放系统提示音。"""

import logging
import subprocess
from pathlib import Path

from src.notification.notifier import Notification, NotificationChannel
from src.utils.i18n import t
from src.utils.platform import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)

_MACOS_SOUNDS = {
    "info": "/System/Library/Sounds/Ping.aiff",
    "warning": "/System/Library/Sounds/Tink.aiff",
    "error": "/System/Library/Sounds/Basso.aiff",
    "success": "/System/Library/Sounds/Glass.aiff",
}

_MACOS_DEFAULT = "/System/Library/Sounds/Ping.aiff"


class SoundNotifyChannel(NotificationChannel):
    """声音通知通道。

    - macOS: afplay 播放 /System/Library/Sounds/ 音效
    - Windows: winsound.MessageBeep() 系统预定义声音
    """

    @property
    def name(self) -> str:
        return "sound"

    def send(self, notification: Notification) -> bool:
        if IS_MACOS:
            return self._send_macos(notification)
        elif IS_WINDOWS:
            return self._send_windows(notification)
        else:
            logger.warning(t("sound_notify.log.platform_unsupported", system="Linux"))
            return False

    def _send_macos(self, notification: Notification) -> bool:
        try:
            sound_file = _MACOS_SOUNDS.get(
                notification.level, _MACOS_DEFAULT
            )
            if not Path(sound_file).exists():
                sound_file = _MACOS_DEFAULT

            subprocess.run(
                ["afplay", sound_file],
                capture_output=True,
                timeout=5,
            )
            return True
        except Exception as e:
            logger.error(t("sound_notify.log.send_failed_macos", error=e))
            return False

    def _send_windows(self, notification: Notification) -> bool:
        try:
            import winsound

            sound_map = {
                "info": winsound.MB_ICONASTERISK,
                "warning": winsound.MB_ICONEXCLAMATION,
                "error": winsound.MB_ICONHAND,
                "success": winsound.MB_ICONASTERISK,
            }
            sound_type = sound_map.get(
                notification.level, winsound.MB_ICONASTERISK
            )
            winsound.MessageBeep(sound_type)
            return True
        except Exception as e:
            logger.error(t("sound_notify.log.send_failed_windows", error=e))
            return False
