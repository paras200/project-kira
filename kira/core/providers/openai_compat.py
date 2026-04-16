"""OpenAI-compatible provider adapter.

Covers: OpenRouter, OpenAI, Azure, Groq, Together, Fireworks, Ollama,
LM Studio, DeepSeek, Mistral, and any OpenAI-compatible endpoint.
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


class OpenAICompatibleAdapter(ProviderAdapter):

    name = "openai_compatible"

    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        default_headers: dict[str, str] | None = None,
        provider_name: str = "openai_compatible",
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.provider_name = provider_name
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if default_headers:
            headers.update(default_headers)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(120.0, connect=10.0),
        )

    def _build_messages(self, messages: list[Message]) -> list[dict]:
        result = []
        for msg in messages:
            m: dict = {"role": msg.role}
            if isinstance(msg.content, str):
                m["content"] = msg.content
            elif isinstance(msg.content, list):
                m["content"] = []
                for c in msg.content:
                    if c.type == "text":
                        m["content"].append({"type": "text", "text": c.text})
                    elif c.type == "image_url":
                        m["content"].append(
                            {"type": "image_url", "image_url": {"url": c.image_url}}
                        )
                    elif c.type == "image_base64":
                        m["content"].append(
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{c.media_type};base64,{c.image_base64}"
                                },
                            }
                        )
            else:
                m["content"] = msg.content

            if msg.tool_calls:
                m["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.tool_call_id:
                m["tool_call_id"] = msg.tool_call_id
            if msg.name:
                m["name"] = msg.name
            result.append(m)
        return result

    def _build_body(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None,
        model: str,
        temperature: float,
        max_tokens: int | None,
        stop: list[str] | None,
        stream: bool = False,
    ) -> dict:
        body: dict = {
            "model": model,
            "messages": self._build_messages(messages),
            "temperature": temperature,
            "stream": stream,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if stop:
            body["stop"] = stop
        if tools:
            body["tools"] = [t.to_openai_format() for t in tools]
        if stream:
            body["stream_options"] = {"include_usage": True}
        return body

    def _parse_tool_calls(self, raw_calls: list[dict]) -> list[ToolCall]:
        result = []
        for tc in raw_calls:
            fn = tc.get("function", {})
            args_str = fn.get("arguments", "{}")
            try:
                args = json.loads(args_str)
            except json.JSONDecodeError:
                args = {"_raw": args_str}
            result.append(
                ToolCall(id=tc.get("id", ""), name=fn.get("name", ""), arguments=args)
            )
        return result

    def _parse_response(self, data: dict, latency_ms: int) -> CompletionResponse:
        choice = data.get("choices", [{}])[0]
        msg_data = choice.get("message", {})
        usage_data = data.get("usage", {})

        tool_calls = None
        if msg_data.get("tool_calls"):
            tool_calls = self._parse_tool_calls(msg_data["tool_calls"])

        message = Message(
            role=msg_data.get("role", "assistant"),
            content=msg_data.get("content"),
            tool_calls=tool_calls,
        )
        usage = Usage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )
        return CompletionResponse(
            message=message,
            usage=usage,
            model=data.get("model", ""),
            finish_reason=choice.get("finish_reason", "stop"),
            latency_ms=latency_ms,
            provider=self.provider_name,
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
        body = self._build_body(messages, tools, model, temperature, max_tokens, stop)
        start = time.monotonic()
        resp = await self._client.post("/chat/completions", json=body)
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
        body = self._build_body(
            messages, tools, model, temperature, max_tokens, stop, stream=True
        )
        async with self._client.stream(
            "POST", "/chat/completions", json=body
        ) as resp:
            resp.raise_for_status()
            # Accumulate partial tool calls across chunks
            tool_call_accum: dict[int, dict] = {}

            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    # Flush any accumulated tool calls
                    if tool_call_accum:
                        calls = []
                        for tc_data in tool_call_accum.values():
                            args_str = tc_data.get("arguments", "")
                            try:
                                args = json.loads(args_str)
                            except json.JSONDecodeError:
                                args = {"_raw": args_str}
                            calls.append(
                                ToolCall(
                                    id=tc_data.get("id", ""),
                                    name=tc_data.get("name", ""),
                                    arguments=args,
                                )
                            )
                        yield StreamChunk(
                            delta_tool_calls=calls, finish_reason="tool_calls"
                        )
                    break

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                # Usage comes in the final chunk
                if data.get("usage"):
                    u = data["usage"]
                    yield StreamChunk(
                        usage=Usage(
                            prompt_tokens=u.get("prompt_tokens", 0),
                            completion_tokens=u.get("completion_tokens", 0),
                            total_tokens=u.get("total_tokens", 0),
                        )
                    )
                    continue

                choice = (data.get("choices") or [{}])[0]
                delta = choice.get("delta", {})
                finish = choice.get("finish_reason")

                # Accumulate tool call deltas
                if delta.get("tool_calls"):
                    for tc_delta in delta["tool_calls"]:
                        idx = tc_delta.get("index", 0)
                        if idx not in tool_call_accum:
                            tool_call_accum[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc_delta.get("id"):
                            tool_call_accum[idx]["id"] = tc_delta["id"]
                        fn = tc_delta.get("function", {})
                        if fn.get("name"):
                            tool_call_accum[idx]["name"] = fn["name"]
                        if fn.get("arguments"):
                            tool_call_accum[idx]["arguments"] += fn["arguments"]
                    continue

                text = delta.get("content")
                if text or finish:
                    yield StreamChunk(delta_text=text, finish_reason=finish)

    async def close(self):
        await self._client.aclose()
