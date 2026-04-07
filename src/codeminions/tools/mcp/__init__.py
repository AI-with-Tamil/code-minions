"""Package-level MCP client support for Minion."""

from codeminions.tools.mcp.auth import InMemoryTokenStorage, build_oauth_client_metadata, create_oauth_provider
from codeminions.tools.mcp.client import MCPClient
from codeminions.tools.mcp.compat import mcp_sdk_version
from codeminions.tools.mcp.completions import complete_mcp_prompt, complete_mcp_resource_template
from codeminions.tools.mcp.config import MCPServerConfig, Transport, resolve_mcp_server_config
from codeminions.tools.mcp.display import get_mcp_display_name
from codeminions.tools.mcp.errors import (
    MCPAuthError,
    MCPConfigurationError,
    MCPError,
    MCPProtocolError,
    MCPTransportError,
)
from codeminions.tools.mcp.prompts import get_mcp_prompt, list_mcp_prompts
from codeminions.tools.mcp.registry import register_mcp_server
from codeminions.tools.mcp.resources import (
    list_mcp_resource_templates,
    list_mcp_resources,
    read_mcp_resource,
    subscribe_mcp_resource,
    unsubscribe_mcp_resource,
)
from codeminions.tools.mcp.tools import mcp_tools

__all__ = [
    "MCPClient",
    "InMemoryTokenStorage",
    "create_oauth_provider",
    "build_oauth_client_metadata",
    "MCPServerConfig",
    "Transport",
    "MCPError",
    "MCPConfigurationError",
    "MCPTransportError",
    "MCPProtocolError",
    "MCPAuthError",
    "resolve_mcp_server_config",
    "register_mcp_server",
    "mcp_tools",
    "list_mcp_resources",
    "list_mcp_resource_templates",
    "read_mcp_resource",
    "subscribe_mcp_resource",
    "unsubscribe_mcp_resource",
    "list_mcp_prompts",
    "get_mcp_prompt",
    "complete_mcp_prompt",
    "complete_mcp_resource_template",
    "get_mcp_display_name",
    "mcp_sdk_version",
]
