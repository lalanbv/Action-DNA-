"""Notification 数据模型 + Notifier 多通道分发 单元测试。"""

import threading

import pytest

from src.notification.notifier import Notification, NotificationChannel, Notifier


# ---- Stub 通道 ----


class _StubChannel(NotificationChannel):
    def __init__(self, name: str = "stub", should_succeed: bool = True):
        self._name = name
        self._should_succeed = should_succeed
        self.sent: list[Notification] = []

    @property
    def name(self) -> str:
        return self._name

    def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return self._should_succeed


class _DisabledChannel(_StubChannel):
    @property
    def enabled(self) -> bool:
        return False


class _ErrorChannel(NotificationChannel):
    @property
    def name(self) -> str:
        return "error_ch"

    def send(self, notification: Notification) -> bool:
        raise RuntimeError("通道异常")


# ---- Notification 数据模型 ----


class TestNotification:
    def test_default_level(self):
        n = Notification(title="标题", message="内容")
        assert n.level == "info"
        assert n.level_icon == "ℹ️"
        assert n.level_color == 0x3498DB

    def test_level_icon_mapping(self):
        assert Notification(title="", message="", level="warning").level_icon == "⚠️"
        assert Notification(title="", message="", level="error").level_icon == "❌"
        assert Notification(title="", message="", level="success").level_icon == "✅"

    def test_level_color_mapping(self):
        assert Notification(title="", message="", level="warning").level_color == 0xF39C12
        assert Notification(title="", message="", level="error").level_color == 0xE74C3C
        assert Notification(title="", message="", level="success").level_color == 0x2ECC71

    def test_unknown_level_defaults(self):
        n = Notification(title="", message="", level="unknown")
        assert n.level_icon == "ℹ️"
        assert n.level_color == 0x3498DB

    def test_format_message(self):
        n = Notification(
            title="测试",
            message="",
            data={"loop_count": 10, "profile": "自动化"},
        )
        result = n.format_message("已完成 {{loop_count}} 次，配置: {{profile}}")
        assert result == "已完成 10 次，配置: 自动化"

    def test_format_message_missing_key(self):
        n = Notification(title="", message="")
        result = n.format_message("{{missing}}")
        assert result == "{{missing}}"

    def test_timestamp_auto_set(self):
        n = Notification(title="", message="")
        assert n.timestamp > 0


# ---- Notifier ----


class TestNotifier:
    def test_register_and_get_channel(self):
        notifier = Notifier()
        ch = _StubChannel()
        notifier.register_channel(ch)
        assert notifier.get_channel("stub") is ch

    def test_register_overwrites_same_name(self):
        notifier = Notifier()
        notifier.register_channel(_StubChannel("ch1"))
        ch2 = _StubChannel("ch1")
        notifier.register_channel(ch2)
        assert notifier.get_channel("ch1") is ch2

    def test_unregister_channel(self):
        notifier = Notifier()
        notifier.register_channel(_StubChannel("ch1"))
        notifier.unregister_channel("ch1")
        assert notifier.get_channel("ch1") is None

    def test_unregister_nonexistent(self):
        notifier = Notifier()
        notifier.unregister_channel("nope")  # 不应报错

    def test_channels_returns_copy(self):
        notifier = Notifier()
        notifier.register_channel(_StubChannel("a"))
        channels = notifier.channels
        channels["b"] = _StubChannel("b")
        assert "b" not in notifier.channels

    def test_notify_single_channel(self):
        ch = _StubChannel()
        notifier = Notifier()
        notifier.register_channel(ch)

        n = Notification(title="测试", message="内容")
        results = notifier.notify(n)

        assert results == {"stub": True}
        assert len(ch.sent) == 1
        assert ch.sent[0].title == "测试"

    def test_notify_skips_disabled_channel(self):
        ch = _DisabledChannel("disabled")
        notifier = Notifier()
        notifier.register_channel(ch)

        results = notifier.notify(Notification(title="", message=""))
        assert results == {"disabled": False}
        assert len(ch.sent) == 0

    def test_notify_isolates_channel_errors(self):
        ok_ch = _StubChannel("ok")
        err_ch = _ErrorChannel()
        notifier = Notifier()
        notifier.register_channel(ok_ch)
        notifier.register_channel(err_ch)

        results = notifier.notify(Notification(title="", message=""))
        assert results["ok"] is True
        assert results["error_ch"] is False
        assert len(ok_ch.sent) == 1

    def test_notify_async_does_not_block(self):
        event = threading.Event()
        slow_ch = _StubChannel()
        original_send = slow_ch.send

        def slow_send(notification):
            result = original_send(notification)
            event.set()
            return result

        slow_ch.send = slow_send

        notifier = Notifier()
        notifier.register_channel(slow_ch)

        notifier.notify_async(Notification(title="异步测试", message=""))
        assert event.wait(timeout=2)
        assert len(slow_ch.sent) == 1

    def test_test_all(self):
        ch1 = _StubChannel("a", should_succeed=True)
        ch2 = _StubChannel("b", should_succeed=False)
        notifier = Notifier()
        notifier.register_channel(ch1)
        notifier.register_channel(ch2)

        results = notifier.test_all()
        assert results["a"] is True
        assert results["b"] is False
        assert len(ch1.sent) == 1
        assert ch1.sent[0].title == "Action<DNA> 测试通知"
