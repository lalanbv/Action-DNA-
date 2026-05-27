"""通知通道单元测试 — mock 平台调用验证各通道行为。"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.notification.notifier import Notification
from src.notification.channels.system_notify import SystemNotifyChannel
from src.notification.channels.sound_notify import SoundNotifyChannel
from src.notification.channels.webhook_notify import WebhookNotifyChannel


def _make_notification(**overrides) -> Notification:
    defaults = {"title": "测试", "message": "消息内容", "level": "info"}
    defaults.update(overrides)
    return Notification(**defaults)


# ---- SystemNotifyChannel ----


class TestSystemNotifyChannel:
    def test_name(self):
        assert SystemNotifyChannel().name == "system_notify"

    @patch("src.notification.channels.system_notify.IS_MACOS", True)
    @patch("src.notification.channels.system_notify.IS_WINDOWS", False)
    @patch("subprocess.run")
    def test_macos_success(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ch = SystemNotifyChannel()
        assert ch.send(_make_notification()) is True
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "osascript" in args[0][0]

    @patch("src.notification.channels.system_notify.IS_MACOS", True)
    @patch("src.notification.channels.system_notify.IS_WINDOWS", False)
    @patch("subprocess.run")
    def test_macos_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        ch = SystemNotifyChannel()
        assert ch.send(_make_notification()) is False

    @patch("src.notification.channels.system_notify.IS_MACOS", False)
    @patch("src.notification.channels.system_notify.IS_WINDOWS", False)
    def test_unsupported_platform(self):
        ch = SystemNotifyChannel()
        assert ch.send(_make_notification()) is False

    @patch("src.notification.channels.system_notify.IS_MACOS", True)
    @patch("src.notification.channels.system_notify.IS_WINDOWS", False)
    @patch("subprocess.run", side_effect=TimeoutError)
    def test_macos_timeout(self, mock_run):
        ch = SystemNotifyChannel()
        assert ch.send(_make_notification()) is False

    @patch("src.notification.channels.system_notify.IS_MACOS", True)
    @patch("src.notification.channels.system_notify.IS_WINDOWS", False)
    @patch("subprocess.run")
    def test_test_sends_info_notification(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ch = SystemNotifyChannel()
        assert ch.test() is True


# ---- SoundNotifyChannel ----


class TestSoundNotifyChannel:
    def test_name(self):
        assert SoundNotifyChannel().name == "sound"

    @patch("src.notification.channels.sound_notify.IS_MACOS", True)
    @patch("src.notification.channels.sound_notify.IS_WINDOWS", False)
    @patch("subprocess.run")
    def test_macos_plays_sound(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ch = SoundNotifyChannel()
        assert ch.send(_make_notification(level="error")) is True
        args = mock_run.call_args[0][0]
        assert args[0] == "afplay"
        assert "Basso.aiff" in args[1]

    @patch("src.notification.channels.sound_notify.IS_MACOS", True)
    @patch("src.notification.channels.sound_notify.IS_WINDOWS", False)
    @patch("subprocess.run")
    def test_macos_default_sound_for_unknown_level(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        ch = SoundNotifyChannel()
        ch.send(_make_notification(level="unknown"))
        args = mock_run.call_args[0][0]
        assert "Ping.aiff" in args[1]

    @patch("src.notification.channels.sound_notify.IS_MACOS", False)
    @patch("src.notification.channels.sound_notify.IS_WINDOWS", False)
    def test_unsupported_platform(self):
        ch = SoundNotifyChannel()
        assert ch.send(_make_notification()) is False


# ---- WebhookNotifyChannel ----


class TestWebhookNotifyChannel:
    def test_name(self):
        ch = WebhookNotifyChannel(webhook_url="http://example.com")
        assert ch.name == "webhook_generic"

    @patch("src.notification.channels.webhook_notify.urlopen")
    def test_generic_payload(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WebhookNotifyChannel(webhook_url="http://example.com/hook")
        n = _make_notification()
        assert ch.send(n) is True

        call_args = mock_urlopen.call_args[0][0]
        body = json.loads(call_args.data)
        assert body["title"] == "测试"
        assert body["level"] == "info"

    @patch("src.notification.channels.webhook_notify.urlopen")
    def test_dingtalk_payload(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WebhookNotifyChannel(
            webhook_url="http://example.com/dingtalk?access_token=xxx",
            channel_type="dingtalk",
        )
        n = _make_notification(level="error")
        assert ch.send(n) is True

        call_args = mock_urlopen.call_args[0][0]
        body = json.loads(call_args.data)
        assert body["msgtype"] == "text"
        assert "[ERROR]" in body["text"]["content"]

    @patch("src.notification.channels.webhook_notify.urlopen")
    def test_dingtalk_with_sign(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WebhookNotifyChannel(
            webhook_url="http://example.com/dingtalk?access_token=xxx",
            channel_type="dingtalk",
            secret="SEC_test_secret",
        )
        ch.send(_make_notification())

        url = mock_urlopen.call_args[0][0].full_url
        assert "timestamp=" in url
        assert "sign=" in url

    @patch("src.notification.channels.webhook_notify.urlopen")
    def test_wechat_payload(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WebhookNotifyChannel(
            webhook_url="http://example.com/wechat",
            channel_type="wechat_work",
        )
        ch.send(_make_notification())

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert body["msgtype"] == "text"
        assert "[INFO]" in body["text"]["content"]

    @patch("src.notification.channels.webhook_notify.urlopen")
    def test_discord_payload(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WebhookNotifyChannel(
            webhook_url="http://example.com/discord",
            channel_type="discord",
        )
        ch.send(_make_notification(level="success"))

        body = json.loads(mock_urlopen.call_args[0][0].data)
        assert "embeds" in body
        embed = body["embeds"][0]
        assert "✅" in embed["title"]
        assert embed["color"] == 0x2ECC71
        assert embed["footer"]["text"] == "Action<DNA>"

    @patch("src.notification.channels.webhook_notify.urlopen")
    def test_bark_sends_get(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        ch = WebhookNotifyChannel(
            webhook_url="https://api.day.app/testkey",
            channel_type="bark",
        )
        assert ch.send(_make_notification()) is True

        req = mock_urlopen.call_args[0][0]
        assert req.full_url.startswith("https://api.day.app/testkey/")
        assert req.get_method() == "GET"

    @patch("src.notification.channels.webhook_notify.urlopen")
    def test_http_error_returns_false(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("connection refused")

        ch = WebhookNotifyChannel(webhook_url="http://example.com")
        assert ch.send(_make_notification()) is False
