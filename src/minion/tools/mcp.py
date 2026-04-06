"""MCP tool loader — loads tools from MCP servers as Tool instances."""

from __future__ import annotations

from minion.core.tool import Tool


def mcp_tools(server: str, tools: list[str] | None = None) -> list[Tool]:
    """Load tools from an MCP server.

    Args:
        server: MCP server name (e.g. "github", "sourcegraph")
        tools: Optional list of tool names to load. None = load all.

    Returns:
        List of Tool instances with the same contract as @tool-decorated functions.
    """
    # TODO: Implement MCP client integration
    raise NotImplementedError(
        f"MCP tool loading for server '{server}' not yet implemented. "
        f"Install with: uv add --optional mcp mcp"
    )
