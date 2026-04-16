"""Model router — picks the right provider+model and handles fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import AsyncIterator

from kira.core.models import (
    CompletionResponse,
    Message,
    StreamChunk,
    ToolSchema,
)
from kira.core.providers.base import ProviderAdapter

logger = logging.getLogger(__name__)


@dataclass
class ModelSpec:
    """A provider/model pair like 'openrouter/anthropic/claude-sonnet-4-20250514'."""

    provider: str
    model: str

    @classmethod
    def parse(cls, spec: str) -> "ModelSpec":
        """Parse 'provider/model' string. First segment is provider, rest is model."""
        parts = spec.split("/", 1)
        if len(parts) == 1:
            raise ValueError(
                f"Invalid model spec '{spec}'. Expected 'provider/model'."
            )
        return cls(provider=parts[0], model=parts[1])


class ModelRouter:
    """Routes LLM requests to the right provider with fallback."""

    def __init__(
        self,
        default: str,
        fallback_chain: list[str] | None = None,
        task_routing: dict[str, str] | None = None,
    ):
        self.default = ModelSpec.parse(default)
        self.fallback_chain = [ModelSpec.parse(s) for s in (fallback_chain or [])]
        self.task_routing = {
            k: ModelSpec.parse(v) for k, v in (task_routing or {}).items()
        }
        self.providers: dict[str, ProviderAdapter] = {}

    def register(self, name: str, adapter: ProviderAdapter):
        self.providers[name] = adapter

    def _resolve(
        self, model_override: str | None = None, task_hint: str | None = None
    ) -> list[ModelSpec]:
        """Build ordered list of models to try."""
        specs = []

        if model_override:
            specs.append(ModelSpec.parse(model_override))
        elif task_hint and task_hint in self.task_routing:
            specs.append(self.task_routing[task_hint])

        specs.append(self.default)
        specs.extend(self.fallback_chain)

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for s in specs:
            key = f"{s.provider}/{s.model}"
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique

    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model_override: str | None = None,
        task_hint: str | None = None,
        **kwargs,
    ) -> CompletionResponse:
        specs = self._resolve(model_override, task_hint)
        last_err = None

        for spec in specs:
            adapter = self.providers.get(spec.provider)
            if not adapter:
                logger.warning(f"Provider '{spec.provider}' not registered, skipping")
                continue
            try:
                resp = await adapter.complete(
                    messages=messages, tools=tools, model=spec.model, **kwargs
                )
                resp.provider = spec.provider
                return resp
            except Exception as e:
                logger.warning(
                    f"Provider {spec.provider}/{spec.model} failed: {e}"
                )
                last_err = e

        raise RuntimeError(
            f"All providers failed. Last error: {last_err}"
        )

    async def stream(
        self,
        messages: list[Message],
        tools: list[ToolSchema] | None = None,
        model_override: str | None = None,
        task_hint: str | None = None,
        **kwargs,
    ) -> AsyncIterator[StreamChunk]:
        specs = self._resolve(model_override, task_hint)
        last_err = None

        for spec in specs:
            adapter = self.providers.get(spec.provider)
            if not adapter:
                continue
            try:
                async for chunk in adapter.stream(
                    messages=messages, tools=tools, model=spec.model, **kwargs
                ):
                    yield chunk
                return
            except Exception as e:
                logger.warning(
                    f"Provider {spec.provider}/{spec.model} failed: {e}"
                )
                last_err = e

        raise RuntimeError(f"All providers failed. Last error: {last_err}")

    async def close(self):
        for adapter in self.providers.values():
            await adapter.close()
