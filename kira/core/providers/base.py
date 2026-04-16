"""Base provider adapter interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncIterator

from kira.core.models import (
    CompletionResponse,
    Message,
    StreamChunk,
    ToolSchema,
)


class ProviderAdapter(ABC):
    """Base class for all LLM provider adapters."""

    name: str
    supports_streaming: bool = True
    supports_tool_calls: bool = True
    supports_vision: bool = True
    supports_system_prompt: bool = True

    @abstractmethod
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> CompletionResponse: ...

    @abstractmethod
    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> AsyncIterator[StreamChunk]: ...

    async def close(self):
        """Clean up any resources."""
