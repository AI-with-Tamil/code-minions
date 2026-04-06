"""Transport openers for MCP sessions."""

from __future__ import annotations

import os
from contextlib import AsyncExitStack
from typing import Any

from minion.tools.mcp.compat import ensure_mcp_installed
from minion.tools.mcp.config import MCPServerConfig
from minion.tools.mcp.errors import MCPTransportError


async def open_mcp_streams(config: MCPServerConfig) -> tuple[Any, Any, AsyncExitStack]:
    ensure_mcp_installed()
    stack = AsyncExitStack()
    try:
        if config.transport == "stdio":
            from mcp import StdioServerParameters
            from mcp.client.stdio import stdio_client

            server = StdioServerParameters(
                command=config.command or "",
                args=list(config.args),
                env=(dict(os.environ) | config.env) if config.env else dict(os.environ),
                cwd=config.cwd,
            )
            read_stream, write_stream = await stack.enter_async_context(stdio_client(server))
            return read_stream, write_stream, stack

        if config.transport == "streamable_http":
            from httpx import AsyncClient
            from mcp.client.streamable_http import streamable_http_client

            http_client = AsyncClient(
                headers=config.headers,
                timeout=config.timeout_seconds,
                auth=config.http_auth,
            )
            http_client = await stack.enter_async_context(http_client)
            read_stream, write_stream, _ = await stack.enter_async_context(
                streamable_http_client(
                    config.url or "",
                    http_client=http_client,
                    terminate_on_close=config.terminate_on_close,
                )
            )
            return read_stream, write_stream, stack

        from mcp.client.sse import sse_client

        read_stream, write_stream = await stack.enter_async_context(
            sse_client(
                config.url or "",
                headers=config.headers,
                timeout=config.timeout_seconds,
                sse_read_timeout=config.sse_read_timeout,
                auth=config.http_auth,
            )
        )
        return read_stream, write_stream, stack
    except Exception as exc:
        await stack.aclose()
        raise MCPTransportError(str(exc)) from exc
