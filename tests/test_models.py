"""Tests for core data models."""

from __future__ import annotations

from kira.core.models import (
    Content,
    Message,
    ToolCall,
    ToolResult,
    ToolSchema,
    TurnBudget,
    Usage,
)


class TestMessage:
    def test_text_from_string_content(self):
        msg = Message(role="user", content="hello")
        assert msg.text == "hello"

    def test_text_from_content_blocks(self):
        msg = Message(
            role="user",
            content=[
                Content(type="text", text="hello"),
                Content(type="text", text="world"),
            ],
        )
        assert msg.text == "hello world"

    def test_text_from_none(self):
        msg = Message(role="assistant", content=None)
        assert msg.text == ""

    def test_message_with_tool_calls(self):
        tc = ToolCall(id="tc1", name="terminal", arguments={"command": "ls"})
        msg = Message(role="assistant", content="running command", tool_calls=[tc])
        assert msg.tool_calls[0].name == "terminal"
        assert msg.tool_calls[0].arguments == {"command": "ls"}

    def test_tool_message(self):
        msg = Message(role="tool", content="output", tool_call_id="tc1", name="terminal")
        assert msg.role == "tool"
        assert msg.tool_call_id == "tc1"


class TestToolSchema:
    def test_to_openai_format(self):
        schema = ToolSchema(
            name="test_tool",
            description="A test tool",
            parameters={"type": "object", "properties": {"x": {"type": "string"}}},
        )
        fmt = schema.to_openai_format()
        assert fmt["type"] == "function"
        assert fmt["function"]["name"] == "test_tool"
        assert fmt["function"]["description"] == "A test tool"
        assert "x" in fmt["function"]["parameters"]["properties"]


class TestTurnBudget:
    def test_not_exhausted_initially(self):
        budget = TurnBudget()
        assert not budget.is_exhausted()

    def test_exhausted_by_iterations(self):
        budget = TurnBudget(max_iterations=2)
        budget.record(Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        budget.record(Usage(prompt_tokens=100, completion_tokens=50, total_tokens=150))
        assert budget.is_exhausted()

    def test_exhausted_by_tokens(self):
        budget = TurnBudget(max_input_tokens=500)
        budget.record(Usage(prompt_tokens=600, completion_tokens=0, total_tokens=600))
        assert budget.is_exhausted()

    def test_exhausted_by_cost(self):
        budget = TurnBudget(max_cost_usd=0.50)
        budget.record(Usage(), cost=0.60)
        assert budget.is_exhausted()

    def test_tracks_cumulative(self):
        budget = TurnBudget()
        budget.record(Usage(prompt_tokens=100), cost=0.01)
        budget.record(Usage(prompt_tokens=200), cost=0.02)
        assert budget.current_iterations == 2
        assert budget.current_input_tokens == 300
        assert budget.current_cost == 0.03


class TestUsage:
    def test_defaults(self):
        u = Usage()
        assert u.prompt_tokens == 0
        assert u.completion_tokens == 0
        assert u.total_tokens == 0


class TestToolResult:
    def test_success(self):
        r = ToolResult(success=True, output="done", outcome={"key": "val"})
        assert r.success
        assert r.output == "done"
        assert r.outcome["key"] == "val"

    def test_failure(self):
        r = ToolResult(success=False, output="error")
        assert not r.success
        assert r.outcome is None
