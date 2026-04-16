"""Internal message format. All providers normalize to these types."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Content:
    type: str  # "text" | "image_url" | "image_base64"
    text: str | None = None
    image_url: str | None = None
    image_base64: str | None = None
    media_type: str | None = None


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class Message:
    role: str  # "system" | "user" | "assistant" | "tool"
    content: str | list[Content] | None = None
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None
    metadata: dict[str, Any] | None = None

    @property
    def text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            return " ".join(c.text or "" for c in self.content if c.text)
        return ""


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass
class CompletionResponse:
    message: Message
    usage: Usage
    model: str
    finish_reason: str  # "stop" | "tool_calls" | "length"
    cost: float | None = None
    latency_ms: int = 0
    provider: str = ""
    raw: dict[str, Any] | None = None


@dataclass
class StreamChunk:
    delta_text: str | None = None
    delta_tool_calls: list[ToolCall] | None = None
    finish_reason: str | None = None
    usage: Usage | None = None


@dataclass
class ToolSchema:
    name: str
    description: str
    parameters: dict[str, Any]
    requires_approval: bool = False
    timeout_seconds: int = 30
    category: str = "general"

    def to_openai_format(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolResult:
    success: bool
    output: str
    outcome: dict[str, Any] | None = None


@dataclass
class ToolContext:
    session_id: str
    workspace: str
    rules: list[str] = field(default_factory=list)


@dataclass
class TurnBudget:
    max_iterations: int = 25
    max_input_tokens: int = 100_000
    max_output_tokens: int = 16_000
    max_cost_usd: float = 1.00
    current_iterations: int = 0
    current_input_tokens: int = 0
    current_cost: float = 0.0

    def is_exhausted(self) -> bool:
        return (
            self.current_iterations >= self.max_iterations
            or self.current_input_tokens >= self.max_input_tokens
            or self.current_cost >= self.max_cost_usd
        )

    def record(self, usage: Usage, cost: float | None = None):
        self.current_iterations += 1
        self.current_input_tokens += usage.prompt_tokens
        if cost:
            self.current_cost += cost
