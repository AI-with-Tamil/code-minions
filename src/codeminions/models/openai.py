"""OpenAIModel — OpenAI adapter."""

from __future__ import annotations

import os

from codeminions.models._base import Message, ModelResponse, ToolCall, ToolSchema


class OpenAIModel:
    """OpenAI LLM adapter."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 1.0,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
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
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError(
                "OpenAIModel requires the 'openai' package. "
                "Install with: uv add --optional openai openai"
            )

        if not self.api_key:
            raise RuntimeError(
                "No OpenAI API key. Set OPENAI_API_KEY or pass api_key= to OpenAIModel."
            )

        client = AsyncOpenAI(api_key=self.api_key)

        # Convert messages — prepend system as first message
        api_messages: list[dict] = [{"role": "system", "content": system}]
        for msg in messages:
            if msg.role == "tool":
                api_messages.append({
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                })
            elif msg.role == "assistant" and msg.tool_calls:
                tool_calls_api = []
                for tc in msg.tool_calls:
                    import json
                    tool_calls_api.append({
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                    })
                api_messages.append({
                    "role": "assistant",
                    "content": msg.content or None,
                    "tool_calls": tool_calls_api,
                })
            else:
                api_messages.append({"role": msg.role, "content": msg.content})

        # Convert tools
        api_tools = []
        for t in tools:
            api_tools.append({
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            })

        kwargs: dict = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": self.temperature,
            "messages": api_messages,
        }
        if api_tools:
            kwargs["tools"] = api_tools

        resp = await client.chat.completions.create(**kwargs)
        choice = resp.choices[0]

        tool_calls = []
        if choice.message.tool_calls:
            import json
            for tc in choice.message.tool_calls:
                tool_calls.append(ToolCall(
                    name=tc.function.name,
                    args=json.loads(tc.function.arguments),
                    id=tc.id,
                ))

        stop_reason = "end_turn"
        if choice.finish_reason == "tool_calls":
            stop_reason = "tool_use"
        elif choice.finish_reason == "length":
            stop_reason = "max_tokens"

        return ModelResponse(
            tool_calls=tool_calls,
            text=choice.message.content or "",
            stop_reason=stop_reason,
            input_tokens=resp.usage.prompt_tokens if resp.usage else 0,
            output_tokens=resp.usage.completion_tokens if resp.usage else 0,
        )
