"""Tool — typed, decorated functions the LLM agent can call."""

from __future__ import annotations

import asyncio
import inspect
import functools
from dataclasses import dataclass, field
from typing import Any, Callable, get_type_hints


class ToolDefinitionError(Exception):
    """Raised at import time when a @tool-decorated function violates the contract."""


@dataclass
class ToolOutputPolicy:
    max_chars: int = 50_000
    truncation_msg: str = "... [truncated, {remaining} chars omitted]"


@dataclass
class ToolResult:
    """What the runner returns to the model after a tool call."""
    id: str = ""
    content: str | None = None
    error: str | None = None
    recoverable: bool = True


@dataclass
class Tool:
    """A validated, schema-bearing tool the agent can call."""
    name: str
    description: str
    fn: Callable[..., Any]
    parameters: dict[str, Any]       # JSON Schema for params (excludes ctx)
    required: list[str]
    output_policy: ToolOutputPolicy = field(default_factory=ToolOutputPolicy)
    is_async: bool = False

    def schema(self) -> dict[str, Any]:
        """Return the tool schema sent to the model."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.parameters,
                "required": self.required,
            },
        }

    async def execute(self, ctx: Any, **kwargs: Any) -> ToolResult:
        """Execute the tool, catching errors and applying output policy."""
        try:
            if self.is_async:
                result = await self.fn(ctx, **kwargs)
            else:
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(
                    None, functools.partial(self.fn, ctx, **kwargs)
                )
            content = str(result) if result is not None else ""
            # Apply truncation
            if len(content) > self.output_policy.max_chars:
                remaining = len(content) - self.output_policy.max_chars
                msg = self.output_policy.truncation_msg.format(remaining=remaining)
                content = content[: self.output_policy.max_chars] + msg
            return ToolResult(content=content)
        except Exception as e:
            return ToolResult(error=str(e))


# Python type → JSON Schema type
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _python_type_to_json_schema(annotation: Any) -> dict[str, Any]:
    """Convert a Python type annotation to a JSON Schema fragment."""
    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        args = getattr(annotation, "__args__", ())
        items = _python_type_to_json_schema(args[0]) if args else {}
        return {"type": "array", "items": items}
    if origin is dict:
        return {"type": "object"}
    if annotation in _TYPE_MAP:
        return {"type": _TYPE_MAP[annotation]}
    return {"type": "string"}


def tool(
    description: str = "",
    output_policy: ToolOutputPolicy | None = None,
) -> Callable[[Callable[..., Any]], Tool]:
    """Decorator that converts a function into a Tool with schema generation.

    Rules enforced at decoration time:
    - First param must be `ctx` (RunContext)
    - No *args or **kwargs
    - All params must be typed
    - Return type must be typed
    """
    def decorator(fn: Callable[..., Any]) -> Tool:
        sig = inspect.signature(fn)
        params = list(sig.parameters.values())

        # Validate first param is ctx
        if not params or params[0].name != "ctx":
            raise ToolDefinitionError(
                f"Tool '{fn.__name__}': first parameter must be 'ctx: RunContext'"
            )

        # No *args / **kwargs
        for p in params:
            if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
                raise ToolDefinitionError(
                    f"Tool '{fn.__name__}': *args/**kwargs not allowed"
                )

        # Get type hints
        try:
            hints = get_type_hints(fn)
        except Exception:
            hints = fn.__annotations__

        # Validate all params typed (skip ctx)
        for p in params[1:]:
            if p.name not in hints:
                raise ToolDefinitionError(
                    f"Tool '{fn.__name__}': parameter '{p.name}' must have a type annotation"
                )

        # Validate return type
        if "return" not in hints:
            raise ToolDefinitionError(
                f"Tool '{fn.__name__}': must have a return type annotation"
            )

        # Build JSON schema for params (skip ctx)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in params[1:]:
            schema = _python_type_to_json_schema(hints[p.name])
            if p.default is not inspect.Parameter.empty:
                schema["default"] = p.default
            else:
                required.append(p.name)
            properties[p.name] = schema

        is_async = inspect.iscoroutinefunction(fn)

        return Tool(
            name=fn.__name__,
            description=description or fn.__doc__ or "",
            fn=fn,
            parameters=properties,
            required=required,
            output_policy=output_policy or ToolOutputPolicy(),
            is_async=is_async,
        )

    return decorator
