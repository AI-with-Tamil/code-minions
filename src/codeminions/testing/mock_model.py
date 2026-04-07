"""MockModel — replays scripted responses. No API calls."""

from __future__ import annotations

from codeminions.models._base import Message, ModelResponse, ToolSchema


class MockExhaustedError(Exception):
    """Raised when MockModel has no more responses to return."""


class MockModel:
    """Replays a scripted sequence of responses. No API calls.

    Responses consumed in order. If responses exhausted before done() called,
    raises MockExhaustedError.
    """

    def __init__(self, responses: list[ModelResponse] | None = None) -> None:
        self._responses = list(responses) if responses else []
        self._position = 0

    async def call(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
        system: str,
        max_tokens: int,
    ) -> ModelResponse:
        if self._position >= len(self._responses):
            raise MockExhaustedError(
                f"MockModel exhausted: {self._position} responses consumed, "
                f"no more available. Ensure done() is called in the script."
            )
        response = self._responses[self._position]
        self._position += 1
        return response
