"""Display helpers for MCP metadata."""

from __future__ import annotations

from typing import Any


def get_mcp_display_name(obj: Any) -> str:
    """Return the best display name for a tool/resource/prompt/template."""
    try:
        from mcp.shared.metadata_utils import get_display_name

        return get_display_name(obj)
    except Exception:
        title = getattr(obj, "title", None)
        if title:
            return str(title)
        annotations = getattr(obj, "annotations", None)
        annotation_title = getattr(annotations, "title", None) if annotations else None
        if annotation_title:
            return str(annotation_title)
        return str(getattr(obj, "name", getattr(obj, "uri", "<unknown>")))
