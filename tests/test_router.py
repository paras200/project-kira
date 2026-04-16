"""Tests for model router and provider resolution."""

from __future__ import annotations

import pytest

from kira.core.router import ModelSpec


class TestModelSpec:
    def test_parse_two_parts(self):
        spec = ModelSpec.parse("ollama/llama3.1:8b")
        assert spec.provider == "ollama"
        assert spec.model == "llama3.1:8b"

    def test_parse_three_parts(self):
        spec = ModelSpec.parse("openrouter/anthropic/claude-sonnet-4-20250514")
        assert spec.provider == "openrouter"
        assert spec.model == "anthropic/claude-sonnet-4-20250514"

    def test_parse_invalid(self):
        with pytest.raises(ValueError, match="Invalid model spec"):
            ModelSpec.parse("just-a-model-name")


class TestModelRouter:
    def test_resolve_default(self, router):
        specs = router._resolve()
        assert specs[0].provider == "test"
        assert specs[0].model == "model-a"

    def test_resolve_with_override(self, router):
        specs = router._resolve(model_override="custom/my-model")
        assert specs[0].provider == "custom"
        assert specs[0].model == "my-model"
        # Default should still be in the list
        assert any(s.model == "model-a" for s in specs)

    def test_resolve_with_task_hint(self, router):
        specs = router._resolve(task_hint="summarize")
        assert specs[0].provider == "test"
        assert specs[0].model == "model-cheap"

    def test_resolve_unknown_task(self, router):
        specs = router._resolve(task_hint="unknown_task")
        # Falls back to default
        assert specs[0].model == "model-a"

    def test_resolve_deduplicates(self, router):
        specs = router._resolve()
        keys = [f"{s.provider}/{s.model}" for s in specs]
        assert len(keys) == len(set(keys))

    def test_fallback_chain_order(self, router):
        specs = router._resolve()
        assert specs[0].model == "model-a"  # default
        assert specs[1].model == "model-b"  # fallback

    def test_register_provider(self, router):
        from unittest.mock import MagicMock

        adapter = MagicMock()
        router.register("my_provider", adapter)
        assert "my_provider" in router.providers

    @pytest.mark.asyncio
    async def test_complete_no_providers_raises(self, router):
        from kira.core.models import Message

        with pytest.raises(RuntimeError, match="All providers failed"):
            await router.complete(messages=[Message(role="user", content="hi")])
