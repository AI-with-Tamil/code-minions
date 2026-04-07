"""ClaudeModel — Anthropic Claude adapter."""

from __future__ import annotations

import os
from pathlib import Path

from codeminions._internal.env import load_env_file
from codeminions.models._base import Message, ModelResponse, ToolCall, ToolSchema


class ClaudeModel:
    """Anthropic Claude LLM adapter."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        base_url: str | None = None,
        max_tokens: int = 8096,
        temperature: float = 1.0,
    ) -> None:
        load_env_file(Path.cwd() / ".env")
        self.model = _resolve_anthropic_model_alias(model)
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.auth_token = os.environ.get("ANTHROPIC_API_TOKEN", "")
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "")
        self.max_tokens = max_tokens
        self.temperature = temperature

    async def call(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
        system: str,
        max_tokens: int,
    ) -> ModelResponse:
        try:
            import anthropic
        except ImportError:
            raise ImportError(
                "ClaudeModel requires the 'anthropic' package. "
                "Install with: uv add --optional claude anthropic"
            )

        if not self.api_key:
            if not self.auth_token:
                raise RuntimeError(
                    "No Anthropic credentials. Set ANTHROPIC_API_KEY or ANTHROPIC_API_TOKEN, "
                    "or pass api_key= to ClaudeModel."
                )

        client_kwargs: dict[str, str] = {}
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        if self.auth_token:
            client_kwargs["auth_token"] = self.auth_token
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        client = anthropic.AsyncAnthropic(**client_kwargs)

        # Convert messages
        api_messages = []
        for msg in messages:
            if msg.role == "tool":
                api_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.tool_call_id,
                        "content": msg.content,
                    }],
                })
            elif msg.role == "assistant" and msg.tool_calls:
                content = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tc in msg.tool_calls:
                    content.append({
                        "type": "tool_use",
                        "id": tc.id,
                        "name": tc.name,
                        "input": tc.args,
                    })
                api_messages.append({"role": "assistant", "content": content})
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        # Convert tools
        api_tools = []
        for t in tools:
            api_tools.append({
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            })

        resp = await client.messages.create(
            model=self.model,
            max_tokens=max_tokens or self.max_tokens,
            temperature=self.temperature,
            system=system,
            messages=api_messages,
            tools=api_tools if api_tools else anthropic.NOT_GIVEN,
        )

        # Parse response
        tool_calls = []
        text_parts = []
        for block in resp.content:
            if block.type == "tool_use":
                tool_calls.append(ToolCall(
                    name=block.name,
                    args=block.input,
                    id=block.id,
                ))
            elif block.type == "text":
                text_parts.append(block.text)

        stop_reason = "end_turn"
        if resp.stop_reason == "tool_use":
            stop_reason = "tool_use"
        elif resp.stop_reason == "max_tokens":
            stop_reason = "max_tokens"

        return ModelResponse(
            tool_calls=tool_calls,
            text="\n".join(text_parts),
            stop_reason=stop_reason,
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
        )


def _resolve_anthropic_model_alias(model: str) -> str:
    if model.startswith("claude") or model.startswith("anthropic"):
        lowered = model.lower()
        if "haiku" in lowered:
            return os.environ.get("ANTHROPIC_HAIKU_MODEL", model)
        if "opus" in lowered:
            return os.environ.get("ANTHROPIC_OPUS_MODEL", model)
        if "sonnet" in lowered:
            return os.environ.get("ANTHROPIC_SONNET_MODEL", model)
    return model
