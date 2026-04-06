"""Resource helpers for MCP servers."""

from __future__ import annotations

from typing import Any

from minion.tools.mcp.client import MCPClient, run_sync
from minion.tools.mcp.config import MCPServerConfig, resolve_mcp_server_config
from minion.tools.mcp.parsing import render_resource_result


def list_mcp_resources(
    server: str | MCPServerConfig,
    *,
    ctx: Any | None = None,
    **overrides: Any,
) -> list[Any]:
    config = resolve_mcp_server_config(server=server, **overrides)

    async def _list() -> list[Any]:
        async with MCPClient(config, ctx=ctx) as client:
            return await client.list_resources()

    return run_sync(_list())


def read_mcp_resource(
    server: str | MCPServerConfig,
    uri: str,
    *,
    ctx: Any | None = None,
    **overrides: Any,
) -> str:
    config = resolve_mcp_server_config(server=server, **overrides)

    async def _read() -> str:
        async with MCPClient(config, ctx=ctx) as client:
            result = await client.read_resource(uri)
            return render_resource_result(result)

    return run_sync(_read())
