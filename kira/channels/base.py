"""Base channel adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Awaitable, Callable, Optional


@dataclass
class IncomingMessage:
    """A message received from any channel."""

    channel: str  # "telegram" | "email" | "cli" | "api"
    channel_id: str  # Chat/thread ID
    sender: str  # User identifier
    text: str
    media: Optional[list] = None
    reply_to: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)


class ChannelAdapter(ABC):
    """Base class for messaging platform adapters."""

    name: str
    supports_streaming: bool = False
    supports_media: bool = False

    @abstractmethod
    async def start(self):
        """Start listening for messages."""

    @abstractmethod
    async def stop(self):
        """Stop listening and clean up."""

    @abstractmethod
    async def send(self, channel_id: str, message: str):
        """Send a message to a specific channel/chat."""

    @abstractmethod
    def on_message(self, callback: Callable[[IncomingMessage], Awaitable[None]]):
        """Register a callback for incoming messages."""
