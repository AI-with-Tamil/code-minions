"""OAuth client helpers for protected MCP servers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from codeminions.tools.mcp.compat import ensure_mcp_installed


@dataclass
class InMemoryTokenStorage:
    """Simple in-memory token storage for MCP OAuth clients."""

    tokens: Any | None = None
    client_info: Any | None = None

    async def get_tokens(self) -> Any | None:
        return self.tokens

    async def set_tokens(self, tokens: Any) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> Any | None:
        return self.client_info

    async def set_client_info(self, client_info: Any) -> None:
        self.client_info = client_info


def create_oauth_provider(
    *,
    server_url: str,
    client_metadata: Any,
    storage: Any | None = None,
    redirect_handler: Callable[[str], Awaitable[None]] | None = None,
    callback_handler: Callable[[], Awaitable[tuple[str, str | None]]] | None = None,
    timeout: float = 300.0,
    client_metadata_url: str | None = None,
) -> Any:
    """Create an OAuthClientProvider for protected MCP servers."""
    ensure_mcp_installed()
    from mcp.client.auth import OAuthClientProvider

    return OAuthClientProvider(
        server_url=server_url,
        client_metadata=client_metadata,
        storage=storage or InMemoryTokenStorage(),
        redirect_handler=redirect_handler,
        callback_handler=callback_handler,
        timeout=timeout,
        client_metadata_url=client_metadata_url,
    )


def build_oauth_client_metadata(
    *,
    redirect_uris: list[Any],
    scope: str | None = None,
    client_name: str | None = None,
    grant_types: list[str] | None = None,
    response_types: list[str] | None = None,
) -> Any:
    """Build OAuthClientMetadata with sensible defaults for MCP clients."""
    ensure_mcp_installed()
    from mcp.shared.auth import OAuthClientMetadata

    return OAuthClientMetadata(
        redirect_uris=redirect_uris,
        scope=scope,
        client_name=client_name,
        grant_types=grant_types or ["authorization_code", "refresh_token"],
        response_types=response_types or ["code"],
    )
