"""Model adapters."""

from codeminions.models._base import BaseModelProtocol, Message, ModelResponse, ToolCall, ToolSchema
from codeminions.models.claude import ClaudeModel
from codeminions.models.openai import OpenAIModel

__all__ = [
    "BaseModelProtocol",
    "ClaudeModel",
    "Message",
    "ModelResponse",
    "OpenAIModel",
    "ToolCall",
    "ToolSchema",
]
