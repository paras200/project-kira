"""Anthropic Messages API adapter.

Handles the Anthropic-specific format: system as separate field,
content blocks, tool_use/tool_result roles.
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator

import httpx

from kira.core.models import (
    CompletionResponse,
    Message,
    StreamChunk,
    ToolCall,
    ToolSchema,
    Usage,
)

from .base import ProviderAdapter


class AnthropicAdapter(ProviderAdapter):

    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    def _extract_system(self, messages: list[Message]) -> tuple[str | None, list[Message]]:
        """Pull out system messages (Anthropic wants them separate)."""
        system_parts = []
        non_system = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.text)
            else:
                non_system.append(msg)
        system = "\n\n".join(system_parts) if system_parts else None
        return system, non_system

    def _build_content(self, msg: Message) -> str | list[dict]:
        if isinstance(msg.content, str):
            return msg.content
        if isinstance(msg.content, list):
            blocks = []
            for c in msg.content:
                if c.type == "text":
                    blocks.append({"type": "text", "text": c.text})
                elif c.type == "image_url":
                    blocks.append(
                        {
                            "type": "image",
                            "source": {"type": "url", "url": c.image_url},
                        }
                    )
                elif c.type == "image_base64":
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": c.media_type or "image/png",
                                "data": c.image_base64,
                            },
                        }
                    )
            return blocks
        return msg.content or ""

    def _build_messages(self, messages: list[Message]) -> list[dict]:
        result = []
        for msg in messages:
            if msg.role == "assistant" and msg.tool_calls:
                # Anthropic uses content blocks for tool_use
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.text})
                for tc in msg.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.name,
                            "input": tc.arguments,
                        }
                    )
                result.append({"role": "assistant", "content": content})
            elif msg.role == "tool":
                # Anthropic uses tool_result content blocks inside a user message
                result.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": msg.tool_call_id,
                                "content": msg.text,
                            }
                        ],
                    }
                )
            else:
                result.append(
                    {"role": msg.role, "content": self._build_content(msg)}
                )
        return result

    def _build_tools(self, tools: list[ToolSchema]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.parameters,
            }
            for t in tools
        ]

    def _parse_response(self, data: dict, latency_ms: int) -> CompletionResponse:
        content_blocks = data.get("content", [])
        text_parts = []
        tool_calls = []

        for block in content_blocks:
            if block["type"] == "text":
                text_parts.append(block["text"])
            elif block["type"] == "tool_use":
                tool_calls.append(
                    ToolCall(
                        id=block["id"],
                        name=block["name"],
                        arguments=block.get("input", {}),
                    )
                )

        finish = data.get("stop_reason", "end_turn")
        if finish == "end_turn":
            finish = "stop"
        elif finish == "tool_use":
            finish = "tool_calls"

        usage_data = data.get("usage", {})
        message = Message(
            role="assistant",
            content="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls if tool_calls else None,
        )
        usage = Usage(
            prompt_tokens=usage_data.get("input_tokens", 0),
            completion_tokens=usage_data.get("output_tokens", 0),
            total_tokens=usage_data.get("input_tokens", 0)
            + usage_data.get("output_tokens", 0),
        )
        return CompletionResponse(
            message=message,
            usage=usage,
            model=data.get("model", ""),
            finish_reason=finish,
            latency_ms=latency_ms,
            provider="anthropic",
            raw=data,
        )

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> CompletionResponse:
        system, msgs = self._extract_system(messages)
        body: dict = {
            "model": model,
            "messages": self._build_messages(msgs),
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = self._build_tools(tools)
        if stop:
            body["stop_sequences"] = stop

        start = time.monotonic()
        resp = await self._client.post("/v1/messages", json=body)
        latency_ms = int((time.monotonic() - start) * 1000)
        resp.raise_for_status()
        return self._parse_response(resp.json(), latency_ms)

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stop: list[str] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        system, msgs = self._extract_system(messages)
        body: dict = {
            "model": model,
            "messages": self._build_messages(msgs),
            "max_tokens": max_tokens or 4096,
            "temperature": temperature,
            "stream": True,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = self._build_tools(tools)
        if stop:
            body["stop_sequences"] = stop

        tool_accum: dict[str, dict] = {}  # tool_use_id -> {name, input_json}

        async with self._client.stream("POST", "/v1/messages", json=body) as resp:
            resp.raise_for_status()
            current_event = ""
            async for line in resp.aiter_lines():
                if line.startswith("event: "):
                    current_event = line[7:]
                    continue
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                if current_event == "content_block_start":
                    block = data.get("content_block", {})
                    if block.get("type") == "tool_use":
                        tool_accum[block["id"]] = {
                            "name": block.get("name", ""),
                            "input_json": "",
                        }
                elif current_event == "content_block_delta":
                    delta = data.get("delta", {})
                    if delta.get("type") == "text_delta":
                        yield StreamChunk(delta_text=delta.get("text"))
                    elif delta.get("type") == "input_json_delta":
                        # Find which tool this belongs to
                        data.get("index", 0)
                        # Accumulate JSON string
                        for tid, td in tool_accum.items():
                            td["input_json"] += delta.get("partial_json", "")
                            break  # Only one active at a time
                elif current_event == "message_delta":
                    delta = data.get("delta", {})
                    stop_reason = delta.get("stop_reason")
                    if stop_reason == "tool_use" and tool_accum:
                        calls = []
                        for tid, td in tool_accum.items():
                            try:
                                args = json.loads(td["input_json"])
                            except json.JSONDecodeError:
                                args = {"_raw": td["input_json"]}
                            calls.append(
                                ToolCall(id=tid, name=td["name"], arguments=args)
                            )
                        yield StreamChunk(
                            delta_tool_calls=calls, finish_reason="tool_calls"
                        )
                    elif stop_reason == "end_turn":
                        yield StreamChunk(finish_reason="stop")
                    usage_data = data.get("usage", {})
                    if usage_data:
                        yield StreamChunk(
                            usage=Usage(
                                prompt_tokens=usage_data.get("input_tokens", 0),
                                completion_tokens=usage_data.get("output_tokens", 0),
                                total_tokens=usage_data.get("input_tokens", 0)
                                + usage_data.get("output_tokens", 0),
                            )
                        )

    async def close(self):
        await self._client.aclose()
