"""Tool adaptation from MCP into Minion Tool instances."""

from __future__ import annotations

from typing import Any

from codeminions.core.tool import Tool, ToolOutputPolicy
from codeminions.tools.mcp.client import MCPClient, run_sync
from codeminions.tools.mcp.config import MCPServerConfig, Transport, resolve_mcp_server_config
from codeminions.tools.mcp.errors import MCPConfigurationError
from codeminions.tools.mcp.parsing import render_call_tool_result, require_successful_tool_result


def mcp_tools(
    server: str | MCPServerConfig,
    tools: list[str] | None = None,
    *,
    transport: Transport | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
    sse_read_timeout: float | None = None,
    read_timeout_seconds: float | None = None,
    terminate_on_close: bool | None = None,
    roots: list[str] | None = None,
    http_auth: Any | None = None,
    sampling_callback: Any | None = None,
    elicitation_callback: Any | None = None,
    logging_callback: Any | None = None,
    message_handler: Any | None = None,
) -> list[Tool]:
    """Load tools from an MCP server."""
    config = resolve_mcp_server_config(
        server=server,
        transport=transport,
        command=command,
        args=args,
        env=env,
        cwd=cwd,
        url=url,
        headers=headers,
        timeout_seconds=timeout_seconds,
        sse_read_timeout=sse_read_timeout,
        read_timeout_seconds=read_timeout_seconds,
        terminate_on_close=terminate_on_close,
        roots=roots,
        http_auth=http_auth,
        sampling_callback=sampling_callback,
        elicitation_callback=elicitation_callback,
        logging_callback=logging_callback,
        message_handler=message_handler,
    )

    tool_names = set(tools) if tools else None
    discovered = run_sync(_list_tools(config))

    loaded: list[Tool] = []
    missing = set(tool_names or [])
    for remote_tool in discovered:
        if tool_names is not None and remote_tool.name not in tool_names:
            continue
        missing.discard(remote_tool.name)
        loaded.append(_adapt_mcp_tool(config, remote_tool))

    if missing:
        available = ", ".join(sorted(t.name for t in discovered)) or "<none>"
        wanted = ", ".join(sorted(missing))
        raise MCPConfigurationError(
            f"MCP server requested unknown tools: {wanted}. Available tools: {available}"
        )

    return loaded


async def _list_tools(config: MCPServerConfig) -> list[Any]:
    async with MCPClient(config) as client:
        return await client.list_tools()


def _adapt_mcp_tool(config: MCPServerConfig, remote_tool: Any) -> Tool:
    async def _call(ctx: Any, **kwargs: Any) -> str:
        async with MCPClient(config, ctx=ctx) as client:
            result = await client.call_tool(remote_tool.name, kwargs)
        require_successful_tool_result(result)
        return render_call_tool_result(result)

    input_schema = dict(remote_tool.inputSchema or {"type": "object"})
    properties = dict(input_schema.get("properties") or {})
    required = [str(item) for item in input_schema.get("required") or []]
    title = remote_tool.title or remote_tool.name
    description = remote_tool.description or f"MCP tool '{title}'"

    return Tool(
        name=remote_tool.name,
        description=description,
        fn=_call,
        parameters=properties,
        required=required,
        input_schema=input_schema,
        output_policy=ToolOutputPolicy(),
        is_async=True,
    )
