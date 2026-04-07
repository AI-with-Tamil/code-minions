"""Result parsing helpers for MCP responses."""

from __future__ import annotations

import json
from typing import Any

from codeminions.tools.mcp.errors import MCPProtocolError


def render_call_tool_result(result: Any) -> str:
    parts: list[str] = []

    for item in getattr(result, "content", []):
        rendered = render_content_item(item)
        if rendered:
            parts.append(rendered)

    if parts:
        return "\n\n".join(parts)

    structured = getattr(result, "structuredContent", None)
    if structured is not None:
        return json.dumps(structured, indent=2, sort_keys=True)

    return ""


def render_resource_result(result: Any) -> str:
    parts = [render_resource_content(item) for item in getattr(result, "contents", [])]
    rendered = [part for part in parts if part]
    return "\n\n".join(rendered)


def render_prompt_result(result: Any) -> str:
    messages: list[str] = []
    description = getattr(result, "description", None)
    if description:
        messages.append(description)

    for message in getattr(result, "messages", []):
        role = getattr(message, "role", "assistant")
        content = render_content_item(getattr(message, "content", ""))
        messages.append(f"{role}: {content}")

    return "\n\n".join(part for part in messages if part)


def render_content_item(item: Any) -> str:
    if isinstance(item, str):
        return item

    item_type = getattr(item, "type", "")
    if item_type == "text":
        return str(getattr(item, "text", ""))
    if item_type == "image":
        mime_type = getattr(item, "mimeType", "application/octet-stream")
        data = getattr(item, "data", "")
        return f"[image content: {mime_type}, {len(str(data))} bytes]"
    if item_type == "audio":
        mime_type = getattr(item, "mimeType", "application/octet-stream")
        data = getattr(item, "data", "")
        return f"[audio content: {mime_type}, {len(str(data))} bytes]"
    if item_type in {"resource_link", "resource"}:
        return json.dumps(_dump_model(item), indent=2, sort_keys=True)

    if hasattr(item, "text"):
        return str(getattr(item, "text"))
    if hasattr(item, "data"):
        return json.dumps(_dump_model(item), indent=2, sort_keys=True)
    if hasattr(item, "model_dump"):
        return json.dumps(item.model_dump(mode="json"), indent=2, sort_keys=True)
    return str(item)


def render_resource_content(item: Any) -> str:
    text = getattr(item, "text", None)
    if text is not None:
        return str(text)

    blob = getattr(item, "blob", None)
    if blob is not None:
        mime_type = getattr(item, "mimeType", "application/octet-stream")
        return f"[blob resource: {mime_type}, {len(str(blob))} bytes]"

    if hasattr(item, "uri"):
        return json.dumps(_dump_model(item), indent=2, sort_keys=True)
    return str(item)


def require_successful_tool_result(result: Any) -> None:
    if getattr(result, "isError", False):
        raise MCPProtocolError(render_call_tool_result(result) or "MCP tool call failed")


def _dump_model(item: Any) -> dict[str, Any]:
    if not hasattr(item, "model_dump"):
        raise MCPProtocolError(f"Unsupported MCP content item: {item!r}")
    return item.model_dump(mode="json")
