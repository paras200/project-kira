"""Tests for provider adapters — message building and response parsing."""

from __future__ import annotations

import json

from kira.core.models import Message, ToolCall, ToolSchema
from kira.core.providers.anthropic_adapter import AnthropicAdapter
from kira.core.providers.openai_compat import OpenAICompatibleAdapter


class TestOpenAICompatibleAdapter:
    def setup_method(self):
        self.adapter = OpenAICompatibleAdapter(
            base_url="https://test.example.com/v1",
            api_key="test-key",
            provider_name="test",
        )

    def test_build_simple_messages(self):
        msgs = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there"),
        ]
        built = self.adapter._build_messages(msgs)
        assert len(built) == 3
        assert built[0] == {"role": "system", "content": "You are helpful"}
        assert built[1] == {"role": "user", "content": "Hello"}
        assert built[2] == {"role": "assistant", "content": "Hi there"}

    def test_build_tool_call_message(self):
        msg = Message(
            role="assistant",
            content="Let me check",
            tool_calls=[ToolCall(id="tc1", name="terminal", arguments={"command": "ls"})],
        )
        built = self.adapter._build_messages([msg])
        assert built[0]["tool_calls"][0]["id"] == "tc1"
        assert built[0]["tool_calls"][0]["function"]["name"] == "terminal"
        assert json.loads(built[0]["tool_calls"][0]["function"]["arguments"]) == {"command": "ls"}

    def test_build_tool_result_message(self):
        msg = Message(
            role="tool", content="file1.py\nfile2.py", tool_call_id="tc1", name="terminal"
        )
        built = self.adapter._build_messages([msg])
        assert built[0]["role"] == "tool"
        assert built[0]["tool_call_id"] == "tc1"
        assert built[0]["name"] == "terminal"

    def test_build_body_with_tools(self):
        msgs = [Message(role="user", content="hi")]
        tools = [
            ToolSchema(
                name="test",
                description="test tool",
                parameters={"type": "object", "properties": {}},
            )
        ]
        body = self.adapter._build_body(msgs, tools, "gpt-4", 0.7, None, None)
        assert body["model"] == "gpt-4"
        assert len(body["tools"]) == 1
        assert body["tools"][0]["function"]["name"] == "test"

    def test_build_body_streaming(self):
        msgs = [Message(role="user", content="hi")]
        body = self.adapter._build_body(msgs, None, "gpt-4", 0.7, None, None, stream=True)
        assert body["stream"] is True
        assert body["stream_options"] == {"include_usage": True}

    def test_parse_tool_calls(self):
        raw = [
            {
                "id": "tc1",
                "function": {"name": "terminal", "arguments": '{"command": "ls"}'},
            }
        ]
        parsed = self.adapter._parse_tool_calls(raw)
        assert len(parsed) == 1
        assert parsed[0].name == "terminal"
        assert parsed[0].arguments == {"command": "ls"}

    def test_parse_tool_calls_bad_json(self):
        raw = [{"id": "tc1", "function": {"name": "test", "arguments": "not json"}}]
        parsed = self.adapter._parse_tool_calls(raw)
        assert parsed[0].arguments == {"_raw": "not json"}

    def test_parse_response(self):
        data = {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "Hello!"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
            },
            "model": "gpt-4",
        }
        resp = self.adapter._parse_response(data, latency_ms=100)
        assert resp.message.content == "Hello!"
        assert resp.usage.prompt_tokens == 10
        assert resp.finish_reason == "stop"
        assert resp.latency_ms == 100
        assert resp.provider == "test"


class TestAnthropicAdapter:
    def setup_method(self):
        self.adapter = AnthropicAdapter(api_key="test-key")

    def test_extract_system(self):
        msgs = [
            Message(role="system", content="Be helpful"),
            Message(role="user", content="Hi"),
        ]
        system, non_system = self.adapter._extract_system(msgs)
        assert system == "Be helpful"
        assert len(non_system) == 1
        assert non_system[0].role == "user"

    def test_extract_multiple_system(self):
        msgs = [
            Message(role="system", content="Rule 1"),
            Message(role="system", content="Rule 2"),
            Message(role="user", content="Hi"),
        ]
        system, non_system = self.adapter._extract_system(msgs)
        assert "Rule 1" in system
        assert "Rule 2" in system
        assert len(non_system) == 1

    def test_build_tool_use_message(self):
        msg = Message(
            role="assistant",
            content="Checking...",
            tool_calls=[ToolCall(id="tc1", name="search", arguments={"q": "test"})],
        )
        built = self.adapter._build_messages([msg])
        assert built[0]["role"] == "assistant"
        content = built[0]["content"]
        assert content[0]["type"] == "text"
        assert content[1]["type"] == "tool_use"
        assert content[1]["name"] == "search"

    def test_build_tool_result_message(self):
        msg = Message(role="tool", content="result data", tool_call_id="tc1")
        built = self.adapter._build_messages([msg])
        assert built[0]["role"] == "user"
        assert built[0]["content"][0]["type"] == "tool_result"
        assert built[0]["content"][0]["tool_use_id"] == "tc1"

    def test_build_tools_format(self):
        tools = [
            ToolSchema(
                name="test",
                description="desc",
                parameters={"type": "object", "properties": {"x": {"type": "string"}}},
            )
        ]
        built = self.adapter._build_tools(tools)
        assert built[0]["name"] == "test"
        assert built[0]["input_schema"]["type"] == "object"

    def test_parse_response_text(self):
        data = {
            "content": [{"type": "text", "text": "Hello!"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
            "model": "claude-sonnet",
        }
        resp = self.adapter._parse_response(data, latency_ms=50)
        assert resp.message.content == "Hello!"
        assert resp.finish_reason == "stop"
        assert resp.usage.prompt_tokens == 10

    def test_parse_response_tool_use(self):
        data = {
            "content": [
                {"type": "text", "text": "Let me search"},
                {
                    "type": "tool_use",
                    "id": "tc1",
                    "name": "web_search",
                    "input": {"query": "test"},
                },
            ],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 20, "output_tokens": 30},
            "model": "claude-sonnet",
        }
        resp = self.adapter._parse_response(data, latency_ms=80)
        assert resp.finish_reason == "tool_calls"
        assert resp.message.tool_calls[0].name == "web_search"
        assert resp.message.tool_calls[0].arguments == {"query": "test"}
