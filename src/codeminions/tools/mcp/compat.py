"""Compatibility helpers for the MCP Python SDK."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from codeminions.tools.mcp.errors import MCPConfigurationError


def mcp_sdk_version() -> str:
    try:
        return version("mcp")
    except PackageNotFoundError:
        return "unknown"


def ensure_mcp_installed() -> None:
    try:
        import mcp  # noqa: F401
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise MCPConfigurationError(
            "MCP support requires the optional dependency group. "
            "Install with: uv add --optional mcp mcp"
        ) from exc
