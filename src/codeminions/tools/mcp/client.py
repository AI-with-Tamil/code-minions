"""High-level MCP client wrapper for Minion."""

from __future__ import annotations

import asyncio
import threading
from queue import Queue
from typing import Any

from codeminions.tools.mcp.config import MCPServerConfig, resolve_mcp_server_config
from codeminions.tools.mcp.session import MCPInitialization, open_mcp_session


class MCPClient:
    """Thin convenience wrapper around an MCP ClientSession."""

    def __init__(self, config: MCPServerConfig, *, ctx: Any | None = None) -> None:
        self.config = config
        self.ctx = ctx
        self.initialization = MCPInitialization()
        self._handle: Any | None = None
        self._manager: Any | None = None

    @classmethod
    def from_server(
        cls,
        server: str | MCPServerConfig,
        *,
        ctx: Any | None = None,
        **overrides: Any,
    ) -> "MCPClient":
        config = resolve_mcp_server_config(server=server, **overrides)
        return cls(config, ctx=ctx)

    async def __aenter__(self) -> "MCPClient":
        self._manager = open_mcp_session(self.config, ctx=self.ctx)
        self._handle = await self._manager.__aenter__()
        self.initialization = self._handle.initialization
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._manager is not None:
            await self._manager.__aexit__(exc_type, exc, tb)
        self._manager = None
        self._handle = None

    @property
    def session(self) -> Any:
        if self._handle is None:
            raise RuntimeError("MCPClient session is not open")
        return self._handle.session

    async def list_tools(self) -> list[Any]:
        return await _collect_paginated(self.session.list_tools, "tools")

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        return await self.session.call_tool(name, arguments=arguments or {})

    async def list_resources(self) -> list[Any]:
        return await _collect_paginated(self.session.list_resources, "resources")

    async def list_resource_templates(self) -> list[Any]:
        return await _collect_paginated(self.session.list_resource_templates, "resourceTemplates")

    async def read_resource(self, uri: str) -> Any:
        return await self.session.read_resource(uri)

    async def subscribe_resource(self, uri: str) -> Any:
        return await self.session.subscribe_resource(uri)

    async def unsubscribe_resource(self, uri: str) -> Any:
        return await self.session.unsubscribe_resource(uri)

    async def list_prompts(self) -> list[Any]:
        return await _collect_paginated(self.session.list_prompts, "prompts")

    async def get_prompt(self, name: str, arguments: dict[str, str] | None = None) -> Any:
        return await self.session.get_prompt(name, arguments=arguments or {})

    async def complete_prompt(
        self,
        *,
        name: str,
        argument_name: str,
        argument_value: str,
        context_arguments: dict[str, str] | None = None,
    ) -> Any:
        from mcp import types

        return await self.session.complete(
            ref=types.PromptReference(type="ref/prompt", name=name),
            argument={"name": argument_name, "value": argument_value},
            context_arguments=context_arguments,
        )

    async def complete_resource_template(
        self,
        *,
        uri_template: str,
        argument_name: str,
        argument_value: str,
        context_arguments: dict[str, str] | None = None,
    ) -> Any:
        from mcp import types

        return await self.session.complete(
            ref=types.ResourceTemplateReference(type="ref/resource", uri=uri_template),
            argument={"name": argument_name, "value": argument_value},
            context_arguments=context_arguments,
        )

    async def send_ping(self) -> Any:
        return await self.session.send_ping()


async def _collect_paginated(method: Any, field_name: str) -> list[Any]:
    items: list[Any] = []
    cursor: str | None = None
    while True:
        result = await method(cursor=cursor)
        items.extend(getattr(result, field_name))
        cursor = getattr(result, "nextCursor", None)
        if not cursor:
            break
    return items


def run_sync(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def _runner() -> None:
        try:
            queue.put((True, asyncio.run(awaitable)))
        except BaseException as exc:  # pragma: no cover - sync bridge
            queue.put((False, exc))

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    ok, value = queue.get()
    thread.join()
    if ok:
        return value
    raise value
