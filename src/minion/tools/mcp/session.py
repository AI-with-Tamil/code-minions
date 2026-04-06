"""Session lifecycle for MCP clients."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from minion.tools.mcp.compat import ensure_mcp_installed
from minion.tools.mcp.config import MCPServerConfig
from minion.tools.mcp.transport import open_mcp_streams


@dataclass
class MCPInitialization:
    server_info: Any | None = None
    capabilities: Any | None = None
    instructions: str | None = None
    protocol_version: str | None = None


@dataclass
class MCPSessionHandle:
    session: Any
    initialization: MCPInitialization


@asynccontextmanager
async def open_mcp_session(config: MCPServerConfig, ctx: Any | None = None) -> Any:
    ensure_mcp_installed()
    from mcp import ClientSession, types

    read_stream, write_stream, stack = await open_mcp_streams(config)
    try:
        roots = list(config.roots)
        if ctx is not None and hasattr(getattr(ctx, "env", None), "root"):
            env_root = getattr(ctx.env, "root")
            if env_root:
                roots.append(str(env_root))

        session = ClientSession(
            read_stream,
            write_stream,
            read_timeout_seconds=(
                timedelta(seconds=config.read_timeout_seconds)
                if config.read_timeout_seconds is not None
                else None
            ),
            sampling_callback=config.sampling_callback,
            elicitation_callback=config.elicitation_callback,
            logging_callback=config.logging_callback,
            message_handler=config.message_handler,
            list_roots_callback=((lambda: _list_roots_callback(roots)) if roots else None),
            client_info=types.Implementation(
                name="minion-sdk",
                version="0.1.0",
            ),
        )
        session = await stack.enter_async_context(session)
        result = await session.initialize()
        handle = MCPSessionHandle(
            session=session,
            initialization=MCPInitialization(
                server_info=getattr(result, "serverInfo", None),
                capabilities=getattr(result, "capabilities", None),
                instructions=getattr(result, "instructions", None),
                protocol_version=getattr(result, "protocolVersion", None),
            ),
        )
        yield handle
    finally:
        await stack.aclose()


async def _list_roots_callback(roots: list[str]) -> list[Any]:
    from mcp import types

    return [
        types.Root(uri=Path(root).resolve().as_uri(), name=Path(root).name or None)
        for root in roots
    ]
