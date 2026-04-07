"""BaseModelProtocol — structural typing for LLM adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str = ""


@dataclass
class Message:
    role: Literal["user", "assistant", "tool"]
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str = ""


@dataclass
class ToolSchema:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass
class ModelResponse:
    tool_calls: list[ToolCall] = field(default_factory=list)
    text: str = ""
    stop_reason: Literal["tool_use", "end_turn", "max_tokens"] = "end_turn"
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class BaseModelProtocol(Protocol):
    async def call(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
        system: str,
        max_tokens: int,
    ) -> ModelResponse: ...
