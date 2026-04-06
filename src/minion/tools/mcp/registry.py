"""In-process registry for named MCP server configs."""

from __future__ import annotations

from minion.tools.mcp.errors import MCPConfigurationError


_SERVER_REGISTRY: dict[str, object] = {}


def register_mcp_server(name: str, config: object) -> None:
    """Register a named MCP server for later use."""
    _SERVER_REGISTRY[name] = config


def get_registered_mcp_server(name: str) -> object:
    """Return a registered MCP server config or raise."""
    if name not in _SERVER_REGISTRY:
        raise MCPConfigurationError(f"No registered MCP server named '{name}'")
    return _SERVER_REGISTRY[name]


def has_registered_mcp_server(name: str) -> bool:
    return name in _SERVER_REGISTRY
