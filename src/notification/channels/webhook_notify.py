"""Webhook 通知通道 — 支持钉钉/企业微信/Discord/Bark/Generic 五种格式。"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import urllib.parse
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import Request, urlopen

from src.notification.notifier import Notification, NotificationChannel
from src.utils.i18n import t

logger = logging.getLogger(__name__)


class WebhookNotifyChannel(NotificationChannel):
    """Webhook 通知通道。

    支持五种服务格式：
    - dingtalk: 钉钉机器人（含 HMAC-SHA256 签名）
    - wechat_work: 企业微信 text 消息
    - discord: embed 格式（颜色、时间戳、footer）
    - bark: iOS 推送（GET 请求）
    - generic: 通用 JSON POST
    """

    def __init__(
        self,
        webhook_url: str,
        channel_type: str = "generic",
        secret: str = "",
        timeout: int = 5,
    ) -> None:
        self._url = webhook_url
        self._type = channel_type
        self._secret = secret
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"webhook_{self._type}"

    def send(self, notification: Notification) -> bool:
        try:
            if self._type == "bark":
                return self._send_bark(notification)
            payload = self._build_payload(notification)
            url = self._build_signed_url() if self._secret else self._url
            return self._send_post(payload, url)
        except Exception as e:
            logger.error(t("webhook_notify.log.send_failed", error=e))
            return False

    # ---- Payload 构造 ----

    def _build_payload(self, notification: Notification) -> dict:
        builders = {
            "dingtalk": self._build_dingtalk_payload,
            "wechat_work": self._build_wechat_payload,
            "discord": self._build_discord_payload,
        }
        builder = builders.get(self._type, self._build_generic_payload)
        return builder(notification)

    def _build_dingtalk_payload(self, n: Notification) -> dict:
        content = f"[{n.level.upper()}] {n.title}\n{n.message}"
        payload = {
            "msgtype": "text",
            "text": {"content": content},
        }
        return payload

    def _build_signed_url(self) -> str:
        """生成带 HMAC-SHA256 签名的钉钉 URL（不修改实例状态）。"""
        timestamp = str(round(datetime.now(timezone.utc).timestamp() * 1000))
        string_to_sign = f"{timestamp}\n{self._secret}"
        hmac_code = hmac.new(
            self._secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        sep = "&" if "?" in self._url else "?"
        return f"{self._url}{sep}timestamp={timestamp}&sign={sign}"

    def _build_wechat_payload(self, n: Notification) -> dict:
        content = f"[{n.level.upper()}] {n.title}\n{n.message}"
        return {
            "msgtype": "text",
            "text": {"content": content},
        }

    def _build_discord_payload(self, n: Notification) -> dict:
        return {
            "embeds": [{
                "title": f"{n.level_icon} {n.title}",
                "description": n.message,
                "color": n.level_color,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "footer": {"text": "Action<DNA>"},
            }]
        }

    def _build_generic_payload(self, n: Notification) -> dict:
        return {
            "title": n.title,
            "message": n.message,
            "level": n.level,
            "timestamp": n.timestamp,
            "data": n.data,
        }

    # ---- 发送方法 ----

    def _send_bark(self, notification: Notification) -> bool:
        body = urllib.parse.quote(
            f"[{notification.level.upper()}] {notification.title}\n"
            f"{notification.message}"
        )
        url = f"{self._url.rstrip('/')}/{body}"
        try:
            req = Request(url)
            with urlopen(req, timeout=self._timeout) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(t("webhook_notify.log.bark_failed", error=e))
            return False

    def _send_post(self, payload: dict, url: str | None = None) -> bool:
        target = url or self._url
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        req = Request(target, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                return 200 <= resp.status < 300
        except URLError as e:
            logger.error(t("webhook_notify.log.http_post_failed", error=e))
            return False
