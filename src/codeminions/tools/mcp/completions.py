"""Completion helpers for MCP prompts and resource templates."""

from __future__ import annotations

from typing import Any

from codeminions.tools.mcp.client import MCPClient, run_sync
from codeminions.tools.mcp.config import MCPServerConfig, resolve_mcp_server_config


def complete_mcp_prompt(
    server: str | MCPServerConfig,
    *,
    name: str,
    argument_name: str,
    argument_value: str,
    context_arguments: dict[str, str] | None = None,
    ctx: Any | None = None,
    **overrides: Any,
) -> list[str]:
    config = resolve_mcp_server_config(server=server, **overrides)

    async def _complete() -> list[str]:
        async with MCPClient(config, ctx=ctx) as client:
            result = await client.complete_prompt(
                name=name,
                argument_name=argument_name,
                argument_value=argument_value,
                context_arguments=context_arguments,
            )
            return list(result.completion.values)

    return run_sync(_complete())


def complete_mcp_resource_template(
    server: str | MCPServerConfig,
    *,
    uri_template: str,
    argument_name: str,
    argument_value: str,
    context_arguments: dict[str, str] | None = None,
    ctx: Any | None = None,
    **overrides: Any,
) -> list[str]:
    config = resolve_mcp_server_config(server=server, **overrides)

    async def _complete() -> list[str]:
        async with MCPClient(config, ctx=ctx) as client:
            result = await client.complete_resource_template(
                uri_template=uri_template,
                argument_name=argument_name,
                argument_value=argument_value,
                context_arguments=context_arguments,
            )
            return list(result.completion.values)

    return run_sync(_complete())
