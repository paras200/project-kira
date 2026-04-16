"""Telegram channel adapter — receive and send messages via Telegram Bot API.

Setup:
1. Create a bot via @BotFather on Telegram
2. Get the bot token
3. Add token to ~/.kira/secrets.yaml as TELEGRAM_BOT_TOKEN
4. Add your Telegram user ID to settings.yaml channels.telegram.allowed_users
5. Start chatting with your bot on Telegram
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Optional

import httpx

from .base import ChannelAdapter, IncomingMessage

logger = logging.getLogger(__name__)


class TelegramChannel(ChannelAdapter):
    """Telegram bot adapter using long-polling (no webhooks needed)."""

    name = "telegram"
    supports_streaming = False
    supports_media = True

    def __init__(self, bot_token: str, allowed_users: Optional[list[int]] = None):
        self.bot_token = bot_token
        self.allowed_users = set(allowed_users or [])
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._callback: Optional[Callable[[IncomingMessage], Awaitable[None]]] = None
        self._running = False
        self._offset = 0
        self._client: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start polling for Telegram updates."""
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=10.0))

        # Verify bot token
        try:
            resp = await self._client.get(f"{self._base_url}/getMe")
            data = resp.json()
            if not data.get("ok"):
                raise ValueError(f"Invalid bot token: {data.get('description', 'unknown error')}")
            bot_info = data["result"]
            logger.info(
                f"Telegram bot connected: @{bot_info.get('username', '?')} "
                f"(id: {bot_info.get('id')})"
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to connect to Telegram: {e}")
            raise

        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram channel started (long-polling)")

    async def stop(self):
        """Stop polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.aclose()
        logger.info("Telegram channel stopped")

    async def send(self, channel_id: str, message: str):
        """Send a text message to a Telegram chat."""
        if not self._client:
            return

        # Telegram has a 4096 char limit per message
        chunks = self._split_message(message, 4096)
        for chunk in chunks:
            try:
                await self._client.post(
                    f"{self._base_url}/sendMessage",
                    json={
                        "chat_id": int(channel_id),
                        "text": chunk,
                        "parse_mode": "Markdown",
                    },
                )
            except Exception:
                # Retry without markdown if it fails (malformed markdown)
                try:
                    await self._client.post(
                        f"{self._base_url}/sendMessage",
                        json={"chat_id": int(channel_id), "text": chunk},
                    )
                except Exception as e:
                    logger.error(f"Failed to send Telegram message: {e}")

    async def send_typing(self, channel_id: str):
        """Show typing indicator."""
        if not self._client:
            return
        try:
            await self._client.post(
                f"{self._base_url}/sendChatAction",
                json={"chat_id": int(channel_id), "action": "typing"},
            )
        except Exception:
            pass

    def on_message(self, callback: Callable[[IncomingMessage], Awaitable[None]]):
        """Register the message handler callback."""
        self._callback = callback

    async def _poll_loop(self):
        """Long-polling loop for Telegram updates."""
        while self._running:
            try:
                resp = await self._client.get(
                    f"{self._base_url}/getUpdates",
                    params={
                        "offset": self._offset,
                        "timeout": 30,
                        "allowed_updates": json.dumps(["message"]),
                    },
                )

                if resp.status_code != 200:
                    logger.warning(f"Telegram poll error: HTTP {resp.status_code}")
                    await asyncio.sleep(5)
                    continue

                data = resp.json()
                if not data.get("ok"):
                    logger.warning(f"Telegram poll error: {data.get('description')}")
                    await asyncio.sleep(5)
                    continue

                for update in data.get("result", []):
                    self._offset = update["update_id"] + 1
                    await self._handle_update(update)

            except asyncio.CancelledError:
                break
            except httpx.ReadTimeout:
                # Normal for long-polling
                continue
            except Exception as e:
                logger.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)

    async def _handle_update(self, update: dict):
        """Process a single Telegram update."""
        message = update.get("message")
        if not message:
            return

        chat_id = message.get("chat", {}).get("id")
        user_id = message.get("from", {}).get("id")
        text = message.get("text", "")

        if not text or not chat_id:
            return

        # Auth check
        if self.allowed_users and user_id not in self.allowed_users:
            logger.warning(f"Unauthorized Telegram user: {user_id}")
            await self.send(str(chat_id), "Unauthorized. Your user ID is not in the allowed list.")
            return

        # Build incoming message
        sender_name = message.get("from", {}).get("first_name", str(user_id))
        incoming = IncomingMessage(
            channel="telegram",
            channel_id=str(chat_id),
            sender=sender_name,
            text=text,
            metadata={
                "user_id": user_id,
                "message_id": message.get("message_id"),
                "chat_type": message.get("chat", {}).get("type"),
            },
        )

        if self._callback:
            try:
                await self.send_typing(str(chat_id))
                await self._callback(incoming)
            except Exception as e:
                logger.error(f"Error handling Telegram message: {e}")
                await self.send(str(chat_id), f"Error: {e}")

    @staticmethod
    def _split_message(text: str, max_len: int) -> list[str]:
        """Split a long message into chunks."""
        if len(text) <= max_len:
            return [text]
        chunks = []
        while text:
            if len(text) <= max_len:
                chunks.append(text)
                break
            # Try to split at a newline
            split_at = text.rfind("\n", 0, max_len)
            if split_at == -1:
                split_at = max_len
            chunks.append(text[:split_at])
            text = text[split_at:].lstrip("\n")
        return chunks
