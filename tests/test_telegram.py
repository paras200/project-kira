"""Tests for Telegram channel adapter."""

from __future__ import annotations

from kira.channels.base import ChannelAdapter, IncomingMessage
from kira.channels.telegram import TelegramChannel


class TestTelegramChannel:
    def test_inherits_channel_adapter(self):
        assert issubclass(TelegramChannel, ChannelAdapter)

    def test_constructor(self):
        channel = TelegramChannel(bot_token="test-token", allowed_users=[123, 456])
        assert channel.bot_token == "test-token"
        assert channel.allowed_users == {123, 456}
        assert channel.name == "telegram"

    def test_empty_allowed_users(self):
        channel = TelegramChannel(bot_token="test-token")
        assert channel.allowed_users == set()

    def test_split_short_message(self):
        chunks = TelegramChannel._split_message("short message", 4096)
        assert len(chunks) == 1
        assert chunks[0] == "short message"

    def test_split_long_message(self):
        msg = "line\n" * 2000  # ~10000 chars
        chunks = TelegramChannel._split_message(msg, 4096)
        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 4096

    def test_split_preserves_content(self):
        msg = "A" * 5000
        chunks = TelegramChannel._split_message(msg, 4096)
        reassembled = "".join(chunks)
        assert reassembled == msg

    def test_message_handler_registration(self):
        channel = TelegramChannel(bot_token="test-token")

        async def handler(msg):
            pass

        channel.on_message(handler)
        assert channel._callback is handler


class TestIncomingMessage:
    def test_create_message(self):
        msg = IncomingMessage(
            channel="telegram",
            channel_id="12345",
            sender="John",
            text="Hello Kira",
            metadata={"user_id": 67890},
        )
        assert msg.channel == "telegram"
        assert msg.channel_id == "12345"
        assert msg.sender == "John"
        assert msg.text == "Hello Kira"
        assert msg.metadata["user_id"] == 67890

    def test_default_fields(self):
        msg = IncomingMessage(channel="cli", channel_id="0", sender="user", text="hi")
        assert msg.media is None
        assert msg.reply_to is None
        assert msg.timestamp is not None
