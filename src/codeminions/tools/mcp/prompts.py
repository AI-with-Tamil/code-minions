"""Prompt helpers for MCP servers."""

from __future__ import annotations

from typing import Any

from codeminions.tools.mcp.client import MCPClient, run_sync
from codeminions.tools.mcp.config import MCPServerConfig, resolve_mcp_server_config
from codeminions.tools.mcp.parsing import render_prompt_result


def list_mcp_prompts(
    server: str | MCPServerConfig,
    *,
    ctx: Any | None = None,
    **overrides: Any,
) -> list[Any]:
    config = resolve_mcp_server_config(server=server, **overrides)

    async def _list() -> list[Any]:
        async with MCPClient(config, ctx=ctx) as client:
            return await client.list_prompts()

    return run_sync(_list())


def get_mcp_prompt(
    server: str | MCPServerConfig,
    name: str,
    arguments: dict[str, str] | None = None,
    *,
    ctx: Any | None = None,
    **overrides: Any,
) -> str:
    config = resolve_mcp_server_config(server=server, **overrides)

    async def _get() -> str:
        async with MCPClient(config, ctx=ctx) as client:
            result = await client.get_prompt(name, arguments=arguments)
            return render_prompt_result(result)

    return run_sync(_get())
